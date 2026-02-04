from repos.supabase_repo import SupabaseRepo
from utils.i18n import get_msg, parse_index
from services.line_notify import LinePushService
from linebot.v3.messaging import Configuration
from config import LINE_CHANNEL_ACCESS_TOKEN
from services.rich_menu_service import RichMenuService

class UserService:
    def __init__(self):
        self.repo = SupabaseRepo()
        # 如果需要通知管理員，可以使用 push service
        self.push = LinePushService(Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN))
        self.rich_menu = RichMenuService()
        
    def handle_registration(self, line_user_id: str, user_text: str, user_display_name: str) -> str:
        """處理初次註冊的 Wizard 流程"""
        # 1. 檢查是否已有流程狀態
        state = self.repo.get_state(line_user_id, "registration")
        
        # 如果沒有狀態，代表剛開始 (Step 1: 選語言)
        if not state:
            self.repo.upsert_state(line_user_id, "registration", "ask_lang", {})
            # 預設用中文問，因為還不知道語言
            return get_msg("reg.ask_lang", lang="zh")

        step = state["step"]
        payload = state.get("payload") or {}

        # Step 2: 處理語言選擇 -> 進入選身分
        if step == "ask_lang":
            idx = parse_index(user_text)
            if idx == 1:
                selected_lang = "zh"
            elif idx == 2:
                selected_lang = "en"
            else:
                return get_msg("reg.ask_lang", lang="zh") # 輸入錯誤重問

            # 儲存語言偏好到 payload，進入下一步
            payload["lang"] = selected_lang
            self.repo.upsert_state(line_user_id, "registration", "ask_role", payload)
            return get_msg("reg.ask_role", lang=selected_lang)

        # Step 3: 處理身分選擇 -> 完成註冊
        elif step == "ask_role":
            lang = payload.get("lang", "zh")
            idx = parse_index(user_text)
            
            role = ""
            if idx == 1:
                role = "student"
                reply_key = "reg.complete_student"
            elif idx == 2:
                role = "teacher_pending" # 設定為待審核
                reply_key = "reg.complete_teacher_pending"
            else:
                return get_msg("reg.ask_role", lang=lang)

            # 建立 Profile
            self.repo.create_profile({
                "line_user_id": line_user_id,
                "name": user_display_name,
                "role": role,
                "language": lang
            })

            # 清除註冊狀態
            self.repo.clear_state(line_user_id, "registration")
            
            # === 新增：根據角色綁定選單 ===
            if role == "student":
                self.rich_menu.link_user_menu(line_user_id, "student")
            elif role == "teacher_pending":
                # 待審核時，可以先給 student 選單，或者不給選單(預設)
                # 這裡選擇不給，或者您可以做一個 "guest" 選單
                pass 
            # ==========================
            
            return get_msg(reply_key, lang=lang)

        return "Registration Error"

    def admin_list_pending_teachers(self, admin_line_id: str) -> str:
        """Admin: 列出待審核老師"""
        lang = "zh" # Admin 預設語言，或從 DB 查
        pending_list = self.repo.list_pending_teachers()
        
        if not pending_list:
            return get_msg("admin.no_pending_teachers", lang=lang)

        lines = [get_msg("admin.pending_teacher_list", lang=lang)]
        for i, p in enumerate(pending_list, 1):
            lines.append(f"{i}) {p['name']} (ID: {p['id']})")
        
        lines.append("\n" + get_msg("admin.approve_instr", lang=lang))
        return "\n".join(lines)

    def admin_approve_teacher(self, admin_line_id: str, idx: int) -> str:
        """Admin: 通過審核"""
        lang = "zh"
        pending_list = self.repo.list_pending_teachers()
        
        if not pending_list or idx < 1 or idx > len(pending_list):
            return get_msg("common.invalid_input", lang=lang)

        target = pending_list[idx - 1]
        self.repo.update_profile_role(target["id"], "teacher")
        
        # === 新增：審核通過後，幫該老師切換成 Teacher 選單 ===
        target_line_id = target.get("line_user_id") # 需確認 list_pending_teachers 有 select line_user_id
        if target_line_id:
             self.rich_menu.link_user_menu(target_line_id, "teacher")
             # 發送通知
             self.push.push_text(target_line_id, "🎉 恭喜！您的老師權限已開通，選單已更新。")
        # ==========================

        return get_msg("admin.approve_success", lang=lang, name=target["name"])