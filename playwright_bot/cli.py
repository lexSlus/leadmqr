import asyncio
import json
import os
from pathlib import Path

from playwright.async_api import async_playwright

from playwright_bot.workflows import run_single_pass





# async def main():
#     async with async_playwright() as pw:
#         context = await pw.chromium.launch_persistent_context(
#             user_data_dir=SETTINGS.user_data_dir,  # папка для хранения куков/сессии
#             headless=False,
#             viewport=None,
#             args=getattr(SETTINGS, "chromium_args", ["--no-sandbox"]),
#             slow_mo=getattr(SETTINGS, "slow_mo", 0)
#         )
#
#         # Берём первую открытую вкладку или создаём новую
#         page = context.pages[0] if context.pages else await context.new_page()
#
#         await page.goto(f"{SETTINGS.base_url}/login", wait_until="domcontentloaded")
#         print("Войди вручную и реши капчу (у тебя 2 минуты)...")
#         await page.wait_for_timeout(120_000)  # 2 минуты на логин
#
#         # Закрывать контекст можно, но не обязательно — всё сохранится в user_data_dir
#         await context.close()

USER_DATA_DIR = "./playwright_profile"


# async def main():
#     Path(USER_DATA_DIR).mkdir(parents=True, exist_ok=True)
#     async with async_playwright() as p:
#         ctx = await p.chromium.launch_persistent_context(
#             user_data_dir=USER_DATA_DIR,
#             headless=False,
#             args=[
#                 "--disable-blink-features=AutomationControlled",
#                 "--start-maximized",
#             ],
#             viewport=None,
#         )
#         page = await ctx.new_page()
#         await page.goto("https://www.thumbtack.com/", wait_until="load")
#         print("\n>>> В открывшемся окне залогинься и пройди капчу.")
#         input(">>> Когда всё готово, нажми Enter здесь...")
#         await ctx.storage_state(path=os.path.join(USER_DATA_DIR, "storage_state.json"))
#         print(f">>> Профиль сохранён в: {USER_DATA_DIR}")
#         await ctx.close()

# async def main():
#         result =  await run_single_pass(headless=False)
#         print(f"[BOT RESULT] {result}")
#         return result


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