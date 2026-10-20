# 5 · Что дальше | short: Что дальше | kind: ref
Ты прошла весь путь: от чужой «грязной» базы до слоя данных с чистыми типами, гарантированными инвариантами, изоляцией филиалов, тестами и поставкой. Что открывается теперь:

- **Express, NestJS, GraphQL (следующие лабы цепочки Node-бэкенда).** Prisma 7 в них уже есть как «гарнир»: теперь ты понимаешь, что стоит за `include`, `$transaction` и кодами `P2002`. Выбирай Express (`сам Node и HTTP`), затем NestJS и GraphQL.
- **Prisma ORM 8.** Документация сайта prisma.io уже по умолчанию про неё (пока release candidate). Это **другая модель работы**, а не обновление:

| Что | Prisma 7 (эта лаба) | Prisma ORM 8 |
|---|---|---|
| описание данных | `schema.prisma`, `prisma.config.ts` | контракт `contract.prisma` (первая строка `// use prisma-8`) или контракт на TypeScript |
| клиент | `prisma generate`, `@prisma/client` | `npx prisma contract emit`, нет `@prisma/client`, свой `db` |
| запросы | `prisma.user.findMany({ include })` | `db.orm.public.User.include("posts").all()`, SQL/pipeline builder |
| миграции | `migrate dev`, `migrate deploy` | `migration plan` → ревью → `db migrate --advance-ref`; граф миграций |
| перехват запросов | `$extends` | middleware (budgets, lints, cache) |
| базы | PostgreSQL, MySQL, SQLite, MongoDB… | PostgreSQL (RC), MongoDB (early access), SQLite (экспериментально) |

  Когда пересматривать выбор: после финального релиза 8, когда она поддержит нужные базы и когда срок поддержки Prisma 7 станет аргументом. Установка Prisma 8 рядом с 7 в одном приложении — путь из документации «Coming from Prisma ORM 7». Весь слой данных этой лабы (SQL-миграции, `EXCLUDE`, RLS, триггеры, ledger) переносится как есть: меняется только способ описать данные и ходить в базу.
- **Другие инструменты для сравнения.** Drizzle и Kysely — «ближе к SQL», с иным балансом типов и удобства; полезно один раз сделать на них хотя бы три запроса из этой лабы.
- **Prisma Accelerate, Optimize, Postgres.** Облачные продукты Prisma (кэш, пул, анализ запросов, хостинг); в лабе не использовались, ты понимаешь, какие задачи они решают (пул соединений — 17.1–17.3, анализ запросов — 8.3 и 17.4).
- **PostgreSQL глубже.** Партиционирование, репликация, логическая репликация, `pg_repack`, расширения (PostGIS, pgvector) — PostgreSQL-лаба и документация; всё, что ты делала в этой лабе, работает поверх.
- **Kubernetes.** Если развернёшь такую систему в кластере: миграции — отдельная Job на релиз (18.4), роль приложения — через Secret, пул — по числу реплик (17.1).
- **Наблюдаемость.** Метрики и трассировки слоя данных (18.5) — на настоящий стек: Prometheus, Grafana, Tempo/Jaeger.

Что почитать: [документация Prisma 7](https://www.prisma.io/docs/orm/v7), [документация PostgreSQL 18](https://www.postgresql.org/docs/18/), [Use The Index, Luke](https://use-the-index-luke.com/), [документация Vitest](https://vitest.dev/).
