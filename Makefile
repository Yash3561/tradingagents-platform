.PHONY: up down dev frontend backend logs clean

# Start all services
up:
	docker compose --profile dev up -d

# Stop all services
down:
	docker compose down

# Frontend dev server (local, no Docker)
frontend:
	cd frontend && npm install && npm run dev

# Backend dev server (local, no Docker)
backend:
	cd backend && uvicorn app.main:app --reload --port 8000

# View logs
logs:
	docker compose logs -f backend frontend

# Clean volumes (WARNING: deletes all data)
clean:
	docker compose down -v

# Install frontend deps
install-fe:
	cd frontend && npm install

# Run DB migrations
migrate:
	cd backend && alembic upgrade head

# Seed dev data
seed:
	cd backend && python -m scripts.seed_dev
