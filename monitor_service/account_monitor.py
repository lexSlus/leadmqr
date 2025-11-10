# account_monitor.py
"""
Монитор для одного аккаунта Thumbtack.
Отслеживает новые лиды и отправляет их в RabbitMQ.
"""
import asyncio
import hashlib
import json
import logging
import os
import time
from typing import Optional, Dict, Any, List, Set
from playwright.async_api import Browser, BrowserContext, Page

from monitor_service.config import CONFIG
from monitor_service.database.schemas import Account

from playwright_bot.thumbtack_bot import ThumbTackBot

logger = logging.getLogger(__name__)


class AccountMonitor:
    """
    Монитор одного аккаунта.
    Запускает бесконечный цикл проверки новых лидов.
    """
    
    def __init__(self, account: Account, celery_app, browser_pool, db_client):
        self.account = account
        self.celery_app = celery_app
        self.browser_pool = browser_pool  # Пул браузеров (один браузер для всех)
        self.db_client = db_client  # Клиент БД для дедупликации лидов
        self.stop_event = asyncio.Event()
        
        # Playwright ресурсы
        # НЕ храним playwright и browser - они в browser_pool
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.bot: Optional[ThumbTackBot] = None
        
        # Путь к файлу сессии
        self.session_path = os.path.join(
            CONFIG.sessions_dir,
            f"session_{account.account_id}.json"
        )
        
        logger.info(f"[Monitor {account.account_id}] Инициализирован")
    
    async def start(self):
        """Запускает мониторинг аккаунта."""
        logger.info(f"[Monitor {self.account.account_id}] Запуск мониторинга...")
        
        try:
            # Создаем папку для сессий
            os.makedirs(CONFIG.sessions_dir, exist_ok=True)
            
            # Инициализируем Playwright
            await self._init_browser()
            
            # Запускаем основной цикл мониторинга
            await self._monitoring_loop()
            
        except Exception as e:
            logger.error(f"[Monitor {self.account.account_id}] Критическая ошибка: {e}", exc_info=True)
        finally:
            # Гарантированная очистка
            await self._cleanup()
    
    async def _init_browser(self):
        """Инициализирует контекст (вкладку) из общего браузера."""
        logger.info(f"[Monitor {self.account.account_id}] Инициализация контекста...")
        
        # Берем браузер из пула (один браузер для всех мониторов)
        browser = await self.browser_pool.get_browser()
        
        # Загружаем сессию, если есть
        storage_state = None
        if os.path.exists(self.session_path):
            logger.info(f"[Monitor {self.account.account_id}] Загрузка сессии из {self.session_path}")
            try:
                with open(self.session_path, 'r') as f:
                    storage_state = json.load(f)
            except Exception as e:
                logger.warning(f"[Monitor {self.account.account_id}] Не удалось загрузить сессию: {e}")
        
        # Создаем контекст (вкладку) из общего браузера
        context_options = {
            "locale": "en-US",
            "viewport": {"width": 1920, "height": 1080}
        }
        if storage_state:
            context_options["storage_state"] = storage_state
        
        self.context = await browser.new_context(**context_options)
        # Устанавливаем явный default timeout для всех операций (чтобы избежать 20 сек по умолчанию)
        self.context.set_default_timeout(5000)  # 5 секунд вместо дефолтных 30
        
        # Блокируем ненужные ресурсы для ускорения и добавляем заголовки против кеширования
        async def handle_route(route):
            if route.request.resource_type in ["image", "font", "media"]:
                await route.abort()
            else:
                # Добавляем заголовки против кеширования для API запросов
                headers = route.request.headers
                if "api" in route.request.url or "leads" in route.request.url:
                    headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                    headers["Pragma"] = "no-cache"
                    headers["Expires"] = "0"
                await route.continue_(headers=headers)
        
        # Проверяем авторизацию через API (если есть сохраненная сессия)
        needs_auth = True
        if storage_state:
            logger.info(f"[Monitor {self.account.account_id}] Проверка авторизации через API...")
            try:
                test_response = await self.context.request.get(
                    f"{CONFIG.base_url}/api/pro/new-leads",
                    timeout=2000
                )
                if test_response.status == 200:
                    logger.info(f"[Monitor {self.account.account_id}] Авторизация через API успешна, страница не нужна")
                    needs_auth = False
                elif test_response.status == 401:
                    logger.info(f"[Monitor {self.account.account_id}] API вернул 401, нужна авторизация")
                    needs_auth = True
            except Exception as e:
                # Если проверка API не удалась (таймаут, сеть и т.д.), 
                # предполагаем что сессия валидна и пропускаем авторизацию
                # Основной цикл проверит авторизацию при первом запросе
                logger.warning(f"[Monitor {self.account.account_id}] Ошибка при проверке API: {e}")
                logger.info(f"[Monitor {self.account.account_id}] Пропускаем авторизацию, используем сессию. Основной цикл проверит авторизацию.")
                needs_auth = False
        
        # Открываем страницу только если нужна авторизация
        if needs_auth:
            # Создаем временную страницу для авторизации
            temp_page = await self.context.new_page()
            await temp_page.route("**/*", handle_route)
            
            # Создаем бота с credentials из БД
            self.bot = ThumbTackBot(
                temp_page,
                email=self.account.email,
                password=self.account.password
            )
            
            # Открываем страницу лидов для авторизации (нужно для получения cookies)
            logger.info(f"[Monitor {self.account.account_id}] Инициализация авторизации...")
            await temp_page.goto(f"{CONFIG.base_url}/pro-leads", wait_until="domcontentloaded", timeout=10000)
            await self._ensure_authenticated(temp_page)
            
            # После авторизации закрываем страницу - она не нужна для API запросов
            await temp_page.close()
            logger.info(f"[Monitor {self.account.account_id}] Авторизация завершена, страница закрыта")
        else:
            # Создаем бота для совместимости (может понадобиться для lead_key_from_url)
            # Но страницу не создаем
            self.bot = ThumbTackBot(
                None,  # page не нужна, только для lead_key_from_url
                email=self.account.email,
                password=self.account.password
            )
        
        self.page = None
        logger.info(f"[Monitor {self.account.account_id}] Используем только API запросы")
        
        logger.info(f"[Monitor {self.account.account_id}] Браузер инициализирован")
    
    async def _init_browser_context(self):
        """Переинициализирует контекст (используется при перезапуске)."""
        # Сохраняем сессию перед перезапуском
        await self._save_session()
        
        # Закрываем старый контекст (браузер остается в пуле)
        old_context = self.context
        self.context = None
        
        if old_context:
            try:
                await old_context.close()
            except Exception:
                pass
        
        # Переинициализируем браузер (используем ту же логику)
        await self._init_browser()
    
    async def _get_leads_from_api(self) -> Optional[List[Dict[str, Any]]]:
        """
        Получает лиды напрямую через API, без загрузки страницы.
        Использует авторизацию из контекста (cookies).
        
        Returns:
            Список лидов в формате, совместимом с list_new_leads(), 
            или None если нужна переавторизация (401)
        """
        # Добавляем timestamp для гарантированного обхода кеша (как window.location.reload(true))
        # Это гарантирует, что каждый запрос уникален и не будет кешироваться
        timestamp = int(time.time() * 1000)  # миллисекунды
        api_url = f"{CONFIG.base_url}/api/pro/new-leads?_t={timestamp}"
        
        headers = {
            "Accept": "application/json",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Requested-With": "XMLHttpRequest",  # Указываем, что это AJAX запрос
        }
        
        try:
            # Используем request из контекста (он уже авторизован через cookies)
            response = await self.context.request.get(
                api_url,
                headers=headers,
                timeout=2000  # Быстрый таймаут - 2 секунды
            )
            
            # Проверяем WAF challenge (202 с заголовком x-amzn-waf-action: challenge)
            waf_action = response.headers.get('x-amzn-waf-action', '')
            if response.status == 202 and waf_action == 'challenge':
                logger.warning(
                    f"[Monitor {self.account.account_id}] API вернул 202 с WAF challenge - нужно открыть страницу для прохождения challenge"
                )
                # Открываем страницу в браузере для прохождения WAF challenge
                if not self.page or self.page.is_closed():
                    self.page = await self.context.new_page()
                try:
                    await self.page.goto(f"{CONFIG.base_url}/pro-leads", wait_until="networkidle", timeout=20000)
                    await asyncio.sleep(3)  # Даем время на прохождение challenge
                    # Сохраняем обновленную сессию после прохождения challenge
                    await self._save_session()
                    # Закрываем страницу
                    await self.page.close()
                    self.page = None
                    logger.info(f"[Monitor {self.account.account_id}] WAF challenge пройден, повторяем API запрос")
                    # Повторяем API запрос после прохождения challenge
                    return await self._get_leads_from_api()
                except Exception as e:
                    logger.error(f"[Monitor {self.account.account_id}] Ошибка при прохождении WAF challenge: {e}")
                    if self.page and not self.page.is_closed():
                        await self.page.close()
                    self.page = None
                    return []
            
            if response.status == 200 or response.status == 202:
                # 200 OK или 202 Accepted (без WAF challenge) - оба статуса означают успешный ответ
                try:
                    json_data = await response.json()
                    # Логируем количество лидов в ответе для отладки
                    new_leads_count = len(json_data.get("newLeads", []))
                    logger.info(
                        f"[Monitor {self.account.account_id}] API вернул JSON (status {response.status}), "
                        f"newLeads в ответе: {new_leads_count}"
                    )
                    leads = self._extract_leads_from_api_response(json_data)
                    logger.info(
                        f"[Monitor {self.account.account_id}] Извлечено {len(leads)} лидов после обработки"
                    )
                    return leads
                except Exception as json_error:
                    # Если не JSON, логируем первые 200 символов ответа для отладки
                    text = await response.text()
                    logger.error(
                        f"[Monitor {self.account.account_id}] API вернул не JSON. "
                        f"Status: {response.status}, Content-Type: {response.headers.get('content-type', 'unknown')}, "
                        f"Response preview: {text[:200]}"
                    )
                    return []
            elif response.status == 401:
                logger.warning(
                    f"[Monitor {self.account.account_id}] API вернул 401 - нужна переавторизация"
                )
                # Возвращаем специальный маркер для немедленной переавторизации
                return None  # None означает, что нужна переавторизация
            else:
                text = await response.text()
                logger.error(
                    f"[Monitor {self.account.account_id}] API запрос вернул ошибку: {response.status}. "
                    f"Response: {text[:200]}"
                )
                return []
        
        except Exception as e:
            logger.error(
                f"[Monitor {self.account.account_id}] Ошибка при API запросе: {e}",
                exc_info=True
            )
            return []
    
    def _extract_leads_from_api_response(self, json_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Извлекает лиды из ответа API /api/pro/new-leads.
        Формат данных идентичен list_new_leads() для совместимости.
        
        Args:
            json_data: JSON ответ от API
            
        Returns:
            Список лидов в формате, идентичном list_new_leads()
        """
        leads = []
    
        if not isinstance(json_data, dict):
            logger.error(
                f"[Monitor {self.account.account_id}] API ответ имеет неожиданный тип: {type(json_data)}. "
                f"Ожидается dict с ключом 'newLeads'"
            )
            return []
        
        # Извлекаем список лидов из ответа
        new_leads = json_data.get("newLeads", [])
        
        logger.info(
            f"[Monitor {self.account.account_id}] API ответ содержит {len(new_leads)} элементов в newLeads"
        )
        
        # Логируем bidPK всех лидов для отладки
        if new_leads:
            bid_pks = [lead.get("bidPK", "N/A") for lead in new_leads]
            logger.info(f"[Monitor {self.account.account_id}] Найдено лидов в API: {len(new_leads)}, bidPK: {bid_pks}")
        
        for index, lead_data in enumerate(new_leads):
            bid_pk = lead_data.get("bidPK", "")
            customer_contact_time = lead_data.get("customerContactTime", "")
            is_unread = lead_data.get("isUnread", True)
            
            # Логируем информацию о каждом лиде
            logger.info(
                f"[Monitor {self.account.account_id}] Лид #{index+1}: bidPK={bid_pk}, "
                f"isUnread={is_unread}, customerContactTime={customer_contact_time}"
            )
            
            # Извлекаем данные из componentGroups
            component_groups = lead_data.get("componentGroups", [])
            
            name = ""
            category = ""
            location = ""
            
            for group in component_groups:
                # Извлекаем имя из intentComponents
                intent_components = group.get("intentComponents", [])
                for component in intent_components:
                    if component.get("type") == "avatarTitleSubtitle":
                        name = component.get("title", "")
                
                # Извлекаем категорию и адрес из requestDetailComponents
                request_components = group.get("requestDetailComponents", [])
                for component in request_components:
                    category = component.get("title", "")
                    
                    # Извлекаем адрес
                    icon_groups = component.get("iconTitleAddressGroups", [])
                    for icon_group in icon_groups:
                        icon_addresses = icon_group.get("iconTitleAddresses", [])
                        for addr in icon_addresses:
                            if addr.get("icon") == "map-pin--small":
                                location = addr.get("title", "")
            
            # Формируем href (используем bidPK)
            href = f"/pro-leads/{bid_pk}" if bid_pk else ""
            
            if not href:
                continue
            
            # Извлекаем lead_id из href (как в list_new_leads)
            if href.startswith("/pro-leads/"):
                lead_id = href.replace("/pro-leads/", "")
            else:
                lead_id = hashlib.md5((href or "").encode("utf-8")).hexdigest()[:12]
            
            # Формат идентичен list_new_leads() для совместимости
            lead = {
                "index": index,
                "href": href,
                "lead_id": lead_id,
                "lead_key": self.bot.lead_key_from_url(href) if self.bot else "",
                "name": name.strip(),
                "category": category.strip(),
                "location": location.strip(),
                "has_view": True,
            }
            
            leads.append(lead)
        
        return leads
    
    async def _ensure_authenticated(self, page=None):
        """Проверяет авторизацию и переавторизуется при необходимости."""
        if page is None:
            page = self.page
        if page is None:
            return
        
        if "login" in page.url.lower():
            logger.warning(f"[Monitor {self.account.account_id}] Перенаправлен на логин, переавторизация...")
            await self.bot.login_if_needed()
            await self.bot.open_leads()
            
            # Сохраняем новое состояние после переавторизации
            await self._save_session()
    
    async def _save_session(self):
        """Сохраняет сессию в файл."""
        try:
            if self.context:
                storage_state = await self.context.storage_state()
                with open(self.session_path, 'w') as f:
                    json.dump(storage_state, f)
                logger.debug(f"[Monitor {self.account.account_id}] Сессия сохранена")
        except Exception as e:
            logger.warning(f"[Monitor {self.account.account_id}] Ошибка при сохранении сессии: {e}")
    
    async def _monitoring_loop(self):
        """
        Основной цикл мониторинга с использованием API вместо DOM-парсинга.
        Получает лиды напрямую через API /api/pro/new-leads.
        """
        cycle_count = 0
        last_restart_time = asyncio.get_event_loop().time()
        last_cycle_start = asyncio.get_event_loop().time()
        last_auth_check_time = asyncio.get_event_loop().time()
        auth_check_interval = 300  # Проверяем авторизацию раз в 5 минут
        
        logger.info(f"[Monitor {self.account.account_id}] Запуск цикла мониторинга (API режим)...")
        
        while not self.stop_event.is_set():
            try:
                cycle_start = asyncio.get_event_loop().time()
                cycle_count += 1
                
                # Проверяем, не пора ли перезапустить браузер (каждые 3 часа)
                current_time = asyncio.get_event_loop().time()
                if current_time - last_restart_time > CONFIG.restart_interval_sec:
                    logger.info(f"[Monitor {self.account.account_id}] Перезапуск браузера (прошло {CONFIG.restart_interval_sec} сек)")
                    await self._restart_browser()
                    last_restart_time = current_time
                    last_auth_check_time = current_time
                
                # Периодически проверяем авторизацию через API (раз в 5 минут)
                # Если API вернет 401, тогда откроем страницу для переавторизации
                auth_time = 0.0
                if current_time - last_auth_check_time > auth_check_interval:
                    auth_start = asyncio.get_event_loop().time()
                    # Проверяем авторизацию через API запрос
                    try:
                        test_response = await self.context.request.get(
                            f"{CONFIG.base_url}/api/pro/new-leads",
                            timeout=2000
                        )
                        if test_response.status == 401:
                            logger.warning(f"[Monitor {self.account.account_id}] API вернул 401, нужна переавторизация")
                            # Открываем страницу для переавторизации
                            if not self.page or self.page.is_closed():
                                self.page = await self.context.new_page()
                            await self.page.goto(f"{CONFIG.base_url}/pro-leads", wait_until="domcontentloaded", timeout=10000)
                            await self._ensure_authenticated(self.page)
                            # Сохраняем сессию после переавторизации
                            await self._save_session()
                            # Закрываем страницу после переавторизации
                            await self.page.close()
                            self.page = None
                    except Exception as e:
                        logger.warning(f"[Monitor {self.account.account_id}] Ошибка при проверке авторизации: {e}")
                    auth_time = asyncio.get_event_loop().time() - auth_start
                    last_auth_check_time = current_time
                
                # Получаем лиды через API (быстро, без загрузки страницы)
                api_start = asyncio.get_event_loop().time()
                leads = await self._get_leads_from_api()
                api_time = asyncio.get_event_loop().time() - api_start
                
                # Если API вернул 401 (leads == None), нужна немедленная переавторизация
                if leads is None:
                    logger.warning(f"[Monitor {self.account.account_id}] API вернул 401, немедленная переавторизация...")
                    auth_start = asyncio.get_event_loop().time()
                    try:
                        # Открываем страницу для переавторизации
                        if not self.page or (self.page and self.page.is_closed()):
                            self.page = await self.context.new_page()
                        await self.page.goto(f"{CONFIG.base_url}/pro-leads", wait_until="domcontentloaded", timeout=10000)
                        
                        # Создаем бота с правильной страницей для переавторизации
                        self.bot = ThumbTackBot(
                            self.page,
                            email=self.account.email,
                            password=self.account.password
                        )
                        
                        await self._ensure_authenticated(self.page)
                        # Сохраняем сессию после переавторизации
                        await self._save_session()
                        # Закрываем страницу после переавторизации
                        await self.page.close()
                        self.page = None
                        # Обновляем бота для API режима (без страницы)
                        self.bot = ThumbTackBot(
                            None,
                            email=self.account.email,
                            password=self.account.password
                        )
                        logger.info(f"[Monitor {self.account.account_id}] Переавторизация завершена")
                    except Exception as e:
                        logger.error(f"[Monitor {self.account.account_id}] Ошибка при переавторизации: {e}", exc_info=True)
                        # В случае ошибки закрываем страницу и сбрасываем бота
                        if self.page and not self.page.is_closed():
                            await self.page.close()
                        self.page = None
                        self.bot = ThumbTackBot(
                            None,
                            email=self.account.email,
                            password=self.account.password
                        )
                    auth_time = asyncio.get_event_loop().time() - auth_start
                    last_auth_check_time = current_time
                    # После переавторизации пропускаем обработку лидов в этом цикле
                    leads = []
                
                # Логируем результат API запроса
                if leads:
                    logger.info(
                        f"[Monitor {self.account.account_id}][cycle={cycle_count}]: "
                        f"Найдено {len(leads)} лидов через API (за {api_time:.2f}сек)"
                    )
                    processed = await self._process_leads(leads)
                    logger.info(
                        f"[Monitor {self.account.account_id}][cycle={cycle_count}]: "
                        f"обработано {processed}/{len(leads)} лидов"
                    )
                else:
                    logger.debug(
                        f"[Monitor {self.account.account_id}][cycle={cycle_count}]: "
                        f"лидов не найдено (API запрос: {api_time:.2f}сек)"
                    )
                
                cycle_duration = asyncio.get_event_loop().time() - cycle_start
                time_since_last = cycle_start - last_cycle_start if cycle_count > 1 else 0
                last_cycle_start = cycle_start
                
                logger.info(
                    f"[Monitor {self.account.account_id}][cycle={cycle_count}] "
                    f"Время цикла: {cycle_duration:.2f}сек "
                    f"(API: {api_time:.2f}сек, auth: {auth_time:.2f}сек) "
                    f"С момента прошлого цикла: {time_since_last:.2f}сек"
                )
                
                await asyncio.sleep(CONFIG.poll_interval_sec)
                
            except Exception as e:
                logger.error(
                    f"[Monitor {self.account.account_id}][cycle={cycle_count}]: ошибка: {e}",
                    exc_info=True
                )
                await asyncio.sleep(CONFIG.poll_interval_sec)
    
    async def _restart_browser(self):
        """Перезапускает контекст (для обновления сессии и очистки памяти)."""
        logger.info(f"[Monitor {self.account.account_id}] Перезапуск контекста...")
        
        # Сохраняем сессию перед закрытием
        await self._save_session()
        
        # Закрываем старый контекст (браузер остается в пуле)
        old_context = self.context
        
        if old_context:
            try:
                await old_context.close()
            except Exception:
                pass
        
        # Устанавливаем context в None только после закрытия
        self.context = None
        
        # Переинициализируем контекст (браузер остается в пуле)
        # _init_browser_context() сам сохранит сессию, поэтому не нужно делать это дважды
        await self._init_browser_context()
    
    async def _process_leads(self, leads: List[Dict[str, Any]]) -> int:
        """
        Обрабатывает найденные лиды и отправляет их в RabbitMQ.
        Использует БД для дедупликации (проверяет processed_leads).
        Возвращает количество обработанных лидов.
        """
        processed_count = 0
        
        for lead in leads:
            lead_key = lead.get("lead_key")
            if not lead_key:
                continue
            
            # Проверяем в БД, не обработан ли уже этот лид
            db_check_start = asyncio.get_event_loop().time()
            try:
                is_processed = await self.db_client.is_lead_processed(
                    self.account.account_id,
                    lead_key
                )
                db_check_time = asyncio.get_event_loop().time() - db_check_start
                if db_check_time > 0.1:  # Логируем только если проверка заняла больше 100мс
                    logger.warning(
                        f"[Monitor {self.account.account_id}] Проверка БД для лида {lead_key} заняла {db_check_time:.3f}сек"
                    )
                if is_processed:
                    logger.info(f"[Monitor {self.account.account_id}] Лид {lead_key} уже был обработан (проверка БД вернула True), пропускаем")
                    continue
                else:
                    logger.debug(f"[Monitor {self.account.account_id}] Лид {lead_key} НЕ обработан (проверка БД вернула False), продолжаем обработку")
            except Exception as e:
                db_check_time = asyncio.get_event_loop().time() - db_check_start
                logger.warning(
                    f"[Monitor {self.account.account_id}] Ошибка при проверке лида в БД (заняло {db_check_time:.3f}сек): {e}"
                )
                # Продолжаем обработку, если БД недоступна
            
            # Отправляем задачу в RabbitMQ через Celery
            try:
                logger.info(
                    f"[Monitor {self.account.account_id}] Отправка лида {lead_key} (bidPK={lead.get('lead_id', 'N/A')}) "
                    f"в RabbitMQ очередь {CONFIG.queue_name}"
                )
                self.celery_app.send_task(
                    CONFIG.task_name,
                    args=[self.account.account_id, lead],
                    queue=CONFIG.queue_name,
                    retry=False
                )
                logger.info(f"[Monitor {self.account.account_id}] Лид {lead_key} отправлен в RabbitMQ")
                
                # Помечаем лид как обработанный в БД
                try:
                    await self.db_client.mark_lead_as_processed(
                        self.account.account_id,
                        lead_key
                    )
                    logger.info(f"[Monitor {self.account.account_id}] Лид {lead_key} помечен как обработанный в БД")
                except Exception as e:
                    logger.warning(f"[Monitor {self.account.account_id}] Ошибка при сохранении лида в БД: {e}")
                
                processed_count += 1
                
                logger.info(
                    f"[Monitor {self.account.account_id}] "
                    f"Лид {lead_key} отправлен в очередь {CONFIG.queue_name}"
                )
                
            except Exception as e:
                logger.error(
                    f"[Monitor {self.account.account_id}] "
                    f"Ошибка при отправке лида {lead_key}: {e}",
                    exc_info=True
                )
        
        return processed_count
    
    async def stop(self):
        """Останавливает мониторинг."""
        logger.info(f"[Monitor {self.account.account_id}] Остановка...")
        self.stop_event.set()
    
    async def _cleanup(self):
        """Очищает ресурсы (закрывает только контекст, браузер остается в пуле)."""
        logger.info(f"[Monitor {self.account.account_id}] Очистка ресурсов...")
        
        # Сохраняем сессию
        await self._save_session()
        
        # Закрываем контекст (браузер остается в пуле для других мониторов)
        if self.context:
            try:
                await self.context.close()
            except Exception:
                pass
        
        logger.info(f"[Monitor {self.account.account_id}] Очистка завершена")

