from supabase import create_client
from config import SUPABASE_URL, SUPABASE_KEY

class SupabaseRepo:
    def __init__(self):
        self.sb = create_client(SUPABASE_URL, SUPABASE_KEY)

    def get_profile_by_line_user_id(self, line_user_id: str):
        res = self.sb.table("profiles") \
            .select("*") \
            .eq("line_user_id", line_user_id) \
            .single() \
            .execute()
        return res.data

    def list_pending_proposals(self, teacher_id: str):
        res = self.sb.table("time_proposals") \
            .select("*") \
            .eq("to_teacher_id", teacher_id) \
            .eq("status", "pending") \
            .order("start_time") \
            .execute()
        return res.data

    def rpc_accept_proposal(self, proposal_id: str, teacher_id: str):
        res = self.sb.rpc(
            "accept_proposal",
            {
                "p_proposal_id": proposal_id,
                "p_teacher_profile_id": teacher_id
            }
        ).execute()
        return res.data

    def list_upcoming_bookings(self, profile_id: str):
        res = self.sb.table("bookings") \
            .select("*") \
            .or_(f"teacher_id.eq.{profile_id},student_id.eq.{profile_id}") \
            .eq("status", "confirmed") \
            .execute()
        return res.data

    def cancel_booking(self, booking_id: str, cancel_by: str, reason: str):
        self.sb.table("bookings") \
            .update({
                "status": "canceled",
                "cancel_by": cancel_by,
                "cancel_reason": reason
            }) \
            .eq("booking_id", booking_id) \
            .execute()
