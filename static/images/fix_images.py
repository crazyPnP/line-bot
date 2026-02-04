import os
from PIL import Image

def resize_and_compress(role, input_path):
    if not os.path.exists(input_path):
        print(f"❌ 找不到檔案: {input_path}")
        return

    # 1. 設定目標尺寸 (必須與 rich_menu_service.py 中的設定完全一致)
    if role == "student":
        target_size = (2500, 1686)
    else:
        target_size = (2500, 843)

    try:
        # 2. 開啟並轉換圖片
        img = Image.open(input_path)
        img = img.convert("RGB") # 轉為 RGB 以存成 JPEG
        
        # 3. 強制調整尺寸 (Resize)
        # 使用 LANZOS 濾鏡保持畫質
        img_resized = img.resize(target_size, Image.Resampling.LANCZOS)
        
        # 4. 存檔並確保 < 1MB
        # 直接覆蓋原檔，或您可以改檔名
        output_path = input_path 
        
        quality = 90
        while quality > 10:
            img_resized.save(output_path, "JPEG", quality=quality)
            
            # 檢查檔案大小
            file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
            
            if file_size_mb < 0.95: # 留一點緩衝，小於 0.95MB
                print(f"✅ {role} 修正完成: {target_size[0]}x{target_size[1]} | {file_size_mb:.2f}MB")
                return
            
            # 如果還是太大，降低品質重試
            quality -= 5
            print(f"   ...檔案仍太大 ({file_size_mb:.2f}MB)，嘗試降低品質至 {quality}")

    except Exception as e:
        print(f"❌ 處理 {role} 時發生錯誤: {e}")

def main():
    # 請確認您的檔案路徑與檔名是否正確 (.jpg)
    tasks = [
        ("student", "static/images/rich_menu_student.jpg"),
        ("teacher", "static/images/rich_menu_teacher.jpg"),
        ("admin",   "static/images/rich_menu_admin.jpg")
    ]

    print("🔧 開始修正圖片尺寸與大小...")
    for role, path in tasks:
        resize_and_compress(role, path)

if __name__ == "__main__":
    main()