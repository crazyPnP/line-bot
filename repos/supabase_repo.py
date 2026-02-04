from supabase import create_client
from config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
from utils.time_utils import now_utc_iso

class SupabaseRepo:
    def __init__(self):
        self.sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

    # ==============================
    # 1. Profile 相關 (使用者資料)
    # ==============================
    def create_profile(self, profile_data: dict):
        """建立新使用者資料"""
        self.sb.from_("profile").insert(profile_data).execute()
    
    def update_profile_role(self, profile_id: str, new_role: str):
        """管理員更新使用者角色 (例如將 teacher_pending 改為 teacher)"""
        return self.sb.from_("profile") \
            .update({"role": new_role}) \
            .eq("id", profile_id) \
            .execute()

    def list_pending_teachers(self):
        """列出所有待審核的老師 (role = 'teacher_pending')"""
        res = (
            self.sb.from_("profile")
            .select("*")
            .eq("role", "teacher_pending")
            .order("created_at", desc=True) # 假設 profile 有 created_at，若無可拿掉 order
            .execute()
        )
        return res.data or []
        
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
    
    def get_profile_names_by_ids(self, profile_ids: list[str]) -> dict[str, str]:
        """批次查詢使用者名稱，避免 N+1 問題"""
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
        return self.sb.from_("profile") \
            .update({"language": lang}) \
            .eq("line_user_id", line_user_id) \
            .execute()

    def list_teachers(self):
        """列出所有老師詳細資訊"""
        res = (
            self.sb.from_("profile")
            .select("id,line_user_id,role,name")
            .eq("role", "teacher")
            .order("id")
            .execute()
        )
        return res.data or []

    def list_teachers_simple(self):
        """列出所有老師簡要資訊 (Admin 選單用)"""
        res = (
            self.sb.from_("profile")
            .select("id,name,role")
            .eq("role", "teacher")
            .order("name")
            .execute()
        )
        return res.data or []

    # ==============================
    # 2. Time Proposal 相關 (提案)
    # ==============================
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

    # ==============================
    # 3. Bookings 相關 (正式課程)
    # ==============================
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
    
    def get_confirmed_booking_by_id(self, booking_id: int):
        res = (
            self.sb
            .from_("bookings")
            .select("*")
            .eq("id", booking_id)
            .eq("status", "confirmed")
            .maybe_single()
            .execute()
        )
        return res.data

    def cancel_booking(self, booking_id: str, cancel_by: str, reason: str):
        patch = {
            "status": "canceled",
            "canceled_at": now_utc_iso(),
            "cancel_by": cancel_by,
            "cancel_reason": reason,
            "updated_at": now_utc_iso(),
        }
        self.sb.from_("bookings").update(patch).eq("id", booking_id).execute()

    def create_booking_from_proposal(self, proposal_id: str, teacher_profile_id: str):
        """
        老師接受提案的核心邏輯：
        1. 檢查並鎖定提案
        2. 建立正式 Booking
        3. 更新提案狀態
        """
        # 1. 取得提案資料
        res_p = self.sb.from_("time_proposals").select("*").eq("id", proposal_id).execute()
        if not res_p.data:
            return None
        
        p = res_p.data[0]
        if p["status"] != "pending":
            return None

        # 2. 準備 Booking 資料
        booking_data = {
            "proposal_id": p["id"],
            "teacher_id": teacher_profile_id,
            "student_id": p["proposed_by"],
            "start_time": p["start_time"],
            "end_time": p["end_time"],
            "class_mode": p.get("class_mode", "general"),
            "price": 0, 
            "currency": "TWD",
            "status": "confirmed",
            "created_at": now_utc_iso(),
            "updated_at": now_utc_iso()
        }

        # 3. 寫入 Bookings 表
        res_b = self.sb.from_("bookings").insert(booking_data).execute()
        if not res_b.data:
            return None
            
        new_booking = res_b.data[0]

        # 4. 更新 Time Proposal 狀態為 accepted
        self.sb.from_("time_proposals").update({
            "status": "accepted",
            "updated_at": now_utc_iso()
        }).eq("id", proposal_id).execute()

        return new_booking["id"]

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

    # ==============================
    # 4. Conversation State (Wizard 狀態)
    # ==============================
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
        existing = self.get_state(line_user_id, flow)
        now = now_utc_iso()
        data = {
            "step": step,
            "payload": payload,
            "updated_at": now,
        }

        if existing:
            self.sb.from_("conversation_state").update(data) \
                .eq("line_user_id", line_user_id) \
                .eq("flow", flow) \
                .execute()
        else:
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