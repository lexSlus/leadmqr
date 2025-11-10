# main.py
import uvicorn
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

# Настраиваем логирование ПЕРЕД импортом модулей, чтобы все логгеры получили правильные настройки
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    force=True  # Перезаписываем существующие настройки (важно если модули импортировались ранее)
)

# Явно настраиваем уровень логирования для playwright_bot (мог быть создан до basicConfig)
playwright_logger = logging.getLogger("playwright_bot")
playwright_logger.setLevel(logging.INFO)

logger = logging.getLogger(__name__)

# --- ⬇️ ВОТ СВЯЗЬ ⬇️ ---
# Импортируем наш ПУЛ и Менеджер Тасок (после настройки логирования)
from browser_service.browser_pool import BrowserPool
from browser_service.task_manager import SessionManager
# --- ⬆️ ВОТ СВЯЗЬ ⬆️ ---

# --- Глобальный Пул и Менеджер Сессий ---
# Создаем один экземпляр пула. FastAPI будет им управлять.
# 1 браузер, несколько контекстов для параллельной обработки задач
# TODO: Замени на config.TARGET_BROWSER_COUNT и config.TARGET_CONTEXT_COUNT
pool = BrowserPool(num_browsers=1, num_contexts=3)
# Используем переменную окружения для папки сессий (общая с monitor_service)
import os
sessions_dir = os.getenv("SESSIONS_DIR", "sessions")
session_manager = SessionManager(pool=pool, sessions_dir=sessions_dir)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle hooks для FastAPI: запуск и остановка пула браузеров."""
    # Запуск: инициализируем пул и сессии
    logger.info("Запуск FastAPI: инициализация пула браузеров...")
    await pool.start()
    await session_manager.initialize_sessions()  # Создаст папку /sessions
    logger.info("Пул браузеров инициализирован")
    
    yield
    
    # Остановка: закрываем все активные сессии и пул
    logger.info("Остановка FastAPI: закрытие пула браузеров...")
    await session_manager.cleanup_all_active_sessions()  # Закрывает все активные сессии
    await pool.stop()
    logger.info("Пул браузеров закрыт")


app = FastAPI(title="Завод Исполнителей (MS)", lifespan=lifespan)

# --- WebSocket API ---
@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Основная "дверь" для "Рабочих" (W1-W4).
    Управляет сессией и вызывает "мозг" (task_manager).
    """
    await websocket.accept()
    logger.info(f"Клиент (Рабочий) подключился: {websocket.client.host}")
    
    session_id: str | None = None
    
    try:
        while True:
            data = await websocket.receive_json()
            command = data.get("command")
            task_data = data.get("data", {})
            req_id = data.get("request_id", "unknown")

            logger.info(f"[{req_id}] Получена команда: {command}")

            try:
                match command:
                    case "session_start":
                        account_id = task_data.get("account_id")
                        if not account_id:
                            raise ValueError("account_id is required")
                        
                        session_id = await session_manager.session_start(account_id)
                        
                        await websocket.send_json({
                            "status": "ok",
                            "response_to": req_id,
                            "session_id": session_id
                        })
                        logger.info(f"[{req_id}] Session started: {session_id}")

                    case "session_stop":
                        sid = data.get("session_id") or session_id
                        if sid:
                            await session_manager.session_stop(sid)
                            await websocket.send_json({
                                "status": "ok",
                                "response_to": req_id
                            })
                            session_id = None
                            break
                        else:
                            raise ValueError("No session_id provided")

                    # --- "Умные" ручки (шаги обработки лида) ---
                    # Последовательность: step_open_leads -> step_open_lead_details -> step_extract_full_name -> step_send_message -> step_extract_phone
                    case "step_open_leads" | "step_open_lead_details" | "step_extract_full_name" | "step_send_message" | "step_extract_phone":
                        sid = data.get("session_id") or session_id
                        if not sid:
                            raise ValueError("No session_id provided")
                        
                        # 1. "Завод" (MS) выполняет шаг
                        result = await session_manager.execute_step(
                            session_id=sid,
                            command=command,
                            task_data=task_data
                        )
                        
                        # 2. ✅ "Завод" (MS) ГОВОРИТ ВОРКЕРУ, ЧТО СДЕЛАНО
                        await websocket.send_json({
                            "status": "ok",
                            "response_to": req_id,
                            "command": command,  # Явно указываем, какой шаг выполнен
                            "session_id": sid,
                            "result": result
                        })
                        logger.info(f"[{req_id}] Step '{command}' completed successfully")

                    case _:
                        raise ValueError(f"Неизвестная команда: {command}")

            except Exception as e:
                logger.error(f"[{req_id}] Ошибка выполнения команды {command}: {e}", exc_info=True)
                # 3. ✅ "Завод" (MS) ГОВОРИТ ВОРКЕРУ, ЧТО ВСЕ ПЛОХО
                await websocket.send_json({
                    "status": "error",
                    "response_to": req_id,
                    "message": str(e)
                })

    except WebSocketDisconnect:
        logger.info(f"Клиент (Рабочий) отключился: {websocket.client.host}")
    except Exception as e:
        logger.error(f"Критическая ошибка WebSocket: {e}", exc_info=True)
    finally:
        # Гарантированно закрываем сессию при отключении
        if session_id:
            try:
                logger.warning(f"Клиент отключился, принудительная очистка сессии {session_id}")
                await session_manager.session_stop(session_id)
            except Exception as e:
                logger.error(f"Ошибка при очистке сессии {session_id}: {e}")


# --- Health Check ---
@app.get("/health", response_class=HTMLResponse)
async def health():
    return "<html><body><h1>Завод (MS) работает!</h1></body></html>"


if __name__ == "__main__":
    logger.info("Запуск Uvicorn в режиме отладки...")
    # 'reload=True' будет следить за изменениями во всех .py файлах
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)

