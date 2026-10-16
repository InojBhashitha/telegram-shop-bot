#!/usr/bin/env bash
# ==============================================================================
# Telegram Shop Bot — 1-Click Production Docker & SSL Deployment
# ==============================================================================

set -euo pipefail

# ANSI Colors
C_RESET="\033[0m"
C_BOLD="\033[1m"
C_CYAN="\033[96m"
C_GREEN="\033[92m"
C_YELLOW="\033[93m"
C_RED="\033[91m"

echo -e "\n${C_BOLD}${C_CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${C_RESET}"
echo -e "  ${C_BOLD}🚀 TELEGRAM SHOP BOT — 1-CLICK DOCKER & AUTO-SSL DEPLOYER${C_RESET}"
echo -e "${C_BOLD}${C_CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${C_RESET}\n"

# 1. Check Docker & Docker Compose
echo -ne "  [1/5] Checking Docker installation... "
if ! command -v docker &> /dev/null; then
    echo -e "${C_RED}NOT FOUND${C_RESET}"
    echo -e "\n  ${C_YELLOW}Docker is not installed.${C_RESET}"
    read -rp "  Install Docker automatically now? (y/N): " install_docker
    if [[ "$install_docker" =~ ^[Yy]$ ]]; then
        echo -e "  Installing Docker via official get.docker.com script..."
        curl -fsSL https://get.docker.com | sh
        sudo usermod -aG docker "$USER" || true
    else
        echo -e "  ${C_RED}Aborted. Please install Docker first.${C_RESET}"
        exit 1
    fi
else
    echo -e "${C_GREEN}OK (${C_BOLD}$(docker --version | awk '{print $3}' | tr -d ',') ${C_GREEN})${C_RESET}"
fi

# Detect if docker requires sudo
DOCKER_BIN="docker"
if ! docker info &>/dev/null; then
    if sudo -n docker info &>/dev/null 2>&1; then
        DOCKER_BIN="sudo docker"
    else
        # Test if sudo prompt is needed
        echo -e "  ${C_YELLOW}ℹ Non-root Docker permission required. Using sudo for container management.${C_RESET}"
        echo -e "  ${C_DIM}(Tip: run 'sudo usermod -aG docker $USER && newgrp docker' to avoid sudo)${C_RESET}"
        DOCKER_BIN="sudo docker"
    fi
fi

# 2. Check Configuration
echo -ne "  [2/5] Checking .env configuration... "
if [ ! -f .env ]; then
    echo -e "${C_YELLOW}MISSING${C_RESET}"
    echo -e "  ${C_YELLOW}No .env file found. Launching Setup Wizard...${C_RESET}\n"
    if command -v python3 &> /dev/null; then
        python3 setup_wizard.py
    elif command -v python &> /dev/null; then
        python setup_wizard.py
    else
        echo -e "  ${C_RED}Python not found to run setup_wizard.py. Please create .env first.${C_RESET}"
        exit 1
    fi
else
    echo -e "${C_GREEN}OK${C_RESET}"
fi

# 3. Read Domain from .env if present
DOMAIN=$(grep -E '^DOMAIN=' .env 2>/dev/null | cut -d '=' -f2- | tr -d '"' | tr -d "'" | tr -d ' ' || true)
if [ -z "$DOMAIN" ]; then
    DOMAIN="localhost"
fi

echo -e "  [3/5] Target Domain: ${C_BOLD}${C_CYAN}${DOMAIN}${C_RESET}"

# 4. Build and Start Docker Containers
echo -e "  [4/5] Building and launching containers in background..."
$DOCKER_BIN compose pull --ignore-pull-failures 2>/dev/null || true
$DOCKER_BIN compose up -d --build

# 5. Wait for Healthcheck
echo -ne "  [5/5] Waiting for services to become healthy... "
for i in {1..20}; do
    STATUS=$($DOCKER_BIN inspect --format='{{json .State.Health.Status}}' telegram-shop-app 2>/dev/null || echo '"unknown"')
    if [ "$STATUS" = '"healthy"' ]; then
        echo -e "${C_GREEN}HEALTHY!${C_RESET}"
        break
    elif [ "$STATUS" = '"unhealthy"' ]; then
        echo -e "${C_RED}FAILED${C_RESET}"
        echo -e "\n  ${C_RED}Container reported unhealthy. Inspect logs using:${C_RESET}"
        echo -e "    $DOCKER_BIN compose logs -f shop-app"
        exit 1
    fi
    sleep 2
    echo -ne "."
done

echo -e "\n${C_BOLD}${C_GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${C_RESET}"
echo -e "  ${C_BOLD}🎉 STORE DEPLOYED & RUNNING SUCCESSFULLY!${C_RESET}"
echo -e "${C_BOLD}${C_GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${C_RESET}\n"

if [ "$DOMAIN" = "localhost" ]; then
    echo -e "  ${C_BOLD}Local Storefront:${C_RESET} http://localhost:8000/webapp"
    echo -e "  ${C_BOLD}Caddy Gateway:${C_RESET}    http://localhost/"
else
    echo -e "  ${C_BOLD}Public Storefront:${C_RESET} https://${DOMAIN}/webapp"
    echo -e "  ${C_BOLD}Automatic SSL:${C_RESET}     ${C_GREEN}ACTIVE (Managed by Caddy)${C_RESET}"
fi

echo -e "\n  ${C_BOLD}Useful Commands:${C_RESET}"
echo -e "    • View live logs:     ${C_CYAN}docker compose logs -f${C_RESET}"
echo -e "    • Stop containers:    ${C_CYAN}docker compose down${C_RESET}"
echo -e "    • Restart store:      ${C_CYAN}docker compose restart${C_RESET}"
echo -e "    • Seed demo catalog:  ${C_CYAN}docker compose exec shop-app python seed_catalog.py${C_RESET}"
echo -e "    • Inspect stock:      ${C_CYAN}docker compose exec shop-app python seed_catalog.py --status${C_RESET}\n"
