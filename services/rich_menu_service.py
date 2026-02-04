import os
from config import (
    LINE_CHANNEL_ACCESS_TOKEN,
    RICH_MENU_STUDENT_ID,
    RICH_MENU_TEACHER_ID,
    RICH_MENU_ADMIN_ID
)
from repos.supabase_repo import SupabaseRepo

# 1. API 客戶端相關 (Client & API)
from linebot.v3.messaging import (
    MessagingApi,
    MessagingApiBlob,
    ApiClient,
    Configuration
)

# 2. 資料模型相關 (Models) - 修正這裡
from linebot.v3.messaging.models import (
    RichMenuRequest,
    RichMenuArea,
    RichMenuBounds,
    RichMenuAction,  # 這是 Rich Menu 專用的 Action
    RichMenuSize,
    MessageAction    # 如果您使用 message 類型的動作，需引用此項或直接用 RichMenuAction
)

class RichMenuService:
    def __init__(self):
        self.configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
        self.api_client = ApiClient(self.configuration)
        self.messaging_api = MessagingApi(self.api_client)
        self.blob_api = MessagingApiBlob(self.api_client)
        self.repo = SupabaseRepo()

    def create_menu_if_not_exists(self, role: str, image_path: str):
        """
        建立圖文選單並上傳圖片
        """
        # 1. 定義選單結構
        areas = self._get_areas_by_role(role)
        if not areas:
            print(f"No areas defined for role: {role}")
            return None

        rich_menu_request = RichMenuRequest(
            size=RichMenuSize(width=2500, height=1686 if role == "student" else 843),
            selected=False,
            name=f"{role}_menu",
            chat_bar_text="開啟選單",
            areas=areas
        )

        # 2. 建立選單物件 (使用 MessagingApi)
        rich_menu_id = self.messaging_api.create_rich_menu(rich_menu_request).rich_menu_id
        
        # 3. 上傳圖片 (修正：必須使用 Blob API)
        try:
            with open(image_path, 'rb') as f:
                image_bytes = f.read()
                # 注意：v3 上傳圖片使用的是 blob_api
                self.blob_api.set_rich_menu_image(
                    rich_menu_id=rich_menu_id,
                    body=image_bytes,
                    _headers={'Content-Type': 'image/jpeg'} # 明確指定 Content-Type
                )
            print(f"✅ Created Rich Menu for {role}: {rich_menu_id}")
            return rich_menu_id
        except Exception as e:
            print(f"❌ Failed to upload image for {role}: {e}")
            # 如果圖片上傳失敗，建議刪除建立好的 menu 以免殘留
            self.messaging_api.delete_rich_menu(rich_menu_id)
            return None

    def link_user_menu(self, line_user_id: str, role: str):
        """
        將指定使用者的選單切換為該角色對應的選單
        """
        # 2. 修改讀取方式：直接使用 config 變數，而非 os.getenv
        menu_id = None
        if role == "student":
            menu_id = RICH_MENU_STUDENT_ID
        elif role == "teacher":
            menu_id = RICH_MENU_TEACHER_ID
        elif role == "admin":
            menu_id = RICH_MENU_ADMIN_ID
        
        if menu_id:
            try:
                self.messaging_api.link_rich_menu_id_to_user(line_user_id, menu_id)
                print(f"Linked {line_user_id} to {role} menu ({menu_id})")
            except Exception as e:
                print(f"Failed to link menu: {e}")
        else:
            print(f"No menu ID found for role: {role} in config.py")

    def _get_areas_by_role(self, role: str):
        """定義按鈕區域與觸發文字 (需與 webhook 關鍵字一致)"""
        if role == "student":
            # 學生選單 (2500x1686)
            return [
                RichMenuArea(bounds=RichMenuBounds(x=0, y=0, width=1250, height=843), 
                             action=RichMenuAction(type="message", label="預約", text="預約課程")),
                RichMenuArea(bounds=RichMenuBounds(x=1250, y=0, width=1250, height=843), 
                             action=RichMenuAction(type="message", label="待確認", text="查看預約課程")),
                RichMenuArea(bounds=RichMenuBounds(x=0, y=843, width=1250, height=843), 
                             action=RichMenuAction(type="message", label="課表", text="我的課表")),
                RichMenuArea(bounds=RichMenuBounds(x=1250, y=843, width=1250, height=843), 
                             action=RichMenuAction(type="message", label="重置", text="重新開始"))
            ]
        
        elif role == "teacher":
            # 老師選單 (2500x843)
            w = 2500 // 3
            return [
                RichMenuArea(bounds=RichMenuBounds(x=0, y=0, width=w, height=843), 
                             action=RichMenuAction(type="message", label="審核", text="待確認課程")),
                RichMenuArea(bounds=RichMenuBounds(x=w, y=0, width=w, height=843), 
                             action=RichMenuAction(type="message", label="課表", text="我的課表")),
                RichMenuArea(bounds=RichMenuBounds(x=w*2, y=0, width=2500-w*2, height=843), 
                             action=RichMenuAction(type="message", label="重置", text="重新開始"))
            ]

        elif role == "admin":
             # Admin 選單 (2500x843)
            w = 2500 // 3
            return [
                RichMenuArea(bounds=RichMenuBounds(x=0, y=0, width=w, height=843), 
                             action=RichMenuAction(type="message", label="審核老師", text="審核老師")),
                RichMenuArea(bounds=RichMenuBounds(x=w, y=0, width=w, height=843), 
                             action=RichMenuAction(type="message", label="選老師", text="選老師")),
                RichMenuArea(bounds=RichMenuBounds(x=w*2, y=0, width=2500-w*2, height=843), 
                             action=RichMenuAction(type="message", label="重置", text="重新開始"))
            ]
        return []