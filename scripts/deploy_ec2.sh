#!/bin/bash
# EC2 first-time setup script
# Run this once on a fresh Ubuntu 22.04 EC2 instance
# chmod +x deploy_ec2.sh && ./deploy_ec2.sh

set -e

echo "==> Updating system..."
sudo apt-get update -qq && sudo apt-get upgrade -y -qq

echo "==> Installing Docker..."
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update -qq
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Run Docker without sudo
sudo usermod -aG docker $USER
newgrp docker

echo "==> Installing Git..."
sudo apt-get install -y git

echo "==> Cloning repo..."
# Replace with your actual repo URL
git clone https://github.com/YOUR_USERNAME/tradingagents-platform.git
cd tradingagents-platform

echo "==> Setting up environment..."
cp .env.example .env
echo ""
echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
echo "IMPORTANT: Edit .env now with your actual keys:"
echo "  nano .env"
echo "Then re-run: docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d"
echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
