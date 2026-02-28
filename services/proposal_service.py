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

    def student_start_proposal(self, line_user_id: str, lang: str) -> str:
        """
        學生開始預約：第一步改為列出老師供選擇
        """
        teachers = self.repo.list_teachers()
        if not teachers:
            return get_msg("proposal.no_teachers", lang=lang)

        # 準備老師選單
        lines = ["請選擇老師（輸入數字）：" if lang == "zh" else "Step 1: Select a teacher (Enter number):"]
        teacher_list = []
        for i, t in enumerate(teachers, 1):
            lines.append(f"{i}) {t['name']}")
            # 儲存到 payload 以供下一步解析比對
            teacher_list.append({"id": t["id"], "name": t["name"]})

        # 初始化 Wizard 狀態，並進入 teacher 步驟
        self.repo.upsert_state(line_user_id, "proposal_create", "teacher", {"teachers": teacher_list})
        
        return "\n".join(lines)

    def student_list_pending(self, student_profile_id: str, lang: str) -> str:
        rows = self.repo.list_student_pending_proposals(student_profile_id)
        if not rows:
            return get_msg("proposal.no_pending", lang=lang)

        # 批次查詢老師名稱
        teacher_ids = list({r.get("to_teacher_id") for r in rows if r.get("to_teacher_id")})
        name_map = self.repo.get_profile_names_by_ids(teacher_ids) if teacher_ids else {}

        lines = [get_msg("proposal.pending_list_title", lang=lang)]
        for i, r in enumerate(rows, 1):
            t_name = name_map.get(r.get("to_teacher_id"), "Unknown")
            start = fmt_taipei(r["start_time"])
            
            mode_key = r.get("class_mode", "conversation")
            mode_map_dict = {
                "conversation": get_msg("mode.conversation", lang=lang),
                "grammar": get_msg("mode.grammar", lang=lang),
                "kids": get_msg("mode.kids_english", lang=lang)
            }
            t_mode = mode_map_dict.get(mode_key, mode_key)
            
            # 格式：1) 老師: 承承 | 對話 | 2026-11-12 09:00
            lines.append(f"{i}) 老師: {t_name} | {t_mode} | {start}")

        lines.append("\n" + get_msg("proposal.cancel_instr", lang=lang))
        return "\n".join(lines)

    def student_cancel_pending_by_index(self, student_profile_id: str, idx: int, lang: str) -> str:
        rows = self.repo.list_student_pending_proposals(student_profile_id)
        if not rows or idx < 1 or idx > len(rows):
            return get_msg("proposal.not_found", lang=lang, count=len(rows or []))

        r = rows[idx - 1]
        
        if self.repo.cancel_student_pending_proposal(r["id"], student_profile_id):
            # 為了取消成功的訊息，撈取老師名稱
            t_id = r.get("to_teacher_id")
            t_name = "Unknown"
            if t_id:
                t_prof = self.repo.get_profile_by_id(t_id)
                if t_prof:
                    t_name = t_prof.get("name", "Unknown")

            mode_key = r.get("class_mode", "conversation")
            mode_map_dict = {
                "conversation": get_msg("mode.conversation", lang=lang),
                "grammar": get_msg("mode.grammar", lang=lang),
                "kids": get_msg("mode.kids_english", lang=lang)
            }
            mode_str = mode_map_dict.get(mode_key, mode_key)
            time_str = fmt_taipei(r['start_time'])

            if lang == "zh":
                return f"✅ 已取消提案 #{idx}\n\n老師：{t_name}\n類型：{mode_str}\n時間：{time_str}"
            else:
                return f"✅ Proposal #{idx} canceled.\n\nTeacher: {t_name}\nMode: {mode_str}\nTime: {time_str}"
        
        return get_msg("proposal.cancel_pending_fail", lang=lang)

    def teacher_list_pending(self, teacher_profile_id: str, lang: str) -> str:
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

    def teacher_accept_by_index(self, teacher_profile_id: str, idx: int, lang: str, teacher_name: str) -> str:
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
                              teacher=teacher_name, 
                              time=fmt_taipei(p["start_time"]))
                self.push.push_text(student_line_id, msg)

            return get_msg("teacher.accept_success", lang=lang, idx=idx)
        
        return get_msg("teacher.accept_fail", lang=lang)

    def teacher_reject_by_index(self, teacher_profile_id: str, idx: int, reason: str, lang: str, teacher_name: str) -> str:
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
                          teacher=teacher_name, 
                          reason=reason or "No reason provided")
            self.push.push_text(student_line_id, msg)

        return get_msg("teacher.reject_success", lang=lang, idx=idx)

    def handle_student_pending_action(self, line_user_id: str, student_profile_id: str, user_text: str, lang: str) -> str:
        if user_text.startswith("Cancel") or user_text.startswith("取消"):
            idx = parse_index(user_text)
            if idx is None: return get_msg("common.invalid_input", lang=lang)
            
            reply = self.student_cancel_pending_by_index(student_profile_id, idx, lang)
            self.repo.clear_state(line_user_id, "student_action")
            return reply
            
        self.repo.clear_state(line_user_id, "student_action")
        return get_msg("common.action_cancelled", lang=lang)

    def handle_teacher_pending_action(self, line_user_id: str, teacher_profile_id: str, user_text: str, lang: str, teacher_name: str) -> str:
        if user_text.startswith("Accept") or user_text.startswith("接受"):
            idx = parse_index(user_text)
            reply = self.teacher_accept_by_index(teacher_profile_id, idx, lang, teacher_name)
            self.repo.clear_state(line_user_id, "teacher_action")
            return reply
            
        elif user_text.startswith("Reject") or user_text.startswith("拒絕"):
            idx = parse_index(user_text)
            reason = re.sub(r"^(Reject|拒絕)\s*\d+\s*", "", user_text).strip()
            reply = self.teacher_reject_by_index(teacher_profile_id, idx, reason, lang, teacher_name)
            self.repo.clear_state(line_user_id, "teacher_action")
            return reply
            
        self.repo.clear_state(line_user_id, "teacher_action")
        return get_msg("common.action_cancelled", lang=lang)

    def student_wizard_input(self, line_user_id: str, student_profile_id: str, text: str, lang: str) -> str:
        state = self.repo.get_state(line_user_id, "proposal_create")
        if not state:
            return get_msg("common.unsupported_cmd", lang=lang)

        step = state["step"]
        payload = state.get("payload") or {}

        # === Step 1: 選擇老師 (Teacher) ===
        if step == "teacher":
            idx = parse_index(text)
            teachers = payload.get("teachers", [])
            
            if idx and 1 <= idx <= len(teachers):
                selected_t = teachers[idx - 1]
                payload["to_teacher_id"] = selected_t["id"]
                payload["teacher_name"] = selected_t["name"]
                
                # 推進到選擇課程模式
                self.repo.upsert_state(line_user_id, "proposal_create", "mode", payload)
                return get_msg("proposal.ask_mode", lang=lang)
            else:
                return get_msg("common.invalid_input", lang=lang)

        # === Step 2: 選擇課程模式 (Mode) ===
        elif step == "mode":
            idx = parse_index(text)
            modes = {1: "conversation", 2: "grammar", 3: "kids"}
            
            if idx in modes:
                payload["class_mode"] = modes[idx]
                self.repo.upsert_state(line_user_id, "proposal_create", "time", payload)
                return get_msg("proposal.ask_time", lang=lang)
            else:
                return get_msg("common.invalid_input", lang=lang)

        # === Step 3: 輸入時間 (Time) ===
        elif step == "time":
            payload["time_text"] = text
            self.repo.upsert_state(line_user_id, "proposal_create", "confirm", payload)
            
            mode_map = {"conversation": "對話 (Conversation)", "grammar": "文法 (Grammar)", "kids": "兒童 (Kids)"}
            mode_label = mode_map.get(payload["class_mode"], payload["class_mode"])
            
            # 取得老師名字
            t_name = payload.get("teacher_name", "Unknown")
            
            # 依據要求格式化確認訊息
            if lang == "zh":
                return (
                    "請確認您的預約資訊：\n"
                    f"老師 : {t_name}\n"
                    f"類別：{mode_label}\n"
                    f"時間：{text}\n\n"
                    "1) 確認 (Yes)\n"
                    "2) 取消 (No)"
                )
            else:
                return (
                    "Please confirm your booking details:\n"
                    f"Teacher : {t_name}\n"
                    f"Mode: {mode_label}\n"
                    f"Time: {text}\n\n"
                    "1) Confirm (Yes)\n"
                    "2) Cancel (No)"
                )

        # === Step 4: 最終確認 (Confirm) ===
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
                    "proposed_by": student_profile_id,
                    "proposed_by_role": "student",
                    "to_teacher_id": payload.get("to_teacher_id"), # [關鍵新增] 將老師 ID 寫入資料庫
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
    
    def cancel_any_flow(self, line_user_id: str, lang: str) -> str:
        self.repo.clear_state(line_user_id, "proposal_create")
        self.repo.clear_state(line_user_id, "student_action")
        self.repo.clear_state(line_user_id, "teacher_action")
        return get_msg("common.cancel", lang=lang)