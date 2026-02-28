#!/usr/bin/env bash
set -euo pipefail

# Установка SSL-сертификата Let's Encrypt для мехмат-билеты.рф
# Запускать после того, как DNS A-запись заработает.

DOMAIN="xn----7sbendrvcb5df1a1g.xn--p1ai"

# 1. Установить certbot
if ! command -v certbot &>/dev/null; then
    echo "Устанавливаю certbot..."
    sudo apt update
    sudo apt install -y certbot python3-certbot-nginx
fi

# 2. Проверить что домен резолвится
echo "Проверяю DNS для $DOMAIN..."
if ! host "$DOMAIN" &>/dev/null; then
    echo "Ошибка: домен $DOMAIN не резолвится. Добавь A-запись у регистратора."
    exit 1
fi

# 3. Выпустить сертификат (certbot сам обновит nginx конфиг)
echo "Выпускаю сертификат..."
sudo certbot --nginx -d "$DOMAIN"

# 4. Проверить автообновление
echo "Проверяю автообновление..."
sudo certbot renew --dry-run

echo ""
echo "SSL установлен. Сайт доступен по https://$DOMAIN"
