#!/usr/bin/env bash
# Генерация стартового дампа starter/rental-legacy.dump (custom-формат, без владельцев и прав).
# ⚠ НЕ ЗАПУСКАЛСЯ (20.10.2026): написан вместе с методичкой, прогон — в очереди на проверку.
# Требует Docker. Временный контейнер rental-gen удаляется в конце. Запуск из корня репозитория: ./tools/make_dump.sh
set -euo pipefail
cd "$(dirname "$0")/.."
NAME=rental-gen
docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" -e POSTGRES_PASSWORD=postgres postgres:18 >/dev/null
trap 'docker rm -f "$NAME" >/dev/null 2>&1 || true' EXIT
until docker exec "$NAME" pg_isready -U postgres >/dev/null 2>&1; do sleep 1; done
sleep 2
docker exec "$NAME" psql -U postgres -v ON_ERROR_STOP=1 -c 'CREATE DATABASE rental' >/dev/null
docker exec -i "$NAME" psql -U postgres -d rental -v ON_ERROR_STOP=1 < tools/legacy_seed.sql
docker exec "$NAME" psql -U postgres -d rental -c 'SELECT (SELECT count(*) FROM "tbl_Branches") branches, (SELECT count(*) FROM "tbl_Items") items, (SELECT count(*) FROM "tbl_Customers") customers, (SELECT count(*) FROM "tbl_Bookings") bookings, (SELECT count(*) FROM "tbl_Payments") payments, (SELECT count(*) FROM "tbl_DepositLog") deposit_log'
mkdir -p starter
docker exec "$NAME" pg_dump -U postgres -d rental -Fc --no-owner --no-acl > starter/rental-legacy.dump
ls -l starter/rental-legacy.dump
