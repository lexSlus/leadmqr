.PHONY: help network-up network-down monitor-up monitor-down browser-up browser-down workers-up workers-down all-up all-down logs

help: ## Показать справку
	@echo "Доступные команды:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

network-create: ## Создать общую сеть thumbtack_network
	@echo "Создание сети thumbtack_network..."
	@docker network create thumbtack_network 2>/dev/null || echo "Сеть уже существует"

network-rm: ## Удалить сеть thumbtack_network
	@echo "Удаление сети thumbtack_network..."
	@docker network rm thumbtack_network 2>/dev/null || echo "Сеть не найдена"

monitor-up: ## Запустить monitor_service (с инфраструктурой)
	cd monitor_service && docker-compose up -d

monitor-down: ## Остановить monitor_service
	cd monitor_service && docker-compose down

monitor-logs: ## Показать логи monitor_service
	docker logs -f monitor_service

browser-up: ## Запустить browser_service
	cd browser_service && docker-compose up -d

browser-down: ## Остановить browser_service
	cd browser_service && docker-compose down

browser-logs: ## Показать логи browser_service
	docker logs -f browser_service

workers-up: ## Запустить workers
	cd workers && docker-compose up -d

workers-down: ## Остановить workers
	cd workers && docker-compose down

workers-logs: ## Показать логи workers
	docker logs -f celery_worker

all-up: network-create ## Запустить все сервисы
	@echo "Запуск всех сервисов..."
	$(MAKE) monitor-up
	@echo "Ожидание готовности RabbitMQ..."
	@sleep 5
	$(MAKE) browser-up
	@echo "Ожидание готовности browser_service..."
	@sleep 3
	$(MAKE) workers-up
	@echo "Все сервисы запущены!"
	@echo "Не забудьте применить миграции: make migrate"

all-down: ## Остановить все сервисы
	@echo "Остановка всех сервисов..."
	$(MAKE) workers-down
	$(MAKE) browser-down
	$(MAKE) monitor-down

migrate: ## Применить миграции Alembic
	docker exec -it monitor_service alembic upgrade head

logs: ## Показать логи всех сервисов
	@echo "Логи monitor_service (Ctrl+C для выхода):"
	@docker logs -f monitor_service &
	@echo "Логи browser_service:"
	@docker logs -f browser_service &
	@echo "Логи workers:"
	@docker logs -f celery_worker &
	@wait

ps: ## Показать статус всех контейнеров
	docker ps --filter "name=monitor_service|browser_service|celery_worker|rabbitmq|postgres"

