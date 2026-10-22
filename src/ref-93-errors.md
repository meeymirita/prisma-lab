# 2 · Справочник ошибок: симптом → причина → что делать | short: Справочник ошибок | kind: ref
Диагностика идёт сверху вниз: **окружение → подключение → схема и клиент → миграции → запросы → транзакции → пул**. Главные инструменты: лог запросов (`SQL_LOG=1`), `EXPLAIN`, `psql`, `migrate status`.

**Установка и окружение**

| Симптом | Причина | Что делать |
|---|---|---|
| `prisma --version` показывает 8.x | поставлен `latest` вместо Prisma 7 | закрепить `prisma@7`, `@prisma/client@7`, `@prisma/adapter-pg@7`; чистая установка (1.4) |
| `Environment variable not found: DATABASE_URL` | `.env` не подхвачен | `import 'dotenv/config'` в `prisma.config.ts` и в `db.ts` |
| `datasource property url is no longer supported` | адрес остался в `schema.prisma` | адрес — только в `prisma.config.ts` |
| `Cannot find module './generated/prisma/client.js'` | не запущен `generate` или другой `output` | `npx prisma generate`; проверить `output` (4.6) |
| `Cannot find module '…/generated/prisma/sql.js'` или `TS2307` на импорте TypedSQL | обычный `generate` без `--sql` стёр `sql.ts` | всегда `npm run generate` = `prisma generate --sql` (9.5) |
| `Failed to load config file … Cannot resolve environment variable: DATABASE_URL` в скрипте | скрипт не импортирует `db.ts`, `.env` никто не прочитал | `import 'dotenv/config'` первой строкой скрипта |
| типы «старые» после правки схемы | `generate` не запускается сам (Prisma 7) | запускать вручную, добавить в `postinstall` (4.7) |
| `prisma.$use is not a function` | middleware убран | `$extends` с компонентом `query` (15.1) |
| ошибка адаптера: `adapter` обязателен | клиент Prisma 7 без `PrismaPg` | передать `adapter` в конструктор (4.6) |

**Подключение и пул**

| Симптом | Причина | Что делать |
|---|---|---|
| `P1001: Can't reach database server` | контейнер не запущен, не тот порт | `docker ps`, `docker start rental-pg`, порт 5433 |
| `P1017: Server has closed the connection` | сервер оборвал соединение (рестарт, таймаут) | повторить, проверить таймауты (17.6) |
| `sorry, too many clients already` | суммарные пулы превысили `max_connections` | один клиент на процесс; посчитать `процессы × max` (17.1–17.2) |
| запросы «зависли», сервис молчит | пул исчерпан транзакциями | не делать долгого в транзакции; `maxWait`, `connectionTimeoutMillis` (12.5, 17.7) |
| `P2028: Unable to start a transaction in the given time` | нет свободного соединения за `maxWait` | освободить пул, сократить транзакции |
| `prepared statement "s0" already exists` | пулер в режиме без prepared statements | `max_prepared_statements` > 0 / режим `transaction` (17.3) |

**Миграции**

| Симптом | Причина | Что делать |
|---|---|---|
| `P3005: database schema is not empty` | `migrate deploy` к непустой базе без baseline | baseline: `migrate diff … > 0_init`, `migrate resolve --applied 0_init` (3.4) |
| `P3006: Migration failed to apply cleanly to the shadow database` | история не проигрывается с нуля | исправить миграцию (3.4, 18.3); частые причины: объект, которого на shadow-базе ещё нет (`_prisma_migrations`, 16.2), и `ALTER COLUMN … DROP DEFAULT` на генерируемой колонке |
| `column "…" of relation … is a generated column` + `DROP DEFAULT` в автомиграции | Prisma не знает про `GENERATED ALWAYS` | `@default(dbgenerated())` у поля (11.4, 13.3) |
| `migrate dev --create-only` создал файл с одной строкой `-- This is an empty migration.` | Prisma 7 создаёт файл всегда, даже если менять нечего | это признак «схема = база»; папку удалить (4.5, 8.5) |
| автомиграция хочет `DROP INDEX` у ручного GIN-индекса | Prisma умеет описать `Gin`-индекс, а он не описан | `@@index([поле(ops: raw("gin_trgm_ops"))], type: Gin, map: "…")` (8.5) |
| `P3009`/`P3018`: миграция не применилась | SQL упал на базе | прочитать ошибку; исправить новой миграцией; `migrate resolve --rolled-back` |
| `Drift detected` и вопрос «reset?» | база изменена мимо миграций | **не соглашаться**; откатить правку или зафиксировать миграцией и `resolve --applied` (11.5) |
| «migration was modified after it was applied» | правили применённую миграцию | вернуть файл; правка — новой миграцией (11.7) |
| миграция «переименование» удалила данные | авто-SQL = `DROP` + `ADD` | `--create-only`, править на `RENAME COLUMN` (10.2) |
| `SET NOT NULL` долго блокирует таблицу | нет проверенного `CHECK` | `CHECK … NOT VALID` → `VALIDATE` → `SET NOT NULL` (11.3) |
| `VALIDATE CONSTRAINT` падает | в данных есть нарушения (сироты, дубли) | найти запросом, исправить, повторить (11.1) |

**Запросы и данные**

| Симптом | Причина | Что делать |
|---|---|---|
| запрос медленный | `Seq Scan`, нет индекса, N+1 | лог запросов → `EXPLAIN` → индекс или `include` (6.3, 8.3) |
| сотни запросов вместо одного | N+1 в цикле | `include`/`IN`/`relationLoadStrategy: 'join'` (6.3–6.4) |
| индекс есть, не используется | `ILIKE`, ведущий `%`, функция над колонкой | триграммный GIN, индекс по выражению (8.5, 8.7) |
| глубокая страница медленная | `OFFSET` линеен | `cursor`/keyset (8.2) |
| `TypeError: Do not know how to serialize a BigInt` | `bigint` из `count`/`bigint`-колонки в JSON | `Number(x)`/строка до отдачи (7.4) |
| копейки не сходятся | деньги в `number`/`float` | `Decimal`, `numeric(12,2)`, явное округление (14.1) |
| таблица «не видна» клиенту | нет первичного ключа (`@@ignore`) | добавить ключ миграцией (3.6) |
| поле «не пришло» | не в `select`, а `as any` скрыл ошибку | добавить поле, убрать `as any` (5.7) |
| `Unique constraint failed` (`P2002`) | дубль | перевести в доменную ошибку; для идемпотентности вернуть существующее (7.6, 14.3) |

**Транзакции, права, изоляция**

| Симптом | Причина | Что делать |
|---|---|---|
| потерянное обновление | «прочитал — прибавил — записал» | `increment`, версия, `FOR UPDATE` (12.3) |
| лимит нарушен при параллельных запросах | write skew | `Serializable` + повтор по `P2034` (12.4) |
| `P2034` | конфликт или дедлок | повторить транзакцию целиком; для дедлока — единый порядок блокировок (12.4, 12.7) |
| двойная бронь | проверка в коде, гонка | `EXCLUDE` в базе (13.3) |
| бронь «не в том дне» в отчёте | дата считана в поясе сессии | `AT TIME ZONE tz` филиала (13.7) |
| `permission denied for table …` | у роли нет прав | `GRANT`; новые таблицы — `DEFAULT PRIVILEGES` (16.2) |
| филиал видит чужие данные | `set_config(…, false)`, параметр остался на соединении из пула | `true` и запрос в одной транзакции (16.4, 16.7) |
| тест изоляции зелёный, а утечка есть | тест под владельцем (обходит RLS) | запускать под `rental_app` (16.6) |
| soft delete «протекает» | обход через связи, `_count`, raw | тесты на обход; перенос правила в базу (15.7) |
| `invalid input syntax for type integer: ""` | пустая строка в параметре сессии | `NULLIF(current_setting(…), '')` (16.3) |
