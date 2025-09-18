# 🚀 Команды для удаленного тестирования LeadMQR

## 1. Подготовка

```bash
# Включить BuildKit
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

# Проверить .env файл
cat .env | grep TT_
# Должно быть:
# TT_EMAIL=your_email@example.com  
# TT_PASSWORD=your_password
```

## 2. Запуск системы

```bash
# Запустить все сервисы
docker compose -f docker-compose-dev.yaml up --build -d

# Проверить статус
docker compose -f docker-compose-dev.yaml ps

# Смотреть логи всех сервисов
docker compose -f docker-compose-dev.yaml logs -f
```

## 3. Тестирование полного флоу

### Отправка тестового лида:
```bash
# Вход в веб-контейнер
docker compose -f docker-compose-dev.yaml exec web bash

# Django shell
python manage.py shell
```

```python
# В Django shell - отправляем реальный лид с телефоном
from leads.tasks import process_single_lead_task

# Лид с РЕАЛЬНЫМ href где есть телефон
test_lead = {
    'index': 0,
    'href': '/pro-inbox/messages/552361562202349575',  # Реальный href
    'lead_key': '040fce53dd765b65513b5e5c118a02e5',  # MD5 от href
    'name': 'Real Lead with Phone',
    'category': 'Real Category', 
    'location': 'Real Location',
    'has_view': True
}

print('=== ОТПРАВЛЯЕМ ЛИД С ТЕЛЕФОНОМ ===')
result = process_single_lead_task.apply_async(args=[test_lead], queue='lead_proc')
print(f'Task ID: {result.id}')
print('✅ Лид отправлен!')
```

### Ожидаемый флоу:
1. **Celery Worker** получает задачу
2. **Открывает /pro-leads** на Thumbtack
3. **Переходит к лиду** по href
4. **Отправляет шаблон** сообщение
5. **Заходит в /pro-inbox/messages**
6. **Ищет сообщение** с lead_key=040fce53dd765b65513b5e5c118a02e5
7. **Находит телефон** +13478601753
8. **Отправляет в очередь ai_calls**
9. **AI Worker** создает звонок в Vocaly

## 4. Мониторинг

```bash
# Логи воркера обработки лидов
docker compose -f docker-compose-dev.yaml logs -f celery_worker

# Логи AI воркера  
docker compose -f docker-compose-dev.yaml logs -f celery_worker_ai

# Логи LeadProducer
docker compose -f docker-compose-dev.yaml logs -f lead_producer
```

## 5. Проверка результатов

```python
# В Django shell
from leads.models import FoundPhone, ProcessedLead
from ai_calls.models import AICall

print('=== FoundPhone ===')
for phone in FoundPhone.objects.all().order_by('-created_at')[:5]:
    print(f'Lead: {phone.lead_key}, Phone: {phone.phone}, Created: {phone.created_at}')

print('\n=== ProcessedLead ===')  
for lead in ProcessedLead.objects.all().order_by('-created_at')[:5]:
    print(f'Lead: {lead.key}, Created: {lead.created_at}')

print('\n=== AICall ===')
for call in AICall.objects.all().order_by('-created_at')[:5]:
    print(f'Lead: {call.lead_key}, Phone: {call.to_phone}, Status: {call.status}, Created: {call.created_at}')
```

## 6. Очистка для повторного тестирования

```python
# В Django shell
from leads.models import FoundPhone, ProcessedLead
from ai_calls.models import AICall

# Очищаем все данные
FoundPhone.objects.all().delete()
ProcessedLead.objects.all().delete() 
AICall.objects.all().delete()
print("✅ Данные очищены для повторного тестирования")
```

## 7. Альтернативный тест с новым лидом

```python
# Если хотите протестировать с новым лидом
test_lead_new = {
    'index': 0,
    'href': '/pro-leads/NEW_LEAD_ID',  # Замените на реальный ID
    'lead_key': 'NEW_LEAD_KEY',        # MD5 от href
    'name': 'New Test Lead',
    'category': 'Test Category',
    'location': 'Test Location', 
    'has_view': True
}

result = process_single_lead_task.apply_async(args=[test_lead_new], queue='lead_proc')
print(f'Task ID: {result.id}')
```

## 🔧 Устранение проблем

### Если воркер падает на логине:
1. Проверьте VPN подключение
2. Проверьте креденшалы в .env
3. Проверьте что Thumbtack доступен

### Если не находит телефон:
1. Убедитесь что lead_key совпадает с MD5 от href
2. Проверьте что сообщение есть в inbox
3. Проверьте селекторы в tt_selectors.py

### Если AI звонок не создается:
1. Проверьте настройки Vocaly в .env
2. Проверьте логи AI воркера
3. Проверьте что блокировка дублей отключена в ai_calls/services.py
