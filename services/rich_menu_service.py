import os
from config import (
    LINE_CHANNEL_ACCESS_TOKEN,
    RICH_MENU_STUDENT_ID,
    RICH_MENU_TEACHER_ID,
    RICH_MENU_ADMIN_ID
)
from repos.supabase_repo import SupabaseRepo
from linebot.v3.messaging import (
    MessagingApi,
    MessagingApiBlob,
    ApiClient,
    Configuration
)
from linebot.v3.messaging.models import (
    RichMenuRequest,
    RichMenuArea,
    RichMenuBounds,
    RichMenuSize,
    MessageAction  
)

class RichMenuService:
    def __init__(self):
        self.configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
        self.api_client = ApiClient(self.configuration)
        self.messaging_api = MessagingApi(self.api_client)
        self.blob_api = MessagingApiBlob(self.api_client)
        self.repo = SupabaseRepo()

    def create_menu_if_not_exists(self, role: str, image_path: str):
        areas = self._get_areas_by_role(role)
        if not areas:
            return None

        # [重要] 尺寸必須與圖片解析度 1800x1200 一致
        rich_menu_request = RichMenuRequest(
            size=RichMenuSize(width=1800, height=1200),
            selected=False,
            name=f"{role}_menu",
            chat_bar_text="開啟選單",
            areas=areas
        )

        try:
            rich_menu_id = self.messaging_api.create_rich_menu(rich_menu_request).rich_menu_id
            
            content_type = 'image/png' if image_path.lower().endswith('.png') else 'image/jpeg'
            
            with open(image_path, 'rb') as f:
                image_bytes = f.read()
                self.blob_api.set_rich_menu_image(
                    rich_menu_id=rich_menu_id,
                    body=image_bytes,
                    _headers={'Content-Type': content_type}
                )
            
            print(f"✅ Created Rich Menu for {role}: {rich_menu_id}")
            return rich_menu_id

        except Exception as e:
            print(f"❌ Failed to create menu/upload image for {role}: {e}")
            return None

    def link_user_menu(self, line_user_id: str, role: str):
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

    def _get_areas_by_role(self, role: str):
        """定義 2欄 x 3列 (6個按鈕) 的網格座標。總尺寸 1800 x 1200"""
        # 欄位 X 座標與寬度 (1800 / 2 = 900)
        col1_x, col_w = 0, 900
        col2_x = 900
        
        # 列 Y 座標與高度 (1200 / 3 = 400)
        row1_y, row_h = 0, 400
        row2_y = 400
        row3_y = 800

        if role == "student":
            return [
                RichMenuArea(bounds=RichMenuBounds(x=col1_x, y=row1_y, width=col_w, height=row_h), action=MessageAction(label="預約課程", text="預約課程")),
                RichMenuArea(bounds=RichMenuBounds(x=col2_x, y=row1_y, width=col_w, height=row_h), action=MessageAction(label="查看預約課程", text="查看預約課程")),
                RichMenuArea(bounds=RichMenuBounds(x=col1_x, y=row2_y, width=col_w, height=row_h), action=MessageAction(label="我的課表", text="我的課表")),
                RichMenuArea(bounds=RichMenuBounds(x=col2_x, y=row2_y, width=col_w, height=row_h), action=MessageAction(label="切換語言", text="切換語言")),
                RichMenuArea(bounds=RichMenuBounds(x=col1_x, y=row3_y, width=col_w, height=row_h), action=MessageAction(label="取消流程", text="取消流程")),
                RichMenuArea(bounds=RichMenuBounds(x=col2_x, y=row3_y, width=col_w, height=row_h), action=MessageAction(label="操作說明", text="操作說明"))
            ]
        elif role == "teacher":
            return [
                RichMenuArea(bounds=RichMenuBounds(x=col1_x, y=row1_y, width=col_w, height=row_h), action=MessageAction(label="待確認課程", text="待確認課程")),
                RichMenuArea(bounds=RichMenuBounds(x=col2_x, y=row1_y, width=col_w, height=row_h), action=MessageAction(label="我的課表", text="我的課表")),
                RichMenuArea(bounds=RichMenuBounds(x=col1_x, y=row2_y, width=col_w, height=row_h), action=MessageAction(label="切換語言", text="切換語言")),
                RichMenuArea(bounds=RichMenuBounds(x=col2_x, y=row2_y, width=col_w, height=row_h), action=MessageAction(label="結算薪資", text="結算薪資")),
                RichMenuArea(bounds=RichMenuBounds(x=col1_x, y=row3_y, width=col_w, height=row_h), action=MessageAction(label="取消流程", text="取消流程")),
                RichMenuArea(bounds=RichMenuBounds(x=col2_x, y=row3_y, width=col_w, height=row_h), action=MessageAction(label="操作說明", text="操作說明"))
            ]
        elif role == "admin":
            return [
                RichMenuArea(bounds=RichMenuBounds(x=col1_x, y=row1_y, width=col_w, height=row_h), action=MessageAction(label="切換老師", text="切換老師")),
                RichMenuArea(bounds=RichMenuBounds(x=col2_x, y=row1_y, width=col_w, height=row_h), action=MessageAction(label="選老師", text="選老師")),
                RichMenuArea(bounds=RichMenuBounds(x=col1_x, y=row2_y, width=col_w, height=row_h), action=MessageAction(label="切換學生", text="切換學生")),
                RichMenuArea(bounds=RichMenuBounds(x=col2_x, y=row2_y, width=col_w, height=row_h), action=MessageAction(label="結算薪資", text="結算薪資")),
                RichMenuArea(bounds=RichMenuBounds(x=col1_x, y=row3_y, width=col_w, height=row_h), action=MessageAction(label="切換語言", text="切換語言")),
                RichMenuArea(bounds=RichMenuBounds(x=col2_x, y=row3_y, width=col_w, height=row_h), action=MessageAction(label="操作說明", text="操作說明"))
            ]
        return []