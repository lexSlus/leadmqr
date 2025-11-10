# Умный Dockerfile для monitor_service
# Поддерживает prod и vnc режимы через ARG BUILD_MODE

ARG BUILD_MODE=prod
FROM python:3.10-slim

WORKDIR /app

# Устанавливаем базовые зависимости ОС
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    xvfb \
    xauth \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем VNC зависимости (только для BUILD_MODE=vnc)
ARG BUILD_MODE
RUN if [ "$BUILD_MODE" = "vnc" ]; then \
    apt-get update && apt-get install -y --no-install-recommends \
    x11vnc \
    fluxbox \
    wget \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /opt/novnc \
    && wget -qO- https://github.com/novnc/noVNC/archive/v1.4.0.tar.gz | tar xz --strip 1 -C /opt/novnc \
    && mkdir -p /opt/novnc/utils/websockify \
    && wget -qO- https://github.com/novnc/websockify/archive/v0.11.0.tar.gz | tar xz --strip 1 -C /opt/novnc/utils/websockify \
    && apt-get update && apt-get install -y --no-install-recommends python3-numpy \
    && rm -rf /var/lib/apt/lists/*; \
    fi

# Копируем общий модуль playwright_bot
COPY playwright_bot/ ./playwright_bot/

# Устанавливаем Python-зависимости (включая playwright)
COPY monitor_service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Устанавливаем Playwright и его браузеры (после установки playwright пакета)
RUN playwright install --with-deps chromium

# Копируем код сервиса мониторинга
COPY monitor_service/ ./monitor_service/

# Создаем папку для сессий
RUN mkdir -p /sessions

# Копируем VNC скрипт (будет использован только в vnc режиме)
COPY monitor_service/start_with_vnc.sh /start_with_vnc.sh
RUN chmod +x /start_with_vnc.sh

# CMD убран - команда запуска будет указана в docker-compose.yml
