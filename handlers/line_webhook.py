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

import re
from utils.i18n import get_msg

handler = WebhookHandler(LINE_CHANNEL_SECRET)
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
proposal_service = ProposalService()
booking_service = BookingService()
repo = SupabaseRepo()

api_client = ApiClient(configuration)
messaging_api = MessagingApi(api_client)

def _parse_index(text: str):
    m = re.search(r'(\d+)', text)
    return int(m.group(1)) if m else None

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

    # 1. 取得或初始化 Profile 與語系
    profile = repo.get_profile_by_line_user_id(line_user_id)
    if not profile:
        # 初次註冊
        repo.create_profile({"line_user_id": line_user_id, "role": "student", "language": "zh", "name": "User"})
        profile = repo.get_profile_by_line_user_id(line_user_id)
        lang = "zh"
        _reply_text(event.reply_token, get_msg("menu.welcome", lang=lang, name="User"))
        return

    lang = profile.get("language", "zh")
    role = profile.get("role", "student")

    # 2. 管理員模式判斷 (Impersonation)
    admin_view = get_admin_view(line_user_id) if role == "admin" else {}
    effective_role = admin_view.get("as_role", role)
    admin_as_teacher_id = admin_view.get("as_teacher_id")

    # ======================
    # 通用指令 (Common Commands)
    # ======================
    if text in ("切換語言", "Switch Language"):
        new_lang = "en" if lang == "zh" else "zh"
        repo.update_profile(profile["id"], {"language": new_lang})
        _reply_text(event.reply_token, get_msg("menu.switch_lang", lang=new_lang))
        return

    if text in ("取消流程", "Cancel"):
        reply = proposal_service.student_cancel_flow(line_user_id)
        _reply_text(event.reply_token, reply)
        return

    # ======================
    # 管理員專屬指令
    # ======================
    if role == "admin":
        if text == "切換學生":
            repo.clear_state(line_user_id, "mode")
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

        # 處理選老師後的輸入
        state_mode = repo.get_state(line_user_id, "mode")
        if state_mode and state_mode["step"] == "pick_teacher":
            idx = _parse_index(text)
            teacher_list = state_mode["payload"].get("list", [])
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
    # 學生功能 (Student)
    # ======================
    if effective_role == "student":
        if text in ("提案", "Proposal"):
            reply = proposal_service.student_start_proposal(line_user_id)
        elif text in ("取消提案", "Pending"):
            reply = proposal_service.student_list_pending(line_user_id)
        elif text.startswith("取消提案 "):
            idx = _parse_index(text)
            reply = proposal_service.student_cancel_pending_by_index(line_user_id, idx)
        elif text in ("取消課程", "Bookings"):
            reply = booking_service.student_list_confirmed(line_user_id)
        elif text.startswith("取消課程 "):
            idx = _parse_index(text)
            reply = booking_service.student_cancel_confirmed_by_index(line_user_id, idx)
        elif text.startswith("查看課程 "):
            b_id = _parse_index(text)
            reply = booking_service.get_confirmed_booking_by_id(b_id, line_user_id=line_user_id)
        else:
            # 檢查是否在提案流程中 (Wizard)
            state = repo.get_state(line_user_id, "proposal_create")
            if state:
                reply = proposal_service.student_wizard_input(line_user_id, text)
            else:
                reply = get_msg("common.unsupported_cmd", lang=lang)

    # ======================
    # 老師功能 (Teacher)
    # ======================
    elif effective_role == "teacher":
        t_prof_id = admin_as_teacher_id if role == "admin" else profile["id"]
        
        if not t_prof_id:
            _reply_text(event.reply_token, get_msg("admin.switch_teacher", lang=lang))
            return

        if text in ("待審核", "Pending"):
            reply = proposal_service.teacher_list_pending(t_prof_id)
        elif text.startswith("接受"):
            idx = _parse_index(text)
            reply = proposal_service.teacher_accept_by_index(t_prof_id, idx) if idx else "Format: Accept 1"
        elif text.startswith("拒絕"):
            idx = _parse_index(text)
            # 拒絕邏輯可延伸加入原因
            reply = proposal_service.teacher_reject_by_index(t_prof_id, idx, "Teacher busy") if idx else "Format: Reject 1"
        else:
            reply = get_msg("common.unsupported_cmd", lang=lang)

    _reply_text(event.reply_token, reply)