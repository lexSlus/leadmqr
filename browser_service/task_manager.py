# task_manager.py
import logging
import uuid
import os
import json
import asyncio
from typing import Optional, Dict, Any
from playwright.async_api import BrowserContext, Page
from browser_service.browser_pool import BrowserPool
from playwright_bot.thumbtack_bot import ThumbTackBot

logger = logging.getLogger(__name__)


class SessionManager:
    """
    Управляет активными сессиями (контекстами/вкладками).
    Использует пул предзагруженных контекстов для ускорения обработки задач.
    """
    
    def __init__(self, pool: BrowserPool, sessions_dir: str = "sessions"):
        self.pool = pool
        self.sessions_dir = sessions_dir
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()  # Защищает доступ к self.sessions
    
    async def initialize_sessions(self):
        """Вызывается из main.py при старте для создания папки."""
        os.makedirs(self.sessions_dir, exist_ok=True)
        logger.info(f"Папка сессий {self.sessions_dir} готова.")
    
    def _get_session_path(self, account_id: str) -> str:
        """Генерирует стандартизированный путь к файлу сессии."""
        return os.path.join(self.sessions_dir, f"session_{account_id}.json")
    
    async def session_start(self, account_id: str) -> str:
        """
        Создает новую сессию для аккаунта.
        Получает контекст из пула, загружает cookies, создает бота.
        """
        session_path = self._get_session_path(account_id)
        session_id = f"session_{uuid.uuid4().hex[:8]}"
        context = None
        page = None
        browser_for_session = None
        
        try:
            logger.info(f"[SessionManager] ⏳ Получение контекста для {account_id}...")
            
            # Получаем контекст из пула (может подождать, если пул пуст)
            context, page, browser_for_session = await self.pool.get_preloaded_context()
            logger.info(f"[SessionManager] ✅ Контекст получен для {account_id}")
            
            # Загружаем cookies из файла сессии (если есть)
            if os.path.exists(session_path):
                try:
                    with open(session_path, 'r') as f:
                        storage_state = json.load(f)
                    cookies = storage_state.get("cookies", [])
                    if cookies:
                        await context.add_cookies(cookies)
                        logger.info(f"[SessionManager] Загружено {len(cookies)} cookies для {account_id}")
                except Exception as e:
                    logger.warning(f"[SessionManager] Ошибка при загрузке сессии: {e}")
            
            # Регистрируем сессию
            async with self._lock:
                self.sessions[session_id] = {
                    "context": context,
                    "page": page,
                    "bot": None,
                    "account_id": account_id,
                    "session_path": session_path,
                    "is_preloaded": True,
                    "browser": browser_for_session
                }
            
            # Создаем бота и обновляем сессию
            bot = ThumbTackBot(page)
            async with self._lock:
                if session_id in self.sessions:
                    self.sessions[session_id]["bot"] = bot
                else:
                    raise Exception(f"Session {session_id} was removed before bot creation")
            
            logger.info(f"[SessionManager] Session {session_id} created for {account_id}")
            return session_id
            
        except Exception as e:
            # При ошибке очищаем сессию и возвращаем контекст в пул
            async with self._lock:
                self.sessions.pop(session_id, None)
            
            if context and page and browser_for_session:
                logger.warning(f"[SessionManager] Ошибка при старте сессии {session_id}: {e}. Возвращаем контекст.")
                try:
                    await self.pool.release_preloaded_context(context, page, browser_for_session)
                except Exception as release_error:
                    logger.error(f"[SessionManager] Ошибка при возврате контекста: {release_error}")
            
            raise
    
    async def session_stop(self, session_id: str) -> None:
        """
        Закрывает сессию и возвращает контекст в пул.
        Гарантирует возврат контекста даже при ошибках (finally блок).
        """
        # Извлекаем сессию атомарно
        async with self._lock:
            if session_id not in self.sessions:
                logger.warning(f"[SessionManager] Session {session_id} not found")
                return
            
            logger.info(f"[SessionManager] ⏹️ Stopping session {session_id} (активных: {len(self.sessions)})")
            session = self.sessions.pop(session_id)
        
        # Извлекаем данные из сессии
        context = session.get("context")
        page = session.get("page")
        session_path = session.get("session_path")
        is_preloaded = session.get("is_preloaded", False)
        browser_for_session = session.get("browser") if is_preloaded else None

        try:
            # Пытаемся сохранить сессию (не критично, если не удастся)
            if context and session_path:
                try:
                    storage_state = await context.storage_state()
                    with open(session_path, 'w') as f:
                        json.dump(storage_state, f)
                    logger.info(f"[SessionManager] 💾 Сессия {session_id} сохранена")
                except Exception as e:
                    logger.warning(f"[SessionManager] Ошибка при сохранении сессии {session_id}: {e}")
        finally:
            # ГАРАНТИРОВАННО возвращаем контекст в пул (выполняется всегда, даже при ошибках)
            if is_preloaded and context and page and browser_for_session:
                try:
                    await self.pool.release_preloaded_context(context, page, browser_for_session)
                    logger.info(f"[SessionManager] ✅ Контекст возвращен в пул (активных: {len(self.sessions)})")
                except Exception as e:
                    logger.error(f"[SessionManager] ❌ Ошибка при возврате контекста: {e}", exc_info=True)
            
            logger.info(f"[SessionManager] Session {session_id} stopped")
    
    async def cleanup_all_active_sessions(self):
        """Закрывает все активные сессии. Вызывается при остановке сервера."""
        logger.info(f"Очистка {len(self.sessions)} активных сессий...")
        session_ids = list(self.sessions.keys())
        for sid in session_ids:
            await self.session_stop(sid)
    
    async def execute_step(self, session_id: str, command: str, task_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Выполняет шаг команды в рамках существующей сессии."""
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")
        
        session = self.sessions[session_id]
        bot: ThumbTackBot = session["bot"]
        page: Page = session["page"]
        
        logger.info(f"[SessionManager] Executing '{command}' for session {session_id}")
        
        match command:
            case "step_open_leads":
                await bot.open_leads()
                return {"url": page.url, "status": "opened"}
            
            case "step_open_lead_details":
                lead = task_data.get("lead", {})
                if not lead:
                    raise ValueError("lead data is required")
                await bot.open_lead_details(lead)
                return {"url": page.url, "status": "opened"}
            
            case "step_extract_full_name":
                full_name = await bot.extract_full_name_from_details()
                return {"full_name": full_name}
            
            case "step_send_message":
                message_text = task_data.get("message_text")
                await bot.send_template_message(text=message_text, dry_run=False)
                return {"status": "sent"}
            
            case "step_extract_phone":
                phone = await bot.extract_phone()
                return {"phone": phone}
            
            case _:
                raise ValueError(f"Unknown command: {command}")
