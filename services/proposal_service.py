import re
from datetime import datetime, timedelta
from utils.time_utils import now_utc_iso, fmt_taipei
from utils.i18n import get_msg, parse_index
from repos.supabase_repo import SupabaseRepo
from services.line_notify import LinePushService
from linebot.v3.messaging import Configuration
from config import LINE_CHANNEL_ACCESS_TOKEN

class ProposalService:
    def __init__(self):
        self.repo = SupabaseRepo()
        self.push = LinePushService(Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN))

    # 移除 _get_lang 以避免重複查詢

    def student_start_proposal(self, line_user_id: str) -> str:
        """
        學生開始預約
        優化：一次查詢取得 Lang
        """
        profile = self.repo.get_profile_by_line_user_id(line_user_id)
        if not profile: return get_msg("common.not_found_profile", "zh")
        lang = profile.get("language", "zh")

        # 初始化 Wizard 狀態
        self.repo.upsert_state(line_user_id, "proposal_create", "mode", {})
        
        # 這裡假設您的 get_msg 有支援 prompt_mode，或直接回傳選擇引導
        return get_msg("proposal.ask_mode", lang=lang)

    def student_list_pending(self, line_user_id: str) -> str:
        """
        列出學生待審核提案
        優化：一次查詢取得 Lang 與 ID
        """
        profile = self.repo.get_profile_by_line_user_id(line_user_id)
        if not profile: return get_msg("common.not_found_profile", "zh")
        lang = profile.get("language", "zh")

        rows = self.repo.list_student_pending_proposals(profile["id"])
        if not rows:
            return get_msg("proposal.no_pending", lang=lang)

        # 批次查詢老師名稱
        teacher_ids = list({r.get("to_teacher_id") for r in rows if r.get("to_teacher_id")})
        name_map = self.repo.get_profile_names_by_ids(teacher_ids) if teacher_ids else {}

        lines = [get_msg("proposal.pending_list_title", lang=lang)]
        for i, r in enumerate(rows, 1):
            t_name = name_map.get(r["to_teacher_id"], "Unknown")
            start = fmt_taipei(r["start_time"])
            lines.append(f"{i}) {t_name} | {start}")

        lines.append("\n" + get_msg("proposal.cancel_instr", lang=lang))
        return "\n".join(lines)

    def student_cancel_pending_by_index(self, line_user_id: str, idx: int) -> str:
        """
        學生取消待審核提案
        優化：一次查詢
        """
        profile = self.repo.get_profile_by_line_user_id(line_user_id)
        if not profile: return get_msg("common.not_found_profile", "zh")
        lang = profile.get("language", "zh")

        rows = self.repo.list_student_pending_proposals(profile["id"])
        if not rows or idx < 1 or idx > len(rows):
            return get_msg("proposal.not_found", lang=lang, count=len(rows or []))

        r = rows[idx - 1]
        
        # 執行取消
        if self.repo.cancel_student_pending_proposal(r["id"], profile["id"]):
            # 為了回傳訊息，獲取老師名字
            t_id = r.get("to_teacher_id")
            t_name = "Teacher"
            if t_id:
                t_prof = self.repo.get_profile_by_id(t_id)
                if t_prof: t_name = t_prof.get("name", "Teacher")
            
            return get_msg("proposal.cancel_pending_success", lang=lang, idx=idx, teacher=t_name, time=fmt_taipei(r['start_time']))
        
        return get_msg("proposal.cancel_pending_fail", lang=lang)

    def teacher_list_pending(self, teacher_profile_id: str) -> str:
        """
        老師查看待審核提案
        優化：直接透過 teacher_profile_id 查詢 Profile (如果是 Admin 扮演，這裡的 ID 已經是老師的 ID)
        """
        t_prof = self.repo.get_profile_by_id(teacher_profile_id)
        if not t_prof: return "Teacher profile not found"
        lang = t_prof.get("language", "zh")

        rows = self.repo.list_pending_proposals_for_teacher(teacher_profile_id)
        if not rows:
            return get_msg("teacher.no_pending", lang=lang)

        # 批次查詢學生名稱
        student_ids = list({r.get("proposed_by") for r in rows if r.get("proposed_by")})
        name_map = self.repo.get_profile_names_by_ids(student_ids) if student_ids else {}

        lines = [get_msg("teacher.pending_list_title", lang=lang)]
        for i, r in enumerate(rows, 1):
            s_name = name_map.get(r["proposed_by"], "Unknown")
            start = fmt_taipei(r["start_time"])
            # 顯示格式：1) 學生名 | 時間 | 課程模式
            lines.append(f"{i}) {s_name} | {start} | {r.get('class_mode','General')}")

        lines.append("\n" + get_msg("teacher.action_instr", lang=lang))
        return "\n".join(lines)

    def teacher_accept_by_index(self, teacher_profile_id: str, idx: int) -> str:
        """
        老師接受提案
        優化：一次查詢老師 Profile
        """
        t_prof = self.repo.get_profile_by_id(teacher_profile_id)
        if not t_prof: return "Profile error"
        lang = t_prof.get("language", "zh")

        rows = self.repo.list_pending_proposals_for_teacher(teacher_profile_id)
        if not rows or idx < 1 or idx > len(rows):
            return get_msg("proposal.not_found", lang=lang, count=len(rows or []))

        p = rows[idx - 1]
        
        # 建立 booking 並更新 proposal
        booking_id = self.repo.create_booking_from_proposal(p["id"], teacher_profile_id)
        
        if booking_id:
            # 推播通知學生
            student_line_id = self.repo.get_line_user_id_by_profile_id(p["proposed_by"])
            if student_line_id:
                # 需查詢學生語言
                s_prof = self.repo.get_profile_by_id(p["proposed_by"])
                s_lang = s_prof.get("language", "zh") if s_prof else "zh"
                
                msg = get_msg("student.notify_accepted", lang=s_lang, 
                              teacher=t_prof.get("name", "Teacher"), 
                              time=fmt_taipei(p["start_time"]))
                self.push.push_text(student_line_id, msg)

            return get_msg("teacher.accept_success", lang=lang, idx=idx)
        
        return get_msg("teacher.accept_fail", lang=lang)

    def teacher_reject_by_index(self, teacher_profile_id: str, idx: int, reason: str) -> str:
        """
        老師拒絕提案
        優化：一次查詢老師 Profile
        """
        t_prof = self.repo.get_profile_by_id(teacher_profile_id)
        if not t_prof: return "Profile error"
        lang = t_prof.get("language", "zh")

        rows = self.repo.list_pending_proposals_for_teacher(teacher_profile_id)
        if not rows or idx < 1 or idx > len(rows):
            return get_msg("proposal.not_found", lang=lang, count=len(rows or []))

        p = rows[idx - 1]
        self.repo.update_proposal(p["id"], {
            "status": "rejected",
            "responded_at": now_utc_iso(),
            "responded_by": teacher_profile_id,
            "response_note": reason or "No reason provided"
        })

        # 推播通知學生
        student_line_id = self.repo.get_line_user_id_by_profile_id(p["proposed_by"])
        if student_line_id:
            s_prof = self.repo.get_profile_by_id(p["proposed_by"])
            s_lang = s_prof.get("language", "zh") if s_prof else "zh"
            
            msg = get_msg("teacher.notify_rejected", lang=s_lang, 
                          teacher=t_prof.get("name", "Teacher"), 
                          reason=reason or "No reason provided")
            self.push.push_text(student_line_id, msg)

        return get_msg("teacher.reject_success", lang=lang, idx=idx)

    # ========= Wizards (僅負責轉發與狀態檢查，實際語言由 action 方法內決定) =========

    def student_action_wizard(self, line_user_id: str, user_text: str) -> str:
        # 這裡需要 lang 回傳 "Unsupported"，所以還是得查一次
        # 但如果是有效指令，這會是唯一一次查詢 (因為後續方法會重用? 不，後續方法是獨立的)
        # 為了極致優化，可以將 profile 傳入 action 方法，但這會破壞介面封裝。
        # 目前維持這樣即可，因為 Wizard 主要是路由。
        
        profile = self.repo.get_profile_by_line_user_id(line_user_id)
        if not profile: return "Profile Error"
        lang = profile.get("language", "zh")

        state = self.repo.get_state(line_user_id, "student_action")
        if not state: return get_msg("common.unsupported_cmd", lang=lang)

        step = state["step"]
        if user_text.startswith("Cancel") or user_text.startswith("取消"):
            idx = parse_index(user_text)
            if idx is None: return get_msg("common.invalid_input", lang=lang)
            
            if step == "viewing_pending":
                # 這裡會再次查詢 profile，但為了保持 student_cancel_pending_by_index 的獨立性，這是可接受的。
                # 若要極致優化，可重構為傳遞 profile 物件。
                reply = self.student_cancel_pending_by_index(line_user_id, idx)
            elif step == "viewing_confirmed":
                from services.booking_service import BookingService
                reply = BookingService().student_cancel_confirmed_by_index(line_user_id, idx)
            else:
                return get_msg("common.unsupported_cmd", lang=lang)
            
            self.repo.clear_state(line_user_id, "student_action")
            return reply

        return get_msg("common.unsupported_cmd", lang=lang)

    def teacher_action_wizard(self, line_user_id: str, user_text: str) -> str:
        # 同樣獲取 operator 的語言 (可能是 admin 扮演)
        profile = self.repo.get_profile_by_line_user_id(line_user_id)
        if not profile: return "Profile Error"
        lang = profile.get("language", "zh")

        state = self.repo.get_state(line_user_id, "teacher_action")
        if not state: return get_msg("common.unsupported_cmd", lang=lang)

        step = state["step"]
        payload = state.get("payload") or {}
        t_id = payload.get("teacher_profile_id")

        if step == "viewing_pending":
            if user_text.startswith("Accept") or user_text.startswith("接受"):
                return self.teacher_accept_by_index(t_id, parse_index(user_text))
            elif user_text.startswith("Reject") or user_text.startswith("拒絕"):
                idx = parse_index(user_text)
                reason = re.sub(r"^(Reject|拒絕)\s*\d+\s*", "", user_text).strip()
                return self.teacher_reject_by_index(t_id, idx, reason)
        
        elif step == "viewing_confirmed" and (user_text.startswith("Cancel") or user_text.startswith("取消")):
            from services.booking_service import BookingService
            return BookingService().teacher_cancel_confirmed_by_index(t_id, parse_index(user_text), line_user_id)

        return get_msg("common.unsupported_cmd", lang=lang)

    def student_wizard_input(self, line_user_id: str, text: str) -> str:
        """
        學生預約流程的 Wizard (狀態機處理)
        """
        # 1. 取得 Profile 與 Lang (一次查詢)
        profile = self.repo.get_profile_by_line_user_id(line_user_id)
        if not profile: return "Profile Error"
        lang = profile.get("language", "zh")

        # 2. 取得目前的對話狀態
        state = self.repo.get_state(line_user_id, "proposal_create")
        if not state:
            # 如果沒有狀態，代表流程已中斷或過期
            return get_msg("common.unsupported_cmd", lang=lang)

        step = state["step"]
        payload = state.get("payload") or {}

        # === Step 1: 選擇課程模式 (Mode) ===
        if step == "mode":
            idx = parse_index(text)
            # 定義選項對映
            modes = {1: "conversation", 2: "grammar", 3: "kids"}
            
            if idx in modes:
                # 儲存選擇
                payload["class_mode"] = modes[idx]
                
                # 更新狀態到下一步：詢問時間 (Time)
                self.repo.upsert_state(line_user_id, "proposal_create", "time", payload)
                
                return get_msg("proposal.ask_time", lang=lang)
            else:
                return get_msg("common.invalid_input", lang=lang)

        # === Step 2: 輸入時間 (Time) ===
        elif step == "time":
            # 這裡暫時做簡單的字串儲存
            # TODO: 建議未來加入日期格式檢查 (如 YYYY-MM-DD HH:MM)
            payload["time_text"] = text
            
            # 更新狀態到下一步：確認 (Confirm)
            self.repo.upsert_state(line_user_id, "proposal_create", "confirm", payload)
            
            # 準備確認訊息的參數
            mode_map = {"conversation": "對話 (Conversation)", "grammar": "文法 (Grammar)", "kids": "兒童 (Kids)"}
            mode_label = mode_map.get(payload["class_mode"], payload["class_mode"])
            
            return get_msg("proposal.confirm_details", lang=lang, 
                           mode=mode_label, 
                           time=text)

        # === Step 3: 最終確認 (Confirm) ===
        elif step == "confirm":
            # 接受的肯定詞
            if text.lower() in ["yes", "y", "ok", "1", "確認", "是"]:
                
                # 嘗試解析時間並計算結束時間 (預設+50分鐘)
                # 這裡使用簡單的字串處理，建議輸入標準 ISO 格式 (例如: 2023-10-30 10:00)
                start_txt = payload.get("time_text")
                try:
                    # 嘗試利用 dateutil 解析 (如果環境有安裝)
                    from dateutil import parser
                    dt = parser.parse(start_txt)
                    end_dt = dt + timedelta(minutes=50)
                    start_iso = dt.isoformat()
                    end_iso = end_dt.isoformat()
                except:
                    # 如果解析失敗，回退到原始字串 (可能會導致寫入資料庫失敗)
                    # 建議在 production 環境強制要求格式
                    start_iso = start_txt
                    end_iso = start_txt 

                # 建立提案資料
                proposal_data = {
                    "proposed_by": profile["id"],
                    "proposed_by_role": "student",
                    "class_mode": payload.get("class_mode"),
                    "start_time": start_iso,
                    "end_time": end_iso,
                    "status": "pending",
                    "created_at": now_utc_iso()
                }
                
                # 寫入資料庫
                self.repo.create_time_proposal(proposal_data)
                
                # 清除狀態
                self.repo.clear_state(line_user_id, "proposal_create")
                
                # (選用) 這裡可以加入通知老師的邏輯
                
                return get_msg("proposal.created_success", lang=lang)
            
            # 否定詞 -> 取消
            elif text.lower() in ["no", "n", "cancel", "2", "取消", "否"]:
                self.repo.clear_state(line_user_id, "proposal_create")
                return get_msg("common.cancel", lang=lang)
            
            else:
                return get_msg("common.invalid_input", lang=lang)

        return get_msg("common.unsupported_cmd", lang=lang)
    
    def cancel_any_flow(self, line_user_id: str) -> str:
        """通用取消"""
        # 這裡只需要 lang，查一次
        profile = self.repo.get_profile_by_line_user_id(line_user_id)
        lang = profile.get("language", "zh") if profile else "zh"
        
        self.repo.clear_state(line_user_id, "proposal_create")
        self.repo.clear_state(line_user_id, "student_action")
        self.repo.clear_state(line_user_id, "teacher_action")
        
        return get_msg("common.cancel", lang=lang)