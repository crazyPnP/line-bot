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

    def student_start_proposal(self, line_user_id: str) -> str:
        profile = self.repo.get_profile_by_line_user_id(line_user_id)
        if not profile: return get_msg("common.not_found_profile", "zh")
        lang = profile.get("language", "zh")
        self.repo.upsert_state(line_user_id, "proposal_create", "mode", {})
        return get_msg("proposal.ask_mode", lang=lang)

    def student_list_pending(self, line_user_id: str) -> str:
        profile = self.repo.get_profile_by_line_user_id(line_user_id)
        if not profile: return get_msg("common.not_found_profile", "zh")
        lang = profile.get("language", "zh")

        rows = self.repo.list_student_pending_proposals(profile["id"])
        if not rows:
            return get_msg("proposal.no_pending", lang=lang)

        lines = [get_msg("proposal.pending_list_title", lang=lang)]
        for i, r in enumerate(rows, 1):
            start = fmt_taipei(r["start_time"])
            mode_key = r.get("class_mode", "conversation")
            mode_map_dict = {
                "conversation": get_msg("mode.conversation", lang=lang),
                "grammar": get_msg("mode.grammar", lang=lang),
                "kids": get_msg("mode.kids_english", lang=lang)
            }
            t_mode = mode_map_dict.get(mode_key, mode_key)
            lines.append(f"{i}) {t_mode} | {start}")

        lines.append("\n" + get_msg("proposal.cancel_instr", lang=lang))
        return "\n".join(lines)

    def student_cancel_pending_by_index(self, line_user_id: str, idx: int) -> str:
        profile = self.repo.get_profile_by_line_user_id(line_user_id)
        if not profile: return get_msg("common.not_found_profile", "zh")
        lang = profile.get("language", "zh")

        rows = self.repo.list_student_pending_proposals(profile["id"])
        if not rows or idx < 1 or idx > len(rows):
            return get_msg("proposal.not_found", lang=lang, count=len(rows or []))

        r = rows[idx - 1]
        
        if self.repo.cancel_student_pending_proposal(r["id"], profile["id"]):
            mode_key = r.get("class_mode", "conversation")
            mode_map_dict = {
                "conversation": get_msg("mode.conversation", lang=lang),
                "grammar": get_msg("mode.grammar", lang=lang),
                "kids": get_msg("mode.kids_english", lang=lang)
            }
            mode_str = mode_map_dict.get(mode_key, mode_key)
            time_str = fmt_taipei(r['start_time'])

            if lang == "zh":
                return f"✅ 已取消提案 #{idx}\n\n類型：{mode_str}\n時間：{time_str}"
            else:
                return f"✅ Proposal #{idx} canceled.\n\nMode: {mode_str}\nTime: {time_str}"
        
        return get_msg("proposal.cancel_pending_fail", lang=lang)

    def teacher_list_pending(self, teacher_profile_id: str) -> str:
        t_prof = self.repo.get_profile_by_id(teacher_profile_id)
        if not t_prof: return "Teacher profile not found"
        lang = t_prof.get("language", "zh")

        rows = self.repo.list_pending_proposals_for_teacher(teacher_profile_id)
        if not rows:
            return get_msg("teacher.no_pending", lang=lang)

        student_ids = list({r.get("proposed_by") for r in rows if r.get("proposed_by")})
        name_map = self.repo.get_profile_names_by_ids(student_ids) if student_ids else {}

        lines = [get_msg("teacher.pending_list_title", lang=lang)]
        for i, r in enumerate(rows, 1):
            s_name = name_map.get(r["proposed_by"], "Unknown")
            start = fmt_taipei(r["start_time"])
            mode_key = r.get("class_mode", "conversation")
            mode_map_dict = {
                "conversation": get_msg("mode.conversation", lang=lang),
                "grammar": get_msg("mode.grammar", lang=lang),
                "kids": get_msg("mode.kids_english", lang=lang)
            }
            t_mode = mode_map_dict.get(mode_key, mode_key)
            lines.append(f"{i}) 學生: {s_name} | {t_mode} | {start}")

        lines.append("\n" + get_msg("teacher.action_instr", lang=lang))
        return "\n".join(lines)

    def teacher_accept_by_index(self, teacher_profile_id: str, idx: int) -> str:
        t_prof = self.repo.get_profile_by_id(teacher_profile_id)
        if not t_prof: return "Profile error"
        lang = t_prof.get("language", "zh")

        rows = self.repo.list_pending_proposals_for_teacher(teacher_profile_id)
        if not rows or idx < 1 or idx > len(rows):
            return get_msg("proposal.not_found", lang=lang, count=len(rows or []))

        p = rows[idx - 1]
        booking_id = self.repo.create_booking_from_proposal(p["id"], teacher_profile_id)
        
        if booking_id:
            student_line_id = self.repo.get_line_user_id_by_profile_id(p["proposed_by"])
            if student_line_id:
                s_prof = self.repo.get_profile_by_id(p["proposed_by"])
                s_lang = s_prof.get("language", "zh") if s_prof else "zh"
                msg = get_msg("student.notify_accepted", lang=s_lang, 
                              teacher=t_prof.get("name", "Teacher"), 
                              time=fmt_taipei(p["start_time"]))
                self.push.push_text(student_line_id, msg)

            return get_msg("teacher.accept_success", lang=lang, idx=idx)
        
        return get_msg("teacher.accept_fail", lang=lang)

    def teacher_reject_by_index(self, teacher_profile_id: str, idx: int, reason: str) -> str:
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

        student_line_id = self.repo.get_line_user_id_by_profile_id(p["proposed_by"])
        if student_line_id:
            s_prof = self.repo.get_profile_by_id(p["proposed_by"])
            s_lang = s_prof.get("language", "zh") if s_prof else "zh"
            msg = get_msg("teacher.notify_rejected", lang=s_lang, 
                          teacher=t_prof.get("name", "Teacher"), 
                          reason=reason or "No reason provided")
            self.push.push_text(student_line_id, msg)

        return get_msg("teacher.reject_success", lang=lang, idx=idx)

    # === [重構後] 專屬處理 Pending 狀態的邏輯 ===
    def handle_student_pending_action(self, line_user_id: str, user_text: str, lang: str) -> str:
        """專處理學生查看 Pending 提案時的對話"""
        if user_text.startswith("Cancel") or user_text.startswith("取消"):
            idx = parse_index(user_text)
            if idx is None: return get_msg("common.invalid_input", lang=lang)
            
            reply = self.student_cancel_pending_by_index(line_user_id, idx)
            self.repo.clear_state(line_user_id, "student_action")
            return reply
            
        self.repo.clear_state(line_user_id, "student_action")
        return get_msg("common.action_cancelled", lang=lang)

    def handle_teacher_pending_action(self, line_user_id: str, t_id: str, user_text: str, lang: str) -> str:
        """專處理老師查看 Pending 提案時的對話"""
        if user_text.startswith("Accept") or user_text.startswith("接受"):
            reply = self.teacher_accept_by_index(t_id, parse_index(user_text))
            self.repo.clear_state(line_user_id, "teacher_action")
            return reply
            
        elif user_text.startswith("Reject") or user_text.startswith("拒絕"):
            idx = parse_index(user_text)
            reason = re.sub(r"^(Reject|拒絕)\s*\d+\s*", "", user_text).strip()
            reply = self.teacher_reject_by_index(t_id, idx, reason)
            self.repo.clear_state(line_user_id, "teacher_action")
            return reply
            
        self.repo.clear_state(line_user_id, "teacher_action")
        return get_msg("common.action_cancelled", lang=lang)

    def student_wizard_input(self, line_user_id: str, text: str) -> str:
        # ... (保留原有的建立提案流程邏輯，無更動) ...
        profile = self.repo.get_profile_by_line_user_id(line_user_id)
        if not profile: return "Profile Error"
        lang = profile.get("language", "zh")

        state = self.repo.get_state(line_user_id, "proposal_create")
        if not state:
            return get_msg("common.unsupported_cmd", lang=lang)

        step = state["step"]
        payload = state.get("payload") or {}

        if step == "mode":
            idx = parse_index(text)
            modes = {1: "conversation", 2: "grammar", 3: "kids"}
            if idx in modes:
                payload["class_mode"] = modes[idx]
                self.repo.upsert_state(line_user_id, "proposal_create", "time", payload)
                return get_msg("proposal.ask_time", lang=lang)
            else:
                return get_msg("common.invalid_input", lang=lang)

        elif step == "time":
            payload["time_text"] = text
            self.repo.upsert_state(line_user_id, "proposal_create", "confirm", payload)
            mode_map = {"conversation": "對話 (Conversation)", "grammar": "文法 (Grammar)", "kids": "兒童 (Kids)"}
            mode_label = mode_map.get(payload["class_mode"], payload["class_mode"])
            return get_msg("proposal.confirm_details", lang=lang, mode=mode_label, time=text)

        elif step == "confirm":
            if text.lower() in ["yes", "y", "ok", "1", "確認", "是"]:
                start_txt = payload.get("time_text")
                try:
                    from dateutil import parser
                    dt = parser.parse(start_txt)
                    end_dt = dt + timedelta(minutes=50)
                    start_iso = dt.isoformat()
                    end_iso = end_dt.isoformat()
                except:
                    start_iso = start_txt
                    end_iso = start_txt 

                proposal_data = {
                    "proposed_by": profile["id"],
                    "proposed_by_role": "student",
                    "class_mode": payload.get("class_mode"),
                    "start_time": start_iso,
                    "end_time": end_iso,
                    "status": "pending",
                    "created_at": now_utc_iso()
                }
                self.repo.create_time_proposal(proposal_data)
                self.repo.clear_state(line_user_id, "proposal_create")
                return get_msg("proposal.created_success", lang=lang)
            
            elif text.lower() in ["no", "n", "cancel", "2", "取消", "否"]:
                self.repo.clear_state(line_user_id, "proposal_create")
                return get_msg("common.cancel", lang=lang)
            else:
                return get_msg("common.invalid_input", lang=lang)
            
        self.repo.clear_state(line_user_id, "proposal_create")
        return get_msg("common.unsupported_cmd", lang=lang)
    
    def cancel_any_flow(self, line_user_id: str) -> str:
        profile = self.repo.get_profile_by_line_user_id(line_user_id)
        lang = profile.get("language", "zh") if profile else "zh"
        self.repo.clear_state(line_user_id, "proposal_create")
        self.repo.clear_state(line_user_id, "student_action")
        self.repo.clear_state(line_user_id, "teacher_action")
        return get_msg("common.cancel", lang=lang)