from telethon.sync import TelegramClient
from telethon.sessions import StringSession

# 填入你剛剛取得的資料
api_id = 35016246
api_hash = 'f91ac54a5743e1982affcfb7e8f56ce1'

# 執行這段程式碼，它會在終端機要求你輸入手機號碼，並發送驗證碼給你
with TelegramClient(StringSession(), api_id, api_hash) as client:
    print("登入成功！請將下面這串超長代碼複製起來，這就是你的萬能鑰匙：")
    print("\n")
    print(client.session.save()) 
    print("\n")