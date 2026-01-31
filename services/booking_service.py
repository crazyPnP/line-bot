from datetime import datetime, timedelta
from utils.time_utils import fmt_taipei
from repos.supabase_repo import SupabaseRepo


class BookingService:
    def __init__(self):
        self.repo = SupabaseRepo()
        
    def _can_cancel(self, start_time_iso: str) -> bool:
        start_dt = datetime.fromisoformat(start_time_iso)
        return start_dt - datetime.now() >= timedelta(minutes=30)

    # ===== Student: list confirmed bookings =====
    def student_list_confirmed(self, line_user_id: str) -> str:
        profile = self.repo.get_profile_by_line_user_id(line_user_id)
        if not profile:
            return "找不到你的 profile，請稍後再試。"

        rows = self.repo.list_confirmed_bookings_for_profile(profile["id"])
        rows = [r for r in rows if r.get("student_id") == profile["id"]]

        if not rows:
            return "你目前沒有已成立的課程。"

        teacher_ids = list({r.get("teacher_id") for r in rows if r.get("teacher_id")})
        teacher_map = self.repo.get_profile_names_by_ids(teacher_ids)

        lines = ["📌 你的已成立課程："]
        for i, r in enumerate(rows, 1):
            teacher_name = teacher_map.get(r["teacher_id"], "未知老師")
            start = fmt_taipei(r["start_time"])
            end = fmt_taipei(r["end_time"])

            lines.append(
                f"{i})\n"
                f"老師：{teacher_name}\n"
                f"時間：{start} ~ {end}\n"
            )

        lines.append("取消請輸入：取消課程 1")
        return "\n".join(lines)

    # ===== Student: cancel confirmed booking =====
    def student_cancel_confirmed_by_index(self, line_user_id: str, idx: int) -> str:
        profile = self.repo.get_profile_by_line_user_id(line_user_id)
        if not profile:
            return "找不到你的 profile，請稍後再試。"

        rows = self.repo.list_confirmed_bookings_for_profile(profile["id"])
        rows = [r for r in rows if r.get("student_id") == profile["id"]]

        if not rows:
            return "你目前沒有已成立的課程。"

        if idx < 1 or idx > len(rows):
            return f"序號錯誤，請輸入 1 ~ {len(rows)}"

        b = rows[idx - 1]

        if not self._can_cancel(b["start_time"]):
            return "❌ 距離上課時間 30 分鐘內不可取消。"

        self.repo.cancel_booking(
            booking_id=b["id"],      # ✅ 一律用 id
            cancel_by="student",
            reason="student_cancel"
        )

        return "✅ 已成功取消課程。"
