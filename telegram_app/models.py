from django.db import models


class TelegramSubscriber(models.Model):
    """
    Модель для хранения пользователей, которые подписались на уведомления через бота.
    """
    chat_id = models.BigIntegerField(
        unique=True, 
        verbose_name="Chat ID пользователя"
    )
    user_id = models.BigIntegerField(
        unique=True, 
        verbose_name="Telegram User ID"
    )
    username = models.CharField(
        max_length=100, 
        blank=True, 
        null=True, 
        verbose_name="Username"
    )
    first_name = models.CharField(
        max_length=100, 
        blank=True, 
        null=True, 
        verbose_name="Имя"
    )
    created_at = models.DateTimeField(
        auto_now_add=True, 
        verbose_name="Дата подписки"
    )

    def __str__(self):
        return f"{self.first_name or self.username} ({self.chat_id})"

    class Meta:
        verbose_name = "Подписчик Telegram"
        verbose_name_plural = "Подписчики Telegram"
