# browser_pool.py
import asyncio
import logging
from typing import Tuple
from playwright.async_api import async_playwright, Playwright, Browser, BrowserContext, Page

logger = logging.getLogger(__name__)

class BrowserPool:
    """
    Управляет пулом "вечных" процессов Playwright.
    Использует asyncio.Queue для управления предзагруженными контекстами.
    Задачи автоматически ждут в очереди, если все контексты заняты.
    """
    def __init__(self, num_browsers: int = 1, num_contexts: int = 5):
        """
        Args:
            num_browsers: Количество браузеров (обычно 1)
            num_contexts: Количество предзагруженных контекстов (жесткое ограничение на параллелизм)
        """
        self.num_browsers = num_browsers
        self.num_contexts = num_contexts
        self.playwright: Playwright | None = None
        self.browsers: list[Browser] = []
        
        # Очередь предзагруженных контекстов
        # asyncio.Queue автоматически заставляет задачи ждать, если очередь пуста
        self._preloaded_contexts_queue: asyncio.Queue[Tuple[BrowserContext, Page, Browser]] = asyncio.Queue(
            maxsize=self.num_contexts
        )

    async def start(self):
        """Запускает браузер(ы) и заполняет очередь предзагруженными контекстами."""
        try:
            self.playwright = await async_playwright().start()
            logger.info(f"Запуск {self.num_browsers} браузер(ов) в пуле...")
            
            for _ in range(self.num_browsers):
                browser = await self.playwright.chromium.launch(
                    headless=False  # Запускаем в видимом режиме (xvfb-run в Dockerfile)
                )
                self.browsers.append(browser)
            
            logger.info(f"Пул из {len(self.browsers)} браузер(ов) успешно запущен.")
            
            # Предзагружаем контексты для ускорения и видимости в VNC
            # Распределяем контексты равномерно по браузерам
            await self._preload_all_contexts()
        except Exception as e:
            logger.error(f"Критическая ошибка: не удалось запустить пул браузеров: {e}", exc_info=True)
            raise
    
    async def _preload_all_contexts(self):
        """Создает предзагруженные контексты, распределяя их равномерно по всем браузерам."""
        if not self.browsers:
            logger.error("Нет браузеров для создания контекстов")
            return
        
        # Распределяем контексты равномерно по браузерам
        contexts_per_browser = self.num_contexts // len(self.browsers)
        extra_contexts = self.num_contexts % len(self.browsers)
        
        logger.info(f"Создание {self.num_contexts} предзагруженных контекстов на {len(self.browsers)} браузере(ах)...")
        logger.info(f"Распределение: {contexts_per_browser} контекстов на браузер (+ {extra_contexts} дополнительных)")
        
        context_index = 0
        for browser_idx, browser in enumerate(self.browsers):
            # Первые extra_contexts браузеров получают на 1 контекст больше
            contexts_for_this_browser = contexts_per_browser + (1 if browser_idx < extra_contexts else 0)
            
            for i in range(contexts_for_this_browser):
                context_index += 1
                try:
                    context_options = {"locale": "en-US"}
                    context = await browser.new_context(**context_options)
                    page = await context.new_page()
                    # Открываем пустую страницу, чтобы браузер был виден в VNC
                    await page.goto("about:blank", wait_until="domcontentloaded", timeout=5000)
                    
                    # Кладем "горячий" контекст в очередь
                    await self._preloaded_contexts_queue.put((context, page, browser))
                    logger.info(f"Предзагруженный контекст #{context_index}/{self.num_contexts} создан на браузере #{browser_idx+1}")
                except Exception as e:
                    logger.warning(f"Не удалось предзагрузить контекст #{context_index} на браузере #{browser_idx+1}: {e}")
        
        queue_size = self._preloaded_contexts_queue.qsize()
        logger.info(f"Создано {queue_size}/{self.num_contexts} предзагруженных контекстов на {len(self.browsers)} браузере(ах)")
    
    async def get_preloaded_context(self) -> Tuple[BrowserContext, Page, Browser]:
        """
        Атомарно берет контекст из пула.
        
        ВОТ ВСЯ МАГИЯ:
        - Если очередь не пуста → сразу возвращает контекст
        - Если очередь пуста (все контексты заняты) → автоматически "засыпает" (await)
        - Проснется, когда release_preloaded_context вернет контекст в очередь
        
        Это решает проблему "Тасманского дьявола" (Stampede):
        Задачи 5-50 будут ждать в очереди, а не создавать 46 контекстов одновременно.
        """
        import time
        queue_size_before = self._preloaded_contexts_queue.qsize()
        wait_start = time.time()
        logger.info(f"[BrowserPool] Ожидание доступного контекста... (в очереди: {queue_size_before}/{self.num_contexts})")
        
        # Эта строка - вся магия. Она атомарно ждет и берет.
        # Задачи 5-50 "заснут" здесь и выстроятся в очередь.
        context, page, browser = await self._preloaded_contexts_queue.get()
        
        wait_duration = time.time() - wait_start
        queue_size_after = self._preloaded_contexts_queue.qsize()
        if wait_duration > 0.1:
            logger.warning(f"[BrowserPool] ⚠️ Контекст получен после ожидания {wait_duration:.3f} сек! (в очереди было: {queue_size_before}, осталось: {queue_size_after})")
        else:
            logger.info(f"[BrowserPool] Контекст получен (в очереди осталось: {queue_size_after}/{self.num_contexts}, ожидание: {wait_duration:.3f} сек)")
        return (context, page, browser)

    async def release_preloaded_context(self, context: BrowserContext, page: Page, browser: Browser):
        """
        Очищает и возвращает контекст в пул.
        
        Когда контекст возвращается в очередь, одна из "спящих" задач автоматически проснется.
        """
        try:
            queue_size_before = self._preloaded_contexts_queue.qsize()
            logger.info(f"[BrowserPool] 🔄 Начало возврата контекста в пул (в очереди: {queue_size_before}/{self.num_contexts})")
            
            # Очищаем cookies и возвращаем в чистое состояние
            await context.clear_cookies()
            logger.debug(f"[BrowserPool] Cookies очищены")
            
            await page.goto("about:blank", wait_until="domcontentloaded", timeout=5000)
            logger.debug(f"[BrowserPool] Страница переведена на about:blank")
            
            # Возвращаем "очищенный" контекст обратно в очередь
            # Это разбудит одну из "спящих" задач
            await self._preloaded_contexts_queue.put((context, page, browser))
            queue_size_after = self._preloaded_contexts_queue.qsize()
            logger.info(f"[BrowserPool] ✅ Контекст возвращен в пул (в очереди: {queue_size_after}/{self.num_contexts}, было: {queue_size_before})")
        except Exception as e:
            # Если контекст "сломался" (например, браузер закрыт),
            # создаем новый контекст на замену, чтобы пул не "иссяк"
            logger.warning(f"Ошибка при возврате контекста в пул: {e}. Создаем новый на замену.")
            try:
                # Используем тот же браузер или первый доступный
                target_browser = browser if browser in self.browsers else self.browsers[0]
                context_options = {"locale": "en-US"}
                new_context = await target_browser.new_context(**context_options)
                new_page = await new_context.new_page()
                await new_page.goto("about:blank", wait_until="domcontentloaded", timeout=5000)
                await self._preloaded_contexts_queue.put((new_context, new_page, target_browser))
                logger.info("Создан новый контекст на замену сломанного.")
            except Exception as e2:
                logger.error(f"Критическая ошибка: не удалось восполнить пул: {e2}")

    async def stop(self):
        """Закрывает все браузеры и предзагруженные контексты."""
        logger.info("Остановка пула браузеров...")
        
        # Очищаем очередь, закрывая все контексты
        while not self._preloaded_contexts_queue.empty():
            try:
                context, page, _ = await self._preloaded_contexts_queue.get_nowait()
                if context:
                    await context.close()
            except asyncio.QueueEmpty:
                break
            except Exception as e:
                logger.warning(f"Ошибка при закрытии контекста: {e}")
        
        for browser in self.browsers:
            try:
                await browser.close()
            except Exception as e:
                logger.warning(f"Ошибка при закрытии браузера: {e}")
        
        if self.playwright:
            await self.playwright.stop()
        logger.info("Пул браузеров остановлен.")

    async def get_browser(self) -> Browser:
        """
        Выдает браузер из пула (для обратной совместимости).
        Используется только если нужен браузер вне очереди (не рекомендуется).
        """
        if not self.browsers:
            raise RuntimeError("Пул браузеров не инициализирован.")
        return self.browsers[0]  # Возвращаем первый браузер
