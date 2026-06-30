#!/bin/bash
# Oracle Cloud Free Tier — ARM Ubuntu 22.04 setup
# Free forever: 4 ARM cores, 24GB RAM
# Run once after SSH-ing into your instance:
# ssh ubuntu@YOUR_ORACLE_IP
# curl -s https://raw.githubusercontent.com/YOUR_USERNAME/tradingagents-platform/main/scripts/deploy_oracle.sh | bash

set -e

echo "==> Updating system..."
sudo apt-get update -qq && sudo apt-get upgrade -y -qq

echo "==> Installing Docker..."
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
newgrp docker

echo "==> Installing Git + extras..."
sudo apt-get install -y git nginx-common

echo "==> Configuring firewall (Oracle uses iptables, not ufw by default)..."
# Oracle Cloud blocks ports at the OS level too — open 80 and 443
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save 2>/dev/null || true

echo "==> Cloning repo..."
git clone https://github.com/YOUR_USERNAME/tradingagents-platform.git
cd tradingagents-platform

echo "==> Setting up .env..."
cp .env.example .env

echo ""
echo "=============================================="
echo " NEXT STEPS:"
echo "=============================================="
echo " 1. Edit your environment file:"
echo "    nano .env"
echo ""
echo " 2. Fill in:"
echo "    ANTHROPIC_API_KEY=sk-ant-..."
echo "    ALPACA_API_KEY=PK..."
echo "    ALPACA_API_SECRET=..."
echo "    FRONTEND_URL=https://your-app.vercel.app"
echo ""
echo " 3. Start everything:"
echo "    docker compose up -d"
echo ""
echo " 4. Check it works:"
echo "    curl http://localhost:8000/health"
echo "=============================================="
