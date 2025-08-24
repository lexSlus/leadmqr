import asyncio
import json
import os
from playwright_bot.workflows import run_single_pass





USER_DATA_DIR = "./playwright_profile"



os.environ["EMAIL"] = "your_email@example.com"
os.environ["PASSWORD"] = "your_password_here"
os.environ["BASE_URL"] = "https://www.thumbtack.com"
os.environ["LEADS_PATH"] = "/leads"

# хранилище профиля/сессии локально
os.environ["USER_DATA_DIR"] = "./.data/tt_profile"
os.environ["STORAGE_STATE"] = "./.data/state.json"

# браузер
os.environ["HEADLESS"] = "False"
os.environ["SLOW_MO"] = "150"

async def main():
    result = await run_single_pass()
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    # гарантируем что папка есть
    os.makedirs("./.data/tt_profile", exist_ok=True)
    asyncio.run(main())