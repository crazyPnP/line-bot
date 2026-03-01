from services.rich_menu_service import RichMenuService
from dotenv import load_dotenv

load_dotenv()

def main():
    service = RichMenuService()
    
    # 改回讀取壓縮後產生的小於 1MB 的 jpg 檔案
    menus = [
        ("student", "static/images/rich_menu_student.jpg"),
        ("teacher", "static/images/rich_menu_teacher.jpg"),
        ("admin", "static/images/rich_menu_admin.jpg")
    ]

    print("正在建立與上傳 Rich Menus...")
    for role, path in menus:
        try:
            menu_id = service.create_menu_if_not_exists(role, path)
            if menu_id:
                print(f"✅ 角色 {role} 建立成功 -> ID: {menu_id}")
                print(f"請將此 ID 更新至您的 .env 檔案：\nRICH_MENU_{role.upper()}_ID={menu_id}\n")
        except Exception as e:
            print(f"❌ 建立 {role} 選單時發生錯誤: {e}")

if __name__ == "__main__":
    main()