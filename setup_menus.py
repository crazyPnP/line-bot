# setup_menus.py (放在專案根目錄)
from services.rich_menu_service import RichMenuService
from dotenv import load_dotenv

load_dotenv()

def main():
    service = RichMenuService()
    
    # 請確保 static/images/ 下有這三張圖
    # 您可以先隨便找三張圖改名測試
    menus = [
        ("student", "static/images/rich_menu_student.png"),
        ("teacher", "static/images/rich_menu_teacher.png"),
        ("admin", "static/images/rich_menu_admin.png")
    ]

    print("正在建立 Rich Menus...")
    for role, path in menus:
        try:
            menu_id = service.create_menu_if_not_exists(role, path)
            print(f"✅ Role: {role} -> ID: {menu_id}")
            print(f"請將此 ID 加入您的 .env 檔案：\nRICH_MENU_{role.upper()}_ID={menu_id}\n")
        except Exception as e:
            print(f"❌ Error creating {role}: {e}")

if __name__ == "__main__":
    main()