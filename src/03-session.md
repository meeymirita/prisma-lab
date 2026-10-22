# Сессия 3 · Чужая база: аудит и db pull
dur: ~4 ч

## 3.1 Аудит запросами: список болячек | short: Аудит данных | est: ~50 мин
### intro
**Слова шага:** *профилирование данных*, *регулярное выражение в SQL*, *`FILTER`*, *осиротевшая строка*, *нормализация*, *`daterange`*.

:::tip Если совсем просто
В шаге 1.5 ты осмотрела квартиру глазами. Теперь берёшь рулетку и уровень: **измеряешь** каждую болячку числом. «Даты в трёх форматах» — это не впечатление, а «45 % в одном, 40 % в другом, 15 % в третьем». Цифры понадобятся в сессиях 10–11, когда будешь убеждаться, что ни одна строка не потерялась.
:::

Запросы пишем в `psql` (функция `psqlr` из шага 1.3). **Ничего не меняем** — только читаем. Начнём с форматов: как записаны даты, деньги и сколько осиротевших строк.

```bash run
psqlr() { docker exec -i rental-pg psql -U postgres -d rental "$@"; }
psqlr <<'SQL'
-- 1. форматы дат начала брони
SELECT CASE WHEN d_from ~ '^\d{10}$' THEN 'unix'
            WHEN d_from ~ '^\d{2}\.\d{2}\.\d{4}$' THEN 'dd.mm.yyyy'
            WHEN d_from ~ '^\d{4}-\d{2}-\d{2}$' THEN 'yyyy-mm-dd'
            ELSE 'другое' END AS формат, count(*)
FROM "tbl_Bookings" GROUP BY 1 ORDER BY 2 DESC;

-- 2. форматы денег
SELECT CASE WHEN price ~ 'руб$' THEN 'с «руб»'
            WHEN price ~ '\.' THEN 'через точку'
            WHEN price ~ ',' THEN 'через запятую'
            ELSE 'другое' END AS формат, count(*)
FROM "tbl_Bookings" GROUP BY 1 ORDER BY 2 DESC;

-- 3. статусы без справочника
SELECT status, count(*) FROM "tbl_Bookings" GROUP BY 1 ORDER BY 1;

-- 4. осиротевшие брони: ссылаются на несуществующих клиентов и предметы
SELECT count(*) FILTER (WHERE c.id IS NULL) AS без_клиента,
       count(*) FILTER (WHERE i.id IS NULL) AS без_предмета
FROM "tbl_Bookings" b
LEFT JOIN "tbl_Customers" c ON c.id = b.cust_id
LEFT JOIN "tbl_Items" i ON i.id = b.item_id;
SQL
```

### result
```out auto
```

Должно получиться примерно: форматы дат — около 45 % `dd.mm.yyyy`, около 40 % `yyyy-mm-dd`, около 15 % `unix`; деньги — три формата (`руб`, точка, запятая) примерно по трети; статусы 0–7; сирот порядка **полутора тысяч** без клиента и **около девятисот** без предмета. Записывай **свои** числа в `NOTES.md`. Теперь вторая партия: дубли, пересечения, битые данные, индексы.

```bash run
psqlr() { docker exec -i rental-pg psql -U postgres -d rental "$@"; }
psqlr <<'SQL'
-- 5. дубли клиентов: один телефон в разных форматах
SELECT count(*) AS телефонов_с_дублями
FROM (SELECT right(regexp_replace(phone, '\D', '', 'g'), 10) AS p
      FROM "tbl_Customers" GROUP BY 1 HAVING count(*) > 1) t;

-- 6. битый JSON в meta (нет закрывающей скобки)
SELECT count(*) AS битых FROM "tbl_Items" WHERE meta IS NOT NULL AND meta !~ '\}$';

-- 7. повторные платежи: один ext_ref встречается дважды
SELECT count(*) AS повторных_ext_ref
FROM (SELECT ext_ref FROM "tbl_Payments" GROUP BY 1 HAVING count(*) > 1) t;

-- 8. двойные брони: пересечения у одного предмета (с нормализацией трёх форматов дат)
WITH b AS (
  SELECT id, item_id,
         CASE WHEN d_from ~ '^\d{10}$' THEN to_timestamp(d_from::bigint)::date
              WHEN d_from ~ '^\d{2}\.' THEN to_date(d_from, 'DD.MM.YYYY') ELSE to_date(d_from, 'YYYY-MM-DD') END AS d1,
         CASE WHEN d_to ~ '^\d{10}$' THEN to_timestamp(d_to::bigint)::date
              WHEN d_to ~ '^\d{2}\.' THEN to_date(d_to, 'DD.MM.YYYY') ELSE to_date(d_to, 'YYYY-MM-DD') END AS d2
  FROM "tbl_Bookings" WHERE status <> 4)
SELECT count(*) AS пар_пересечений
FROM b x JOIN b y ON x.item_id = y.item_id AND x.id < y.id
WHERE daterange(x.d1, x.d2, '[]') && daterange(y.d1, y.d2, '[]');

-- 9. индексы и внешние ключи: что есть?
SELECT tablename, indexname FROM pg_indexes WHERE schemaname = 'public' ORDER BY 1;
SELECT count(*) AS внешних_ключей FROM pg_constraint WHERE contype = 'f';
SQL
```

### result
```out auto
```

Ожидаемо: дублей около **девяти тысяч** телефонов, битых `meta` около **ста двадцати**, повторных платежей порядка **трёх тысяч**, пар пересечений около **ста пятидесяти** (двойные брони уже случились!), индексы — только `…_pkey`, внешних ключей **ноль**. Это и есть «наследство».

### why
Каждое из этих чисел — контрольная точка. Через пять сессий, когда ты будешь переводить `price` из текста в `numeric`, вернись сюда: «все ли 300 000 строк переехали?» Сверка счётчиков до и после — единственный способ доказать, что в чистке ничего не потеряно.

### deep Команды по частям
`regexp_replace(phone, '\D', '', 'g')` — вычёркивает все **не** цифры из телефона (`\D` — не цифра, `'g'` — по всей строке); `right(..., 10)` — последние десять цифр: `+7 (912) 345-67-89` и `8-912-345-67-89` дают один и тот же `9123456789`. `count(*) FILTER (WHERE …)` — счётчик только по строкам, подходящим под условие. `daterange(a, b, '[]') && daterange(c, d, '[]')` — «диапазоны пересекаются» (`&&`), скобки `[]` — обе границы включительно: бронь на 5–7 января и на 7–9 января пересекаются по 7-му.

### deep Если не получилось
- **Запрос 8 идёт дольше минуты** — самосоединение без индексов на 300 тысячах строк; добавь `SET max_parallel_workers_per_gather = 4;` в начале или подожди; в сессии 8 мы научимся делать такое быстро.
- **`invalid input syntax for type date`** — в данных попался формат, которого нет в `CASE`: найди его запросом `SELECT d_from FROM "tbl_Bookings" WHERE d_from !~ '^\d{10}$|^\d{2}\.\d{2}\.\d{4}$|^\d{4}-\d{2}-\d{2}$' LIMIT 5`.

### quiz
- Как посчитать осиротевшие строки и какой JOIN для этого нужен?
- Что делает `right(regexp_replace(phone, '\D', '', 'g'), 10)` и зачем это для поиска дублей?
- Почему у диапазонов дат в запросе 8 стоят скобки `[]`?

### links
- https://www.postgresql.org/docs/18/functions-matching.html | регулярные выражения | PostgreSQL 18: Pattern Matching
- https://www.postgresql.org/docs/18/rangetypes.html | диапазонные типы | PostgreSQL 18: Range Types

## 3.2 prisma db pull: что Prisma поняла и чего нет | short: Интроспекция | est: ~45 мин
### intro
**Слова шага:** *интроспекция*, *`prisma db pull`*, *`prisma.config.ts`*, *`@@ignore`*, *уникальный идентификатор*.

:::tip Если совсем просто
`db pull` — это «описание квартиры по осмотру»: Prisma заходит в базу, смотрит на таблицы и пишет по ним схему. Видно стены и двери (таблицы, колонки, ключи), но не видно, как жильцы ими пользуются: что `price` — это деньги, а `status` — это статус брони. Всё, что ты знаешь о смысле, придётся дописывать руками.
:::

```svg
@introspection
```

Сначала минимальные файлы. **Конфиг** (`prisma.config.ts` в корне `rentkit/`):

```ts
// prisma.config.ts
import 'dotenv/config'
import { defineConfig, env } from 'prisma/config'

export default defineConfig({
  schema: 'prisma/schema.prisma',
  migrations: { path: 'prisma/migrations' },
  datasource: { url: env('DATABASE_URL') },
})
```

**Схема** — пока только «шапка» (адрес базы в схеме больше не пишем):

```prisma
// prisma/schema.prisma
generator client {
  provider = "prisma-client"
  output   = "../src/generated/prisma"
}

datasource db {
  provider = "postgresql"
}
```

```bash run
cd ~/prisma-lab/rentkit
mkdir -p prisma
npx prisma db pull
npx prisma validate
head -50 prisma/schema.prisma
```

### result
```out auto
```

Prisma перечислит найденные таблицы и допишет в `schema.prisma` модели. Что в них смотреть:

- имена моделей **как у таблиц**: `tbl_Bookings`, `tbl_Customers`… (переименуем в шаге 3.3);
- **связей (`@relation`) нет** — их нет в базе (нет внешних ключей), Prisma угадывать не умеет;
- у `tbl_DepositLog` модель есть, но с пометкой **`@@ignore`** и комментарием `/// The underlying table does not contain a valid unique identifier…`, а в выводе `db pull` — предупреждение `The following models were ignored`: в таблице нет первичного ключа и нет уникального индекса, а Prisma **требует у каждой модели уникальный идентификатор** — и клиент такую модель не увидит (разберёмся в шаге 3.6);
- `daily_price`, `price` — `String`, `deposit` — `Float`, `status` — `Int @db.SmallInt`: Prisma честно описала то, что есть.

### why
`db pull` — самая быстрая точка входа в чужую базу, но он даёт **описание, а не понимание**. Всё, что в базе нарисовано слабо (текстовые даты, числовые статусы, отсутствие ключей), в схеме окажется нарисованным так же слабо. Это отправная точка для чистки, а не готовая схема.

### deep Что произойдёт при повторном `db pull`
Если ты вручную правила схему (переименовала модели через `@@map`, добавила `@relation`), повторный `db pull` **перезапишет** файл. Prisma умеет сохранять часть ручных правок (имена через `@map`/`@@map` и комментарии), но связи и атрибуты часто теряются — **сверьтесь** с поведением в вашей версии. Безопасный приём: перед `db pull` делай копию (`cp prisma/schema.prisma /tmp/schema.bak`) или смотри результат без записи: `npx prisma db pull --print`.

### deep Если не получилось
- **`Environment variable not found: DATABASE_URL`** — не подхватился `.env`: в `prisma.config.ts` должна быть первая строка `import 'dotenv/config'`, а `.env` лежать рядом с ним (корень `rentkit/`).
- **`Can't reach database server at localhost:5433`** — контейнер не запущен (`docker start rental-pg`) или порт другой.
- **`datasource property url is no longer supported in schema files`** — в `schema.prisma` остался `url = env(...)` из старых примеров: удали, адрес — только в `prisma.config.ts`.

### quiz
- Что делает `prisma db pull` и чего он не может узнать о базе?
- Почему `tbl_DepositLog` помечена `@@ignore`, и что это значит для клиента?
- Чем опасен повторный `db pull`, если ты уже правила схему?

### links
- https://www.prisma.io/docs/orm/v7/prisma-schema/introspection | интроспекция | Prisma 7: Introspection
- https://www.prisma.io/docs/orm/v7/reference/prisma-config-reference | prisma.config.ts | Prisma 7: Config API

## 3.3 Имена: @map и @@map — красиво в коде, как было в базе | short: Переименование моделей | est: ~35 мин
### intro
**Слова шага:** *`@@map`*, *`@map`*, *имя модели*, *имя таблицы*, *соглашения об именовании*.

:::tip Если совсем просто
В базе таблица называется `"tbl_Bookings"` — в коде же хочется писать `prisma.booking`. `@@map` — это табличка-переводчик на двери: «в коде эту комнату называем Booking, а в базе она по-прежнему tbl_Bookings». Ничего в базе при этом не меняется.
:::

Переименуем **модели** (поля пока оставим как есть — этим займётся сессия 4). Для каждой модели: меняем имя на «нормальное» (в единственном числе, `PascalCase`) и добавляем `@@map` со старым именем таблицы.

```prisma schema
// prisma/schema.prisma (фрагмент: только заголовки моделей и @@map; тела не трогаем)
model Branch {
  id   Int     @id @default(autoincrement())
  name String? @db.VarChar(100)
  city String? @db.VarChar(100)
  tz   String? @db.VarChar(40)

  @@map("tbl_Branches")
}

model Item {
  id          Int     @id @default(autoincrement())
  branch_id   Int?
  sku         String? @db.VarChar(30)
  title       String?
  category    String? @db.VarChar(40)
  daily_price String?
  deposit     Float?
  active      Int?    @db.SmallInt
  meta        String?

  @@map("tbl_Items")
}

model Customer {
  id        Int     @id @default(autoincrement())
  CustName  String?
  phone     String?
  email     String?
  branch_id Int?
  created   String?

  @@map("tbl_Customers")
}

model Booking {
  id        Int     @id @default(autoincrement())
  cust_id   Int?
  item_id   Int?
  branch_id Int?
  d_from    String?
  d_to      String?
  price     String?
  deposit   Float?
  status    Int?    @db.SmallInt
  note      String?

  @@map("tbl_Bookings")
}

model Payment {
  id         Int     @id @default(autoincrement())
  booking_id Int?
  amount     Float?
  paid       String?
  kind       Int?    @db.SmallInt
  ext_ref    String?

  @@map("tbl_Payments")
}
```

```bash run
cd ~/prisma-lab/rentkit
npx prisma format
npx prisma validate
```

### result
```out auto
```

`format` расставит отступы и выровняет колонки; `validate` подтвердит, что схема корректна. Таблицы в базе при этом **не тронуты**: `@@map` — только соответствие имён внутри Prisma.

### why
Имя, которое видишь в коде каждый день, должно быть удобным: `prisma.booking.findMany` читается легче, чем `prisma.tbl_Bookings.findMany`. А настоящие имена в базе остаются как есть, и это важно: старый код (который ещё живёт на «проде») продолжает работать.

### deep Как ещё можно
Для уже исправленных баз часто используют `@@map` в нижнем регистре со снейк-кейсом (`bookings`). У нас имена «плохие» нарочно: переименование таблиц в базе — это **миграция**, и делать её на живой системе нужно осторожно (сессия 10). Пока соглашаемся с чужими именами через `@@map`.

### quiz
- Что делает `@@map("tbl_Bookings")` и чего он не делает?
- Почему переименовывать таблицу в базе — отдельная осторожная операция, а `@@map` — безопасная?
- Для чего нужны `format` и `validate`?

### links
- https://www.prisma.io/docs/orm/v7/prisma-schema/data-model/database-mapping | маппинг имён | Prisma 7: Database mapping
- https://www.prisma.io/docs/orm/v7/prisma-client/setup-and-configuration/custom-model-and-field-names | свои имена моделей | Prisma 7: Custom model and field names

## 3.4 Baseline: превращаем существующую базу в «нулевую миграцию» | short: Baseline миграций | est: ~55 мин
### intro
**Слова шага:** *миграция*, *baseline*, *`migrate diff`*, *`migrate resolve --applied`*, *история миграций*, *shadow database*, *`_prisma_migrations`*.

:::tip Если совсем просто
История миграций — это журнал ремонтов квартиры: «в январе поставили перегородку, в феврале заменили проводку». У нашей квартиры журнала нет: её построили до нас. Baseline — это первая запись «квартира принята в таком состоянии», с которой начинается журнал. Prisma не пытается эту запись выполнить заново (всё уже построено), а просто отмечает: «принято».
:::

Порядок по документации Prisma 7 («Baselining», **сверьтесь** с точным названием флагов в вашей версии `prisma migrate diff`):

```bash run
cd ~/prisma-lab/rentkit
mkdir -p prisma/migrations/0_init
npx prisma migrate diff \
  --from-empty \
  --to-schema prisma/schema.prisma \
  --script > prisma/migrations/0_init/migration.sql
head -30 prisma/migrations/0_init/migration.sql
```

### result
```out auto
```

`migrate diff --from-empty --to-schema` печатает SQL, который **создал бы** всё, что описано в схеме, «с пустого места». Мы сохраняем его как нулевую миграцию (префикс `0_` нужен, чтобы она шла первой в алфавитном порядке).

**Проверим, что в нулевой миграции есть и журнал залогов.** Модель `tbl_DepositLog` помечена `@@ignore` — клиент её не видит, но для **миграций** она по-прежнему часть схемы, и `migrate diff` включил её в SQL (`CREATE TABLE "tbl_DepositLog"` идёт в начале вывода). Это важно: история миграций должна быть **полной**. Prisma проверяет изменения на временной «теневой» (shadow) базе, **проигрывая историю с нуля**, и если бы таблицы в истории не было, а следующая миграция (шаг 3.6) её меняет, проигрывание упало бы.

```bash run
cd ~/prisma-lab/rentkit
grep -c 'CREATE TABLE' prisma/migrations/0_init/migration.sql
grep -n 'tbl_DepositLog' prisma/migrations/0_init/migration.sql
```

### result
```out auto
```

Теперь отметим baseline как **уже применённый** (в базе всё уже есть) и проверим статус:

```bash run
cd ~/prisma-lab/rentkit
npx prisma migrate resolve --applied 0_init
npx prisma migrate status
psqlr() { docker exec -i rental-pg psql -U postgres -d rental "$@"; }
psqlr -c 'SELECT migration_name, finished_at IS NOT NULL AS applied FROM _prisma_migrations'
```

### result
```out auto
```

Ожидаем: `Database schema is up to date!`, а в таблице `_prisma_migrations` — одна запись `0_init`. Prisma создала эту служебную таблицу и впервые записала в неё «квартира принята».

### why
Без baseline `prisma migrate dev` попытается создать все таблицы заново и упадёт с «already exists» — или, хуже, предложит «сбросить базу». А «сбросить базу» на унаследованных данных — это потеря 300 тысяч броней. Baseline — единственный способ подключить Prisma Migrate к существующей базе **без потери данных**.

### deep Команды по частям
`migrate diff --from-empty --to-schema schema.prisma --script`: `--from-empty` — «отправная точка: ничего нет», `--to-schema` — «цель: то, что описано в схеме», `--script` — вывести SQL, а не человекочитаемое описание. `migrate resolve --applied 0_init` — записать в `_prisma_migrations`, что миграция применена, **не выполняя её SQL**. Противоположная команда — `--rolled-back` (миграция не удалась и откатана вручную; пригодится в сессии 11).

### deep Если не получилось
- **`Error: unknown option --to-schema`** (или аналогичная) — в вашей версии флаг называется иначе (`--to-schema-datamodel` в старых): `npx prisma migrate diff --help`.
- **Prisma просит `shadow database` и не может её создать** — у пользователя нет права `CREATEDB`; у нас пользователь `postgres` (суперпользователь), поэтому ошибки быть не должно. Иначе задай `datasource.shadowDatabaseUrl` в `prisma.config.ts`.
- **`P3005: The database schema is not empty`** — применять `migrate deploy` к непустой базе без baseline; наша команда `resolve --applied` и решает эту проблему.

### quiz
- Что делает baseline и почему без него `migrate dev` ломает унаследованную базу?
- Чем `migrate resolve --applied` отличается от `migrate deploy`?
- Почему `tbl_DepositLog` есть в `0_init`, хотя клиент её «не видит» (`@@ignore`)?

### links
- https://www.prisma.io/docs/orm/v7/prisma-migrate/workflows/baselining | baselining | Prisma 7: Baselining a database
- https://www.prisma.io/docs/orm/v7/prisma-migrate/understanding-prisma-migrate/shadow-database | shadow database | Prisma 7: Shadow database

## 3.5 prisma studio, validate, format — три мелочи | short: Studio, validate, format | est: ~25 мин
### intro
**Слова шага:** *`prisma studio`*, *`prisma validate`*, *`prisma format`*, *проверка схемы*.

:::tip Если совсем просто
Три инструмента «под рукой»: **studio** — окно, где можно посмотреть и подправить данные мышкой (как DBeaver, но от Prisma), **validate** — «схема написана правильно?», **format** — «причесать схему».
:::

```bash run
cd ~/prisma-lab/rentkit
npx prisma validate
npx prisma format
npx prisma generate
ls src/generated/prisma | head
```

### result
```out auto
```

`prisma generate` создаст клиент в `src/generated/prisma/` (так мы указали в `output`) — первый раз; дальше его нужно запускать после **каждого** изменения схемы. `prisma studio` запускается командой `npx prisma studio` и открывается в браузере (**сверьтесь**: в Prisma 7 он берёт адрес базы из `datasource` в `prisma.config.ts`); в лабе мы пользуемся им только для беглого взгляда — основная работа идёт через `psql`, потому что Studio скрывает SQL.

### why
Эти три команды — «гигиена»: `validate` и `format` стоит запускать перед каждым коммитом, `generate` — после каждой правки схемы. Привычка делать их автоматически (в CI, сессия 18) спасает от «у меня работает, а у коллеги нет».

### deep Если не получилось
- **`prisma generate` не создал папку** — проверь `output` в `schema.prisma` (путь считается от файла схемы, `../src/generated/prisma` от `prisma/`) и права на запись.
- **Studio не открывается** — порт 5555 занят; запусти с `--port 5556`.

### quiz
- Когда нужно запускать `prisma generate`?
- Чем Studio удобен и чем неудобен для разбора запросов?

### links
- https://www.prisma.io/docs/orm/v7/reference/prisma-cli-reference | справочник CLI | Prisma 7: CLI reference

## 3.6 🔨 Таблица без первичного ключа: клиент её «не видит» | short: 🔨 Таблица без PK | est: ~50 мин
### intro
**Слова шага:** *`@@ignore`*, *первичный ключ*, *ручная миграция*, *`migrate deploy`*, *имя папки миграции*, *`P3006`*.

:::tip Если совсем просто
В журнале залогов (`tbl_DepositLog`) строки нигде не пронумерованы: нельзя сказать «исправь запись №5», потому что у неё нет номера. Prisma требует у каждой модели такой номер (уникальный идентификатор) — иначе модели просто нет в клиенте. Лечение: добавить колонку-номер в базу **миграцией** и подтянуть модель.
:::

Проверим, что клиент действительно **не видит** журнал залогов:

```bash run
cd ~/prisma-lab/rentkit
cat > src/intro/08-depositlog.ts <<'EOF'
import 'dotenv/config'
import { PrismaPg } from '@prisma/adapter-pg'
import { PrismaClient } from '../generated/prisma/client.js'

const prisma = new PrismaClient({ adapter: new PrismaPg({ connectionString: process.env.DATABASE_URL! }) })
console.log(Object.keys(prisma).filter((k) => k !== 'constructor' && !k.startsWith('$') && !k.startsWith('_')))
await prisma.$disconnect()
EOF
npx tsx src/intro/08-depositlog.ts
```

### result
```out auto
```

В списке будут `branch`, `item`, `customer`, `booking`, `payment` — но **не `depositLog`**. Чиним в три шага. **Шаг 1** — ручная миграция. Папку называем `ГГГГММДДччммсс_описание` (по алфавиту она должна идти после `0_init`); в ней один файл `migration.sql`:

```sql
-- prisma/migrations/20261020100000_depositlog_pk/migration.sql
ALTER TABLE "tbl_DepositLog" ADD COLUMN "id" SERIAL NOT NULL;
ALTER TABLE "tbl_DepositLog" ADD CONSTRAINT "tbl_DepositLog_pkey" PRIMARY KEY ("id");
```

**Шаг 2** — применить и убедиться, что история в порядке:

```bash run
cd ~/prisma-lab/rentkit
mkdir -p prisma/migrations/20261020100000_depositlog_pk
cat > prisma/migrations/20261020100000_depositlog_pk/migration.sql <<'EOF'
ALTER TABLE "tbl_DepositLog" ADD COLUMN "id" SERIAL NOT NULL;
ALTER TABLE "tbl_DepositLog" ADD CONSTRAINT "tbl_DepositLog_pkey" PRIMARY KEY ("id");
EOF
npx prisma migrate deploy
npx prisma migrate status
```

### result
```out auto
```

**Шаг 3** — подтянуть модель в схему. Проще всего повторить `db pull` (он увидит ключ и уберёт `@@ignore`), но ты уже переименовала модели — поэтому смотри результат без записи и **перенеси модель руками**:

```bash run
cd ~/prisma-lab/rentkit
npx prisma db pull --print | grep -A12 'tbl_DepositLog'
```

### result
```out auto
```

В выводе `db pull --print` модель `tbl_DepositLog` уже **без** `@@ignore` (с колонкой `id`), а внутри неё Prisma оставила комментарий `// *** WARNING ***` — она напоминает, что имена `Booking`, `Branch` и остальных взяты из твоих `@@map`. Это нормально. Теперь замени `@@ignore`-модель в `schema.prisma` на переименованную, с `@@map` (старое определение `tbl_DepositLog` при этом уходит):

```prisma schema
model DepositLog {
  id         Int     @id @default(autoincrement())
  booking_id Int?
  delta      Float?
  ts         BigInt?
  reason     String?

  @@map("tbl_DepositLog")
}
```

Затем `npx prisma format && npx prisma generate` — теперь у клиента есть `depositLog`.

**Приёмка сессии:** `migrate status` — `Database schema is up to date!` с двумя миграциями (`0_init`, `…_depositlog_pk`); `prisma generate` проходит; у клиента пять+одна модель, включая `depositLog`; в `NOTES.md` — полный список болячек с цифрами из шага 3.1.

### why
Эта история учит сразу двум вещам. **Первая:** Prisma ничего не делает с таблицей без идентификатора — молча. Об этом нужно знать, иначе «пропавшие» данные ищут часами. **Вторая:** миграции — это **полная** история, которую можно проиграть с нуля; поэтому важно, что `tbl_DepositLog` попала в `0_init` (`@@ignore` на миграции не влияет): иначе вторая миграция на чистой базе (в CI или у коллеги) упала бы.

### deep Если не получилось
- **`P3006: Migration failed to apply cleanly to the shadow database`** — проигрывание истории на пустой базе упало: чаще всего в `0_init` не хватает таблицы (проверь `grep` из шага 3.4) или порядок папок не тот.
- **`ERROR: column "id" of relation … already exists`** — миграция применена вручную раньше (прямо через `psql`); тогда база и история разошлись (**drift**, разберём в 11.5). Отметь её применённой: `npx prisma migrate resolve --applied 20261020100000_depositlog_pk`.
- **`deploy` не видит новую папку** — в имени должен быть `migration.sql` строго с таким названием.

### quiz
- Почему клиент не видит таблицу без первичного ключа и как это заметить?
- Зачем нужна именно «ручная» миграция в этом шаге?
- Что такое shadow database и почему она требует полной истории миграций?

### links
- https://www.prisma.io/docs/orm/v7/prisma-migrate/workflows/customizing-migrations | ручная правка миграций | Prisma 7: Customizing migrations
- https://www.prisma.io/docs/orm/v7/prisma-schema/introspection#introspection-and-ignore | @@ignore | Prisma 7: Introspection
