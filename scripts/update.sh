#!/bin/bash
# Run this on EC2 to pull latest code and restart services
# ./scripts/update.sh

set -e
cd "$(dirname "$0")/.."

echo "==> Pulling latest..."
git pull origin main

echo "==> Rebuilding backend image..."
docker compose build backend worker

echo "==> Restarting services..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-deps backend worker nginx

echo "==> Done. Logs:"
docker compose logs --tail=20 backend
