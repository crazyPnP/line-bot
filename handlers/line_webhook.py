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

handler = WebhookHandler(LINE_CHANNEL_SECRET)

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
proposal_service = ProposalService()
booking_service = BookingService()
repo = SupabaseRepo()

api_client = ApiClient(configuration)
messaging_api = MessagingApi(api_client)


def _parse_index(text: str):
    m = re.search(r'(\d+)', text)
    if not m:
        return None
    return int(m.group(1))


def get_admin_view(line_user_id: str) -> dict:
    st = repo.get_state(line_user_id, "mode")
    payload = (st.get("payload") or {}) if st else {}
    return payload


def _reply_text(reply_token: str, text: str):
    messaging_api.reply_message(
        ReplyMessageRequest(
            reply_token=reply_token,
            messages=[TextMessage(text=text)]
        )
    )


@handler.add(MessageEvent, message=TextMessageContent)
def handle_event(event):
    if not isinstance(event.source, UserSource):
        return

    text = event.message.text.strip()
    line_user_id = event.source.user_id

    # 取 LINE display name
    try:
        line_profile = messaging_api.get_profile(line_user_id)
        display_name = line_profile.display_name
    except Exception as e:
        print("Failed to get LINE profile:", e)
        display_name = "LINE User"

    profile, is_new = repo.create_student_if_not_exists(line_user_id, display_name)
    role = profile.get("role", "student")

    # ===== admin 視角切換 =====
    admin_view = {}
    effective_role = role
    admin_as_teacher_id = None

    if role == "admin":
        admin_view = get_admin_view(line_user_id)
        effective_role = admin_view.get("as_role", "student")
        admin_as_teacher_id = admin_view.get("as_teacher_id")

        # --- admin: 切換學生模式 ---
        if text in ("切換學生", "學生模式"):
            repo.upsert_state(line_user_id, "mode", "view", {
                "as_role": "student",
                "as_teacher_id": None,
                "as_teacher_name": None,
            })
            _reply_text(event.reply_token, "✅ 已切換為【學生模式】")
            return

        # --- admin: 切換老師模式 ---
        if text in ("切換老師", "老師模式"):
            repo.upsert_state(line_user_id, "mode", "view", {
                "as_role": "teacher",
                "as_teacher_id": admin_view.get("as_teacher_id"),
                "as_teacher_name": admin_view.get("as_teacher_name"),
            })
            _reply_text(event.reply_token, "✅ 已切換為【老師模式】\n請輸入「選老師」選擇要代入的老師。")
            return

        # --- admin: 顯示老師列表 ---
        if text in ("選老師", "選擇老師"):
            teachers = repo.list_teachers_simple()  # 你要在 repo 補這個方法
            if not teachers:
                _reply_text(event.reply_token, "目前沒有老師可選。")
                return

            repo.upsert_state(line_user_id, "mode", "pick_teacher", {
                "as_role": "teacher",
                "teachers": [{"id": t["id"], "name": t.get("name") or "老師"} for t in teachers],
            })

            lines = ["請輸入要代入的老師序號："]
            for i, t in enumerate(teachers, 1):
                lines.append(f"{i}) {t.get('name') or t['id']}")
            _reply_text(event.reply_token, "\n".join(lines))
            return

        # --- admin: 選老師序號 ---
        st = repo.get_state(line_user_id, "mode")
        if st and st.get("step") == "pick_teacher":
            payload = st.get("payload") or {}
            teachers = payload.get("teachers") or []

            idx = _parse_index(text)
            if idx is None:
                _reply_text(event.reply_token, "請輸入老師序號（例如 1）。")
                return
            if idx < 1 or idx > len(teachers):
                _reply_text(event.reply_token, f"序號錯誤，請輸入 1 ~ {len(teachers)}")
                return

            chosen = teachers[idx - 1]
            repo.upsert_state(line_user_id, "mode", "view", {
                "as_role": "teacher",
                "as_teacher_id": chosen["id"],
                "as_teacher_name": chosen["name"],
            })
            _reply_text(event.reply_token, f"✅ 已代入老師：{chosen['name']}\n你可以輸入「待審核」查看提案。")
            return

        # refresh view (可能剛剛切換/選老師後)
        admin_view = get_admin_view(line_user_id)
        effective_role = admin_view.get("as_role", effective_role)
        admin_as_teacher_id = admin_view.get("as_teacher_id", admin_as_teacher_id)

    # welcome
    welcome = ""
    user_name = profile.get("name", display_name)
    if is_new:
        welcome = f"👋 歡迎{user_name}！\n已自動將你的身分註冊為「學生」。\n\n"

    reply = "指令未支援"

    if text == "debug":
        st = repo.get_state(line_user_id, "mode")
        _reply_text(event.reply_token, f"role={role}\nmode_state={st}")
        return

    # ======================
    # Student flow
    # ======================
    if effective_role == "student":
        if text == "提案":
            reply = proposal_service.student_start_proposal(line_user_id)

        elif text == "取消流程":
            reply = proposal_service.student_cancel_flow(line_user_id)

        elif text == "取消提案":
            reply = proposal_service.student_list_pending(line_user_id)

        elif text.startswith("取消提案"):
            idx = _parse_index(text)
            reply = "取消提案格式：取消提案1 或 取消提案 1" if idx is None \
                else proposal_service.student_cancel_pending_by_index(line_user_id, idx)

        elif text == "取消課程":
            reply = booking_service.student_list_confirmed(line_user_id)

        elif text.startswith("取消課程"):
            idx = _parse_index(text)
            reply = "取消課程格式：取消課程1 或 取消課程 1" if idx is None \
                else booking_service.student_cancel_confirmed_by_index(line_user_id, idx)

        else:
            state = repo.get_state(line_user_id, "proposal_create")
            if state:
                reply = proposal_service.student_wizard_input(line_user_id, text)
            else:
                reply = "學生可用：提案、取消提案、取消課程（取消流程）"

    # ======================
    # Teacher flow
    # ======================
    elif effective_role == "teacher":
        # 決定 teacher_profile_id：admin 用代入老師；真老師用自己 profile.id
        if role == "admin":
            teacher_profile_id = admin_as_teacher_id
            if not teacher_profile_id:
                _reply_text(event.reply_token, "你目前是老師模式，但尚未代入老師。\n請先輸入「選老師」。")
                return
        else:
            teacher_profile_id = profile["id"]

        if text in ("待審核", "待審核提案"):
            reply = proposal_service.teacher_list_pending(teacher_profile_id)

        elif text.startswith("接受"):
            idx = _parse_index(text)
            reply = "接受格式：接受1" if idx is None else proposal_service.teacher_accept_by_index(teacher_profile_id, idx)

        elif text.startswith("拒絕"):
            idx = _parse_index(text)
            if idx is None:
                reply = "拒絕格式：拒絕1 原因"
            else:
                reason = re.sub(r"^拒絕\s*\d+\s*", "", text).strip()
                reply = proposal_service.teacher_reject_by_index(teacher_profile_id, idx, reason)

        else:
            reply = "老師可用：待審核 / 接受1 / 拒絕1 原因"

    reply = welcome + reply
    _reply_text(event.reply_token, reply)
