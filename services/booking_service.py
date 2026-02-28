from datetime import datetime, timedelta
from utils.time_utils import fmt_taipei, now_utc_iso
from utils.i18n import get_msg, parse_index
from repos.supabase_repo import SupabaseRepo

class BookingService:
    def __init__(self):
        self.repo = SupabaseRepo()

    # === [新增] 專屬處理 Confirmed 狀態的入口 ===
    def handle_student_confirmed_action(self, line_user_id: str, student_profile_id: str, user_text: str, lang: str) -> str:
        if user_text.startswith("Cancel") or user_text.startswith("取消"):
            idx = parse_index(user_text)
            if idx is None: return get_msg("common.invalid_input", lang=lang)
            
            reply = self.student_cancel_confirmed_by_index(student_profile_id, idx, lang)
            self.repo.clear_state(line_user_id, "student_action")
            return reply
            
        self.repo.clear_state(line_user_id, "student_action")
        return get_msg("common.action_cancelled", lang=lang)

    def handle_teacher_confirmed_action(self, line_user_id: str, teacher_profile_id: str, user_text: str, lang: str) -> str:
        if user_text.startswith("Cancel") or user_text.startswith("取消"):
            idx = parse_index(user_text)
            if idx is None: return get_msg("common.invalid_input", lang=lang)
            
            reply = self.teacher_cancel_confirmed_by_index(teacher_profile_id, idx, lang)
            self.repo.clear_state(line_user_id, "teacher_action")
            return reply
            
        self.repo.clear_state(line_user_id, "teacher_action")
        return get_msg("common.action_cancelled", lang=lang)

    def _can_cancel(self, start_time_iso: str) -> bool:
        start_dt = datetime.fromisoformat(start_time_iso)
        now_dt = datetime.fromisoformat(now_utc_iso())
        return start_dt - now_dt >= timedelta(minutes=30)

    def list_confirmed(self, target_profile_id: str, role: str, lang: str) -> str:
        all_rows = self.repo.list_confirmed_bookings_for_profile(target_profile_id)
        
        if role == "teacher":
            rows = [r for r in all_rows if r.get("teacher_id") == target_profile_id]
            other_label = "學生" if lang == "zh" else "Student"
            other_key = "student_id"
        else:
            rows = [r for r in all_rows if r.get("student_id") == target_profile_id]
            other_label = "老師" if lang == "zh" else "Teacher"
            other_key = "teacher_id"

        if not rows: return get_msg("booking.no_bookings", lang=lang)

        other_ids = list({r.get(other_key) for r in rows if r.get(other_key)})
        name_map = self.repo.get_profile_names_by_ids(other_ids) if other_ids else {}

        lines = [get_msg("booking.list_title", lang=lang)]
        for i, r in enumerate(rows, 1):
            time_str = fmt_taipei(r["start_time"])
            mode_key = r.get("class_mode", "conversation") 
            mode_map_dict = {
                "conversation": get_msg("mode.conversation", lang=lang),
                "grammar": get_msg("mode.grammar", lang=lang),
                "kids": get_msg("mode.kids_english", lang=lang)
            }
            mode_str = mode_map_dict.get(mode_key, mode_key)
            o_name = name_map.get(r.get(other_key), "Unknown")
            lines.append(f"{i}) {other_label}: {o_name} | {mode_str} | {time_str}")

        lines.append("")
        lines.append(get_msg("booking.cancel_instr", lang=lang))
        return "\n".join(lines)

    def student_cancel_confirmed_by_index(self, student_profile_id: str, idx: int, lang: str) -> str:
        rows = self.repo.list_confirmed_bookings_for_profile(student_profile_id)
        rows = [r for r in rows if r.get("student_id") == student_profile_id]

        if not rows or idx < 1 or idx > len(rows):
            return get_msg("proposal.not_found", lang=lang, count=len(rows or []))

        b = rows[idx - 1]
        if not self._can_cancel(b["start_time"]):
            return "很抱歉，距離上課時間已不足 30 分鐘，無法取消課程。" if lang == "zh" else "Sorry, you cannot cancel a class within 30 minutes of the start time."

        self.repo.cancel_booking(booking_id=b["id"], cancel_by=student_profile_id, reason="student_cancel")
        
        mode_key = b.get("class_mode", "conversation")
        mode_map = {
            "conversation": get_msg("mode.conversation", lang=lang),
            "grammar": get_msg("mode.grammar", lang=lang),
            "kids": get_msg("mode.kids_english", lang=lang)
        }
        mode_str = mode_map.get(mode_key, mode_key)
        time_str = fmt_taipei(b['start_time'])

        if lang == "zh":
            return f"✅ 已成功取消課程 #{idx}\n\n類型：{mode_str}\n時間：{time_str}"
        else:
            return f"✅ Booking #{idx} canceled successfully.\n\nMode: {mode_str}\nTime: {time_str}"

    def teacher_cancel_confirmed_by_index(self, teacher_profile_id: str, idx: int, lang: str) -> str:
        rows = self.repo.list_confirmed_bookings_for_profile(teacher_profile_id)
        rows = [r for r in rows if r.get("teacher_id") == teacher_profile_id]

        if not rows or idx < 1 or idx > len(rows):
            return get_msg("proposal.not_found", lang=lang, count=len(rows or []))

        b = rows[idx - 1]
        
        if not self._can_cancel(b["start_time"]):
             return "很抱歉，距離上課時間已不足 30 分鐘，無法取消課程。" if lang == "zh" else "Sorry, you cannot cancel a class within 30 minutes of the start time."
             
        self.repo.cancel_booking(booking_id=b["id"], cancel_by=teacher_profile_id, reason="teacher_cancel")
        return get_msg("booking.cancel_success", lang=lang)