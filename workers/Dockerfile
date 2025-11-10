# Dockerfile для workers
FROM python:3.10-slim

WORKDIR /app

# Устанавливаем зависимости
COPY workers/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код workers
COPY workers/ ./workers/

# Копируем .env файл из корня проекта
COPY .env /app/.env

# CMD убран - команда запуска будет указана в docker-compose.yml
