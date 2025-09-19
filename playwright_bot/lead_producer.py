import asyncio
import logging
from playwright.async_api import async_playwright

# Настраиваем логирование, чтобы видеть сообщения
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] playwright_bot: %(message)s')
log = logging.getLogger("playwright_bot")

async def main():
    """
    Запускает Chrome с debug портом через launchServer() и подключается к нему через connectOverCDP.
    Это правильный способ согласно документации Playwright.
    """
    log.warning("!!! ЗАПУЩЕН СКРИПТ С launchServer + connectOverCDP (v5) !!!")
    
    try:
        playwright = await async_playwright().start()
        
        # Запускаем Chrome с debug портом
        log.info("Запускаем Chrome с debug портом...")
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir="/app/pw_profiles/debug-test-new",
            headless=False,  # False для видимости в chrome://inspect
            args=[
                "--remote-debugging-port=9222",
                "--remote-debugging-address=0.0.0.0",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ]
        )
        
        log.info("Chrome запущен с debug портом 9222")
        
        # Создаем несколько страниц для тестирования
        page1 = await context.new_page()
        await page1.goto("https://google.com")
        
        page2 = await context.new_page()
        await page2.goto("https://example.com")
        
        page3 = await context.new_page()
        await page3.goto("about:blank")
        
        log.warning("!!! БРАУЗЕР ЗАПУЩЕН И ЖДЕТ. ПРОВЕРЯЙТЕ localhost:9222 или chrome://inspect !!!")
        log.info(f"Открыто {len(context.pages)} страниц")
        
        # Бесконечный цикл, чтобы контейнер не завершался
        while True:
            await asyncio.sleep(60)
            log.info("... browser is still running ...")
            
    except Exception as e:
        log.error(f"Критическая ошибка в тестовом скрипте: {e}", exc_info=True)
        # Ждем, чтобы успеть прочитать лог
        await asyncio.sleep(300)

if __name__ == "__main__":
    asyncio.run(main())
