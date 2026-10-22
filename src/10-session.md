# Сессия 10 · Чистка данных I: миграции на живой базе
dur: ~4 ч

## 10.1 Как работает migrate dev: shadow database и история | short: Механика миграций | est: ~40 мин
### intro
**Слова шага:** *`migrate dev`*, *`migrate deploy`*, *shadow database*, *`_prisma_migrations`*, *контрольная сумма*, *`migration.sql`*.

:::tip Если совсем просто
`migrate dev` — это «примерка» на макете: Prisma строит временную копию базы (shadow), проигрывает на ней всю историю ремонта, сравнивает с тем, что ты теперь хочешь, и **сама пишет** недостающий SQL. `migrate deploy` — «боевой монтаж»: никаких примерок, просто выполнить то, что ещё не выполнено. Поэтому первый — для твоего ноутбука, второй — для всего остального.
:::

```svg
@migrate-flow
```

Посмотрим на историю глазами:

```bash run
cd ~/prisma-lab/rentkit
ls prisma/migrations
psqlr() { docker exec -i rental-pg psql -U postgres -d rental "$@"; }
psqlr -c 'SELECT migration_name, left(checksum, 12) AS checksum, finished_at IS NOT NULL AS applied FROM _prisma_migrations ORDER BY started_at'
npx prisma migrate status
```

### result
```out auto
```

Что здесь важно:

- Каждая папка в `prisma/migrations/` — одна миграция (`ГГГГММДДччммсс_имя`) с файлом `migration.sql`. Порядок применения — **по имени папки**.
- В базе таблица **`_prisma_migrations`** помнит, что уже применено, и **контрольную сумму** файла. Если после применения изменить `migration.sql`, `migrate dev` увидит расхождение и откажется работать — историю **не переписывают**.
- **`migrate dev`:** создаёт shadow-базу, проигрывает на ней историю, сравнивает результат со схемой, создаёт новую миграцию из разницы, применяет её и пересоздаёт клиент **только если ты сама запустишь `generate`** (в Prisma 7 автоматически не запускается).
- **`migrate deploy`:** только применяет ещё не применённые миграции; ничего не сравнивает, не создаёт, не спрашивает — для CI и продакшна.
- **`migrate status`:** покажет, что применено, а что нет, и есть ли расхождения.

### why
Понимание этого механизма отделяет «запускаю команды из статьи» от «знаю, что делаю». Три правила, из него вытекающие: историю не переписывают; `dev` — только локально; если `dev` просит сбросить базу, значит, что-то разошлось, и нужно разбираться, а не соглашаться.

### deep Команды по частям
`migrate dev --name X` — создать и применить миграцию с именем `X`; `--create-only` — создать, **не применяя** (дать возможность править SQL); `migrate reset` — удалить базу и применить всё заново (только для разработки, **удаляет данные**); `migrate resolve --applied|--rolled-back` — вручную поправить пометки в `_prisma_migrations`.

### deep Если не получилось
- **`migrate status` пишет про «drift»** — база отличается от истории: кто-то менял её мимо миграций. Разберём в 11.5; сейчас убедись, что не правила таблицы руками.
- **Нет `_prisma_migrations`** — baseline не выполнен (шаг 3.4).

### quiz
- Чем `migrate dev` отличается от `migrate deploy` и где каждый запускают?
- Что случится, если изменить уже применённый `migration.sql`?
- Зачем Prisma создаёт shadow-базу?

### links
- https://www.prisma.io/docs/orm/v7/prisma-migrate/understanding-prisma-migrate/mental-model | модель миграций | Prisma 7: Mental model
- https://www.prisma.io/docs/orm/v7/prisma-migrate/workflows/development-and-production | dev и prod | Prisma 7: Development and production

## 10.2 --create-only и ручная правка: переименование = DROP + ADD | short: Правка миграции | est: ~45 мин
### intro
**Слова шага:** *`--create-only`*, *деструктивная миграция*, *`RENAME COLUMN`*, *песочница*, *проверка SQL перед применением*.

:::tip Если совсем просто
Prisma умеет сравнивать схему с базой, но не умеет **понимать намерение**. Ты переименовала колонку — Prisma видит «одна пропала, другая появилась» и решает: старую удалить, новую создать. Данные из старой — в корзину. Единственная защита — **прочитать SQL до применения** и поправить его руками.
:::

Чтобы не рисковать настоящими таблицами, потренируемся на «песочнице»: заведём в схеме временную модель.

```prisma schema
model Scratch {
  id      Int     @id @default(autoincrement())
  oldName String? @map("old_name")
}
```

```bash run
cd ~/prisma-lab/rentkit
npx prisma migrate dev --name scratch_create
psqlr() { docker exec -i rental-pg psql -U postgres -d rental "$@"; }
psqlr -c "INSERT INTO \"Scratch\"(old_name) SELECT 'строка ' || g FROM generate_series(1, 5) g"
psqlr -c 'SELECT * FROM "Scratch" ORDER BY id'
```

### result
```out auto
```

Теперь «переименуем» поле: в схеме `oldName String? @map("old_name")` → `newName String? @map("new_name")`. И попросим Prisma составить миграцию, **не применяя** её:

```bash run hidden
cd ~/prisma-lab/rentkit && sed -i 's/oldName\( *\)String? @map("old_name")/newName\1String? @map("new_name")/' prisma/schema.prisma
```

```bash run
cd ~/prisma-lab/rentkit
npx prisma migrate dev --create-only --name scratch_rename
cat prisma/migrations/*_scratch_rename/migration.sql
```

### result
```out auto
```

Prisma предупредит о потере данных (`You are about to drop the column … 5 rows…`) и в SQL будет что-то вроде:

```sql
ALTER TABLE "Scratch" DROP COLUMN "old_name",
ADD COLUMN     "new_name" TEXT;
```

Это **удаление данных**. Исправь файл вручную на настоящее переименование и только потом применяй:

```sql into=prisma/migrations/*_scratch_rename/migration.sql
-- prisma/migrations/…_scratch_rename/migration.sql
ALTER TABLE "Scratch" RENAME COLUMN "old_name" TO "new_name";
```

```bash run
cd ~/prisma-lab/rentkit
npx prisma migrate dev
psqlr() { docker exec -i rental-pg psql -U postgres -d rental "$@"; }
psqlr -c 'SELECT * FROM "Scratch" ORDER BY id'
```

### result
```out auto
```

Данные на месте (`строка 1…5` в колонке `new_name`). Правило: **любая миграция, которая переименовывает, меняет тип или удаляет, проверяется глазами перед применением.** Для этого и нужен `--create-only`.

### why
Автоматическая генерация миграций — подарок для добавления, и источник катастроф для переименования и смены типа. На живой базе единственная защита — читать SQL: нет ли `DROP`, `ALTER … TYPE`, `NOT NULL` без значения по умолчанию. К этому приему мы будем прибегать в каждой миграции этой сессии.

### deep Как ещё можно
В схеме можно задать `@map` на **новое** имя, оставив прежнюю колонку: `newName String? @map("old_name")` — переименование **только в коде**, без миграции. Это самый безопасный способ переименовывать (мы так делали в сессии 4). Настоящее переименование колонки в базе нужно, только если тебе действительно важно имя в базе.

### deep Если не получилось
- **`migrate dev` применил миграцию сразу** — забыт `--create-only`; чтобы вернуть данные, придётся восстанавливать из дампа (шаг 1.7): в песочнице это пять строк, в боевой базе — катастрофа.
- **Prisma спрашивает, сбросить ли базу** — она нашла drift; откажись (`n`).

### quiz
- Почему Prisma превращает переименование в `DROP` + `ADD`?
- Зачем нужен флаг `--create-only` и что ты делаешь между созданием и применением?
- Чем «переименование через `@map`» безопаснее настоящего?

### links
- https://www.prisma.io/docs/orm/v7/prisma-migrate/workflows/customizing-migrations | ручная правка миграций | Prisma 7: Customizing migrations

## 10.3 Даты: text в трёх форматах → timestamptz (expand и backfill) | short: Даты: expand + backfill | est: ~65 мин
### intro
**Слова шага:** *expand/contract*, *новая колонка*, *backfill батчами*, *`timestamptz`*, *часовой пояс филиала*, *функция в базе*, *сверка счётчиков*.

:::tip Если совсем просто
Нельзя взять и «поменять тип колонки», пока «прод» работает: таблица на время перестройки блокируется, а при ошибке — потеря. Поэтому строим **рядом**: добавляем новую колонку правильного типа, **заполняем** её из старой небольшими порциями (пока все работают), проверяем, что всё перенеслось, — и только потом переключаем код и убираем старое.
:::

```svg
@expand-contract
```

**Шаг 1 — «расширяем» схему.** Добавь в модели **новые** поля (старые не трогай!):

```prisma schema
enum BookingStatus {
  DRAFT
  CONFIRMED
  ISSUED
  RETURNED
  CANCELLED
  NO_SHOW
  OVERDUE
  DAMAGED
}

model Booking {
  // …старые поля как есть…
  startsAt    DateTime?      @map("starts_at")    @db.Timestamptz(3)
  endsAt      DateTime?      @map("ends_at")      @db.Timestamptz(3)
  total       Decimal?       @db.Decimal(12, 2)
  depositNum  Decimal?       @map("deposit_num")  @db.Decimal(12, 2)
  statusEnum  BookingStatus? @map("status_enum")
}

model Item {
  // …старые поля как есть…
  dailyPriceNum Decimal? @map("daily_price_num") @db.Decimal(12, 2)
  depositNum    Decimal? @map("deposit_num")     @db.Decimal(12, 2)
  metaJson      Json?    @map("meta_json")       @db.JsonB
  metaRaw       String?  @map("meta_raw")
}

model Payment {
  // …старые поля как есть…
  amountNum Decimal?  @map("amount_num") @db.Decimal(12, 2)
  paidAt    DateTime? @map("paid_at")    @db.Timestamptz(3)
}

model Customer {
  // …старые поля как есть…
  createdAt DateTime? @map("created_at") @db.Timestamptz(3)
}
```

```bash run
cd ~/prisma-lab/rentkit
npx prisma migrate dev --create-only --name expand_clean_columns
cat prisma/migrations/*_expand_clean_columns/migration.sql
```

### result
```out auto
```

В миграции — `CREATE TYPE "BookingStatus"` и `ALTER TABLE … ADD COLUMN …` без `DROP`: **добавление безопасно**, всё остальное не трогаем. Допиши в **начало** этого файла две функции нормализации (нужны для backfill; они же останутся в истории, и любой может проиграть миграции с нуля):

```sql prepend=prisma/migrations/*_expand_clean_columns/migration.sql
-- в начало prisma/migrations/…_expand_clean_columns/migration.sql
-- 1) три формата даты → date
CREATE FUNCTION legacy_to_date(v text) RETURNS date LANGUAGE sql IMMUTABLE AS $$
  SELECT CASE
    WHEN v ~ '^\d{10}$'             THEN (to_timestamp(v::bigint) AT TIME ZONE 'UTC')::date
    WHEN v ~ '^\d{2}\.\d{2}\.\d{4}$' THEN to_date(v, 'DD.MM.YYYY')
    WHEN v ~ '^\d{4}-\d{2}-\d{2}$'  THEN to_date(v, 'YYYY-MM-DD')
  END
$$;

-- 2) деньги из текста: «1 200,00 руб», «1200.00», «1200,0» → numeric
CREATE FUNCTION legacy_to_money(v text) RETURNS numeric(12,2) LANGUAGE sql IMMUTABLE AS $$
  SELECT NULLIF(replace(regexp_replace(v, '[^0-9,.]', '', 'g'), ',', '.'), '')::numeric(12,2)
$$;
```

```bash run
cd ~/prisma-lab/rentkit
npx prisma migrate dev
npm run generate
psqlr() { docker exec -i rental-pg psql -U postgres -d rental "$@"; }
psqlr -c "SELECT legacy_to_date('15.01.2026'), legacy_to_date('2026-01-15'), legacy_to_date('1768435200'), legacy_to_money('1 200,00 руб'), legacy_to_money('1200.00'), legacy_to_money('1200,0')"
```

### result
```out auto
```

Три формата даты и три формата денег должны давать одинаковые значения (`2026-01-15` и `1200.00`). **Шаг 2 — backfill:** заполняем новые колонки из старых **батчами по диапазону `id`** — не одним `UPDATE` на 300 тысяч строк (он держал бы блокировки долго). Скрипт `scripts/backfill-dates.ts`:

```ts
// scripts/backfill-dates.ts
import { prisma } from '../src/db.js'

const BATCH = 20_000
const { _max } = await prisma.booking.aggregate({ _max: { id: true } })
const maxId = _max.id ?? 0

for (let lo = 1; lo <= maxId; lo += BATCH) {
  const hi = lo + BATCH - 1
  const n = await prisma.$executeRaw`
    UPDATE "tbl_Bookings" b SET
      starts_at = (legacy_to_date(b.d_from)::timestamp)
                  AT TIME ZONE COALESCE((SELECT tz FROM "tbl_Branches" br WHERE br.id = b.branch_id), 'Europe/Moscow'),
      ends_at   = ((legacy_to_date(b.d_to) + 1)::timestamp)
                  AT TIME ZONE COALESCE((SELECT tz FROM "tbl_Branches" br WHERE br.id = b.branch_id), 'Europe/Moscow')
    WHERE b.id BETWEEN ${lo} AND ${hi} AND b.starts_at IS NULL`
  console.log(`bookings ${lo}-${hi}: обновлено ${n}`)
}
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
mkdir -p scripts
npx tsx scripts/backfill-dates.ts | tail -4
```

### result
```out auto
```

**Шаг 3 — сверка.** Всё ли перенеслось и верно ли:

```bash run
psqlr() { docker exec -i rental-pg psql -U postgres -d rental "$@"; }
psqlr <<'SQL'
SELECT count(*) AS всего,
       count(starts_at) AS с_началом,
       count(*) FILTER (WHERE starts_at IS NULL) AS без_начала,
       count(*) FILTER (WHERE ends_at <= starts_at) AS конец_раньше_начала
FROM "tbl_Bookings";
-- глазами: три строки из разных форматов с поясом филиала
SELECT b.d_from, b.d_to, b.starts_at AT TIME ZONE br.tz AS начало_местное, b.ends_at AT TIME ZONE br.tz AS конец_местное, br.tz
FROM "tbl_Bookings" b JOIN "tbl_Branches" br ON br.id = b.branch_id
WHERE b.id IN (1, 4001, 8003) ORDER BY b.id;
SQL
```

### result
```out auto
```

Ожидаем: `без_начала = 0`, `конец_раньше_начала = 0`, а в локальном времени каждого филиала начало — **полночь**, конец — **полночь следующего дня** (бронь включает день возврата, поэтому правая граница — «следующая полночь», удобно для диапазонов в сессии 13). Если `без_начала > 0` — в данных есть формат, которого нет в функции: найди запросом из шага 3.1 и расширь функцию **новой** миграцией.

### why
Этот приём — «добавить новое, заполнить, проверить, переключить, убрать старое» — применим к любому изменению данных на живой системе. Его цена — время и дисциплина; его выгода — **откат всегда возможен** (старые данные целы), а блокировки короткие. Цифры сверки — единственное доказательство, что миграция верна.

### deep Команды по частям
`(legacy_to_date(d_from)::timestamp) AT TIME ZONE 'Asia/Vladivostok'` — берём «полночь по часам Владивостока» и получаем **момент времени** (`timestamptz`): на «стенных часах» 00:00 одного дня в разных поясах — разные миги. `WHERE … AND b.starts_at IS NULL` — **идемпотентность**: скрипт можно запускать повторно, он не трогает уже заполненное. `BETWEEN lo AND hi` — порция по первичному ключу: каждый `UPDATE` — отдельная короткая транзакция.

### deep Если не получилось
- **`function legacy_to_date(text) does not exist`** — функция не попала в применённую миграцию (дописана после `migrate dev`): создай её отдельной новой миграцией, **не редактируя применённую**.
- **`ends_at <= starts_at` > 0** — `d_to` раньше `d_from` в данных (грязь!); посмотри эти строки и реши: поменять местами или исключить (запиши решение в `NOTES.md`).
- **Скрипт упал на половине** — запусти ещё раз: идемпотентность не даст дублей.

### quiz
- Что такое expand/contract и почему нельзя просто поменять тип колонки?
- Зачем делать backfill порциями, а не одним `UPDATE`?
- Что означает «идемпотентный backfill» и как это достигнуто здесь?

### links
- https://www.prisma.io/docs/orm/v7/prisma-migrate/workflows/customizing-migrations#example-use-the-expand-and-contract-pattern-to-evolve-the-schema-without-downtime | expand и contract | Prisma 7: Expand and contract pattern
- https://www.postgresql.org/docs/18/functions-datetime.html#FUNCTIONS-DATETIME-ZONECONVERT | AT TIME ZONE | PostgreSQL 18: AT TIME ZONE

## 10.4 Деньги: text и float → numeric(12,2) | short: Деньги в numeric | est: ~50 мин
### intro
**Слова шага:** *`numeric(12,2)`*, *`legacy_to_money`*, *округление*, *сверка сумм*, *потеря копейки*.

:::tip Если совсем просто
Деньги в нашем наследстве лежат тремя способами: текстом («1 200,00 руб»), дробным числом с погрешностью (`float`) и просто числом. Приводим их к одному виду — точному десятичному числу с двумя знаками после запятой. Главное — **сверить итоговую сумму до и после**: копейки не должны потеряться.
:::

Колонки уже добавлены (шаг 10.3). Запиши сначала **контрольные суммы «до»** — по ним ты проверишь перенос:

```bash run
psqlr() { docker exec -i rental-pg psql -U postgres -d rental "$@"; }
psqlr <<'SQL'
-- суммы «до» (из старых колонок, с точным округлением)
SELECT 'бронь.price'   AS что, count(*) AS строк, sum(legacy_to_money(price)) AS сумма FROM "tbl_Bookings"
UNION ALL SELECT 'платёж.amount', count(*), sum(round(amount::numeric, 2)) FROM "tbl_Payments"
UNION ALL SELECT 'предмет.daily_price', count(*), sum(legacy_to_money(daily_price)) FROM "tbl_Items"
UNION ALL SELECT 'бронь.deposit', count(*), sum(round(deposit::numeric, 2)) FROM "tbl_Bookings";
SQL
```

### result
```out auto
```

Теперь backfill денег. Скрипт `scripts/backfill-money.ts` (та же схема, что для дат):

```ts
// scripts/backfill-money.ts
import { prisma } from '../src/db.js'

const BATCH = 50_000

async function run(table: string, maxId: number, sql: (lo: number, hi: number) => Promise<number>) {
  for (let lo = 1; lo <= maxId; lo += BATCH) {
    const n = await sql(lo, lo + BATCH - 1)
    console.log(`${table} ${lo}-${lo + BATCH - 1}: ${n}`)
  }
}

const maxB = (await prisma.booking.aggregate({ _max: { id: true } }))._max.id ?? 0
await run('bookings', maxB, (lo, hi) => prisma.$executeRaw`
  UPDATE "tbl_Bookings" SET total = legacy_to_money(price), deposit_num = round(deposit::numeric, 2)
  WHERE id BETWEEN ${lo} AND ${hi} AND total IS NULL`)

const maxP = (await prisma.payment.aggregate({ _max: { id: true } }))._max.id ?? 0
await run('payments', maxP, (lo, hi) => prisma.$executeRaw`
  UPDATE "tbl_Payments" SET amount_num = round(amount::numeric, 2)
  WHERE id BETWEEN ${lo} AND ${hi} AND amount_num IS NULL`)

const maxI = (await prisma.item.aggregate({ _max: { id: true } }))._max.id ?? 0
await run('items', maxI, (lo, hi) => prisma.$executeRaw`
  UPDATE "tbl_Items" SET daily_price_num = legacy_to_money(daily_price), deposit_num = round(deposit::numeric, 2)
  WHERE id BETWEEN ${lo} AND ${hi} AND daily_price_num IS NULL`)

await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx scripts/backfill-money.ts | tail -6
psqlr() { docker exec -i rental-pg psql -U postgres -d rental "$@"; }
psqlr <<'SQL'
SELECT 'бронь.total'   AS что, count(total) AS заполнено, sum(total) AS сумма_после FROM "tbl_Bookings"
UNION ALL SELECT 'платёж.amount_num', count(amount_num), sum(amount_num) FROM "tbl_Payments"
UNION ALL SELECT 'предмет.daily_price_num', count(daily_price_num), sum(daily_price_num) FROM "tbl_Items"
UNION ALL SELECT 'бронь.deposit_num', count(deposit_num), sum(deposit_num) FROM "tbl_Bookings";
SQL
```

### result
```out auto
```

**Сверь** четыре строки: числа в колонке «сумма» должны **совпадать с суммами «до»** копейка в копейку; `заполнено` = число строк «до». Если расхождение — копай: либо в данных есть неожиданный формат (`legacy_to_money` вернула `NULL`), либо округление. Список строк с `NULL` в новой колонке при непустой старой: `SELECT id, price FROM "tbl_Bookings" WHERE total IS NULL AND price IS NOT NULL LIMIT 10`.

### why
Деньги — тот случай, где «почти правильно» — это неправильно. Привязка к цифрам сверки (суммы до и после) превращает чистку из «вроде нормально» в «доказано»; это основа доверия бухгалтерии к твоим миграциям.

### deep Как ещё можно
Если таблица небольшая и простой допустим, тип можно менять на месте: `ALTER TABLE … ALTER COLUMN amount TYPE numeric(12,2) USING round(amount::numeric, 2)`. Но он **перезаписывает всю таблицу** под эксклюзивной блокировкой — на 583 тысячах платежей это секунды без доступа. На живой системе делают expand/contract, как мы.

### deep Если не получилось
- **Суммы «до» и «после» расходятся** — `round(deposit::numeric, 2)` отличается от `legacy_to_money(price)` по правилам округления; сравнивай одинаково округлённые значения.
- **`value too large for numeric(12,2)`** — в данных аномально большое число; найди его запросом `ORDER BY` и реши, что с ним делать.

### quiz
- Почему «суммы до» нужно записать **до** backfill?
- Чем `numeric(12,2)` лучше `float8` для денег?
- Почему смену типа на месте на большой таблице обычно не делают?

### links
- https://www.postgresql.org/docs/18/datatype-numeric.html | числовые типы | PostgreSQL 18: Numeric Types

## 10.5 Статусы в enum, битый JSON в карантин | short: enum и Json | est: ~50 мин
### intro
**Слова шага:** *PostgreSQL enum*, *`CASE`*, *`pg_input_is_valid`*, *`jsonb`*, *карантин «непрочитанного»*, *`created`-колонка*.

:::tip Если совсем просто
Три чистки: числа-статусы превращаем в имена (`3` → `RETURNED`), строку с JSON — в настоящий JSON (`jsonb`), а то, что не читается (битый JSON), **не выбрасываем**, а складываем в «карантин» — отдельную колонку, чтобы человек мог разобраться.
:::

Расшифровку статусов ты составила в шаге 4.4 — переносим в базу:

```ts
// scripts/backfill-misc.ts
import { prisma } from '../src/db.js'

// 1. статус: число → enum (по расшифровке из src/domain/status.ts)
const n1 = await prisma.$executeRaw`
  UPDATE "tbl_Bookings" SET status_enum = (CASE status
      WHEN 0 THEN 'DRAFT' WHEN 1 THEN 'CONFIRMED' WHEN 2 THEN 'ISSUED' WHEN 3 THEN 'RETURNED'
      WHEN 4 THEN 'CANCELLED' WHEN 5 THEN 'NO_SHOW' WHEN 6 THEN 'OVERDUE' WHEN 7 THEN 'DAMAGED' END)::"BookingStatus"
  WHERE status_enum IS NULL AND status IS NOT NULL`
console.log('статусов:', n1)

// 2. meta: валидный JSON → jsonb, остальное — в карантин
const n2 = await prisma.$executeRaw`
  UPDATE "tbl_Items" SET meta_json = meta::jsonb WHERE meta IS NOT NULL AND meta_json IS NULL AND pg_input_is_valid(meta, 'jsonb')`
const n3 = await prisma.$executeRaw`
  UPDATE "tbl_Items" SET meta_raw = meta WHERE meta IS NOT NULL AND meta_raw IS NULL AND NOT pg_input_is_valid(meta, 'jsonb')`
console.log('meta в jsonb:', n2, ' в карантин:', n3)

// 3. платежи: paid (два формата) → paid_at; клиенты: created → created_at (часы центрального офиса — Москва)
const n4 = await prisma.$executeRaw`
  UPDATE "tbl_Payments" SET paid_at = (CASE
      WHEN paid ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}$' THEN to_timestamp(paid, 'YYYY-MM-DD HH24:MI:SS')
      WHEN paid ~ '^[0-9]{2}[.][0-9]{2}[.][0-9]{4} [0-9]{2}:[0-9]{2}$' THEN to_timestamp(paid, 'DD.MM.YYYY HH24:MI') END)
      ::timestamp AT TIME ZONE 'Europe/Moscow'
  WHERE paid_at IS NULL AND paid IS NOT NULL`
const n5 = await prisma.$executeRaw`
  UPDATE "tbl_Customers" SET created_at = (CASE
      WHEN created ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}$' THEN to_timestamp(created, 'YYYY-MM-DD HH24:MI')
      WHEN created ~ '^[0-9]{2}[.][0-9]{2}[.][0-9]{4}$' THEN to_timestamp(created, 'DD.MM.YYYY') END)
      ::timestamp AT TIME ZONE 'Europe/Moscow'
  WHERE created_at IS NULL AND created IS NOT NULL`
console.log('платежей:', n4, ' клиентов:', n5)
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx scripts/backfill-misc.ts
```

### result
```out auto
```

**Обрати внимание на `[0-9]` вместо привычного `\d`.** В шаблонной строке TypeScript обратная косая черта «съедается» ещё до отправки в базу (`\d` превращается в `d`), регулярное выражение молча перестаёт совпадать — и `UPDATE` честно обновит строки значением `NULL`. Поэтому в SQL внутри `` $executeRaw`…` `` пишем классы символов без обратной косой черты (`[0-9]`, `[.]`). Именно такую ловушку и ловит последняя проверка шага.

Ожидаем: статусов — 300 000; `meta` в `jsonb` — около 3 800, в карантин — около 120 (те самые битые); платежей — все; клиентов — все. Сверка:

```bash run
psqlr() { docker exec -i rental-pg psql -U postgres -d rental "$@"; }
psqlr <<'SQL'
SELECT status, status_enum, count(*) FROM "tbl_Bookings" GROUP BY 1, 2 ORDER BY 1;
SELECT count(*) FILTER (WHERE meta IS NOT NULL) AS было_meta,
       count(meta_json) AS в_jsonb, count(meta_raw) AS в_карантине,
       count(*) FILTER (WHERE meta IS NOT NULL AND meta_json IS NULL AND meta_raw IS NULL) AS потеряно
FROM "tbl_Items";
SELECT count(*) FILTER (WHERE paid IS NOT NULL AND paid_at IS NULL) AS платежей_без_даты FROM "tbl_Payments";
SQL
```

### result
```out auto
```

Критерии: **каждое число статуса соответствует одному имени** (8 пар, без `NULL`); `потеряно = 0` (`в_jsonb + в_карантине = было_meta`); `платежей_без_даты = 0`. `pg_input_is_valid(text, 'jsonb')` — функция PostgreSQL 16+: проверяет, **разберётся ли** строка как `jsonb`, не бросая ошибку — идеальный инструмент для «карантина» (в версиях старше пришлось бы писать функцию с `EXCEPTION`).

### why
Принцип «не выбрасывай непонятное — отложи» избавляет от самой неприятной ситуации: «мы почистили, а через месяц выяснилось, что среди битых был важный клиент». Колонка-карантин (`meta_raw`) — дёшево, а человек потом разберётся.

### deep Если не получилось
- **`invalid input value for enum`** — в `status` есть число вне 0–7; найди (`SELECT DISTINCT status`) и дополни расшифровку.
- **`function pg_input_is_valid does not exist`** — версия PostgreSQL ниже 16; у нас 18, проверь `SELECT version()`.
- **`платежей_без_даты` равно числу платежей** — в регулярках остались `\d` (см. выше): замени на `[0-9]` и запусти скрипт ещё раз (он идемпотентен только для `meta`/статусов; для дат добавь в условия `paid_at IS NULL`, как уже сделано).
- **`потеряно > 0`** — в `meta` пустая строка `''` (не `NULL`): `''::jsonb` невалидна и попала бы в карантин, но проверь условия `NOT pg_input_is_valid(...)`.

### quiz
- Зачем нужна колонка-карантин, вместо того чтобы удалить битые значения?
- Что проверяет `pg_input_is_valid` и какая альтернатива была в старых версиях?
- Как проверить, что статусы переехали без потерь?

### links
- https://www.postgresql.org/docs/18/functions-info.html#FUNCTIONS-INFO-VALIDITY | pg_input_is_valid | PostgreSQL 18: pg_input_is_valid
- https://www.postgresql.org/docs/18/datatype-enum.html | enum | PostgreSQL 18: Enumerated Types

## 10.6 Contract: переключаем код и убираем старое | short: Contract | est: ~55 мин
### intro
**Слова шага:** *contract-миграция*, *защитная проверка в миграции*, *`DO $$ … RAISE EXCEPTION`*, *`RENAME COLUMN`*, *переключение кода*, *резервная копия перед удалением*.

:::tip Если совсем просто
Новое рядом заполнено и проверено. Теперь аккуратно **переезжаем**: сначала сменим код на новые колонки, потом (когда уверены) удалим старые. Контракт — необратим: после `DROP COLUMN` назад только из резервной копии. Поэтому перед ним — «страховочная» проверка, которая **не даст** выполнить миграцию, если что-то не дозаполнено, и резервная копия.
:::

**Шаг 1 — резервная копия** (дамп всей базы, на всякий случай):

```bash run
cd ~/prisma-lab
docker exec rental-pg pg_dump -U postgres -d rental -Fc --no-owner --no-acl > starter/rental-before-contract.dump
ls -lh starter/rental-before-contract.dump
```

### result
```out auto
```

**Шаг 2 — contract-миграция.** Создай пустую миграцию (изменений в схеме нет, поэтому Prisma сделает файл с одним комментарием, который мы заменим):

```bash run
cd ~/prisma-lab/rentkit
npx prisma migrate dev --create-only --name contract_clean_columns
ls prisma/migrations | tail -3
```

### result
```out auto
```

Впиши в её `migration.sql` защитную проверку, удаление старого и переименование нового:

```sql into=prisma/migrations/*_contract_clean_columns/migration.sql
-- prisma/migrations/<метка>_contract_clean_columns/migration.sql

-- 0. защита: ничего не удаляем, если новое заполнено не везде
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM "tbl_Bookings" WHERE (d_from IS NOT NULL AND starts_at IS NULL)
                                              OR (price  IS NOT NULL AND total     IS NULL)
                                              OR (status IS NOT NULL AND status_enum IS NULL)) THEN
    RAISE EXCEPTION 'contract остановлен: в tbl_Bookings есть строки без новых значений';
  END IF;
  IF EXISTS (SELECT 1 FROM "tbl_Payments" WHERE amount IS NOT NULL AND amount_num IS NULL) THEN
    RAISE EXCEPTION 'contract остановлен: в tbl_Payments есть строки без amount_num';
  END IF;
  IF EXISTS (SELECT 1 FROM "tbl_Items" WHERE meta IS NOT NULL AND meta_json IS NULL AND meta_raw IS NULL) THEN
    RAISE EXCEPTION 'contract остановлен: в tbl_Items есть непереданный meta';
  END IF;
END $$;

-- 1. брони: убираем текстовые даты, цену, число-статус; новое получает «старые» красивые имена
ALTER TABLE "tbl_Bookings" DROP COLUMN d_from, DROP COLUMN d_to, DROP COLUMN price, DROP COLUMN deposit, DROP COLUMN status;
ALTER TABLE "tbl_Bookings" RENAME COLUMN deposit_num TO deposit;
ALTER TABLE "tbl_Bookings" RENAME COLUMN status_enum TO status;

-- 2. платежи
ALTER TABLE "tbl_Payments" DROP COLUMN amount, DROP COLUMN paid;
ALTER TABLE "tbl_Payments" RENAME COLUMN amount_num TO amount;

-- 3. предметы
ALTER TABLE "tbl_Items" DROP COLUMN daily_price, DROP COLUMN deposit, DROP COLUMN meta;
ALTER TABLE "tbl_Items" RENAME COLUMN daily_price_num TO daily_price;
ALTER TABLE "tbl_Items" RENAME COLUMN deposit_num TO deposit;

-- 4. клиенты
ALTER TABLE "tbl_Customers" DROP COLUMN created;

-- 5. функции нормализации больше не нужны
DROP FUNCTION legacy_to_date(text);
DROP FUNCTION legacy_to_money(text);
```

**Шаг 3 — схема.** Обнови `schema.prisma` под новую форму (старые поля убрать, новые переименовать на финальные имена с `@map` на уже существующие колонки):

```prisma
model Booking {
  id         Int           @id @default(autoincrement())
  customerId Int?          @map("cust_id")
  itemId     Int?          @map("item_id")
  branchId   Int?          @map("branch_id")
  startsAt   DateTime?     @map("starts_at") @db.Timestamptz(3)
  endsAt     DateTime?     @map("ends_at")   @db.Timestamptz(3)
  total      Decimal?      @db.Decimal(12, 2)
  deposit    Decimal?      @db.Decimal(12, 2)
  status     BookingStatus?
  note       String?
  // … связи и индексы как раньше (индексы по status убрать или пересоздать)
  @@map("tbl_Bookings")
}

model Payment {
  id        Int       @id @default(autoincrement())
  bookingId Int?      @map("booking_id")
  amount    Decimal?  @db.Decimal(12, 2)
  paidAt    DateTime? @map("paid_at") @db.Timestamptz(3)
  kind      Int?      @db.SmallInt
  extRef    String?   @map("ext_ref")
  // … связь и индекс
  @@map("tbl_Payments")
}

model Item {
  id           Int     @id @default(autoincrement())
  branchId     Int?    @map("branch_id")
  sku          String? @unique @db.VarChar(30)
  title        String?
  category     String? @db.VarChar(40)
  dailyPrice   Decimal? @map("daily_price") @db.Decimal(12, 2)
  deposit      Decimal? @db.Decimal(12, 2)
  active       Int?    @db.SmallInt
  metaJson     Json?   @map("meta_json") @db.JsonB
  metaRaw      String? @map("meta_raw")
  // … связи и индексы
  @@map("tbl_Items")
}

model Customer {
  // created убрано, остаётся createdAt (created_at)
  // …
}
```

```prisma schema hidden
model Booking {
  id         Int            @id @default(autoincrement())
  customerId Int?           @map("cust_id")
  itemId     Int?           @map("item_id")
  branchId   Int?           @map("branch_id")
  startsAt   DateTime?      @map("starts_at") @db.Timestamptz(3)
  endsAt     DateTime?      @map("ends_at") @db.Timestamptz(3)
  total      Decimal?       @db.Decimal(12, 2)
  deposit    Decimal?       @db.Decimal(12, 2)
  status     BookingStatus?
  note       String?

  customer   Customer?    @relation(fields: [customerId], references: [id])
  item       Item?        @relation(fields: [itemId], references: [id])
  branch     Branch?      @relation(fields: [branchId], references: [id])
  payments   Payment[]
  depositLog DepositLog[]

  @@index([customerId])
  @@index([itemId])
  @@index([branchId])
  @@index([branchId, status, id(sort: Desc)], name: "bookings_branch_status_id")
  @@map("tbl_Bookings")
}

model Payment {
  id        Int       @id @default(autoincrement())
  bookingId Int?      @map("booking_id")
  amount    Decimal?  @db.Decimal(12, 2)
  paidAt    DateTime? @map("paid_at") @db.Timestamptz(3)
  kind      Int?      @db.SmallInt
  extRef    String?   @map("ext_ref")

  booking Booking? @relation(fields: [bookingId], references: [id])

  @@index([bookingId])
  @@map("tbl_Payments")
}

model Item {
  id         Int      @id @default(autoincrement())
  branchId   Int?     @map("branch_id")
  sku        String?  @unique @db.VarChar(30)
  title      String?
  category   String?  @db.VarChar(40)
  dailyPrice Decimal? @map("daily_price") @db.Decimal(12, 2)
  deposit    Decimal? @db.Decimal(12, 2)
  active     Int?     @db.SmallInt
  metaJson   Json?    @map("meta_json") @db.JsonB
  metaRaw    String?  @map("meta_raw")

  branch   Branch?   @relation(fields: [branchId], references: [id])
  bookings Booking[]

  @@index([branchId])
  @@map("tbl_Items")
}

model Customer {
  id        Int       @id @default(autoincrement())
  name      String?   @map("CustName")
  phone     String?
  email     String?
  branchId  Int?      @map("branch_id")
  createdAt DateTime? @map("created_at") @db.Timestamptz(3)

  branch   Branch?   @relation(fields: [branchId], references: [id])
  bookings Booking[]

  @@index([branchId])
  @@index([name(ops: raw("gin_trgm_ops"))], type: Gin, map: "customers_name_trgm")
  @@index([name])
  @@map("tbl_Customers")
}
```

```bash run hidden
cd ~/prisma-lab/rentkit && node -e "const fs=require('fs');const c=JSON.parse(fs.readFileSync('tsconfig.json'));c.include=['src/data','src/lib','src/db.ts','src/domain','scripts','prisma.config.ts'];fs.writeFileSync('tsconfig.json',JSON.stringify(c,null,2))"
```

Старые «уроки» (`src/lessons`, `src/intro`) используют удалённые поля и перестанут компилироваться. Вынеси их из проверки типов — в `tsconfig.json` замени `include` на `["src/data", "src/lib", "src/db.ts", "src/domain", "scripts", "prisma.config.ts"]`; сами файлы оставь как архив.

```bash run
cd ~/prisma-lab/rentkit
npx prisma migrate dev --name sync_after_contract
npm run generate
psqlr() { docker exec -i rental-pg psql -U postgres -d rental "$@"; }
psqlr -c '\d "tbl_Bookings"'
npm run typecheck
```

### result
```out auto
```

Теперь `tbl_Bookings` — с `starts_at`, `ends_at` (`timestamptz`), `total`, `deposit` (`numeric(12,2)`), `status` (enum `BookingStatus`). **Порядок действий в продакшне** (мы сжали его в одну сессию): (1) expand-миграция; (2) backfill; (3) новая версия кода, которая **пишет в обе** колонки и читает новую; (4) убедиться, что старая версия кода больше нигде не работает; (5) contract. Мы пропустили (3)–(4), потому что «прод» у нас — ты одна.

### why
Защитная проверка в `DO $$ … $$` — маленькая привычка, которая спасает данные: contract необратим, и «забыли дозаполнить» должно остановить миграцию, а не оставить дыру. Резервная копия — второй пояс безопасности. А строго упорядоченные шаги expand → backfill → switch → contract дают то, чего нет у «поменять тип одной командой»: возможность остановиться и вернуться на любом этапе.

### deep Если не получилось
- **Миграция остановилась с `contract остановлен`** — защита сработала: найди недозаполненные строки (`SELECT id FROM "tbl_Bookings" WHERE starts_at IS NULL LIMIT 10`), доделай backfill и перезапусти `migrate dev`.
- **`migrate dev` хочет сбросить базу** — расхождение между схемой и базой после ручной миграции: сравни `\d` и схему, поправь схему (особенно `@db.*` и `@map`), **не соглашайся на reset**.
- **Ошибки типов в `src/data`** — там ещё остались старые поля (`startText`, `priceText`): замени на новые.

### quiz
- Какой порядок шагов безопасно меняет данные на живой системе?
- Зачем нужна защитная проверка в начале contract-миграции?
- Почему contract нельзя откатить обычным откатом миграции?

### links
- https://www.prisma.io/docs/orm/v7/prisma-migrate/workflows/customizing-migrations | кастомные миграции | Prisma 7: Customizing migrations
- https://www.prisma.io/docs/orm/v7/prisma-migrate/workflows/generating-down-migrations | down-миграции | Prisma 7: Generating down migrations

## 10.7 🔨 Миграция «переименование» удалила данные | short: 🔨 Потеря данных | est: ~55 мин
### intro
**Слова шага:** *потеря данных при `DROP COLUMN`*, *копия базы через шаблон*, *восстановление из дампа*, *урок про `--create-only`*.

:::tip Если совсем просто
Ты увидела в 10.2, что Prisma превращает переименование в удаление. Теперь повторим то же самое на **копии боевой базы** — чтобы почувствовать масштаб последствий и пройти путь восстановления. Не на настоящей: потеря 300 тысяч строк — это не то, чему нужно учиться на практике.
:::

Сделаем копию базы и «сломаем» в ней:

```bash run
psqlr() { docker exec -i rental-pg psql -U postgres "$@"; }
psqlr -c 'DROP DATABASE IF EXISTS rental_copy'
psqlr -c 'CREATE DATABASE rental_copy TEMPLATE rental'
psqlr -d rental_copy -c 'SELECT count(*) AS до_потери FROM "tbl_Payments" WHERE amount IS NOT NULL'
# «разработчик» переименовал колонку в схеме, не читал SQL и применил как есть:
psqlr -d rental_copy -c 'ALTER TABLE "tbl_Payments" DROP COLUMN amount, ADD COLUMN amount_v2 numeric(12,2)'
psqlr -d rental_copy -c 'SELECT count(*) AS после_потери FROM "tbl_Payments" WHERE amount_v2 IS NOT NULL'
```

### result
```out auto
```

583 тысячи платежей остались без сумм. Теперь **верни**: у тебя есть дамп `starter/rental-before-contract.dump` (шаг 10.6, он **до** contract: колонка `amount` ещё `float8`) и ты знаешь, где живёт настоящая копия (`rental`). Восстанови суммы в `rental_copy`, **не трогая** `rental`:

```bash run
psqlr() { docker exec -i rental-pg psql -U postgres "$@"; }
psqlr -c 'DROP DATABASE IF EXISTS rental_restore'
psqlr -c 'CREATE DATABASE rental_restore'
docker exec -i rental-pg pg_restore -U postgres -d rental_restore --no-owner --no-acl < ~/prisma-lab/starter/rental-before-contract.dump
psqlr -d rental_restore -c 'SELECT count(*) AS в_копии FROM "tbl_Payments" WHERE amount_num IS NOT NULL'
```

### result
```out auto
```

**Твоя задача:** составить и выполнить SQL, который **перенесёт суммы** из `rental_restore.tbl_Payments.amount_num` в `rental_copy.tbl_Payments.amount_v2` по `id` (подсказка: базы разные — нужен `COPY`/`\copy` в промежуточный файл или `dblink`/`postgres_fdw`; проще — через `pg_dump -t` таблицы и временную таблицу), проверить суммы и убрать за собой (`DROP DATABASE rental_copy, rental_restore`). Запиши в `NOTES.md`: что пошло не так, сколько времени заняло восстановление, и **что надо было сделать до миграции**.

**Приёмка сессии:** три «грязных» столбца (даты, деньги, статусы) приведены к нормальным типам expand/contract, сверка сумм и счётчиков до и после проведена, contract-миграция применена с защитной проверкой, резервный дамп сохранён; схема Prisma обновлена, `migrate status` чистый; ни одна строка не потеряна (числа в `NOTES.md`).

### why
Практическое знание о потере данных — не «читал, что так бывает», а «видела, как быстро это случается и как долго возвращать». Три страховки, из которых эта история состоит: читать SQL до применения, делать копию перед необратимым и проверять защитной проверкой, что новое заполнено. Хотя бы две из трёх спасают всегда.

### deep Если не получилось
- **`CREATE DATABASE … TEMPLATE rental` не работает** — в `rental` есть активные подключения (`prisma studio`, скрипт): закрой их или выполни `SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'rental' AND pid <> pg_backend_pid()`.
- **Не получается перенести данные между базами** — самый простой способ: `\copy (SELECT id, amount_num FROM "tbl_Payments") TO '/tmp/pay.csv' CSV` из одной базы и `\copy` в временную таблицу другой, затем `UPDATE … FROM`.
- **Не помнишь, что хранится в дампе** — `pg_restore -l файл | head` покажет оглавление.

### quiz
- Почему такие сценарии отрабатывают на копии, а не на настоящей базе?
- Какие три «страховки» защищают от потери данных при миграциях?
- Как узнать, что лежит внутри дампа, не восстанавливая его?

### links
- https://www.postgresql.org/docs/18/manage-ag-templatedbs.html | базы-шаблоны | PostgreSQL 18: Template Databases
- https://www.postgresql.org/docs/18/app-pgdump.html | pg_dump | PostgreSQL 18: pg_dump
