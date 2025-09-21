import asyncio
import json
import os
from playwright_bot.workflows import run_single_pass





USER_DATA_DIR = "./playwright_profile"



# Правильные переменные окружения с префиксом TT_
os.environ["TT_EMAIL"] = "wkononov@gmail.com"
os.environ["TT_PASSWORD"] = "Oleg@2025"
os.environ["TT_BASE"] = "https://www.thumbtack.com"
os.environ["TT_LEADS_PATH"] = "/leads"

# хранилище профиля/сессии локально
os.environ["TT_USER_DATA_DIR"] = "./.data/tt_profile"
os.environ["TT_STORAGE_STATE"] = "./.data/state.json"

# браузер
os.environ["TT_HEADLESS"] = "False"
os.environ["TT_SLOW_MO"] = "150"

async def main():
    result = await run_single_pass()
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    # гарантируем что папка есть
    os.makedirs("./.data/tt_profile", exist_ok=True)
    asyncio.run(main())