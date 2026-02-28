from linebot.v3.webhook import WebhookHandler
from linebot.v3.webhooks import MessageEvent, TextMessageContent, UserSource
from linebot.v3.messaging import (
    MessagingApi, Configuration, ApiClient,
    ReplyMessageRequest, TextMessage
)

from config import LINE_CHANNEL_SECRET, LINE_CHANNEL_ACCESS_TOKEN
from services.proposal_service import ProposalService
from services.booking_service import BookingService
from repos.supabase_repo import SupabaseRepo
from utils.i18n import get_msg, parse_index
from services.user_service import UserService
from services.rich_menu_service import RichMenuService

handler = WebhookHandler(LINE_CHANNEL_SECRET)
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
proposal_service = ProposalService()
booking_service = BookingService()
repo = SupabaseRepo()
api_client = ApiClient(configuration)
messaging_api = MessagingApi(api_client)
user_service = UserService()
rich_menu_service = RichMenuService()

def get_admin_view(line_user_id: str) -> dict:
    st = repo.get_state(line_user_id, "mode")
    return (st.get("payload") or {}) if st else {}

def _reply_text(reply_token: str, text: str):
    messaging_api.reply_message(
        ReplyMessageRequest(
            reply_token=reply_token,
            messages=[TextMessage(text=text)]
        )
    )

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    line_user_id = event.source.user_id  
    text = event.message.text.strip()    

    try:
        user_profile_resp = messaging_api.get_profile(line_user_id)
        display_name = user_profile_resp.display_name
    except:
        display_name = "User"
        
    # ==========================================
    # 1. 註冊檢核與流程 (Registration Flow)
    # ==========================================
    profile = repo.get_profile_by_line_user_id(line_user_id)
    
    # 如果沒有 Profile，或者正在註冊狀態中 -> 進入註冊 Service
    if not profile or repo.get_state(line_user_id, "registration"):
        reply = user_service.handle_registration(line_user_id, text, display_name)
        _reply_text(event.reply_token, reply)
        return

    # 若已註冊，取得基本資訊
    lang = profile.get("language", "zh")
    role = profile.get("role", "student")

    if text == "更新選單":
        role = profile.get("role", "student")
        rich_menu_service.link_user_menu(line_user_id, role)
        _reply_text(event.reply_token, "✅ 選單已強制更新！")
        return
    # ==========================================
    # 2. 待審核狀態阻擋 (Pending Check)
    # ==========================================
    if role == "teacher_pending":
        _reply_text(event.reply_token, get_msg("reg.pending_alert", lang=lang))
        return

    # ==========================================
    # 3. 正常業務流程 (Existing Flows)
    # ==========================================
    
    admin_view = get_admin_view(line_user_id) if role == "admin" else {}
    effective_role = admin_view.get("as_role")
    if not effective_role:
        effective_role = "student" if role == "admin" else role
        
    admin_as_teacher_id = admin_view.get("as_teacher_id")
    
    # ======================
    # 通用指令 (Common Commands)
    # ======================
    if text in ("切換語言", "Switch Language"):
        new_lang = "en" if lang == "zh" else "zh"
        repo.update_profile_language(line_user_id, new_lang)
        _reply_text(event.reply_token, get_msg("menu.switch_lang", lang=new_lang))
        return

    if text in ("取消流程", "重新開始", "Cancel", "Reset"):
        # 呼叫共用函式清除所有狀態
        reply = proposal_service.cancel_any_flow(line_user_id)
        _reply_text(event.reply_token, reply)
        return

    # ======================
    # 管理員專屬指令 (僅 admin 可用)
    # ======================
    if role == "admin":
        if text == "切換學生":
            # 修正：明確更新狀態為扮演學生，不直接 clear
            repo.upsert_state(line_user_id, "mode", "view", {"as_role": "student"})
            _reply_text(event.reply_token, get_msg("admin.switch_student", lang=lang))
            return
        elif text == "切換老師":
            # 進入選老師流程或單純切換角色
            repo.upsert_state(line_user_id, "mode", "select", {"as_role": "teacher"})
            _reply_text(event.reply_token, get_msg("admin.switch_teacher", lang=lang))
            return
        elif text == "選老師":
            teachers = repo.list_teachers()
            if not teachers:
                _reply_text(event.reply_token, get_msg("admin.no_teachers", lang=lang))
                return
            lines = [get_msg("admin.select_teacher_idx", lang=lang)]
            for i, t in enumerate(teachers, 1):
                lines.append(f"{i}) {t['name']}")
            repo.upsert_state(line_user_id, "mode", "pick_teacher", {"as_role": "teacher", "list": teachers})
            _reply_text(event.reply_token, "\n".join(lines))
            return

        # 處理選老師後的輸入 (pick_teacher 階段)
        state_mode = repo.get_state(line_user_id, "mode")
        if state_mode and state_mode.get("step") == "pick_teacher":
            idx = parse_index(text)
            teacher_list = state_mode.get("payload", {}).get("list", [])
            if idx and 1 <= idx <= len(teacher_list):
                target = teacher_list[idx-1]
                repo.upsert_state(line_user_id, "mode", "view", {
                    "as_role": "teacher",
                    "as_teacher_id": target["id"],
                    "as_teacher_name": target["name"]
                })
                _reply_text(event.reply_token, get_msg("admin.teacher_impersonated", lang=lang, name=target["name"]))
                return

    # ======================
    # 學生功能 (Student Flow)
    # ======================
    if effective_role == "student":
        if text == "預約課程":
            repo.clear_state(line_user_id, "student_action")
            reply = proposal_service.student_start_proposal(line_user_id)
        
        elif text == "查看預約課程":
            repo.clear_state(line_user_id, "proposal_create")
            
            reply = proposal_service.student_list_pending(line_user_id)
            # 進入流程：允許取消「提案」
            repo.upsert_state(line_user_id, "student_action", "viewing_pending", {})
            _reply_text(event.reply_token, reply)
            return
            
        elif text == "我的課表":
            repo.clear_state(line_user_id, "proposal_create")
            
            # 呼叫共用函式
            reply = booking_service.list_confirmed(line_user_id, "student")
            # 進入流程：允許取消「課程」
            repo.upsert_state(line_user_id, "student_action", "viewing_confirmed", {})
            _reply_text(event.reply_token, reply)
            return

        else:
            # 判斷目前在哪個 Wizard 中
            if repo.get_state(line_user_id, "proposal_create"):
                reply = proposal_service.student_wizard_input(line_user_id, text)
            elif repo.get_state(line_user_id, "student_action"):
                reply = proposal_service.student_action_wizard(line_user_id, text)
            else:
                reply = get_msg("common.unsupported_cmd", lang=lang)

    # ======================
    # 老師功能 (Teacher Flow)
    # ======================
    elif effective_role == "teacher":
        t_prof_id = admin_as_teacher_id if role == "admin" else profile["id"]

        # 1. 待確認課程 (進入審核流程)
        if text == "待確認課程":
            reply = proposal_service.teacher_list_pending(t_prof_id)
            repo.upsert_state(line_user_id, "teacher_action", "viewing_pending", {
                "teacher_profile_id": t_prof_id
            })
            _reply_text(event.reply_token, reply)
            return
        
        # 2. 我的課表 (進入課表查看流程)
        elif text == "我的課表":
            # 呼叫共用函式 (先前建議的 list_confirmed)
            reply = booking_service.list_confirmed(line_user_id, "teacher")
            repo.upsert_state(line_user_id, "teacher_action", "viewing_confirmed", {
                "teacher_profile_id": t_prof_id
            })
            _reply_text(event.reply_token, reply)
            return

        # 3. 處理流程中的輸入
        else:
            teacher_state = repo.get_state(line_user_id, "teacher_action")
            if teacher_state:
                # 進入老師專用的行為 Wizard
                reply = proposal_service.teacher_action_wizard(line_user_id, text)
            else:
                reply = get_msg("common.unsupported_cmd", lang=lang)
                
    _reply_text(event.reply_token, reply)