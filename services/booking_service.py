from repos.supabase_repo import SupabaseRepo
from domain.rules import can_cancel_booking

class BookingService:
    def __init__(self):
        self.repo = SupabaseRepo()

    def cancel_by_index(self, line_user_id: str, index: int) -> str:
        profile = self.repo.get_profile_by_line_user_id(line_user_id)
        bookings = self.repo.list_upcoming_bookings(profile["id"])

        booking = bookings[index - 1]

        if not can_cancel_booking(booking["start_time"]):
            return "距離上課不足 30 分鐘，無法取消"

        self.repo.cancel_booking(
            booking_id=booking["booking_id"],
            cancel_by=profile["id"],
            reason="LINE取消"
        )

        return "課程已取消"
