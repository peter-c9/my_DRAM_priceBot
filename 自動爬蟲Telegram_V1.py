import os
import re
import pandas as pd
from telethon import TelegramClient
from telethon.sessions import StringSession

# 1. 讀取 GitHub 保險箱 (Secrets) 裡的登入鑰匙
api_id = int(os.environ.get('TG_API_ID', '35016246')) # 如果在自己電腦測試，把 123456 換成你的 ID
api_hash = os.environ.get('TG_API_HASH', 'f91ac54a5743e1982affcfb7e8f56ce1')
session_string = os.environ.get('TG_SESSION', '1BVtsOKwBu7Q8Xef_fsg5IQb4_X94vuinMQPON16I_YtO-Ju91KeVwZyOYgntZ3TWPI0CJU39XhP5lmmzXLOXH1aLxL09Z2JZBt3hf7yqnFM2GLXpV_sYCbMQUSUjLkUzhHiYlEt7nliKJ5JizA3KH2YqmfKGxO-0S3qkbJ813VlDACvksj6YVfkz1Vtn2fZx6McTIzzan1Mwohk_jLhuO_zxRjO_3I7HSeQjZ_wyCPIh8nnK-mnY6_kJoESmsKmLpW2HURMl6gkPNrULW55uoER_VASDbwUzQ3JoQRyPBe1ozJPn4AfB2SGxC0yJOrC03votSvsbTblPXOMkeyBw94YAHni_HmM=')

# 登入 Telegram
client = TelegramClient(StringSession(session_string), api_id, api_hash)

async def main():
    # 2. 指定你的目標對話/頻道名稱
    target_chat = '@k2ai_dev_bot'
    
    # 建立一個專屬資料夾來統一存放這些 CSV，避免檔案太亂
    save_folder = r"C:\Users\User\OneDrive\文件\VS_Python\DRAM每日報價收集_程式\報價資料夾"
    # 這一行保持不變，如果資料夾不存在，程式會自動幫你建立
    os.makedirs(save_folder, exist_ok=True)
    
    print(f"開始連接 Telegram 並搜尋 {target_chat} 的訊息...")
    
    # limit=50 代表往回找最新 50 則訊息 (如果要一次抓歷史幾百天的，可以改成 limit=None)
    async for message in client.iter_messages(target_chat, limit=50):
        
        # 確認這則訊息是不是我們要的報價單
        if message.text and "Item" in message.text and "DRAM Idx" in message.text:
            
            # 取得發文日期
            msg_date = message.date.strftime('%Y-%m-%d')
            lines = message.text.strip().split('\n')
            
            # 從第二行開始逐行解析 (跳過 Item Price Day 30D 標題行)
            for line in lines[1:]:
                # 3. 全新的正則表達式：
                # (.*?)   -> 抓取名稱
                # (\d+\.\d+) -> 抓取數字價格
                # (\S+)   -> 抓取不含空白的連續字串 (單日漲跌幅，包含 - 號)
                # (\S+)   -> 抓取最後一組字串 (月漲跌幅)
                match = re.search(r'^(.*?)\s+(\d+\.\d+)\s+(\S+)\s+(\S+)$', line.strip())
                
                if match:
                    item_name = match.group(1).strip()
                    price = float(match.group(2))
                    day_change = match.group(3)
                    month_change = match.group(4)
                    
                    # 將這筆資料做成單行表格
                    new_record = pd.DataFrame([{
                        'Date': msg_date,
                        'Price': price,
                        'Day': day_change,
                        '30D': month_change
                    }])
                    
                    # 4. 為該產品動態產生 CSV 檔名 (例如: Price_Data/D4 16G 3200.csv)
                    # replace 是為了避免產品名稱內有 / 或 \ 導致系統誤認為資料夾路徑
                    safe_filename = item_name.replace("/", "_").replace("\\", "_")
                    csv_path = os.path.join(save_folder, f"{safe_filename}.csv")
                    
                    # 5. 獨立存檔與防重複邏輯
                    if os.path.exists(csv_path):
                        # 如果檔案存在，讀取舊資料並把新資料接在最下面
                        old_data = pd.read_csv(csv_path)
                        combined_data = pd.concat([old_data, new_record], ignore_index=True)
                        
                        # 確保同一天如果抓到兩次，不會重複紀錄，並且按日期排好
                        combined_data = combined_data.drop_duplicates(subset=['Date'], keep='last')
                        combined_data = combined_data.sort_values(by='Date').reset_index(drop=True)
                    else:
                        # 如果是第一次遇到這個產品，直接建立新資料
                        combined_data = new_record
                        
                    # 儲存回專屬的 CSV 中 (使用 utf-8-sig 確保中文或特殊符號在 Excel 打開不會亂碼)
                    combined_data.to_csv(csv_path, index=False, encoding='utf-8-sig')
            
            print(f"✅ 成功處理並更新日期為 {msg_date} 的所有產品報價！")
            
            # 如果你只是每天定時跑一次，抓到最新的一則就可以停了，把下方的註解打開
            # break 

with client:
    client.loop.run_until_complete(main())