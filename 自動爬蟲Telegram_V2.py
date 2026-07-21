import os
import re
import pandas as pd
from telethon import TelegramClient
from telethon.sessions import StringSession

# 1. 讀取 GitHub 保險箱 (Secrets) 裡的登入鑰匙
api_id = int(os.environ.get('TG_API_ID', '35016246')) # 如果在自己電腦測試，把 123456 換成你的 ID
api_hash = os.environ.get('TG_API_HASH', 'f91ac54a5743e1982affcfb7e8f56ce1')
session_string = os.environ.get('TG_SESSION', '1BVtsOKwBu7Q8Xef_fsg5IQb4_X94vuinMQPON16I_YtO-Ju91KeVwZyOYgntZ3TWPI0CJU39XhP5lmmzXLOXH1aLxL09Z2JZBt3hf7yqnFM2GLXpV_sYCbMQUSUjLkUzhHiYlEt7nliKJ5JizA3KH2YqmfKGxO-0S3qkbJ813VlDACvksj6YVfkz1Vtn2fZx6McTIzzan1Mwohk_jLhuO_zxRjO_3I7HSeQjZ_wyCPIh8nnK-mnY6_kJoESmsKmLpW2HURMl6gkPNrULW55uoER_VASDbwUzQ3JoQRyPBe1ozJPn4AfB2SGxC0yJOrC03votSvsbTblPXOMkeyBw94YAHni_HmM=')

client = TelegramClient(StringSession(session_string), api_id, api_hash)

async def main():
    target_chat = '@k2ai_dev_bot'
    save_folder = r"C:\Users\User\OneDrive\文件\VS_Python\DRAM每日報價收集_程式\報價資料夾"
    os.makedirs(save_folder, exist_ok=True)
    
    print(f"開始連接 Telegram 並搜尋 {target_chat} 的訊息...")
    
    # 建立一個空清單，用來暫存這次從 Telegram 抓下來的所有報價資料
    all_parsed_data = []
    
    # limit=200：因為你要找回早期被誤刪的資料，可以把這個數字調大 (例如 300, 500)
    async for message in client.iter_messages(target_chat, limit=200):
        if not message.text:
            continue
            
        # 判斷這則訊息是 DRAM 報價還是 GPU 報價
        is_dram = "Item" in message.text and "DRAM Idx" in message.text
        is_gpu = "GPU" in message.text and "$/h" in message.text
        
        if is_dram or is_gpu:
            # 優先嘗試從文字中萃取日期 (例如 GPU 報價首行的 2026-07-14)
            date_match = re.search(r'\d{4}-\d{2}-\d{2}', message.text)
            if date_match:
                msg_date = date_match.group(0)
            else:
                # 若文字沒寫日期，則使用發文當天的日期
                msg_date = message.date.strftime('%Y-%m-%d')
                
            lines = message.text.strip().split('\n')
            
            for line in lines:
                # 使用通用的正則表達式，同時適用於 DRAM 與 GPU 的資料行
                match = re.search(r'^(.*?)\s+(\d+\.\d+)\s+(\S+)\s+(\S+)$', line.strip())
                if match:
                    item_name = match.group(1).strip()
                    
                    # 排除不小心抓到的標題列 (避免把 GPU $/h 當成產品)
                    if "Item" in item_name or "GPU" in item_name:
                        continue
                        
                    price = float(match.group(2))
                    day_change = match.group(3)
                    month_change = match.group(4)
                    
                    # 將抓到的單筆資料先放入暫存清單中
                    all_parsed_data.append({
                        'Item': item_name,
                        'Date': msg_date,
                        'Price': price,
                        'Day': day_change,
                        '30D': month_change
                    })

    # --- 進入智慧存檔階段 ---
    if all_parsed_data:
        # 將剛剛抓到的所有資料轉換成大表格
        df_scraped = pd.DataFrame(all_parsed_data)
        
        # 依照「產品名稱 (Item)」進行分組處理
        for item_name, group_data in df_scraped.groupby('Item'):
            safe_filename = item_name.replace("/", "_").replace("\\", "_")
            csv_path = os.path.join(save_folder, f"{safe_filename}.csv")
            
            # 為了存檔乾淨，先把暫存資料裡不需要的 'Item' 欄位拿掉
            group_data = group_data[['Date', 'Price', 'Day', '30D']].copy()
            
            if os.path.exists(csv_path):
                # 檔案已經存在：讀取舊資料
                df_exist = pd.read_csv(csv_path)
                
                # 取得舊資料中已經擁有的「日期清單」
                existing_dates = set(df_exist['Date'].astype(str))
                
                # 比對：只挑出「新抓到的資料中，日期不在舊檔案裡」的缺漏資料
                df_missing = group_data[~group_data['Date'].astype(str).isin(existing_dates)]
                
                if not df_missing.empty:
                    # 如果有缺漏資料，將舊資料與缺漏資料合併
                    df_combined = pd.concat([df_exist, df_missing], ignore_index=True)
                    # 依照日期排序 (舊到新)
                    df_combined = df_combined.sort_values(by='Date').reset_index(drop=True)
                    # 覆寫回檔案
                    df_combined.to_csv(csv_path, index=False, encoding='utf-8-sig')
                    print(f"🔄 更新成功: [{item_name}] 補齊了 {len(df_missing)} 筆新日期資料。")
                else:
                    # 如果沒有缺漏，程式完全不去碰這個 CSV 檔案
                    pass 
                    print(f"✨ 略過: [{item_name}] 歷史資料已完整，無須更新。") 
                    # (如果你覺得一直印這行太吵，這行目前是被註解隱藏的)
            
            else:
                # 檔案完全不存在：第一次建立
                group_data = group_data.sort_values(by='Date').reset_index(drop=True)
                group_data.to_csv(csv_path, index=False, encoding='utf-8-sig')
                print(f"🆕 建立新檔: [{item_name}] 寫入 {len(group_data)} 筆資料。")
                
        print("\n🎉 所有的 DRAM 與 GPU 報價皆已檢查並同步完畢！")
    else:
        print("❌ 沒有抓取到任何符合格式的報價資料。")

with client:
    client.loop.run_until_complete(main())