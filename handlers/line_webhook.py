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
from services.line_notify import LinePushService  
import traceback 

handler = WebhookHandler(LINE_CHANNEL_SECRET)
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
proposal_service = ProposalService()
booking_service = BookingService()
repo = SupabaseRepo()
api_client = ApiClient(configuration)
messaging_api = MessagingApi(api_client)
user_service = UserService()
rich_menu_service = RichMenuService()
push_service = LinePushService(configuration) 

def get_admin_view(line_user_id: str) -> dict:
    st = repo.get_state(line_user_id, "mode")
    return (st.get("payload") or {}) if st else {}

def _reply_text(reply_token: str, text: str):
    if not text:
        return
    messaging_api.reply_message(
        ReplyMessageRequest(
            reply_token=reply_token,
            messages=[TextMessage(text=str(text))]
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
        
    reply = "" 
    lang = "zh" 

    try:
        # === 1. 註冊檢核與流程 ===
        profile = repo.get_profile_by_line_user_id(line_user_id)
        
        if not profile or repo.get_state(line_user_id, "registration"):
            reply = user_service.handle_registration(line_user_id, text, display_name)
            _reply_text(event.reply_token, reply)
            return

        lang = profile.get("language", "zh")
        role = profile.get("role", "student")
        profile_name = profile.get("name", display_name)

        if text == "更新選單":
            role = profile.get("role", "student")
            rich_menu_service.link_user_menu(line_user_id, role)
            _reply_text(event.reply_token, "✅ 選單已強制更新！")
            return

        # === 2. 待審核狀態阻擋 ===
        if role == "teacher_pending":
            _reply_text(event.reply_token, get_msg("reg.pending_alert", lang=lang))
            return

        # === 3. 正常業務流程 ===
        admin_view = get_admin_view(line_user_id) if role == "admin" else {}
        effective_role = admin_view.get("as_role")
        if not effective_role:
            effective_role = "student" if role == "admin" else role
            
        admin_as_teacher_id = admin_view.get("as_teacher_id")
        admin_as_teacher_name = admin_view.get("as_teacher_name")
        
        # --- 通用指令 ---
        if text in ("切換語言", "Switch Language"):
            new_lang = "en" if lang == "zh" else "zh"
            repo.update_profile_language(line_user_id, new_lang)
            _reply_text(event.reply_token, get_msg("menu.switch_lang", lang=new_lang))
            return

        if text in ("取消流程", "重新開始", "Cancel", "Reset"):
            reply = proposal_service.cancel_any_flow(line_user_id, lang)
            _reply_text(event.reply_token, reply)
            return

        # [新增] 雙語操作說明指令
        if text in ("操作說明", "說明", "Help", "help"):
            # 如果是管理員且沒有在扮演別人，顯示管理員說明；否則顯示當下扮演角色的說明
            help_role = "admin" if role == "admin" and not admin_as_teacher_id else effective_role
            reply = get_msg(f"help.{help_role}", lang=lang)
            _reply_text(event.reply_token, reply)
            return

        # --- 管理員專屬指令 ---
        if role == "admin":
            if text == "待審核名單":
                pending_list = repo.list_pending_teachers()
                if not pending_list:
                    _reply_text(event.reply_token, "✅ 目前沒有待審核的老師。")
                    return
                
                lines = ["📋 待審核老師名單："]
                for i, t in enumerate(pending_list, 1):
                    lines.append(f"{i}) {t['name']}")
                lines.append("\n💡 請輸入「開通 {數字}」來通過審核，例如「開通 1」。")
                
                repo.upsert_state(line_user_id, "mode", "approve_teacher", {"list": pending_list})
                _reply_text(event.reply_token, "\n".join(lines))
                return

            elif text.startswith("開通 "):
                idx = parse_index(text)
                state_mode = repo.get_state(line_user_id, "mode")
                if state_mode and state_mode.get("step") == "approve_teacher":
                    pending_list = state_mode.get("payload", {}).get("list", [])
                    if idx and 1 <= idx <= len(pending_list):
                        target = pending_list[idx - 1]
                        repo.update_profile_role(target["id"], "teacher")
                        rich_menu_service.link_user_menu(target["line_user_id"], "teacher")
                        push_service.push_text(
                            target["line_user_id"], 
                            "🎉 恭喜！您的老師帳號已通過管理員審核！\n\n現在您的選單已切換為老師專屬功能，可以開始接收學生的預約囉。"
                        )
                        _reply_text(event.reply_token, f"✅ 已成功開通老師：{target['name']}")
                        repo.clear_state(line_user_id, "mode")
                        return
                    else:
                        _reply_text(event.reply_token, "❌ 找不到對應的序號，請重新輸入。")
                        return
                else:
                    _reply_text(event.reply_token, "❌ 請先輸入「待審核名單」來獲取最新列表。")
                    return

            elif text in ("價格", "計算價格", "結算薪資"):
                if not admin_as_teacher_id:
                    _reply_text(event.reply_token, "⚠️ 請先使用「選老師」指定要查詢哪位老師。")
                    return
                reply = booking_service.calculate_and_display_salary(
                    admin_as_teacher_id, 
                    admin_as_teacher_name, 
                    lang
                )
                _reply_text(event.reply_token, reply)
                return

            elif text == "切換學生":
                repo.upsert_state(line_user_id, "mode", "view", {"as_role": "student"})
                _reply_text(event.reply_token, get_msg("admin.switch_student", lang=lang))
                return
            elif text == "切換老師":
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

        # --- 學生功能 ---
        if effective_role == "student":
            if text == "預約課程":
                repo.clear_state(line_user_id, "student_action")
                reply = proposal_service.student_start_proposal(line_user_id, lang)
            
            elif text == "查看預約課程":
                repo.clear_state(line_user_id, "proposal_create")
                reply = proposal_service.student_list_pending(profile["id"], lang)
                repo.upsert_state(line_user_id, "student_action", "viewing_pending", {})
                _reply_text(event.reply_token, reply)
                return
                
            elif text == "我的課表":
                repo.clear_state(line_user_id, "proposal_create")
                reply = booking_service.list_confirmed(profile["id"], "student", lang)
                repo.upsert_state(line_user_id, "student_action", "viewing_confirmed", {})
                _reply_text(event.reply_token, reply)
                return

            else:
                if repo.get_state(line_user_id, "proposal_create"):
                    reply = proposal_service.student_wizard_input(line_user_id, profile["id"], text, lang)
                elif state_data := repo.get_state(line_user_id, "student_action"):
                    step = state_data.get("step")
                    if step == "viewing_pending":
                        reply = proposal_service.handle_student_pending_action(line_user_id, profile["id"], text, lang)
                    elif step == "viewing_confirmed":
                        reply = booking_service.handle_student_confirmed_action(line_user_id, profile["id"], text, lang)
                    else:
                        reply = get_msg("common.unsupported_cmd", lang=lang)
                else:
                    reply = get_msg("common.unsupported_cmd", lang=lang)

        # --- 老師功能 ---
        elif effective_role == "teacher":
            t_prof_id = admin_as_teacher_id if role == "admin" and admin_as_teacher_id else profile["id"]
            t_prof_name = admin_as_teacher_name if role == "admin" and admin_as_teacher_name else profile_name

            if text == "待確認課程":
                reply = proposal_service.teacher_list_pending(t_prof_id, lang)
                repo.upsert_state(line_user_id, "teacher_action", "viewing_pending", {
                    "teacher_profile_id": t_prof_id,
                    "teacher_name": t_prof_name
                })
                _reply_text(event.reply_token, reply)
                return
            
            elif text == "我的課表":
                reply = booking_service.list_confirmed(t_prof_id, "teacher", lang)
                repo.upsert_state(line_user_id, "teacher_action", "viewing_confirmed", {
                    "teacher_profile_id": t_prof_id
                })
                _reply_text(event.reply_token, reply)
                return

            # [新增] 讓老師自己也能看自己的薪資
            elif text in ("結算薪資", "Salary"):
                reply = booking_service.calculate_and_display_salary(t_prof_id, t_prof_name, lang)
                _reply_text(event.reply_token, reply)
                return

            else:
                if state_data := repo.get_state(line_user_id, "teacher_action"):
                    step = state_data.get("step")
                    payload = state_data.get("payload") or {}
                    t_id = payload.get("teacher_profile_id") or t_prof_id
                    t_name = payload.get("teacher_name") or t_prof_name

                    if step == "viewing_pending":
                        reply = proposal_service.handle_teacher_pending_action(line_user_id, t_id, text, lang, t_name)
                    elif step == "viewing_confirmed":
                        reply = booking_service.handle_teacher_confirmed_action(line_user_id, t_id, text, lang)
                    else:
                        reply = get_msg("common.unsupported_cmd", lang=lang)
                else:
                    reply = get_msg("common.unsupported_cmd", lang=lang)
                    
        if reply:
            _reply_text(event.reply_token, reply)

    except Exception as e:
        error_msg = f"⚠️ 系統發生內部錯誤：\n類型: {type(e).__name__}\n原因: {str(e)}"
        print(f"[ERROR] 執行時崩潰：\n{traceback.format_exc()}")
        _reply_text(event.reply_token, error_msg)