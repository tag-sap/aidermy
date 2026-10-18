#!/bin/bash

case "$1" in
  backend)
    echo "🔄 Запуск бэкенда..."
    cd /var/www/aidermy/backend
    source venv/bin/activate
    pkill -f gunicorn 2>/dev/null
    # Ждём освобождения порта: иначе новый мастер не сможет забиндиться
    # ("Address already in use"), а старый процесс продолжит отдавать СТАРЫЙ код.
    for i in $(seq 1 30); do
        ss -tln 2>/dev/null | grep -q "127.0.0.1:8000 " || break
        sleep 0.5
    done
    gunicorn -w 1 -k uvicorn.workers.UvicornWorker app.main:app --bind 127.0.0.1:8000 --daemon --capture-output --error-logfile /var/www/aidermy/backend/gunicorn.log --access-logfile /var/www/aidermy/backend/gunicorn_access.log
    # Ждём готовности воркера (а не фиксированные 2 секунды).
    for i in $(seq 1 40); do
        curl -sf http://127.0.0.1:8000/api/health > /dev/null && break
        sleep 0.5
    done
    curl -sf http://127.0.0.1:8000/api/health > /dev/null && echo "✅ Бэкенд работает" || echo "❌ Бэкенд не работает"
    ;;
  frontend)
    echo "🔄 Сборка фронтенда (Vite)..."
    cd /var/www/aidermy/figma-make-preview
    npm install --no-fund --no-audit
    npm run build
    systemctl reload nginx
    curl -s https://aidermy.ru/ > /dev/null && echo "✅ Фронтенд работает" || echo "❌ Фронтенд не работает"
    ;;
  all)
    $0 backend
    $0 frontend
    ;;
  status)
    echo "=== ПРОЦЕССЫ ==="
    ps aux | grep gunicorn | grep -v grep
    echo ""
    echo "=== ПОРТЫ ==="
    ss -tlnp | grep -q ':8000' && echo "✅ Бэкенд (8000) запущен" || echo "❌ Бэкенд (8000) не запущен"
    ;;
  logs)
    tail -f /var/www/aidermy/backend/aidermy_app.log
    ;;
  *)
    echo "Использование: ./start.sh {backend|frontend|all|status|logs}"
    ;;
esac
