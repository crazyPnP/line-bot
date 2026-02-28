from datetime import datetime, timedelta
from utils.time_utils import fmt_taipei, now_utc_iso
from utils.i18n import get_msg
from repos.supabase_repo import SupabaseRepo

class BookingService:
    def __init__(self):
        self.repo = SupabaseRepo()

    def _can_cancel(self, start_time_iso: str) -> bool:
        """檢查是否在 30 分鐘前取消 (使用 UTC 時間比對)"""
        start_dt = datetime.fromisoformat(start_time_iso)
        now_dt = datetime.fromisoformat(now_utc_iso())
        return start_dt - now_dt >= timedelta(minutes=30)

    def list_confirmed(self, line_user_id: str, role: str) -> str:
        """
        學生與老師共用的課表查詢
        """
        # 1. 查詢 Profile (同時取得語言設定與 ID)
        profile = self.repo.get_profile_by_line_user_id(line_user_id)
        if not profile:
            return get_msg("common.not_found_profile", lang="zh")
            
        lang = profile.get("language", "zh")

        # 2. 撈取所有已確認預約
        all_rows = self.repo.list_confirmed_bookings_for_profile(profile["id"])
        
        # 3. 根據角色過濾並定義顯示標籤
        if role == "teacher":
            rows = [r for r in all_rows if r.get("teacher_id") == profile["id"]]
            other_label = "學生" if lang == "zh" else "Student"
            other_key = "student_id"
        else:
            rows = [r for r in all_rows if r.get("student_id") == profile["id"]]
            other_label = "老師" if lang == "zh" else "Teacher"
            other_key = "teacher_id"

        if not rows:
            return get_msg("booking.no_bookings", lang=lang)

        # 4. 批次取得對方名稱 (Batch Fetch)
        other_ids = list({r.get(other_key) for r in rows if r.get(other_key)})
        if other_ids:
            name_map = self.repo.get_profile_names_by_ids(other_ids)
        else:
            name_map = {}

        from utils.time_utils import fmt_taipei
        lines = [get_msg("booking.list_title", lang=lang)]
        for i, r in enumerate(rows, 1):
            time_str = fmt_taipei(r["start_time"])
            
            # 翻譯課程類型
            mode_key = r.get("class_mode", "conversation") 
            mode_map_dict = {
                "conversation": get_msg("mode.conversation", lang=lang),
                "grammar": get_msg("mode.grammar", lang=lang),
                "kids": get_msg("mode.kids_english", lang=lang)
            }
            mode_str = mode_map_dict.get(mode_key, mode_key)
            
            # 取得對方的名稱
            o_name = name_map.get(r.get(other_key), "Unknown")
    
            # 格式：1) 老師: 承承 | 對話 | 2026-11-12 09:00
            lines.append(f"{i}) {other_label}: {o_name} | {mode_str} | {time_str}")

        lines.append("")
        lines.append(get_msg("booking.cancel_instr", lang=lang))
        return "\n".join(lines)

    def student_cancel_confirmed_by_index(self, line_user_id: str, idx: int) -> str:
        """
        學生取消已確認課程 (By Index)
        """
        print(f"--- [DEBUG] 進入 student_cancel_confirmed_by_index ---")
        print(f"[DEBUG] User: {line_user_id}, 選擇取消的 Index: {idx}")

        # 1. 查詢 Profile
        profile = self.repo.get_profile_by_line_user_id(line_user_id)
        if not profile:
            print("[DEBUG] 錯誤：找不到 Profile")
            return get_msg("common.not_found_profile", lang="zh")
        
        lang = profile.get("language", "zh")
        print(f"[DEBUG] Profile ID: {profile.get('id')}, 語言: {lang}")
        
        # 2. 取得該學生所有課程
        rows = self.repo.list_confirmed_bookings_for_profile(profile["id"])
        print(f"[DEBUG] 從資料庫取得的 confirmed bookings 總數量: {len(rows if rows else [])}")

        rows = [r for r in rows if r.get("student_id") == profile["id"]]
        print(f"[DEBUG] 過濾後純屬該學生的 bookings 數量: {len(rows)}")

        if not rows or idx < 1 or idx > len(rows):
            print(f"[DEBUG] 錯誤：課程清單為空，或輸入的 idx({idx}) 超出範圍(1~{len(rows)})")
            return get_msg("proposal.not_found", lang=lang, count=len(rows or []))

        b = rows[idx - 1]
        print(f"[DEBUG] 目標取消的 Booking ID: {b.get('id')}, Start time: {b.get('start_time')}")
        
        # 3. 檢查 30 分鐘限制
        can_cancel_flag = self._can_cancel(b["start_time"])
        print(f"[DEBUG] 檢查 30 分鐘取消限制結果: can_cancel={can_cancel_flag}")

        if not can_cancel_flag:
            print("[DEBUG] 失敗：違反 30 分鐘取消限制")
            # 這裡不依賴 get_msg，直接回傳寫死的字串測試
            return "很抱歉，距離上課時間已不足 30 分鐘，無法取消課程。"

        print(f"[DEBUG] 準備呼叫 repo.cancel_booking (booking_id={b['id']}, cancel_by={profile['id']})")
        # 關鍵修正：將 cancel_by 改為傳入 profile["id"] (UUID 格式) 而不是純字串 "student"
        self.repo.cancel_booking(booking_id=b["id"], cancel_by=profile["id"], reason="student_cancel")
        print("[DEBUG] 取消成功！即將返回成功訊息")

        # --- 關鍵修改：取消成功後，顯示課程類型與時間 ---
        from utils.time_utils import fmt_taipei
        
        mode_key = b.get("class_mode", "conversation")
        mode_map = {
            "conversation": get_msg("mode.conversation", lang=lang),
            "grammar": get_msg("mode.grammar", lang=lang),
            "kids": get_msg("mode.kids_english", lang=lang)
        }
        mode_str = mode_map.get(mode_key, mode_key)
        time_str = fmt_taipei(b['start_time'])

        if lang == "zh":
            return f"✅ 已成功取消課程 #{idx}\n\n類型：{mode_str}\n時間：{time_str}"
        else:
            return f"✅ Booking #{idx} canceled successfully.\n\nMode: {mode_str}\nTime: {time_str}"

    def teacher_cancel_confirmed_by_index(self, teacher_id: str, idx: int, line_user_id: str) -> str:
        """
        老師端取消課程
        注意：這裡 line_user_id 可能是操作者(Admin或Teacher)，lang 應依據操作者決定
        """
        # 1. 查詢操作者的 Profile 以決定回覆語言
        operator_profile = self.repo.get_profile_by_line_user_id(line_user_id)
        lang = operator_profile.get("language", "zh") if operator_profile else "zh"

        # 2. 查詢老師的課程列表
        rows = self.repo.list_confirmed_bookings_for_profile(teacher_id)
        rows = [r for r in rows if r.get("teacher_id") == teacher_id]

        if not rows or idx < 1 or idx > len(rows):
            return get_msg("proposal.not_found", lang=lang, count=len(rows or []))

        b = rows[idx - 1]
        self.repo.cancel_booking(booking_id=b["id"], cancel_by="teacher", reason="teacher_cancel")
        
        return get_msg("booking.cancel_success", lang=lang)

    def get_confirmed_booking_by_id(self, booking_id: int, line_user_id: str = None) -> str:
        """
        查詢單一課程詳情
        """
        # 這裡單純只查一次 Profile (如果需要 lang)，沒有重複查詢問題
        lang = "zh"
        if line_user_id:
            profile = self.repo.get_profile_by_line_user_id(line_user_id)
            if profile:
                lang = profile.get("language", "zh")
        
        b = self.repo.get_confirmed_booking_by_id(booking_id)
        if not b:
            return get_msg("booking.not_found", lang=lang, id=booking_id)

        # 獲取關聯名稱
        profile_ids = [pid for pid in [b.get("teacher_id"), b.get("student_id")] if pid]
        if profile_ids:
            name_map = self.repo.get_profile_names_by_ids(profile_ids)
        else:
            name_map = {}

        teacher_name = name_map.get(b.get("teacher_id"), "Teacher")
        student_name = name_map.get(b.get("student_id"), "Student")
        start = fmt_taipei(b["start_time"])
        end = fmt_taipei(b["end_time"])

        # 定義多語系標籤
        labels = {
            "zh": {"t": "老師", "s": "學生", "time": "時間", "id": "課程 ID"},
            "en": {"t": "Teacher", "s": "Student", "time": "Time", "id": "Booking ID"}
        }
        lb = labels.get(lang, labels["zh"])

        return (
            f"{get_msg('booking.info_title', lang=lang)}\n"
            f"{lb['id']}：{b['id']}\n"
            f"{lb['t']}：{teacher_name}\n"
            f"{lb['s']}：{student_name}\n"
            f"{lb['time']}：{start} ~ {end}"
        )