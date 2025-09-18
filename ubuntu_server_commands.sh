#!/bin/bash
# 🚀 Команды для Ubuntu сервера - LeadMQR тестирование

echo "=== 1. ЗАПУСК СИСТЕМЫ ==="
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1
docker compose -f docker-compose-dev.yaml up --build -d
docker compose -f docker-compose-dev.yaml ps

echo ""
echo "=== 2. ОТПРАВКА ТЕСТОВОГО ЛИДА ==="
docker compose -f docker-compose-dev.yaml exec web python manage.py shell -c "
from leads.tasks import process_single_lead_task

# Реальный лид с телефоном
test_lead = {
    'index': 0,
    'href': '/pro-inbox/messages/552361562202349575',
    'lead_key': '040fce53dd765b65513b5e5c118a02e5',
    'name': 'Real Lead with Phone',
    'category': 'Real Category',
    'location': 'Real Location',
    'has_view': True
}

print('=== ОТПРАВЛЯЕМ ЛИД С ТЕЛЕФОНОМ ===')
result = process_single_lead_task.apply_async(args=[test_lead], queue='lead_proc')
print(f'Task ID: {result.id}')
print('✅ Лид отправлен!')
"

echo ""
echo "=== 3. МОНИТОРИНГ ЛОГОВ ==="
echo "Смотрите логи воркера:"
docker compose -f docker-compose-dev.yaml logs -f celery_worker

echo ""
echo "=== 4. ПРОВЕРКА РЕЗУЛЬТАТОВ ==="
docker compose -f docker-compose-dev.yaml exec web python manage.py shell -c "
from leads.models import FoundPhone, ProcessedLead
from ai_calls.models import AICall

print('=== FoundPhone ===')
for phone in FoundPhone.objects.all().order_by('-created_at')[:3]:
    print(f'Lead: {phone.lead_key}, Phone: {phone.phone}, Created: {phone.created_at}')

print('\n=== ProcessedLead ===')
for lead in ProcessedLead.objects.all().order_by('-created_at')[:3]:
    print(f'Lead: {lead.key}, Created: {lead.created_at}')

print('\n=== AICall ===')
for call in AICall.objects.all().order_by('-created_at')[:3]:
    print(f'Lead: {call.lead_key}, Phone: {call.to_phone}, Status: {call.status}, Created: {call.created_at}')
"
