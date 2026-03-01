from datetime import datetime, timedelta, timezone
from utils.time_utils import fmt_taipei, now_utc_iso
from utils.i18n import get_msg, parse_index
from repos.supabase_repo import SupabaseRepo

class BookingService:
    def __init__(self):
        self.repo = SupabaseRepo()

    def _get_weekday_from_iso(self, iso_str: str, lang: str) -> str:
        """根據 ISO 字串轉換成台灣時間後取得星期幾"""
        try:
            if iso_str.endswith('Z'):
                iso_str = iso_str[:-1] + '+00:00'
            dt = datetime.fromisoformat(iso_str)
            dt_tw = dt.astimezone(timezone(timedelta(hours=8)))
            weekdays_zh = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
            weekdays_en = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            return weekdays_zh[dt_tw.weekday()] if lang == "zh" else weekdays_en[dt_tw.weekday()]
        except Exception:
            return ""

    def calculate_and_display_salary(self, teacher_profile_id: str, teacher_name: str, lang: str) -> str:
        """計算並顯示老師未付款的總薪資與堂數"""
        # 1. 取得該老師所有已確認且「未付款 (unpaid)」的課程
        all_rows = self.repo.list_confirmed_bookings_for_profile(teacher_profile_id)
        unpaid_bookings = [
            r for r in all_rows 
            if r.get("teacher_id") == teacher_profile_id and r.get("payment_status") == "unpaid"
        ]

        if not unpaid_bookings:
            return f"✅ 老師 【{teacher_name}】 目前沒有未付款的課程。" if lang == "zh" else f"✅ Teacher 【{teacher_name}】 has no unpaid bookings."

        # 2. 取得計價規則 (從 price 表)
        price_rules = self.repo.get_all_prices()
        price_dict = {}
        for rule in price_rules:
            t_min = int(rule.get("time(min)", 0))
            c_mode = rule.get("class-mode", "").lower()
            money = int(rule.get("money(PHP)", 0))
            price_dict[(t_min, c_mode)] = money

        total_money = 0
        total_classes = len(unpaid_bookings)

        # 3. 逐堂比對與計算
        for b in unpaid_bookings:
            # 計算該堂課時長 (分鐘)
            try:
                st_str = b["start_time"].replace('Z', '+00:00')
                et_str = b["end_time"].replace('Z', '+00:00')
                st = datetime.fromisoformat(st_str)
                et = datetime.fromisoformat(et_str)
                duration_mins = (et - st).total_seconds() / 60
            except:
                duration_mins = 60  # 解析失敗預設以 60 分鐘計
                
            rule_time = 30 if duration_mins <= 45 else 60

            # 判斷課程模式，需對應資料庫字眼
            raw_mode = b.get("class_mode", "conversation")
            if raw_mode == "小孩學英文": # 相容舊資料
                raw_mode = "kids"
                
            mode_map = {
                "conversation": "conversation",
                "grammar": "grammer", # 對應您資料庫中的拼字
                "kids": "for kid"     # 對應您資料庫中的類別名稱
            }
            rule_mode = mode_map.get(raw_mode, "conversation")

            # 取得對應價格
            money = price_dict.get((rule_time, rule_mode), 0)
            
            # 萬一沒有匹配到規則，給予保底機制
            if money == 0:
                money = price_dict.get((60, "conversation"), 180)

            total_money += money

            # 順便更新資料庫的訂單價格
            self.repo.update_booking_price(b["id"], money, "PHP")

        if lang == "zh":
            return f"💰 【{teacher_name}】的薪資結算\n\n累計未付款堂數：{total_classes} 堂\n結算總金額：{total_money} PHP"
        else:
            return f"💰 Salary for 【{teacher_name}】\n\nUnpaid Classes: {total_classes}\nTotal Amount: {total_money} PHP"

    def handle_student_confirmed_action(self, line_user_id: str, student_profile_id: str, user_text: str, lang: str) -> str:
        if user_text.startswith("Cancel") or user_text.startswith("取消"):
            idx = parse_index(user_text)
            if idx is None: return get_msg("common.invalid_input", lang=lang)
            
            reply = self.student_cancel_confirmed_by_index(student_profile_id, idx, lang)
            self.repo.clear_state(line_user_id, "student_action")
            return reply
            
        self.repo.clear_state(line_user_id, "student_action")
        return get_msg("common.action_cancelled", lang=lang)

    def handle_teacher_confirmed_action(self, line_user_id: str, teacher_profile_id: str, user_text: str, lang: str) -> str:
        if user_text.startswith("Cancel") or user_text.startswith("取消"):
            idx = parse_index(user_text)
            if idx is None: return get_msg("common.invalid_input", lang=lang)
            
            reply = self.teacher_cancel_confirmed_by_index(teacher_profile_id, idx, lang)
            self.repo.clear_state(line_user_id, "teacher_action")
            return reply
            
        self.repo.clear_state(line_user_id, "teacher_action")
        return get_msg("common.action_cancelled", lang=lang)

    def _can_cancel(self, start_time_iso: str) -> bool:
        start_dt = datetime.fromisoformat(start_time_iso)
        now_dt = datetime.fromisoformat(now_utc_iso())
        return start_dt - now_dt >= timedelta(minutes=30)

    def list_confirmed(self, target_profile_id: str, role: str, lang: str) -> str:
        all_rows = self.repo.list_confirmed_bookings_for_profile(target_profile_id)
        
        if role == "teacher":
            rows = [r for r in all_rows if r.get("teacher_id") == target_profile_id]
            other_label = "學生" if lang == "zh" else "Student"
            other_key = "student_id"
        else:
            rows = [r for r in all_rows if r.get("student_id") == target_profile_id]
            other_label = "老師" if lang == "zh" else "Teacher"
            other_key = "teacher_id"

        if not rows: return get_msg("booking.no_bookings", lang=lang)

        other_ids = list({r.get(other_key) for r in rows if r.get(other_key)})
        name_map = self.repo.get_profile_names_by_ids(other_ids) if other_ids else {}

        lines = [get_msg("booking.list_title", lang=lang)]
        for i, r in enumerate(rows, 1):
            time_str = fmt_taipei(r["start_time"])
            weekday_str = self._get_weekday_from_iso(r["start_time"], lang)
            
            mode_key = r.get("class_mode", "conversation") 
            mode_map_dict = {
                "conversation": get_msg("mode.conversation", lang=lang),
                "grammar": get_msg("mode.grammar", lang=lang),
                "kids": get_msg("mode.kids_english", lang=lang)
            }
            mode_str = mode_map_dict.get(mode_key, mode_key)
            o_name = name_map.get(r.get(other_key), "Unknown")
            
            note = r.get("note", "")
            note_str = f"\n   └ 備註: {note}" if note else ""
            
            lines.append(f"{i}) {other_label}: {o_name} | {mode_str} | {time_str} ({weekday_str}){note_str}")

        lines.append("")
        lines.append(get_msg("booking.cancel_instr", lang=lang))
        return "\n".join(lines)

    def student_cancel_confirmed_by_index(self, student_profile_id: str, idx: int, lang: str) -> str:
        rows = self.repo.list_confirmed_bookings_for_profile(student_profile_id)
        rows = [r for r in rows if r.get("student_id") == student_profile_id]

        if not rows or idx < 1 or idx > len(rows):
            return get_msg("proposal.not_found", lang=lang, count=len(rows or []))

        b = rows[idx - 1]
        if not self._can_cancel(b["start_time"]):
            return "很抱歉，距離上課時間已不足 30 分鐘，無法取消課程。" if lang == "zh" else "Sorry, you cannot cancel a class within 30 minutes of the start time."

        self.repo.cancel_booking(booking_id=b["id"], cancel_by=student_profile_id, reason="student_cancel")
        
        mode_key = b.get("class_mode", "conversation")
        mode_map = {
            "conversation": get_msg("mode.conversation", lang=lang),
            "grammar": get_msg("mode.grammar", lang=lang),
            "kids": get_msg("mode.kids_english", lang=lang)
        }
        mode_str = mode_map.get(mode_key, mode_key)
        time_str = fmt_taipei(b['start_time'])
        weekday_str = self._get_weekday_from_iso(b['start_time'], lang)

        if lang == "zh":
            return f"✅ 已成功取消課程 #{idx}\n\n類型：{mode_str}\n時間：{time_str} ({weekday_str})"
        else:
            return f"✅ Booking #{idx} canceled successfully.\n\nMode: {mode_str}\nTime: {time_str} ({weekday_str})"

    def teacher_cancel_confirmed_by_index(self, teacher_profile_id: str, idx: int, lang: str) -> str:
        rows = self.repo.list_confirmed_bookings_for_profile(teacher_profile_id)
        rows = [r for r in rows if r.get("teacher_id") == teacher_profile_id]

        if not rows or idx < 1 or idx > len(rows):
            return get_msg("proposal.not_found", lang=lang, count=len(rows or []))

        b = rows[idx - 1]
        
        if not self._can_cancel(b["start_time"]):
             return "很抱歉，距離上課時間已不足 30 分鐘，無法取消課程。" if lang == "zh" else "Sorry, you cannot cancel a class within 30 minutes of the start time."
             
        self.repo.cancel_booking(booking_id=b["id"], cancel_by=teacher_profile_id, reason="teacher_cancel")
        return get_msg("booking.cancel_success", lang=lang)