from utils.time_utils import now_utc_iso, fmt_taipei, parse_taipei_input_to_utc_iso
from datetime import datetime,timedelta
from repos.supabase_repo import SupabaseRepo
from services.line_notify import LinePushService
from linebot.v3.messaging import Configuration
from config import LINE_CHANNEL_ACCESS_TOKEN

FLOW = "proposal_create"

class ProposalService:
    def __init__(self):
        self.repo = SupabaseRepo()
        self.push = LinePushService(Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN))

    # ========= Student: entry =========
    def student_start_proposal(self, line_user_id: str) -> str:
        self.repo.clear_state(line_user_id, FLOW)

        teachers = self.repo.list_teachers()
        if not teachers:
            return "目前沒有可用的老師，請稍後再試。"

        payload = {
            "teachers": [
                {
                    "id": t["id"],
                    "name": t.get("name", "teacher")
                }
                for t in teachers
            ]
        }

        self.repo.upsert_state(line_user_id, FLOW, "teacher", payload)

        lines = ["📝 開始建立提案", "第 1 步：請選擇老師（輸入數字）"]
        for i, t in enumerate(payload["teachers"], 1):
            lines.append(f"{i}) {t['name']}")

        lines.append("（取消流程：輸入 取消流程）")
        return "\n".join(lines)


    def student_cancel_flow(self, line_user_id: str) -> str:
        self.repo.clear_state(line_user_id, FLOW)
        return "✅ 已取消本次提案流程。"

    def student_wizard_input(self, line_user_id: str, user_text: str) -> str:
        state = self.repo.get_state(line_user_id, FLOW)
        if not state:
            return "你目前沒有進行中的提案流程。請輸入「提案」開始。"

        step = state["step"]
        payload = state.get("payload") or {}

        # Step: teacher
        if step == "teacher":
            s = user_text.strip()
            teachers = payload.get("teachers") or []

            if not s:
                return "請輸入老師序號，例如：1"

            if not s.isdigit():
                return "請輸入老師序號（數字），例如：1"

            idx = int(s)
            if idx < 1 or idx > len(teachers):
                return f"找不到該老師，請輸入 1 ~ {len(teachers)}。"

            payload["to_teacher_id"] = teachers[idx - 1]["id"]
            payload["teacher_name"] = teachers[idx - 1]["name"]

            self.repo.upsert_state(line_user_id, FLOW, "start", payload)
            return "第 2 步：請輸入開始時間（YYYY-MM-DD HH:MM），例如：2025-12-22 19:00"

        # Step: start_time
        if step == "start":
            s = user_text.strip()

            try:
                start_iso_utc = parse_taipei_input_to_utc_iso(s)  # e.g. 2026-12-24T03:00:00+00:00
            except Exception:
                return "開始時間格式錯誤，請用：YYYY-MM-DD HH:MM，例如：2025-12-22 19:00"

            start_dt_utc = datetime.fromisoformat(start_iso_utc)
            min_dt_utc = datetime.fromisoformat(now_utc_iso()) + timedelta(hours=1)

            if start_dt_utc < min_dt_utc:
                return (
                    "開始時間需至少晚於現在 1 小時。\n"
                    f"請輸入 >= {fmt_taipei(min_dt_utc.isoformat())} 的時間。"
                )

            payload["start_time"] = start_iso_utc
            self.repo.upsert_state(line_user_id, FLOW, "end", payload)

            return (
                "第 3 步：請選擇課程時長（輸入數字）\n"
                "1) 30 分鐘\n"
                "2) 1 小時"
            )

        # Step: end_time
        if step == "end":
            s = user_text.strip()

            if s == "1":
                minutes = 30
            elif s == "2":
                minutes = 60
            else:
                return (
                    "請選擇課程時長（輸入數字）：\n"
                    "1) 30 分鐘\n"
                    "2) 1 小時"
                )

            start_dt = datetime.fromisoformat(payload["start_time"])
            end_dt = start_dt + timedelta(minutes=minutes)

            payload["duration_min"] = minutes
            payload["end_time"] = end_dt.isoformat()

            self.repo.upsert_state(line_user_id, FLOW, "mode", payload)

            return (
            "✅ 已設定課程時長\n"
            f"時間：{fmt_taipei(payload['start_time'])} ~ {fmt_taipei(payload['end_time'])}\n\n"
            "第 4 步：請輸入課程類型（輸入數字）\n"
            "1) 對話\n"
            "2) 文法\n"
            "3) 小孩學英文"
        )

        # Step: class_mode
        if step == "mode":
            s = user_text.strip()

            if s == "1":
                mode = "對話"
            elif s == "2":
                mode = "文法"
            elif s == "3":
                mode = "小孩學英文"
            else:
                return (
                    "請選擇課程類型（輸入數字）：\n"
                    "1) 對話\n"
                    "2) 文法\n"
                    "3) 小孩"
            )

            payload["class_mode"] = mode
            self.repo.upsert_state(line_user_id, FLOW, "note", payload)

            return (
                f"✅ 已選擇課程類型：{mode}\n\n"
                "第 5 步：請輸入備註，若無想法請輸入無，例如：想練習面試英文"
            )

        # Step: note -> finalize
        if step == "note":
            payload["note"] = user_text.strip()

            student_profile = self.repo.get_profile_by_line_user_id(line_user_id)
            if not student_profile:
                self.repo.clear_state(line_user_id, FLOW)
                return "找不到你的 profile，請稍後再試。"

            proposal = {
                "proposed_by": student_profile["id"],
                "proposed_by_role": "student",
                "to_teacher_id": payload["to_teacher_id"],
                "start_time": payload["start_time"],
                "end_time": payload["end_time"],
                "class_mode": payload.get("class_mode", ""),
                "note": payload.get("note", ""),
                "status": "pending",
                # responded_* 不填，留給老師端之後處理
            }

            self.repo.create_time_proposal(proposal)
            self.repo.clear_state(line_user_id, FLOW)
            teacher_name = payload.get("teacher_name")
            return (
            "✅ 提案已建立\n"
            f"老師：{teacher_name}\n"
            f"時間：{fmt_taipei(proposal['start_time'])} ~ {fmt_taipei(proposal['end_time'])}\n"
            f"類型：{proposal['class_mode']}\n"
            f"備註：{proposal['note']}\n\n"
            "你可以輸入「取消提案」查看待審核提案。"
        )

        return "流程狀態異常，請輸入「提案」重新開始。"

    # ========= Student: list/cancel pending =========
    def student_list_pending(self, line_user_id: str) -> str:
        student_profile = self.repo.get_profile_by_line_user_id(line_user_id)
        if not student_profile:
            return "找不到你的 profile，請稍後再試。"

        rows = self.repo.list_student_pending_proposals(student_profile["id"])
        if not rows:
            return "你目前沒有 pending 的提案。"

        teacher_ids = list({r.get("to_teacher_id") for r in rows if r.get("to_teacher_id")})
        teacher_map = self.repo.get_profile_names_by_ids(teacher_ids)
        
        lines = ["📌 你的 pending 提案："]
        for i, r in enumerate(rows, 1):
            teacher_id = r.get("to_teacher_id")
            teacher_name = teacher_map.get(teacher_id, teacher_id or "未知老師")
            start = fmt_taipei(r["start_time"])
            end = fmt_taipei(r["end_time"])
            
            lines.append(
                f"{i})\n"
                f"老師：{teacher_name}\n"
                f"時間：{start} ~ {end}\n"
                f"類型：{r.get('class_mode','')}\n"
                f"備註：{r.get('note','')}\n"
            )

        lines.append("取消請輸入：取消提案 1")
        return "\n".join(lines)


    def student_cancel_pending_by_index(self, line_user_id: str, idx: int) -> str:
        student_profile = self.repo.get_profile_by_line_user_id(line_user_id)
        if not student_profile:
            return "找不到你的 profile，請稍後再試。"

        rows = self.repo.list_student_pending_proposals(student_profile["id"])
        if not rows:
            return "你目前沒有 pending 的提案。"

        if idx < 1 or idx > len(rows):
            return f"序號不存在。請輸入 1 ~ {len(rows)}"

        # 先拿到那筆要取消的資料（取消後可能就不是 pending，列表會變）
        r = rows[idx - 1]

        proposal_id = r["id"]  # 你 table 主鍵是 id
        teacher_id = r.get("to_teacher_id")

        teacher_map = self.repo.get_profile_names_by_ids([teacher_id])
        teacher_name = teacher_map.get(teacher_id, teacher_id or "未知老師")

        start = fmt_taipei(r["start_time"])
        end = fmt_taipei(r["end_time"])

        updated = self.repo.cancel_student_pending_proposal(proposal_id, student_profile["id"])
        if not updated:
            return "取消失敗：找不到提案或提案已不是 pending。"

        # ✅ 回傳詳細資訊
        return (
            f"✅ 已取消提案 #{idx}\n\n"
            f"{idx})\n"
            f"老師：{teacher_name}\n"
            f"時間：{start} ~ {end}\n"
            f"類型：{r.get('class_mode','')}\n"
            f"備註：{r.get('note','')}\n"
        )


# ===== Teacher: list pending =====
    def teacher_list_pending(self, teacher_profile_id: str) -> str:
        teacher = self.repo.get_profile_by_id(teacher_profile_id)
        if not teacher:
            return "找不到老師 profile。"

        rows = self.repo.list_pending_proposals_for_teacher(teacher_profile_id)
        if not rows:
            return "目前沒有待審核提案。"

        student_ids = list({r.get("proposed_by") for r in rows if r.get("proposed_by")})
        student_map = self.repo.get_profile_names_by_ids(student_ids)

        lines = ["📩 待審核提案："]
        for i, r in enumerate(rows, 1):
            student_name = student_map.get(r["proposed_by"], "學生")
            start = fmt_taipei(r["start_time"])
            end = fmt_taipei(r["end_time"])
            lines.append(
                f"{i})\n"
                f"學生：{student_name}\n"
                f"時間：{start} ~ {end}\n"
                f"類型：{r.get('class_mode','')}\n"
                f"備註：{r.get('note','')}\n"
            )

        lines.append("操作：接受1 / 拒絕1 原因")
        return "\n".join(lines)

    # ===== Teacher: accept =====
    def teacher_accept_by_index(self, teacher_profile_id: str, idx: int) -> str:
        teacher = self.repo.get_profile_by_id(teacher_profile_id)
        if not teacher:
            return f"找不到老師 profile（id={teacher_profile_id}）。"

        rows = self.repo.list_pending_proposals_for_teacher(teacher_profile_id)
        if not rows:
            return "目前沒有待審核提案。"

        if idx < 1 or idx > len(rows):
            return f"序號錯誤，請輸入 1 ~ {len(rows)}"

        p = rows[idx - 1]
        proposal_id = p["id"]
        student_id = p["proposed_by"]

        # 1) 時段衝突檢查（老師/學生）
        if self.repo.has_booking_conflict(teacher_profile_id, p["start_time"], p["end_time"], "teacher"):
            return "❌ 接受失敗：該時段你已有已成立課程（時間衝突）。"

        if self.repo.has_booking_conflict(student_id, p["start_time"], p["end_time"], "student"):
            return "❌ 接受失敗：學生該時段已有已成立課程（時間衝突）。"

        # 2) 建立 booking（依你的 schema）
        booking = {
            "proposal_id": proposal_id,          # unique FK -> time_proposals.id
            "teacher_id": teacher_profile_id,
            "student_id": student_id,
            "start_time": p["start_time"],
            "end_time": p["end_time"],
            "class_mode": p.get("class_mode", ""),
            "note": p.get("note", ""),
            "status": "confirmed",
            "payment_status": "unpaid",
            "price": 0,
            "currency": "TWD",
        }
        created = self.repo.create_booking(booking)
        if not created:
            return "❌ 建立課程失敗（booking insert 失敗）。"

        # 3) 更新 proposal accepted
        now = now_utc_iso()
        self.repo.update_proposal(proposal_id, {
            "status": "accepted",
            "responded_at": now,
            "responded_by": teacher["id"],
            "response_note": None,
            "updated_at": now,
        })

        # 4) 通知學生
        student_line_id = self.repo.get_line_user_id_by_profile_id(student_id)
        if student_line_id:
            tname = teacher.get("name") or "老師"
            start = fmt_taipei(p["start_time"])
            end = fmt_taipei(p["end_time"])
            msg = (
                f"✅ 你的提案已被 {tname} 接受！\n"
                f"時間：{start} ~ {end}\n"
                f"類型：{p.get('class_mode','')}\n"
                f"備註：{p.get('note','')}"
            )
            self.push.push_text(student_line_id, msg)

        return f"✅ 已接受提案 #{idx}，並建立課程（confirmed）。"

    # ===== Teacher: reject =====
    def teacher_reject_by_index(self, teacher_profile_id: str, idx: int, reason: str) -> str:
        teacher = self.repo.get_profile_by_id(teacher_profile_id)
        if not teacher:
            return f"找不到老師 profile（id={teacher_profile_id}）。"

        rows = self.repo.list_pending_proposals_for_teacher(teacher_profile_id) 
        if not rows:
            return "目前沒有待審核提案。"

        if idx < 1 or idx > len(rows):
            return f"序號錯誤，請輸入 1 ~ {len(rows)}"

        p = rows[idx - 1]
        proposal_id = p["id"]
        student_id = p["proposed_by"]

        now = now_utc_iso()
        self.repo.update_proposal(proposal_id, {
            "status": "rejected",
            "responded_at": now,
            "responded_by": teacher["id"],
            "response_note": reason or "未提供原因",
            "updated_at": now,
        })

        # 通知學生
        student_line_id = self.repo.get_line_user_id_by_profile_id(student_id)
        if student_line_id:
            tname = teacher.get("name") or "老師"
            msg = f"❌ 你的提案被 {tname} 拒絕。\n原因：{reason or '未提供原因'}"
            self.push.push_text(student_line_id, msg)

        return f"✅ 已拒絕提案 #{idx}。"