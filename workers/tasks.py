# tasks.py
"""
Celery задачи - "входная дверь" для воркеров.
Получают задачи из RabbitMQ и делегируют обработку LeadProcessor.
"""
import logging
import time
from celery.exceptions import SoftTimeLimitExceeded
from celery_app import celery_app
from lead_processor import LeadProcessor
from telegram_notifier import TelegramNotifier
from jobber_integration import send_lead_to_jobber, refresh_jobber_token

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,  # bind=True дает нам доступ к `self` (объекту таски)
    name="tasks.process_new_lead",
    max_retries=0,          # Отключили ретраи (0 = не ретраить)
    default_retry_delay=60,  # Ждать 1 минуту перед повтором (не используется, но оставляем)
    acks_late=True          # Не говорить RabbitMQ "ok", пока таска не выполнится
)
def process_new_lead(self, account_id: str, lead_data: dict):
    """
    Эту таску (W1) "Ферма" (LP) кидает в RabbitMQ.
    Она — "входная дверь" для "Рабочего".
    
    Args:
        account_id: ID аккаунта
        lead_data: Данные лида
            {
                "lead_key": "unique_lead_id",
                "message_template": "Hi! We can help...",
                "name": "John Doe",
                "category": "Plumbing",
                "location": "New York, NY",
                "href": "/pro-leads/123456",
                ...
            }
    """
    task_id = self.request.id
    lead_key = lead_data.get('lead_key', 'unknown')
    logger.info(f"[Task {task_id}] [W1-Дверь] ПОЛУЧЕНА. Лид {lead_key} для {account_id}")
    
    try:
        # 1. Создаем "Мозг" (Оркестратор)
        processor = LeadProcessor(
            account_id=account_id, 
            lead_data=lead_data,
            task_id=str(task_id)  # Передаем ID таски для логов
        )

        result = processor.process_lead()
        
        # 3. СОХРАНЯЕМ РЕЗУЛЬТАТ
        # TODO: Здесь ты сохранишь `result["phone"]` в свою БД
        # db.save_lead_result(account_id, lead_key, result["phone"])
        logger.info(f"[Task {task_id}] [W1-Дверь] УСПЕХ. Результат: {result}")
        
        # 4. ОТПРАВЛЯЕМ УВЕДОМЛЕНИЯ (Telegram и Jobber)
        # Отправляем только если обработка успешна и есть телефон
        if result.get("status") == "success" and result.get("phone"):
            variables = result.get("variables", {})
            phone = result.get("phone")
            logger.info(f"[Task {task_id}] [W1-Дверь] Отправка уведомлений для лида {lead_key} (phone: {phone})")
            
            # 4.1. Отправляем в Telegram
            try:
                TelegramNotifier().send_lead_notification(variables, phone)
                logger.info(f"[Task {task_id}] [W1-Дверь] ✅ Telegram notification sent for lead {lead_key}")
            except Exception as e:
                logger.error(f"[Task {task_id}] [W1-Дверь] ❌ Failed to send Telegram notification: {e}", exc_info=True)

            # 4.2. Отправляем в Jobber
            jobber_start = time.time()
            try:
                result = send_lead_to_jobber(variables, phone)
                jobber_time = time.time() - jobber_start
                if result:
                    logger.info(f"[Task {task_id}] [W1-Дверь] ✅ Jobber lead created successfully for lead {lead_key} (время: {jobber_time:.2f}с)")
                else:
                    logger.warning(f"[Task {task_id}] [W1-Дверь] ⚠️ Jobber lead creation returned False for lead {lead_key} (время: {jobber_time:.2f}с)")
            except Exception as e:
                jobber_time = time.time() - jobber_start
                logger.error(f"[Task {task_id}] [W1-Дверь] ❌ Failed to send lead to Jobber (время: {jobber_time:.2f}с): {e}", exc_info=True)

        else:
            logger.warning(f"[Task {task_id}] [W1-Дверь] No phone found for lead {lead_key}, skipping notifications (status: {result.get('status')}, phone: {result.get('phone')})")
        
        return result
        
    except SoftTimeLimitExceeded:
        logger.error(f"[Task {task_id}] [W1-Дверь] Таска превысила лимит времени!")
        # Не повторяем, возвращаем ошибку
        return {"status": "timeout", "error": "Task exceeded time limit"}
        
    except Exception as e:
        # FAILED. Не повторяем (max_retries=0).
        logger.error(
            f"[Task {task_id}] [W1-Дверь] Таска УПАЛА. ФИНАЛЬНАЯ ОШИБКА (без ретраев): {e}",
            exc_info=True  # ОБЯЗАТЕЛЬНО, чтобы видеть полный стек ошибки
        )
        # Пробрасываем ошибку. Celery пометит ее как FAILED.
        raise


@celery_app.task(
    name="tasks.refresh_jobber_token_periodic",
    ignore_result=True
)
def refresh_jobber_token_periodic():
    """
    Периодическая задача для обновления Jobber токена.
    Запускается каждые 50 минут через Celery beat.
    Это предотвращает задержку при отправке лидов, если токен истек.
    """
    logger.info("Jobber: Периодическое обновление токена...")
    try:
        refreshed = refresh_jobber_token()
        if refreshed:
            logger.info("Jobber: ✅ Токен обновлен периодической задачей")
        else:
            logger.debug("Jobber: Токен был валиден, обновление не требовалось")
    except Exception as e:
        logger.error(f"Jobber: ❌ Ошибка в периодическом обновлении токена: {e}", exc_info=True)
