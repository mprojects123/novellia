.PHONY: up down logs psql restart

up:
	docker compose up --build

down:
	docker compose down -v

logs:
	docker compose logs -f api

psql:
	docker compose exec db psql -U novellia -d novellia

restart:
	docker compose down -v && docker compose up --build
