import os
import re
import subprocess  # 用來讓 Python 執行終端機指令 (Git)
import pandas as pd
import yfinance as yf  # 💡 新增：用來抓取股票與 ETF 報價的套件
from telethon import TelegramClient
from telethon.sessions import StringSession
from datetime import timezone, timedelta

# 1. 讀取登入鑰匙 (因為要在本機跑，請確保這裡填寫的是真實資料)
api_id = int(os.environ.get('TG_API_ID', '35016246')) # 如果在自己電腦測試，把 123456 換成你的 ID
api_hash = os.environ.get('TG_API_HASH', 'f91ac54a5743e1982affcfb7e8f56ce1')
session_string = os.environ.get('TG_SESSION', '1BVtsOKwBu7Q8Xef_fsg5IQb4_X94vuinMQPON16I_YtO-Ju91KeVwZyOYgntZ3TWPI0CJU39XhP5lmmzXLOXH1aLxL09Z2JZBt3hf7yqnFM2GLXpV_sYCbMQUSUjLkUzhHiYlEt7nliKJ5JizA3KH2YqmfKGxO-0S3qkbJ813VlDACvksj6YVfkz1Vtn2fZx6McTIzzan1Mwohk_jLhuO_zxRjO_3I7HSeQjZ_wyCPIh8nnK-mnY6_kJoESmsKmLpW2HURMl6gkPNrULW55uoER_VASDbwUzQ3JoQRyPBe1ozJPn4AfB2SGxC0yJOrC03votSvsbTblPXOMkeyBw94YAHni_HmM=')


client = TelegramClient(StringSession(session_string), api_id, api_hash)

async def main():
    target_chat = '@k2ai_dev_bot'
    save_folder = r"C:\Users\User\OneDrive\文件\VS_Python\DRAM每日報價收集_程式\報價資料夾"
    os.makedirs(save_folder, exist_ok=True)
    
    print(f"開始連接 Telegram 並搜尋 {target_chat} 的訊息...")
    
    all_parsed_data = []
    
    # ==========================================
    # 區塊 A：抓取 Telegram 報價
    # ==========================================
    async for message in client.iter_messages(target_chat, limit=200):
        if not message.text:
            continue
            
        tw_time = message.date.astimezone(timezone(timedelta(hours=8)))
        current_date = tw_time.strftime('%Y-%m-%d')
        
        lines = message.text.strip().split('\n')
        
        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue
                
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', line_str)
            if date_match and ("价格" in line_str or "数据" in line_str or "|" in line_str):
                current_date = date_match.group(1)
                continue
                
            match = re.search(r'^(.*?)\s+(\d+\.\d+)\s+(\S+)\s+(\S+)$', line_str)
            if match:
                item_name = match.group(1).strip()
                
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

    # ==========================================
    # 區塊 B：透過 Yahoo Finance 抓取股市報價 (💡 本次修改：回溯歷史資料)
    # ==========================================
    print("\n📈 開始透過 Yahoo Finance 抓取股市歷史報價...")
    
    stock_targets = {
        'NVDA': 'NVDA',
        'DRAM_ETF': 'DRAM'  # 提醒：美股目前沒有代號為 DRAM 的 ETF，這裡先幫你用半導體 ETF(SMH) 替代，如有特定代號可自行修改
    }
    
    for item_name, ticker_symbol in stock_targets.items():
        try:
            ticker = yf.Ticker(ticker_symbol)
            # 💡 修改點：直接指定從 2026-07-01 開始抓取到今天的所有歷史資料
            hist = ticker.history(start="2026-07-01")
            
            if not hist.empty:
                # 💡 修改點：用迴圈把這段期間的「每一天」都讀出來並加入清單
                for i in range(len(hist)):
                    current_date = hist.index[i].strftime('%Y-%m-%d')
                    current_price = round(hist['Close'].iloc[i], 2)
                    
                    # 計算日漲跌，模擬 Telegram 的格式
                    if i > 0:
                        prev_price = hist['Close'].iloc[i-1]
                        day_val = current_price - prev_price
                        day_pct = (day_val / prev_price) * 100
                        sign = "▲" if day_val > 0 else ("▼" if day_val < 0 else "·")
                        day_str = f"{sign}{abs(day_val):.2f}({day_pct:+.2f}%)"
                    else:
                        day_str = "-" # 迴圈的第一天因為沒有前一天可比較，先填入橫槓

                    all_parsed_data.append({
                        'Item': item_name,
                        'Date': current_date,
                        'Price': current_price,
                        'Day': day_str,
                        '30D': '-'  
                    })
                print(f"  ✔️ 成功獲取 {item_name} 歷史報價 (自 2026-07-01 起，共 {len(hist)} 筆交易日)")
        except Exception as e:
            print(f"  ❌ 抓取 {item_name} 失敗: {e}")

    # ==========================================
    # 區塊 C：進入智慧存檔與比對階段
    # ==========================================
    has_updated_files = False  
    
    if all_parsed_data:
        df_scraped = pd.DataFrame(all_parsed_data)
        log_summary = {}

        for item_name, group_data in df_scraped.groupby('Item'):
            safe_filename = item_name.replace("/", "_").replace("\\", "_")
            csv_path = os.path.join(save_folder, f"{safe_filename}.csv")
            
            group_data = group_data[['Date', 'Price', 'Day', '30D']].copy()
            group_data['Date'] = group_data['Date'].astype(str).str.strip()
            group_data['Price'] = group_data['Price'].astype(float)
            
            group_data = group_data.drop_duplicates(subset=['Date'], keep='first')
            
            log_summary[item_name] = {'new': [], 'updated': []}

            if os.path.exists(csv_path):
                df_exist = pd.read_csv(csv_path)
                df_exist['Date'] = df_exist['Date'].astype(str).str.strip()
                df_exist['Price'] = df_exist['Price'].astype(float)
                
                existing_dates = set(df_exist['Date'])
                
                new_dates_df = group_data[~group_data['Date'].isin(existing_dates)]
                new_dates = set(new_dates_df['Date'])
                if new_dates:
                    log_summary[item_name]['new'] = sorted(list(new_dates))
                
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

                affected_dates = sorted(list(new_dates | changed_dates))
                
                if affected_dates:
                    has_updated_files = True  
                    df_exist_keep = df_exist[~df_exist['Date'].isin(changed_dates)]
                    df_to_add = group_data[group_data['Date'].isin(affected_dates)]
                    
                    df_combined = pd.concat([df_exist_keep, df_to_add], ignore_index=True)
                    df_combined = df_combined.sort_values(by='Date').reset_index(drop=True)
                    df_combined.to_csv(csv_path, index=False, encoding='utf-8-sig')
            else:
                has_updated_files = True  
                group_data = group_data.sort_values(by='Date').reset_index(drop=True)
                group_data.to_csv(csv_path, index=False, encoding='utf-8-sig')
                log_summary[item_name]['new'] = sorted(list(group_data['Date']))
                
        # === 顯示最終動作日誌 ===
        print("\n" + "="*50)
        print("📊 本次執行動作日誌 (Action Log)")
        print("="*50)
        
        has_changes_print = False
        for item, actions in log_summary.items():
            new_list = actions['new']
            updated_list = actions['updated']
            
            if new_list or updated_list:
                has_changes_print = True
                print(f"📌 [{item}]")
                if new_list:
                    print(f"   ➕ 補齊/新增缺漏 ({len(new_list)} 筆): {', '.join(new_list)}")
                if updated_list:
                    print(f"   🔄 更新修正價格 ({len(updated_list)} 筆): {', '.join(updated_list)}")
                    
        if not has_changes_print:
            print("⚡ 本次掃描完畢，沒有發現任何缺漏或價格變動。")
            print("⚡ 所有的 CSV 檔案皆為最新狀態。")
        print("="*50 + "\n")

        # === 💡 自動上傳 GitHub 的核心區塊 ===
        if has_updated_files:
            print("🚀 檢測到 CSV 資料有更新，準備自動同步至 GitHub...")
            try:
                project_dir = r"C:\Users\User\OneDrive\文件\VS_Python\DRAM每日報價收集_程式"
                os.chdir(project_dir)

                subprocess.run(["git", "add", "."], check=True)
                subprocess.run(["git", "commit", "-m", "自動更新報價 (含NVDA與ETF歷史補齊)"], check=True)
                subprocess.run(["git", "push"], check=True)
                print("🎉 成功同步上傳至 GitHub！網頁資料將在 1~2 分鐘後更新。")
            except subprocess.CalledProcessError as e:
                print(f"❌ Git 執行失敗！錯誤代碼: {e}")
            except Exception as e:
                print(f"❌ 上傳發生未知錯誤: {e}")
        else:
            print("⚡ 沒有檔案變動，略過上傳 GitHub。")

    else:
        print("❌ 沒有抓取到任何符合格式的報價資料。")

with client:
    client.loop.run_until_complete(main())