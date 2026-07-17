# Makefile для Aidermy

# Переменные
SERVER_IP = 138.124.231.42
SERVER_USER = root
PROJECT_DIR = /var/www/aidermy
BACKEND_DIR = $(PROJECT_DIR)/backend

# === ОБНОВЛЕНИЕ ===
pull:
	ssh $(SERVER_USER)@$(SERVER_IP) "cd $(PROJECT_DIR) && git pull"

# === БЭКЕНД ===
backend: pull
	ssh $(SERVER_USER)@$(SERVER_IP) "cd $(BACKEND_DIR) && source venv/bin/activate && pkill -f gunicorn && gunicorn -w 1 -k uvicorn.workers.UvicornWorker app.main:app --bind 127.0.0.1:8000 --daemon"
	@echo "✅ Бэкенд перезапущен"

# === ФРОНТ ===
frontend: pull
	ssh $(SERVER_USER)@$(SERVER_IP) "cd $(PROJECT_DIR) && npm install && npm run build && pkill -f next && npm start > next.log 2>&1 &"
	@echo "✅ Фронтенд перезапущен"

# === ВСЁ ВМЕСТЕ ===
all: backend frontend
	ssh $(SERVER_USER)@$(SERVER_IP) "systemctl reload nginx"
	@echo "✅ Всё обновлено и перезапущено"

# === ТОЛЬКО ПЕРЕЗАПУСК ===
restart-backend:
	ssh $(SERVER_USER)@$(SERVER_IP) "cd $(BACKEND_DIR) && source venv/bin/activate && pkill -f gunicorn && gunicorn -w 1 -k uvicorn.workers.UvicornWorker app.main:app --bind 127.0.0.1:8000 --daemon"
	@echo "✅ Бэкенд перезапущен"

restart-frontend:
	ssh $(SERVER_USER)@$(SERVER_IP) "cd $(PROJECT_DIR) && pkill -f next && npm start > next.log 2>&1 &"
	@echo "✅ Фронтенд перезапущен"

# === ЛОГИ ===
logs-backend:
	ssh $(SERVER_USER)@$(SERVER_IP) "tail -f $(BACKEND_DIR)/gunicorn.log"

logs-frontend:
	ssh $(SERVER_USER)@$(SERVER_IP) "tail -f $(PROJECT_DIR)/next.log"

# === СТАТУС ===
status:
	ssh $(SERVER_USER)@$(SERVER_IP) "ps aux | grep -E 'gunicorn|next' | grep -v grep"