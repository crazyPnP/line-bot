from datetime import datetime, timedelta
from utils.time_utils import fmt_taipei, now_utc_iso
from repos.supabase_repo import SupabaseRepo
from utils.i18n import get_msg

class BookingService:
    def __init__(self):
        self.repo = SupabaseRepo()

    def _get_lang(self, line_user_id: str) -> str:
        """取得使用者語系偏好，預設為中文"""
        if not line_user_id:
            return "zh"
        profile = self.repo.get_profile_by_line_user_id(line_user_id)
        return profile.get("language", "zh") if profile else "zh"

    def _can_cancel(self, start_time_iso: str) -> bool:
        """檢查是否在 30 分鐘前取消 (使用 UTC 時間比對)"""
        start_dt = datetime.fromisoformat(start_time_iso)
        now_dt = datetime.fromisoformat(now_utc_iso())
        return start_dt - now_dt >= timedelta(minutes=30)

    # ===== Student: cancel confirmed booking =====
    def student_cancel_confirmed_by_index(self, line_user_id: str, idx: int) -> str:
        lang = self._get_lang(line_user_id)
        profile = self.repo.get_profile_by_line_user_id(line_user_id)
        if not profile:
            return get_msg("common.not_found_profile", lang=lang)

        rows = self.repo.list_confirmed_bookings_for_profile(profile["id"])
        rows = [r for r in rows if r.get("student_id") == profile["id"]]

        if not rows:
            return get_msg("booking.no_bookings", lang=lang)

        if idx < 1 or idx > len(rows):
            return get_msg("proposal.not_found", lang=lang, count=len(rows))

        b = rows[idx - 1]

        # 執行 30 分鐘取消限制檢查
        if not self._can_cancel(b["start_time"]):
            return get_msg("booking.cancel_limit", lang=lang)

        self.repo.cancel_booking(
            booking_id=b["id"],
            cancel_by="student",
            reason="student_cancel"
        )

        return get_msg("booking.cancel_success", lang=lang)

    # ===== General: Get booking details by ID =====
    def get_confirmed_booking_by_id(self, booking_id: int, line_user_id: str = None) -> str:
        # 如果有傳入 line_user_id 則判斷語系，否則預設中文
        lang = self._get_lang(line_user_id)
        
        b = self.repo.get_confirmed_booking_by_id(booking_id)
        if not b:
            return get_msg("booking.not_found", lang=lang, id=booking_id)

        # 獲取關聯名稱
        profile_ids = [pid for pid in [b.get("teacher_id"), b.get("student_id")] if pid]
        name_map = self.repo.get_profile_names_by_ids(profile_ids)

        teacher_name = name_map.get(b.get("teacher_id"), "Teacher")
        student_name = name_map.get(b.get("student_id"), "Student")
        start = fmt_taipei(b["start_time"])
        end = fmt_taipei(b["end_time"])

        # 定義多語系標籤
        labels = {
            "zh": {"t": "老師", "s": "學生", "time": "時間", "id": "課程 ID"},
            "en": {"t": "Teacher", "s": "Student", "time": "Time", "id": "Booking ID"}
        }
        lb = labels.get(lang, labels["zh"])

        return (
            f"{get_msg('booking.info_title', lang=lang)}\n"
            f"{lb['id']}：{b['id']}\n"
            f"{lb['t']}：{teacher_name}\n"
            f"{lb['s']}：{student_name}\n"
            f"{lb['time']}：{start} ~ {end}"
        )
        
    def list_confirmed(self, line_user_id: str, role: str) -> str:
        """學生與老師共用的課表查詢"""
        lang = self._get_lang(line_user_id)
        profile = self.repo.get_profile_by_line_user_id(line_user_id)
        if not profile:
            return get_msg("common.not_found_profile", lang=lang)

        # 撈取所有已確認預約
        all_rows = self.repo.list_confirmed_bookings_for_profile(profile["id"])
        
        # 根據角色過濾並定義顯示標籤
        if role == "teacher":
            rows = [r for r in all_rows if r.get("teacher_id") == profile["id"]]
            other_label = "學生" if lang == "zh" else "Student"
            other_key = "student_id"
        else:
            rows = [r for r in all_rows if r.get("student_id") == profile["id"]]
            other_label = "老師" if lang == "zh" else "Teacher"
            other_key = "teacher_id"

        if not rows:
            return get_msg("booking.no_bookings", lang=lang)

        # 取得對方名稱
        other_ids = list({r.get(other_key) for r in rows if r.get(other_key)})
        name_map = self.repo.get_profile_names_by_ids(other_ids)

        lines = [get_msg("booking.list_title", lang=lang)]
        for i, r in enumerate(rows, 1):
            name = name_map.get(r[other_key], "Unknown")
            lines.append(f"{i}) {other_label}: {name} | {fmt_taipei(r['start_time'])}")

        lines.append("\n" + get_msg("booking.cancel_instr", lang=lang))
        return "\n".join(lines)

    def teacher_cancel_confirmed_by_index(self, teacher_id: str, idx: int, line_user_id: str) -> str:
        """老師端取消已成立課程"""
        lang = self._get_lang(line_user_id)
        rows = self.repo.list_confirmed_bookings_for_profile(teacher_id)
        rows = [r for r in rows if r.get("teacher_id") == teacher_id]

        if not rows or idx < 1 or idx > len(rows):
            return get_msg("proposal.not_found", lang=lang, count=len(rows))

        b = rows[idx - 1]
        # 執行取消 (老師取消通常不設 30 分鐘限制，但會發送緊急通知)
        self.repo.cancel_booking(booking_id=b["id"], cancel_by="teacher", reason="teacher_cancel")
        
        # 通知學生 (邏輯略...)
        return get_msg("booking.cancel_success", lang=lang)
