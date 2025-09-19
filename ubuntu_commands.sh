#!/bin/bash

echo "🚀 Команды для запуска на Ubuntu сервере"
echo "========================================"

echo ""
echo "1. Запуск Docker Compose (dev2):"
echo "docker-compose -f docker-compose-dev2.yaml up -d"

echo ""
echo "2. Проверка статуса контейнеров:"
echo "docker-compose -f docker-compose-dev2.yaml ps"

echo ""
echo "3. Логи AI worker:"
echo "docker-compose -f docker-compose-dev2.yaml logs -f celery_worker_ai"

echo ""
echo "4. Логи Lead worker:"
echo "docker-compose -f docker-compose-dev2.yaml logs -f celery_worker"

echo ""
echo "5. Создание тестового лида:"
echo "docker-compose -f docker-compose-dev2.yaml exec web python manage.py shell -c \"
from leads.models import FoundPhone
phone_obj = FoundPhone.objects.create(
    lead_key='ubuntu_test_123',
    phone='+1234567890',
    variables={'customer_name': 'Ubuntu Test', 'service': 'Cleaning'}
)
print(f'✅ Создан тестовый лид: ID={phone_obj.id}')
\""

echo ""
echo "6. Отправка AI call task:"
echo "docker-compose -f docker-compose-dev2.yaml exec web python manage.py shell -c \"
from ai_calls.tasks import enqueue_ai_call
result = enqueue_ai_call.delay('5')
print(f'✅ AI call task отправлен: {result.id}')
\""

echo ""
echo "7. Остановка системы:"
echo "docker-compose -f docker-compose-dev2.yaml down"

echo ""
echo "8. Полная очистка (включая volumes):"
echo "docker-compose -f docker-compose-dev2.yaml down -v"
