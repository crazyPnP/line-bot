from utils.time_utils import now_utc_iso, fmt_taipei, parse_taipei_input_to_utc_iso
from datetime import datetime, timedelta
from repos.supabase_repo import SupabaseRepo
from services.line_notify import LinePushService
from linebot.v3.messaging import Configuration
from config import LINE_CHANNEL_ACCESS_TOKEN
from utils.i18n import get_msg

FLOW = "proposal_create"

class ProposalService:
    def __init__(self):
        self.repo = SupabaseRepo()
        self.push = LinePushService(Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN))

    def _get_lang(self, line_user_id: str) -> str:
        """Helper: 取得使用者語系"""
        profile = self.repo.get_profile_by_line_user_id(line_user_id)
        return profile.get("language", "zh") if profile else "zh"

    # ========= Student: entry =========
    def student_start_proposal(self, line_user_id: str) -> str:
        lang = self._get_lang(line_user_id)
        self.repo.clear_state(line_user_id, FLOW)

        teachers = self.repo.list_teachers()
        if not teachers:
            return get_msg("proposal.no_teachers", lang=lang)

        payload = {
            "teachers": [
                {"id": t["id"], "name": t.get("name", "teacher")}
                for t in teachers
            ]
        }
        self.repo.upsert_state(line_user_id, FLOW, "teacher", payload)

        # 組合老師列表字串
        teacher_lines = []
        for i, t in enumerate(payload["teachers"], 1):
            teacher_lines.append(f"{i}) {t['name']}")
        
        return get_msg("proposal.select_teacher", lang=lang, teachers="\n".join(teacher_lines))

    def student_cancel_flow(self, line_user_id: str) -> str:
        lang = self._get_lang(line_user_id)
        self.repo.clear_state(line_user_id, FLOW)
        return get_msg("proposal.cancel_flow", lang=lang)

    def student_wizard_input(self, line_user_id: str, user_text: str) -> str:
        lang = self._get_lang(line_user_id)
        state = self.repo.get_state(line_user_id, FLOW)
        if not state:
            return get_msg("proposal.wizard_no_state", lang=lang)

        step = state["step"]
        payload = state.get("payload") or {}

        # Step: teacher
        if step == "teacher":
            teachers = payload.get("teachers") or []
            s = user_text.strip()
            if not s.isdigit():
                return get_msg("proposal.input_teacher_idx", lang=lang)

            idx = int(s)
            if idx < 1 or idx > len(teachers):
                return get_msg("proposal.not_found", lang=lang, count=len(teachers))

            payload["to_teacher_id"] = teachers[idx - 1]["id"]
            payload["teacher_name"] = teachers[idx - 1]["name"]
            self.repo.upsert_state(line_user_id, FLOW, "start", payload)
            return get_msg("proposal.input_start_time", lang=lang)

        # Step: start_time
        if step == "start":
            try:
                start_iso_utc = parse_taipei_input_to_utc_iso(user_text.strip())
            except Exception:
                return get_msg("proposal.time_format_error", lang=lang)

            start_dt_utc = datetime.fromisoformat(start_iso_utc)
            min_dt_utc = datetime.fromisoformat(now_utc_iso()) + timedelta(hours=1)

            if start_dt_utc < min_dt_utc:
                return get_msg("proposal.too_soon", lang=lang, min_time=fmt_taipei(min_dt_utc.isoformat()))

            payload["start_time"] = start_iso_utc
            self.repo.upsert_state(line_user_id, FLOW, "end", payload)
            return get_msg("proposal.select_duration", lang=lang)

        # Step: end_time -> select mode
        if step == "end":
            s = user_text.strip()
            minutes = 30 if s == "1" else 60 if s == "2" else None
            if not minutes:
                return get_msg("proposal.select_duration", lang=lang)

            start_dt = datetime.fromisoformat(payload["start_time"])
            end_dt = start_dt + timedelta(minutes=minutes)
            payload["duration_min"] = minutes
            payload["end_time"] = end_dt.isoformat()
            
            self.repo.upsert_state(line_user_id, FLOW, "mode", payload)
            return get_msg("proposal.select_mode", lang=lang)

        # Step: class_mode
        if step == "mode":
            modes = {"1": "對話", "2": "文法", "3": "小孩學英文"} # 建議資料庫存Key，此處簡化處理
            mode = modes.get(user_text.strip())
            if not mode:
                return get_msg("proposal.select_mode", lang=lang)

            payload["class_mode"] = mode
            self.repo.upsert_state(line_user_id, FLOW, "note", payload)
            return get_msg("proposal.input_note", lang=lang)

        # Step: note -> finalize
        if step == "note":
            payload["note"] = user_text.strip()
            student_profile = self.repo.get_profile_by_line_user_id(line_user_id)
            if not student_profile:
                return get_msg("common.not_found_profile", lang=lang)

            proposal = {
                "proposed_by": student_profile["id"],
                "proposed_by_role": "student",
                "to_teacher_id": payload["to_teacher_id"],
                "start_time": payload["start_time"],
                "end_time": payload["end_time"],
                "class_mode": payload.get("class_mode", ""),
                "note": payload.get("note", ""),
                "status": "pending",
            }
            self.repo.create_time_proposal(proposal)
            self.repo.clear_state(line_user_id, FLOW)
            
            return get_msg("proposal.success", lang=lang, 
                           teacher=payload.get("teacher_name"),
                           time=f"{fmt_taipei(proposal['start_time'])}",
                           mode=proposal['class_mode'],
                           note=proposal['note'])

        return get_msg("proposal.wizard_error", lang=lang)

    # ========= Student: list/cancel pending =========
    def student_list_pending(self, line_user_id: str) -> str:
        lang = self._get_lang(line_user_id)
        profile = self.repo.get_profile_by_line_user_id(line_user_id)
        rows = self.repo.list_student_pending_proposals(profile["id"])
        if not rows:
            return get_msg("proposal.no_pending", lang=lang)

        teacher_map = self.repo.get_profile_names_by_ids([r.get("to_teacher_id") for r in rows])
        lines = [get_msg("proposal.pending_list_title", lang=lang)]
        for i, r in enumerate(rows, 1):
            t_name = teacher_map.get(r.get("to_teacher_id"), "Teacher")
            lines.append(f"{i}) {t_name} | {fmt_taipei(r['start_time'])}")
        
        lines.append(get_msg("proposal.cancel_pending_idx", lang=lang))
        return "\n".join(lines)

    def student_cancel_pending_by_index(self, line_user_id: str, idx: int) -> str:
        lang = self._get_lang(line_user_id)
        profile = self.repo.get_profile_by_line_user_id(line_user_id)
        rows = self.repo.list_student_pending_proposals(profile["id"])
        if not rows or idx < 1 or idx > len(rows):
            return get_msg("proposal.not_found", lang=lang, count=len(rows or []))

        r = rows[idx - 1]
        if self.repo.cancel_student_pending_proposal(r["id"], profile["id"]):
            t_name = self.repo.get_profile_names_by_ids([r.get("to_teacher_id")]).get(r.get("to_teacher_id"), "Teacher")
            return get_msg("proposal.cancel_pending_success", lang=lang, idx=idx, teacher=t_name, time=fmt_taipei(r['start_time']))
        return get_msg("proposal.cancel_pending_fail", lang=lang)

    # ========= Teacher: list/accept/reject (通知時需查學生的語言) =========
    def teacher_list_pending(self, teacher_profile_id: str) -> str:
        # 老師介面語系由老師 profile 決定
        teacher_line_id = self.repo.get_line_user_id_by_profile_id(teacher_profile_id)
        lang = self._get_lang(teacher_line_id)
        
        rows = self.repo.list_pending_proposals_for_teacher(teacher_profile_id)
        if not rows:
            return get_msg("teacher.no_pending", lang=lang)

        student_map = self.repo.get_profile_names_by_ids([r.get("proposed_by") for r in rows])
        lines = [get_msg("teacher.pending_list_title", lang=lang)]
        for i, r in enumerate(rows, 1):
            s_name = student_map.get(r["proposed_by"], "Student")
            lines.append(f"{i}) {s_name} | {fmt_taipei(r['start_time'])}")
        return "\n".join(lines)

    def teacher_accept_by_index(self, teacher_profile_id: str, idx: int) -> str:
        # 這裡簡化處理，通知學生時需抓取學生的 lang
        teacher_line_id = self.repo.get_line_user_id_by_profile_id(teacher_profile_id)
        t_lang = self._get_lang(teacher_line_id)
        
        rows = self.repo.list_pending_proposals_for_teacher(teacher_profile_id)
        if idx < 1 or idx > len(rows): return "Error"
        
        p = rows[idx-1]
        # (衝突檢查邏輯略...)
        
        # 通知學生 (關鍵：使用學生的語言)
        student_line_id = self.repo.get_line_user_id_by_profile_id(p["proposed_by"])
        s_lang = self._get_lang(student_line_id)
        
        teacher_profile = self.repo.get_profile_by_id(teacher_profile_id)
        msg = get_msg("teacher.notify_accepted", lang=s_lang, 
                      teacher=teacher_profile.get("name", "Teacher"), 
                      time=fmt_taipei(p['start_time']))
        self.push.push_text(student_line_id, msg)

        return get_msg("teacher.accept_success", lang=t_lang, idx=idx)