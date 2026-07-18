#!/bin/bash

case "$1" in
  backend)
    echo "🔄 Запуск бэкенда..."
    cd /var/www/aidermy/backend
    source venv/bin/activate
    pkill -f gunicorn 2>/dev/null
    gunicorn -w 1 -k uvicorn.workers.UvicornWorker app.main:app --bind 127.0.0.1:8000 --daemon
    sleep 2
    curl -s http://127.0.0.1:8000/api/health > /dev/null && echo "✅ Бэкенд работает" || echo "❌ Бэкенд не работает"
    ;;
  frontend)
    echo "🔄 Запуск фронтенда..."
    cd /var/www/aidermy
    pkill -f "next-server" 2>/dev/null
    pkill -f "node.*next" 2>/dev/null
    npm start > next.log 2>&1 &
    sleep 3
    curl -s http://127.0.0.1:3000 > /dev/null && echo "✅ Фронтенд работает" || echo "❌ Фронтенд не работает"
    ;;
  all)
    $0 backend
    $0 frontend
    ;;
  status)
    echo "=== ПРОЦЕССЫ ==="
    ps aux | grep -E 'gunicorn|next-server' | grep -v grep
    echo ""
    echo "=== ПОРТЫ ==="
    lsof -i :8000 > /dev/null 2>&1 && echo "✅ Бэкенд (8000) запущен" || echo "❌ Бэкенд (8000) не запущен"
    lsof -i :3000 > /dev/null 2>&1 && echo "✅ Фронтенд (3000) запущен" || echo "❌ Фронтенд (3000) не запущен"
    ;;
  logs)
    tail -f /var/www/aidermy/next.log
    ;;
  *)
    echo "Использование: ./start.sh {backend|frontend|all|status|logs}"
    ;;
esac
