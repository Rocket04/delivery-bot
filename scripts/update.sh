#!/usr/bin/env bash
# Обновление бота на VPS одной командой: git pull -> rebuld + restart.
# Запуск:  bash scripts/update.sh     (из корня проекта или из любого места)
# Зависимости кешируются в Docker-слое, поэтому пересборка кода — секунды.
set -euo pipefail

cd "$(dirname "$0")/.."          # корень проекта

git pull --ff-only
docker compose up -d --build

echo "OK: бот обновлён и перезапущен."
echo "Логи: docker compose logs -f bot"