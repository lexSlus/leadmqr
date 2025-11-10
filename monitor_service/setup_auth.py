#!/usr/bin/env python3
"""
Скрипт для ручной настройки авторизации в Thumbtack.
Позволяет пройти капчу и сохранить сессию для автоматического использования.
Сохраняет сессию в формате, совместимом с monitor_service.
"""

import os
import sys
import asyncio
import logging
import json
from playwright.async_api import async_playwright

# Добавляем путь к модулям
sys.path.insert(0, os.path.dirname(__file__))

# Используем CONFIG только для папки сессий
try:
    from monitor_service.config import CONFIG
except ImportError:
    # Если запускается локально без установленного пакета
    import os
    class CONFIG:
        sessions_dir = os.getenv("MONITOR_SESSIONS_DIR", "sessions")

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AuthSetup:
    def __init__(self, email: str, password: str, account_id: str = None, headless: bool = False):
        self.email = email
        self.password = password
        self.account_id = account_id or email.split("@")[0]  # Используем часть email до @ как account_id
        self.headless = headless
        self.pw = None
        self.browser = None
        self.context = None
        self.page = None
    
    async def start(self):
        """Запуск браузера для ручной авторизации"""
        logger.info("🚀 Запуск браузера для ручной авторизации...")
        
        self.pw = await async_playwright().start()
        
        # Используем headless=False для ручной настройки
        self.browser = await self.pw.chromium.launch(
            headless=self.headless,
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
            ]
        )
        
        # Создаем контекст без сохранения (будем сохранять вручную)
        self.context = await self.browser.new_context(
            locale="en-US",
            viewport={"width": 1920, "height": 1080}
        )
        
        self.page = await self.context.new_page()
        
        logger.info("✅ Браузер запущен")
        
    async def setup_auth(self):
        """Процесс ручной авторизации"""
        logger.info("🔐 Начинаем процесс авторизации...")
        logger.info(f"📧 Email: {self.email}")
        logger.info(f"🆔 Account ID: {self.account_id}")
        
        try:
            # Переходим на страницу логина
            logger.info("📱 Переходим на Thumbtack...")
            await self.page.goto("https://www.thumbtack.com/pro-leads", wait_until="domcontentloaded")
            
            # Проверяем, нужно ли логиниться
            current_url = self.page.url
            logger.info(f"📍 Текущий URL: {current_url}")
            
            if "/login" in current_url or "login" in current_url.lower():
                logger.info("🔑 Нужна авторизация, переходим на страницу логина...")
                await self.page.goto("https://www.thumbtack.com/login", wait_until="domcontentloaded")
            else:
                logger.info("✅ Уже авторизованы или на главной странице")
                
            # Ждем, пока пользователь введет логин, пароль и решит капчу
            logger.info("📝 Введите логин и пароль вручную в браузере")
            logger.info(f"   Email: {self.email}")
            logger.info("   Пароль: (введите в браузере)")
            logger.info("⏳ Даю 45 секунд на решение капчи...")
            
            # Ждем 45 секунд для решения капчи
            await asyncio.sleep(45)
            
            logger.info("🎯 После успешного входа нажмите Enter в консоли...")
            
            # Ждем подтверждения от пользователя
            try:
                input("Нажмите Enter когда авторизация будет завершена...")
            except EOFError:
                # Если input() не работает (например, в Docker), ждем еще немного
                logger.info("⏰ Ждем еще 10 секунд...")
                await asyncio.sleep(10)
            
            # Автоматически ждем загрузки контента после авторизации
            logger.info("⏳ Автоматически ждем загрузки контента страницы...")
            
            # Ждем изменения URL (успешный логин)
            logger.info("🔄 Ждем изменения URL после логина...")
            try:
                await self.page.wait_for_function(
                    "() => !window.location.href.includes('/login')",
                    timeout=30000
                )
                logger.info("✅ URL изменился, логин прошел успешно")
            except:
                logger.warning("⚠️ URL не изменился, возможно остались на login")
            
            # Ждем загрузки страницы
            try:
                await self.page.wait_for_load_state("networkidle", timeout=20000)
                logger.info("✅ Сетевая активность завершена")
                await asyncio.sleep(3)
            except Exception as e:
                logger.warning(f"⚠️ Таймаут загрузки: {e}")
                await asyncio.sleep(5)
            
            # Переходим на страницу лидов для проверки
            logger.info("🔄 Переходим на страницу лидов для проверки...")
            try:
                await self.page.goto("https://www.thumbtack.com/pro-leads", wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(3)
            except Exception as e:
                logger.warning(f"⚠️ Не удалось перейти на /pro-leads: {e}")
            
            # Проверяем, что авторизация прошла успешно
            current_url = self.page.url
            logger.info(f"📍 URL после авторизации: {current_url}")
            
            if "/login" not in current_url:
                logger.info("✅ Авторизация успешна!")
                
                # Сохраняем состояние авторизации
                session_file = await self.save_auth_state()
                
                logger.info(f"💾 Состояние авторизации сохранено в {session_file}")
                logger.info("🔄 Теперь monitor_service сможет использовать эту сессию")
                
            else:
                logger.warning("⚠️ Возможно, авторизация не завершена. Проверьте URL.")
                logger.warning("⚠️ Сессия все равно будет сохранена, но может не работать")
                # Сохраняем сессию даже если не уверены в успехе
                session_file = await self.save_auth_state()
                
        except Exception as e:
            logger.error(f"❌ Ошибка при авторизации: {e}", exc_info=True)
            raise
            
    async def save_auth_state(self) -> str:
        """Сохранение состояния авторизации в формате storage_state"""
        try:
            # Получаем storage_state (cookies, localStorage, sessionStorage)
            storage_state = await self.context.storage_state()
            
            # Используем ту же папку, что и monitor_service (для совместимости)
            sessions_dir = CONFIG.sessions_dir
            os.makedirs(sessions_dir, exist_ok=True)
            
            # Формат: session_{account_id}.json (такой же как в monitor_service и browser_service)
            session_file = os.path.join(sessions_dir, f"session_{self.account_id}.json")
            
            logger.info(f"💾 Сохраняем состояние авторизации в {session_file}...")
            
            # Сохраняем storage_state
            with open(session_file, 'w') as f:
                json.dump(storage_state, f, indent=2)
            
            logger.info(f"✅ Состояние авторизации сохранено: {session_file}")
            logger.info(f"   Cookies: {len(storage_state.get('cookies', []))} записей")
            logger.info(f"   Origins: {len(storage_state.get('origins', []))} записей")
            
            return session_file
            
        except Exception as e:
            logger.error(f"❌ Ошибка при сохранении состояния: {e}", exc_info=True)
            raise
            
    async def close(self):
        """Закрытие браузера"""
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.pw:
                await self.pw.stop()
            logger.info("🔒 Браузер закрыт")
        except Exception as e:
            logger.error(f"❌ Ошибка при закрытии браузера: {e}")


async def main():
    """Основная функция"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Ручная настройка авторизации в Thumbtack для monitor_service',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  # Базовый запуск (email и password обязательны)
  python setup_auth.py --email user@example.com --password mypassword
  
  # С указанием account_id (по умолчанию используется часть email до @)
  python setup_auth.py --email user@example.com --password mypassword --account-id my_account
  
  # Запуск в headless режиме (не рекомендуется для ручной настройки)
  python setup_auth.py --email user@example.com --password mypassword --headless
        """
    )
    parser.add_argument('--email', type=str, required=True,
                       help='Email аккаунта Thumbtack')
    parser.add_argument('--password', type=str, required=True,
                       help='Пароль аккаунта Thumbtack')
    parser.add_argument('--account-id', type=str,
                       help='ID аккаунта для имени файла сессии (по умолчанию: часть email до @)')
    parser.add_argument('--headless', action='store_true',
                       help='Запуск в headless режиме (не рекомендуется для ручной настройки)')
    args = parser.parse_args()
    
    # По умолчанию headless=False (оконный режим) для ручной настройки
    auth_setup = AuthSetup(
        email=args.email,
        password=args.password,
        account_id=args.account_id,
        headless=args.headless
    )
    
    try:
        
        # Запускаем браузер
        await auth_setup.start()
        
        # Процесс авторизации
        await auth_setup.setup_auth()
        
        logger.info("🎉 Настройка авторизации завершена!")
        logger.info(f"🚀 Теперь monitor_service сможет использовать сессию для аккаунта {auth_setup.account_id}")
        logger.info(f"📁 Файл сессии: {os.path.join(CONFIG.sessions_dir, f'session_{auth_setup.account_id}.json')}")
        
    except KeyboardInterrupt:
        logger.info("⏹️ Прервано пользователем")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}", exc_info=True)
        sys.exit(1)
    finally:
        await auth_setup.close()


if __name__ == "__main__":
    asyncio.run(main())

