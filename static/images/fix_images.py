import os
from PIL import Image

def resize_and_compress(role, input_path):
    if not os.path.exists(input_path):
        print(f"❌ 找不到檔案: {input_path}")
        return

    # 1. 設定目標尺寸為使用者指定的 1800x1200
    target_size = (1800, 1200)

    try:
        # 2. 開啟並轉換圖片
        img = Image.open(input_path)
        img = img.convert("RGB") # 轉為 RGB 以存成 JPEG
        
        # 3. 強制調整尺寸 (Resize)
        img_resized = img.resize(target_size, Image.Resampling.LANCZOS)
        
        # 4. 存檔並確保 < 1MB
        output_path = input_path.rsplit('.', 1)[0] + '.jpg'
        
        quality = 95
        while quality > 10:
            img_resized.save(output_path, "JPEG", quality=quality)
            
            # 檢查檔案大小
            file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
            
            if file_size_mb < 0.95:
                print(f"✅ {role} 修正完成: {target_size[0]}x{target_size[1]} | {file_size_mb:.2f}MB")
                return
            
            quality -= 5
            print(f"   ...嘗試降低品質至 {quality}")

    except Exception as e:
        print(f"❌ 處理 {role} 時發生錯誤: {e}")

def main():
    tasks = [
        ("student", "static/images/rich_menu_student.jpg"),
        ("teacher", "static/images/rich_menu_teacher.jpg"),
        ("admin",   "static/images/rich_menu_admin.jpg")
    ]

    print("🔧 開始修正圖片尺寸與大小 (1800x1200)...")
    for role, path in tasks:
        # 自動尋找對應的 .png 或 .jpg 檔案
        if not os.path.exists(path):
            png_path = path.replace(".jpg", ".png")
            if os.path.exists(png_path):
                path = png_path
                
        resize_and_compress(role, path)

if __name__ == "__main__":
    main()