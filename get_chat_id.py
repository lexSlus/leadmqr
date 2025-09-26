import logging
import asyncio
import os
import django

# --- НАЧАЛО БЛОКА ИНТЕГРАЦИИ С DJANGO ---
# Указываем Django, где найти файл настроек
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'leadmqr.settings')

# Загружаем Django
django.setup()
# --- КОНЕЦ БЛОКА ИНТЕГРАЦИИ С DJANGO ---

# Теперь можно импортировать Django модели и настройки
from django.conf import settings
from telegram_app.models import TelegramSubscriber

# Используем абсолютный импорт для python-telegram-bot
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Настройка логирования, чтобы видеть, что происходит
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class ChatIdBot:
    """Бот для автоматического получения и сохранения Chat ID."""
    
    def __init__(self):
        self.token = settings.TELEGRAM_BOT_TOKEN
        self.application = Application.builder().token(self.token).build()
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Настраивает обработчики команд."""
        self.application.add_handler(CommandHandler("start", self.start_command))
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Вызывается при команде /start, получает chat_id и сохраняет его в базу данных.
        """
        user = update.effective_user
        chat_id = update.message.chat_id

        # Используем Django ORM для сохранения или обновления подписчика
        subscriber, created = await TelegramSubscriber.objects.aupdate_or_create(
            user_id=user.id,
            defaults={
                'chat_id': chat_id,
                'username': user.username,
                'first_name': user.first_name,
            }
        )

        if created:
            logger.info(f"Новый подписчик сохранен: {user.full_name} с Chat ID {chat_id}")
            print(f"✅ НОВЫЙ ПОДПИСЧИК: {user.full_name} с Chat ID {chat_id}")
            reply_text = (
                f"Привет, {user.first_name}! 👋\n\n"
                f"Ваш <b>Chat ID</b>: <code>{chat_id}</code>\n\n"
                f"Я сохранил его, и теперь вы будете получать уведомления о новых лидах."
            )
        else:
            logger.info(f"Данные подписчика обновлены: {user.full_name} с Chat ID {chat_id}")
            print(f"🔄 ОБНОВЛЕН ПОДПИСЧИК: {user.full_name} с Chat ID {chat_id}")
            reply_text = (
                f"С возвращением, {user.first_name}! 👋\n\n"
                f"Ваш <b>Chat ID</b> <code>{chat_id}</code> уже был в моей базе. Я обновил данные."
            )
        
        await update.message.reply_html(reply_text)
    
    def run(self):
        """Запускает бота."""
        logger.info("Бот запущен и ждет команд для сохранения Chat ID...")
        self.application.run_polling()


if __name__ == '__main__':
    bot = ChatIdBot()
    bot.run()
