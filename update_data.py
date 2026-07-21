import os
import re
import pandas as pd
from telethon import TelegramClient
from telethon.sessions import StringSession
from datetime import timezone, timedelta

# 1. 從環境變數讀取登入鑰匙 (GitHub Actions 會從 Secrets 自動帶入)
api_id_env = os.environ.get('TG_API_ID')
api_id = int(api_id_env) if api_id_env else 1111111  # 預設為數字，避免轉型失敗
api_hash = os.environ.get('TG_API_HASH', '')
session_string = os.environ.get('TG_SESSION', '')

# 建立 Telegram 客戶端
client = TelegramClient(StringSession(session_string), api_id, api_hash)

async def main():
    target_chat = '@k2ai_dev_bot'
    save_folder = "./報價資料夾"
    os.makedirs(save_folder, exist_ok=True)
    
    print(f"開始連接 Telegram 並搜尋 {target_chat} 的訊息...")
    
    all_parsed_data = []
    
    async for message in client.iter_messages(target_chat, limit=200):
        if not message.text:
            continue
            
        # 先以 Telegram 訊息的發送時間 (台灣時間) 作為預設日期
        tw_time = message.date.astimezone(timezone(timedelta(hours=8)))
        current_date = tw_time.strftime('%Y-%m-%d')
        
        lines = message.text.strip().split('\n')
        
        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue
                
            # 💡 檢查該行是否包含日期切換 (例如 "GPU 租赁价格 | 2026-07-16" 或是 "最新数据 2026-07-17")
            # 只要看到明確日期，就將 current_date 更新，這樣同則訊息裡的不同日期也能準確分配
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', line_str)
            if date_match and ("价格" in line_str or "数据" in line_str or "|" in line_str):
                current_date = date_match.group(1)
                continue
                
            # 💡 使用正則表達式解析商品行： (商品名稱) (價格) (日漲跌) (月漲跌)
            # (.*?) 會自動包容包含空白的產品名，如 "D4 16G 3200"
            # (\d+\.\d+) 抓取如 "80.20" 的價格
            # \s+(\S+)\s+(\S+)$ 抓取後面的漲幅文字，即使是 "-" 也能完美抓取
            match = re.search(r'^(.*?)\s+(\d+\.\d+)\s+(\S+)\s+(\S+)$', line_str)
            if match:
                item_name = match.group(1).strip()
                
                # 排除標題列 (Item, GPU, Price 等)
                if item_name in ['GPU', 'Item'] or "Price" in line_str or "$/h" in line_str:
                    continue
                    
                price = float(match.group(2))
                day_change = match.group(3)
                month_change = match.group(4)
                
                all_parsed_data.append({
                    'Item': item_name,
                    'Date': current_date,
                    'Price': price,
                    'Day': day_change,
                    '30D': month_change
                })

    # --- 進入智慧存檔與比對階段 ---
    if all_parsed_data:
        df_scraped = pd.DataFrame(all_parsed_data)
        
        # 準備日誌字典：分類紀錄「新增日期」與「更新價格」
        log_summary = {}

        for item_name, group_data in df_scraped.groupby('Item'):
            safe_filename = item_name.replace("/", "_").replace("\\", "_")
            csv_path = os.path.join(save_folder, f"{safe_filename}.csv")
            
            group_data = group_data[['Date', 'Price', 'Day', '30D']].copy()
            group_data['Date'] = group_data['Date'].astype(str).str.strip()
            group_data['Price'] = group_data['Price'].astype(float)
            
            # 訊息是從最新抓到舊，保留該日期最新的那一筆報價
            group_data = group_data.drop_duplicates(subset=['Date'], keep='first')
            
            log_summary[item_name] = {'new': [], 'updated': []}

            if os.path.exists(csv_path):
                df_exist = pd.read_csv(csv_path)
                df_exist['Date'] = df_exist['Date'].astype(str).str.strip()
                df_exist['Price'] = df_exist['Price'].astype(float)
                
                existing_dates = set(df_exist['Date'])
                
                # 狀況 1：找出 CSV 中完全沒有的新日期
                new_dates_df = group_data[~group_data['Date'].isin(existing_dates)]
                new_dates = set(new_dates_df['Date'])
                if new_dates:
                    log_summary[item_name]['new'] = sorted(list(new_dates))
                
                # 狀況 2：日期已存在，但價格與舊檔案不同 (價格修正)
                changed_dates = set()
                common_df = group_data[group_data['Date'].isin(existing_dates)]
                for _, row in common_df.iterrows():
                    d = row['Date']
                    new_p = row['Price']
                    old_p = df_exist.loc[df_exist['Date'] == d, 'Price'].iloc[0]
                    if new_p != old_p:
                        changed_dates.add(d)
                
                if changed_dates:
                    log_summary[item_name]['updated'] = sorted(list(changed_dates))

                # 將需要「新增」跟「更新」的日期合併
                affected_dates = sorted(list(new_dates | changed_dates))
                
                if affected_dates:
                    # 剔除掉舊檔案中需要被覆蓋掉的資料
                    df_exist_keep = df_exist[~df_exist['Date'].isin(changed_dates)]
                    # 取出本次要寫入的資料
                    df_to_add = group_data[group_data['Date'].isin(affected_dates)]
                    
                    df_combined = pd.concat([df_exist_keep, df_to_add], ignore_index=True)
                    df_combined = df_combined.sort_values(by='Date').reset_index(drop=True)
                    df_combined.to_csv(csv_path, index=False, encoding='utf-8-sig')
            else:
                # 檔案完全不存在：全部當作新建立
                group_data = group_data.sort_values(by='Date').reset_index(drop=True)
                group_data.to_csv(csv_path, index=False, encoding='utf-8-sig')
                log_summary[item_name]['new'] = sorted(list(group_data['Date']))
                
        # === 顯示最終動作日誌 ===
        print("\n" + "="*50)
        print("📊 本次執行動作日誌 (Action Log)")
        print("="*50)
        
        has_changes = False
        for item, actions in log_summary.items():
            new_list = actions['new']
            updated_list = actions['updated']
            
            if new_list or updated_list:
                has_changes = True
                print(f"📌 [{item}]")
                if new_list:
                    print(f"   ➕ 補齊/新增缺漏 ({len(new_list)} 筆): {', '.join(new_list)}")
                if updated_list:
                    print(f"   🔄 更新修正價格 ({len(updated_list)} 筆): {', '.join(updated_list)}")
                    
        if not has_changes:
            print("⚡ 本次掃描完畢，沒有發現任何缺漏或價格變動。")
            print("⚡ 所有的 CSV 檔案皆為最新狀態。")
        print("="*50 + "\n")
        
    else:
        print("❌ 沒有抓取到任何符合格式的報價資料。")

with client:
    client.loop.run_until_complete(main())