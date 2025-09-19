#!/usr/bin/env python3
"""
Надежный запуск Playwright браузера локально с debug портом.
Скрипт будет работать до принудительной остановки (Ctrl+C).
"""

import asyncio
import os
from playwright.async_api import async_playwright

async def main():
    playwright = await async_playwright().start()
    context = None
    
    try:
        user_data_dir = os.path.join(os.getcwd(), "debug_browser_profile")
        print(f"🚀 Запускаем браузер с профилем: {user_data_dir}")
        
        # Запускаем браузер с debug портом
        browser = await playwright.chromium.launch(
            headless=False,
            args=[
                "--remote-debugging-port=9222",
                "--remote-debugging-address=0.0.0.0",
            ],
        )
        
        # Создаем новый контекст
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
        )
        
        # Создаем страницу
        page = await context.new_page()
        await page.goto("https://www.google.com")
        
        # Закрываем все страницы, которые могли восстановиться из профиля
        print("🧹 Закрываем все старые страницы...")
        # context.pages возвращает копию, поэтому итерируемся так
        for page in list(context.pages):
            await page.close()

        # Создаем НОВУЮ страницу, чтобы быть уверенными, что управляем ей
        print("📄 Создаем новую страницу...")
        page = await context.new_page()
        
        print("🌐 Открываем сайт Playwright...")
        # Даем команду перейти на сайт
        await page.goto("https://playwright.dev")
        
        # Явно выводим новую страницу на передний план
        await page.bring_to_front()
        
        print("✅ Браузер запущен и готов к подключению.")
        print("🔧 Откройте в другом браузере chrome://inspect")
        print("   и найдите цель для подключения.")
        print("\n⏳ Скрипт работает... Нажмите Ctrl+C в этом терминале для остановки.")
        
        # Бесконечный цикл, который держит скрипт живым
        await asyncio.Event().wait()

    except KeyboardInterrupt:
        print("\nПолучен сигнал Ctrl+C. Завершаем работу...")
    except Exception as e:
        print(f"\n❌ Произошла критическая ошибка: {e}")
    finally:
        if context:
            await context.close()
        if 'browser' in locals():
            await browser.close()
        await playwright.stop()
        print("✅ Браузер и Playwright остановлены.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nПрограмма принудительно завершена.")

