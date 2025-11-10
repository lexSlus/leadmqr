#!/bin/bash
set -e

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*" >&2
}

log "Запуск VNC окружения..."

rm -f /tmp/.X99-lock /tmp/.X11-unix/X99

log "Запуск Xvfb..."
Xvfb :99 -screen 0 1920x1080x24 -ac +extension GLX +render -noreset > /tmp/xvfb.log 2>&1 &
XVFB_PID=$!
sleep 2
if ! kill -0 $XVFB_PID 2>/dev/null; then
    log "ОШИБКА: Xvfb не запустился!"
    cat /tmp/xvfb.log >&2
    exit 1
fi
export DISPLAY=:99
log "Xvfb запущен (PID: $XVFB_PID)"

log "Запуск fluxbox..."
fluxbox > /tmp/fluxbox.log 2>&1 &
FLUXBOX_PID=$!
sleep 1
log "fluxbox запущен (PID: $FLUXBOX_PID)"

log "Запуск x11vnc..."
x11vnc -display :99 -forever -shared -rfbport 5900 -nopw -bg -xkb -noxrecord -noxfixes -noxdamage -wait 10 -defer 10 > /tmp/x11vnc.log 2>&1
sleep 3
if ! grep -q "Listening for VNC connections" /tmp/x11vnc.log 2>/dev/null; then
    log "Проверяю x11vnc..."
    sleep 1
    if ! grep -q "Listening for VNC connections" /tmp/x11vnc.log 2>/dev/null; then
        log "ОШИБКА: x11vnc не запустился!"
        cat /tmp/x11vnc.log >&2
        exit 1
    fi
fi
log "x11vnc запущен на порту 5900"

log "Запуск websockify (noVNC)..."
cd /opt/novnc/utils/websockify
if python3 -m websockify --help > /dev/null 2>&1; then
    python3 -m websockify --web /opt/novnc 6080 localhost:5900 > /tmp/websockify.log 2>&1 &
elif [ -f "run" ]; then
    ./run --web /opt/novnc 6080 localhost:5900 > /tmp/websockify.log 2>&1 &
elif [ -f "websockify.py" ]; then
    python3 websockify.py --web /opt/novnc 6080 localhost:5900 > /tmp/websockify.log 2>&1 &
else
    log "ОШИБКА: websockify не найден!"
    exit 1
fi
WEBSOCKIFY_PID=$!
sleep 2
if ! kill -0 $WEBSOCKIFY_PID 2>/dev/null; then
    log "ОШИБКА: websockify не запустился!"
    cat /tmp/websockify.log >&2
    exit 1
fi
log "websockify запущен на порту 6080 (PID: $WEBSOCKIFY_PID)"

log "VNC окружение готово! Откройте http://localhost:6080 в браузере"

cd /app

log "Запуск FastAPI..."
exec python -u -m uvicorn browser_service.main:app --host 0.0.0.0 --port 8080 --log-level info --access-log 2>&1

