# 1 · Шпаргалка: CLI, схема, запросы, ошибки | short: Шпаргалка | kind: ref
**CLI Prisma 7**

| Что | Команда |
|---|---|
| версия (проверь, что `7.x`) | `npx prisma --version` |
| проверить и отформатировать схему | `npx prisma validate`, `npx prisma format` |
| прочитать базу в схему | `npx prisma db pull` (`--print` — без записи) |
| создать клиент | `npx prisma generate` — **вручную** после каждой правки схемы; с TypedSQL — всегда `npx prisma generate --sql` (в лабе — `npm run generate`): обычный `generate` стирает `sql.ts` |
| миграция в разработке | `npx prisma migrate dev --name имя` (`--create-only` — только создать, не применять) |
| применить миграции (CI, прод) | `npx prisma migrate deploy` |
| состояние истории | `npx prisma migrate status` |
| пометить применённой / откатанной | `npx prisma migrate resolve --applied имя` / `--rolled-back имя` |
| сбросить базу (**удаляет данные**, только dev) | `npx prisma migrate reset` |
| сравнить источники | `npx prisma migrate diff --from-… --to-… [--script] [--exit-code]` |
| baseline существующей базы | `migrate diff --from-empty --to-schema prisma/schema.prisma --script > prisma/migrations/0_init/migration.sql`, затем `migrate resolve --applied 0_init` |
| сид | `npx prisma db seed` (сам не запускается) |
| окно данных | `npx prisma studio` |

Источники для `migrate diff` (Prisma 7): `--from-empty`, `--from-schema`, `--from-migrations`, `--from-config-datasource` и парные `--to-…`; `--exit-code`: 0 — одинаково, 2 — есть различия.

**Конфиг и клиент**

```ts
// prisma.config.ts
import 'dotenv/config'
import { defineConfig, env } from 'prisma/config'
export default defineConfig({
  schema: 'prisma/schema.prisma',
  migrations: { path: 'prisma/migrations', seed: 'tsx prisma/seed.ts' },
  datasource: { url: env('DATABASE_URL') },        // + shadowDatabaseUrl при необходимости
})
```

```ts
// клиент с адаптером
import { PrismaPg } from '@prisma/adapter-pg'
import { PrismaClient } from './generated/prisma/client.js'
const prisma = new PrismaClient({ adapter: new PrismaPg({ connectionString, max: 10, connectionTimeoutMillis: 3000 }) })
```

**Схема**

| Элемент | Пример |
|---|---|
| поле | `title String`, `note String?`, `tags String[]` |
| ключ и умолчание | `@id @default(autoincrement())`, `@default(now())`, `@default(dbgenerated("gen_random_uuid()"))` |
| имя в базе | `@map("col")`, `@@map("tbl")` |
| тип PostgreSQL | `@db.VarChar(100)`, `@db.Decimal(12, 2)`, `@db.Timestamptz(3)`, `@db.JsonB` |
| связь | `customer Customer? @relation(fields: [customerId], references: [id], onDelete: Restrict)` |
| индексы | `@@index([a, b])`, `@@index([a, b(sort: Desc)])`, `@@unique([a, b])` |
| неподдерживаемое | `Unsupported("tstzrange")?` |
| режим связей | `relationMode = "prisma"` (без внешних ключей в базе) |
| preview | `previewFeatures = ["relationJoins", "typedSql"]` |

**Запросы**

| Что | Пример |
|---|---|
| чтение | `findMany`, `findFirst`, `findUnique`, `…OrThrow`, `count`, `aggregate`, `groupBy` |
| условия | `equals`, `not`, `in`, `lt/lte/gt/gte`, `contains/startsWith/endsWith` (+`mode: 'insensitive'`), `AND/OR/NOT` |
| форма | `select`, `omit`, `include`, `orderBy`, `take`, `skip`, `cursor`, `distinct` |
| связи | `some/every/none`, `is/isNot`, `_count`, `relationLoadStrategy: 'join'` |
| запись | `create`, `update`, `upsert`, `delete`, `createMany`, `createManyAndReturn`, `updateMany`, `deleteMany` |
| атомарно | `{ increment: 1 }`, `{ decrement: 1 }` |
| вложенные записи | `create`, `connect`, `connectOrCreate`, `disconnect` |
| raw | ``$queryRaw`…${v}…` ``, ``$executeRaw`…` ``, `Prisma.sql`, `Prisma.join`, `Prisma.empty`; `$queryRawTyped(fn(...))` |
| транзакции | `$transaction([a, b])`, `$transaction(async (tx) => …, { isolationLevel, maxWait, timeout })` |
| расширения | `$extends({ query, result, model, client })`, `Prisma.defineExtension` |
| события | `log: [{ emit: 'event', level: 'query' }]`, `prisma.$on('query', e => …)` |

**Типы PostgreSQL ↔ TypeScript**

| PostgreSQL | Prisma | TS |
|---|---|---|
| `integer`, `smallint` | `Int` | `number` |
| `bigint` | `BigInt` | `bigint` |
| `numeric(12,2)` | `Decimal` | `Prisma.Decimal` |
| `double precision` | `Float` | `number` |
| `text`, `varchar` | `String` | `string` |
| `timestamptz` | `DateTime` | `Date` |
| `jsonb` | `Json` | `Prisma.JsonValue` |

**Коды ошибок клиента**

| Код | Смысл |
|---|---|
| `P2002` | нарушено ограничение уникальности (с адаптером `pg` имя ограничения — в `meta.driverAdapterError.cause.constraint`) |
| `P2003` | нарушен внешний ключ |
| `P2025` | запись не найдена (update/delete/connect) |
| `P2028` | ошибка API транзакции (таймаут, закрыта) |
| `P2034` | конфликт записи или дедлок — **повторить транзакцию** |
| `P2010` | ошибка сырого запроса (код PostgreSQL в `meta`) |

**PostgreSQL под рукой**

| Что | Команда |
|---|---|
| вход | `docker exec -it rental-pg psql -U postgres -d rental` |
| план | `EXPLAIN (ANALYZE, BUFFERS) …` |
| соединения | `SELECT state, count(*) FROM pg_stat_activity GROUP BY 1` |
| дорогие запросы | `SELECT calls, total_exec_time, query FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 5` |
| блокировки | `SELECT pid, pg_blocking_pids(pid), query FROM pg_stat_activity WHERE cardinality(pg_blocking_pids(pid)) > 0` |
| дамп / восстановление | `pg_dump -Fc --no-owner --no-acl` / `pg_restore --no-owner --no-acl -d база < файл` |
