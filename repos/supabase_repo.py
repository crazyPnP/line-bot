from supabase import create_client
from config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
from utils.time_utils import now_utc_iso

class SupabaseRepo:
    def __init__(self):
        self.sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

    # ===== profiles =====
    def get_profile_by_line_user_id(self, line_user_id: str):
        res = (
            self.sb.from_("profile")
            .select("*")
            .eq("line_user_id", line_user_id)
            .limit(1)
            .execute()
        )
        data = res.data or []
        return data[0] if data else None

    def get_profile_by_id(self, profile_id: str):
        res = (
            self.sb.from_("profile")
            .select("*")
            .eq("id", profile_id)
            .limit(1)
            .execute()
        )
        data = res.data or []
        return data[0] if data else None

    def get_line_user_id_by_profile_id(self, profile_id: str):
        p = self.get_profile_by_id(profile_id)
        return p.get("line_user_id") if p else None

    def create_student_if_not_exists(self, line_user_id: str, display_name: str, role: str = "student"):
        profile = self.get_profile_by_line_user_id(line_user_id)
        if profile:
            return profile, False

        self.sb.from_("profile").insert({
            "line_user_id": line_user_id,
            "name": display_name,
            "role": role,
        }).execute()

        new_profile = self.get_profile_by_line_user_id(line_user_id)
        return new_profile, True

    def update_profile_language(self, line_user_id: str, lang: str):
        """更新使用者的語言偏好 (zh/en)"""
        return self.client.table("profile") \
            .update({"language": lang}) \
            .eq("line_user_id", line_user_id) \
            .execute()

    def list_teachers_simple(self):
        """Admin 模式使用：列出所有老師的簡要資訊"""
        response = self.client.table("profile") \
            .select("id, name") \
            .eq("role", "teacher") \
            .execute()
        return response.data
        
    # ===== time_proposals (student side) =====
    def create_time_proposal(self, proposal: dict):
        res = self.sb.from_("time_proposals").insert(proposal).execute()
        return res.data

    def list_student_pending_proposals(self, student_profile_id: str):
        res = (
            self.sb.from_("time_proposals")
            .select("*")
            .eq("proposed_by", student_profile_id)
            .eq("proposed_by_role", "student")
            .eq("status", "pending")
            .order("start_time")
            .execute()
        )
        return res.data or []

    def cancel_student_pending_proposal(self, proposal_id: str, student_profile_id: str):
        res = (
            self.sb.from_("time_proposals")
            .update({
                "status": "canceled",
                "updated_at": now_utc_iso(),
            })
            .eq("id", proposal_id)
            .eq("proposed_by", student_profile_id)
            .eq("proposed_by_role", "student")
            .eq("status", "pending")
            .execute()
        )
        return res.data or []
    
    # ===== time_proposals (teacher side pending list) =====
    def list_pending_proposals_for_teacher(self, teacher_profile_id: str):
        res = (
            self.sb.from_("time_proposals")
            .select("*")
            .eq("to_teacher_id", teacher_profile_id)
            .eq("status", "pending")
            .order("start_time")
            .execute()
        )
        return res.data or []

    def rpc_accept_proposal(self, proposal_id: str, teacher_profile_id: str):
        res = (
            self.sb.rpc(
                "accept_proposal",
                {
                    "p_proposal_id": proposal_id,
                    "p_teacher_profile_id": teacher_profile_id,
                },
            ).execute()
        )
        return res.data or []
    
    def update_proposal(self, proposal_id: str, patch: dict):
        patch = dict(patch or {})
        patch.setdefault("updated_at", now_utc_iso())

        res = (
            self.sb.from_("time_proposals")
            .update(patch)
            .eq("id", proposal_id)
            .execute()
        )
        return res.data or []

    # ===== bookings =====
    def list_confirmed_bookings_for_profile(self, profile_id: str):
        res = (
            self.sb.from_("bookings")
            .select("*")
            .or_(f"teacher_id.eq.{profile_id},student_id.eq.{profile_id}")
            .eq("status", "confirmed")
            .order("start_time")
            .execute()
        )
        return res.data or []

    def cancel_booking(self, booking_id: str, cancel_by: str, reason: str):
        patch = {
            "status": "canceled",
            "canceled_at": now_utc_iso(),
            "cancel_by": cancel_by,
            "cancel_reason": reason,
            "updated_at": now_utc_iso(),
        }
        self.sb.from_("bookings").update(patch).eq("id", booking_id).execute()

    def create_booking(self, booking: dict):
        booking = dict(booking or {})
        booking.setdefault("created_at", now_utc_iso())
        booking.setdefault("updated_at", now_utc_iso())

        res = self.sb.from_("bookings").insert(booking).execute()
        return res.data or []

    def has_booking_conflict(self, profile_id: str, start_iso: str, end_iso: str, who: str) -> bool:
        col = "teacher_id" if who == "teacher" else "student_id"
        res = (
            self.sb.from_("bookings")
            .select("id")
            .eq(col, profile_id)
            .eq("status", "confirmed")
            .lt("start_time", end_iso)
            .gt("end_time", start_iso)
            .limit(1)
            .execute()
        )
        return bool(res.data)

    def get_confirmed_booking_by_id(self, booking_id: int):
        res = (
            self.client
            .table("bookings")
            .select("*")
            .eq("id", booking_id)
            .eq("status", "confirmed")
            .maybe_single()
            .execute()
        )
        return res.data
# ===== conversation_state (wizard staging) =====
    def get_state(self, line_user_id: str, flow: str):
        res = (
            self.sb.from_("conversation_state")
            .select("*")
            .eq("line_user_id", line_user_id)
            .eq("flow", flow)
            .limit(1)
            .execute()
        )
        data = res.data or []
        return data[0] if data else None

    def upsert_state(self, line_user_id: str, flow: str, step: str, payload: dict):
        # 需要 table 上有 unique(line_user_id, flow)
        existing = self.get_state(line_user_id, flow)
        now = now_utc_iso()
        data = {
            "step": step,
            "payload": payload,
            "updated_at": now,
        }

        if existing:
            # 用 update（不會撞 unique）
            self.sb.from_("conversation_state").update(data) \
                .eq("line_user_id", line_user_id) \
                .eq("flow", flow) \
                .execute()
        else:
            # 用 insert
            self.sb.from_("conversation_state").insert({
                "line_user_id": line_user_id,
                "flow": flow,
                **data
            }).execute()

    def clear_state(self, line_user_id: str, flow: str):
        self.sb.from_("conversation_state").delete() \
            .eq("line_user_id", line_user_id) \
            .eq("flow", flow) \
            .execute()
    
    def list_teachers(self):
        res = (
            self.sb.from_("profile")
            .select("id,line_user_id,role,name")
            .eq("role", "teacher")
            .order("id")
            .execute()
        )
        return res.data or []
    
    def get_profile_names_by_ids(self, profile_ids: list[str]) -> dict[str, str]:
        ids = [i for i in profile_ids if i]
        if not ids:
            return {}

        res = (
            self.sb.from_("profile")
            .select("id,name")
            .in_("id", ids)
            .execute()
        )
        rows = res.data or []
        return {r["id"]: (r.get("name") or r["id"]) for r in rows}
    
    def list_teachers_simple(self):
        res = (
            self.sb.from_("profile")
            .select("id,name,role")
            .eq("role", "teacher")
            .order("name")
            .execute()
        )
        return res.data or []