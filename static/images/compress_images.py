import os
from PIL import Image

def compress_image(input_path, output_path, max_size_mb=1.0):
    if not os.path.exists(input_path):
        print(f"❌ 找不到檔案: {input_path}")
        return

    # 開啟圖片並轉為 RGB (去除 PNG 透明度，因為 JPEG 不支援)
    img = Image.open(input_path)
    img = img.convert("RGB")

    # 初始品質
    quality = 95
    step = 5

    while quality > 10:
        # 儲存為 JPEG
        img.save(output_path, "JPEG", quality=quality, optimize=True)

        # 檢查檔案大小
        file_size = os.path.getsize(output_path) / (1024 * 1024)

        if file_size < max_size_mb:
            print(f"✅ 已轉換並壓縮: {output_path} ({file_size:.2f} MB, Quality: {quality})")
            return

        # 如果還是太大，降低品質重試
        quality -= step

    print(f"⚠️ 警告: 無法將 {input_path} 壓縮至 1MB 以下")

def main():
    # 定義原始 PNG 路徑與輸出的 JPG 路徑
    images = [
        ("static/images/rich_menu_student.png", "static/images/rich_menu_student.jpg"),
        ("static/images/rich_menu_teacher.png", "static/images/rich_menu_teacher.jpg"),
        ("static/images/rich_menu_admin.png",   "static/images/rich_menu_admin.jpg")
    ]

    for png_path, jpg_path in images:
        print(f"正在處理: {png_path} ...")
        compress_image(png_path, jpg_path)

if __name__ == "__main__":
    main()