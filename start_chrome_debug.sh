#!/bin/bash
echo "Запускаем Chrome вручную с debug портом..."

# Находим Chrome
CHROME_PATH=""
if [ -f "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ]; then
    CHROME_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
elif [ -f "/Applications/Chromium.app/Contents/MacOS/Chromium" ]; then
    CHROME_PATH="/Applications/Chromium.app/Contents/MacOS/Chromium"
else
    echo "Chrome не найден! Установите Google Chrome или Chromium."
    exit 1
fi

echo "Используем Chrome: $CHROME_PATH"

# Создаем папку для профиля
mkdir -p ./chrome_debug_profile

# Запускаем Chrome с debug портом
"$CHROME_PATH" \
    --remote-debugging-port=9222 \
    --remote-debugging-address=127.0.0.1 \
    --user-data-dir=./chrome_debug_profile \
    --no-sandbox \
    --disable-setuid-sandbox \
    --disable-dev-shm-usage \
    --disable-gpu \
    --new-window \
    "https://google.com" \
    "https://example.com" \
    "about:blank" &

echo "Chrome запущен. Проверяйте chrome://inspect"