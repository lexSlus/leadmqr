#!/bin/bash

# Скрипт для ручной настройки авторизации в Thumbtack
# Позволяет пройти капчу и сохранить сессию

echo "🔐 Настройка авторизации в Thumbtack"
echo "=================================="
echo ""
echo "Этот скрипт поможет вам:"
echo "1. Открыть браузер"
echo "2. Пройти авторизацию в Thumbtack"
echo "3. Решить капчу (если появится)"
echo "4. Сохранить сессию для автоматического использования"
echo ""
echo "После запуска:"
echo "- Введите логин и пароль"
echo "- Решите капчу если появится"
echo "- Нажмите Enter в консоли когда авторизация завершена"
echo ""

# Проверяем, что мы в правильной директории
if [ ! -f "cli/setup_auth.py" ]; then
    echo "❌ Ошибка: Запустите скрипт из корневой директории проекта"
    echo "   cd /path/to/leadmqr"
    echo "   bash cli/setup_auth.sh"
    exit 1
fi

# Проверяем Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Ошибка: Python3 не найден"
    exit 1
fi

# Проверяем зависимости
echo "🔍 Проверяем зависимости..."
if ! python3 -c "import playwright" 2>/dev/null; then
    echo "❌ Ошибка: Playwright не установлен"
    echo "Установите: pip install playwright"
    echo "Затем: playwright install"
    exit 1
fi

echo "✅ Зависимости проверены"
echo ""

# Запускаем скрипт
echo "🚀 Запускаем браузер для авторизации..."
echo ""

python3 cli/setup_auth.py

echo ""
echo "🎉 Готово! Теперь можно запускать LeadProducer:"
echo "   python cli/run_lead_producer.py"
echo ""

