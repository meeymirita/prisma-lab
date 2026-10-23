# Prisma Lab — «Наследство»: чужая база на Prisma 7 и TypeScript

Лаба по Prisma ORM 7 на сквозном проекте **«Прокат снаряжения» (RentKit)**: вам достаётся чужая рабочая база с грязными данными, без внешних ключей, с дублями и датами в трёх форматах, и её нужно превратить в типизированный слой данных на Prisma + TypeScript, не останавливая «прод». Внутри — линии «деньги» (ledger, идемпотентность, `Decimal`) и «мультитенантность» (филиалы, RLS, client extensions).

**Статус: 🟡 написана 20.10.2026 (19 сессий, 126 шагов, ~76 ч); 22.10.2026 прогнана целиком в Docker (PostgreSQL 18.6, Node 24, Prisma 7.10.1, TypeScript 6.0, Vitest 5): все блоки выполнены по порядку с чистой базы из дампа, 119 блоков «Ожидаемого результата» — настоящий вывод; найдено и исправлено около сорока расхождений. Решения заданий 🔨 — не проверено; PgBouncer, GitHub Actions и сборка образа целиком не проверялись. Подробности — [fixes/backend/prisma.md](https://github.com/meeymirita/lab-fixes/blob/main/backend/prisma.md); план — [`prisma_lab_plan.md`](prisma_lab_plan.md).**

## Что по плану

- 18 сессий + 19-я итоговая (ТЗ без ответа), по ~4 часа, ~76 ч; сложность — средняя–высокая.
- Версия: **Prisma 7** (`prisma@7`; на npm `latest` уже Prisma ORM 8 RC — версии закрепляются явно), PostgreSQL 18, Node 24, TypeScript минимум (объясняется по ходу).
- Вход — стартовый дамп базы (`starter/`, только он). Предзнания — PostgreSQL-лаба.
- Место в порядке: после PostgreSQL, до Express, NestJS и GraphQL (там Prisma-шаги остались, ссылки сюда добавлены).

## Что в репозитории

| Файл | Что |
|---|---|
| `prisma.html` | методичка (собирается из `src/`) |
| `src/*.md` | исходники: `00-meta.md`, `01…19-session.md`, справка `ref-*.md`, `gloss.md`, `schemes.py` (16 схем) |
| `tools/legacy_seed.sql`, `tools/make_dump.sh` | генератор «наследства» и скрипт дампа (запущены 20.10.2026, ~2 минуты) |
| `starter/rental-legacy.dump` | единственный стартовый файл читателя (12 МБ); для читателей раздаётся из бакета: https://meeymirita-files.storage.yandexcloud.net/prisma/rental-legacy.dump |
| `prisma_lab_plan.md` | план лабы: сессии, «грязь» в базе, решения владельца |
| `LICENSE`, `NOTICE` | лицензия и авторство |

Обложка лежит не здесь, а в `works/images/prisma.png` родительского репозитория (так у всех лаб).

## Что дальше

Повторить прогон: `RESET=1 python3 tools/build-manual.py prisma --run --allow-missing` из корня родительского репозитория (нужен Docker; образ — `prisma/Dockerfile`, режим Docker-в-Docker — `prisma/src/run.json`; блоки `ts … file=` записывают файлы шагов, `schema` вносит модели в `schema.prisma` через `tools/schema-merge.mjs`).
