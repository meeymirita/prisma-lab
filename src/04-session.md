# Сессия 4 · Схема Prisma
dur: ~4 ч

## 4.1 Язык схемы: модели, поля, атрибуты | short: Язык схемы | est: ~35 мин
### intro
**Слова шага:** *`model`*, *поле*, *`?` и `[]`*, *атрибут `@`*, *блочный атрибут `@@`*, *комментарий `///`*.

:::tip Если совсем просто
Схема Prisma читается как анкета: «Модель Бронь: номер (целое, ключ, считать по порядку), клиент (целое), заметка (текст, может отсутствовать)». Одиночная `@` описывает одно поле, двойная `@@` — всю модель целиком (под каким именем она в базе, какие индексы).
:::

```prisma
model Example {
  id     Int      @id @default(autoincrement())   // @id — первичный ключ; @default — значение по умолчанию
  title  String                                   // обязательное поле
  note   String?                                  // «?» — может быть null
  tags   String[]                                 // «[]» — список (в PostgreSQL — массив)
  /// Комментарий с тремя слэшами попадает в сгенерированный тип как подсказка
  weight Int      @default(0)

  @@index([title])                                // @@ — атрибут уровня модели
  @@map("tbl_Example")
}
```

Что нужно знать, чтобы читать любую схему:

- **Тип поля** — слева от атрибутов: `Int`, `String`, `Boolean`, `DateTime`, `Decimal`, `Json`, `BigInt`, `Bytes`, `Float` или имя другой модели/enum.
- **`?`** — «может быть `null`», тип в TS получит `| null`; **`[]`** — список.
- **Атрибуты поля:** `@id`, `@unique`, `@default(...)`, `@map("имя_колонки")`, `@db.VarChar(100)` (точный тип PostgreSQL), `@updatedAt`, `@relation(...)`.
- **Атрибуты модели:** `@@id([a, b])` (составной ключ), `@@unique([a, b])`, `@@index([...])`, `@@map("имя_таблицы")`.
- **Комментарии:** `//` — обычный, `///` — попадает в подсказки редактора.

```bash run
cd ~/prisma-lab/rentkit
npx prisma validate
npx prisma format
```

### result
```out auto
```

Файл схемы **не исполняется** — это описание. Prisma читает его и: (а) создаёт по нему клиент (`prisma generate`), (б) сравнивает с базой при миграциях (`migrate dev`). Каждое изменение схемы — это либо только перестройка клиента (переименования с `@map`), либо ещё и **изменение базы** (новая колонка, тип, индекс).

### why
Все остальные сессии — это работа со схемой: добавить связь, enum, индекс, ограничение. Если схема читается «как текст», то каждая правка — это осознанный шаг, а не копирование из чужого примера.

### deep Как ещё можно
Схему можно разбить на несколько файлов (`prisma/schema/*.prisma`) — Prisma 7 это умеет через `schema: 'prisma/schema'` в конфиге (папка вместо файла). Для лабы один файл удобнее; при десятках моделей обычно делят по доменам (`booking.prisma`, `billing.prisma`).

### quiz
- Чем `@` отличается от `@@` в схеме?
- Что значат `String?` и `String[]`?
- Когда изменение схемы меняет базу, а когда — только клиент?

### links
- https://www.prisma.io/docs/orm/v7/prisma-schema/data-model/models | модели | Prisma 7: Models
- https://www.prisma.io/docs/orm/v7/reference/prisma-schema-reference | справочник схемы | Prisma 7: Schema API reference

## 4.2 Типы: PostgreSQL ↔ Prisma ↔ TypeScript | short: Соответствие типов | est: ~40 мин
### intro
**Слова шага:** *нативный тип (`@db.*`)*, *`Decimal`*, *`BigInt`*, *`DateTime`*, *`Json`*, *`timestamptz`*, *потеря точности*.

:::tip Если совсем просто
Три языка: PostgreSQL, Prisma и TypeScript. Одно и то же слово означает в них разное: «число» в PostgreSQL — это `integer`, `bigint`, `numeric`, `double precision`; в TS — только `number` (и `bigint`). Таблица перевода нужна, чтобы деньги не превращались в «почти те же деньги».
:::

```svg
@types-map
```

| PostgreSQL | Prisma (по умолчанию) | TypeScript | Пример `@db.` |
|---|---|---|---|
| `integer`, `smallint` | `Int` | `number` | `@db.SmallInt` |
| `bigint` | `BigInt` | `bigint` | |
| `numeric(12,2)` | `Decimal` | `Prisma.Decimal` | `@db.Decimal(12, 2)` |
| `double precision`, `real` | `Float` | `number` | |
| `text`, `varchar(n)` | `String` | `string` | `@db.VarChar(100)` |
| `boolean` | `Boolean` | `boolean` | |
| `timestamptz`, `timestamp` | `DateTime` | `Date` | `@db.Timestamptz(3)` |
| `date` | `DateTime` | `Date` | `@db.Date` |
| `jsonb`, `json` | `Json` | `Prisma.JsonValue` | |
| `bytea` | `Bytes` | `Buffer`/`Uint8Array` | |
| диапазоны, `tstzrange` | не поддерживается | — | `Unsupported("tstzrange")` |

Три типа, на которых ломаются чаще всего:

1. **`Decimal`**: `numeric` приходит в код как `Prisma.Decimal` (объект из библиотеки `decimal.js`), **не** как `number`. Попытка сложить `a + b` даст склейку строк; нужно `a.plus(b)`. Именно поэтому деньги не хранят в `Float` (сессия 14).
2. **`BigInt`**: приходит как `bigint` (с суффиксом `n`: `10n`). `JSON.stringify` его **не умеет** — получишь `TypeError: Do not know how to serialize a BigInt`. Результат `count(*)` из raw-запроса — тоже `bigint`.
3. **`DateTime`**: в TS — `Date`. В базе `timestamptz` хранит момент времени (UTC), `timestamp` — «голые» часы без пояса. Prisma даёт тебе `Date`, а как его показать — твоя забота (сессия 7.5).

Что у нас в базе, и во что Prisma это превратила после `db pull`: `daily_price text → String`, `deposit double precision → Float`, `status smallint → Int @db.SmallInt`, `ts bigint → BigInt`.

### why
Типы — самое тихое место для ошибок. Код компилируется, запрос выполняется, а `0.1 + 0.2` даёт `0.30000000000000004` в платеже. Таблица перевода нужна, чтобы **до** написания кода понимать, какой тип придёт.

### deep Под капотом: `Decimal` и `Float`
`double precision` хранит число в двоичной дроби — `0.1` в ней не представимо точно. `numeric` хранит десятичные цифры, поэтому `0.1 + 0.2 = 0.3` точно. В лабе деньги в наследстве лежат как `float8` и `text` — их переводим в `numeric(12,2)` в сессии 10.

### quiz
- Почему `numeric` приходит в TS как `Prisma.Decimal`, а не `number`?
- Что произойдёт при `JSON.stringify` объекта с полем `bigint`?
- Чем `timestamptz` отличается от `timestamp`?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/type-safety/prisma-type-system | типы Prisma | Prisma 7: Prisma type system
- https://www.prisma.io/docs/orm/v7/prisma-migrate/workflows/native-database-types | нативные типы | Prisma 7: Native database types

## 4.3 Идентификаторы и значения по умолчанию | short: @id и @default | est: ~30 мин
### intro
**Слова шага:** *`@id`*, *`autoincrement()`*, *`uuid()`*, *`cuid()`*, *`now()`*, *`dbgenerated()`*, *default на стороне клиента и базы*.

:::tip Если совсем просто
Номерок в гардеробе можно выдавать по порядку (1, 2, 3…) или случайным кодом (`9f3a-…`). По порядку — удобно читать, но легко угадать; случайный — неугадываемый, но неудобный. `@default` — кто и когда номерок выдаёт.
:::

| Значение | Кто генерирует | Особенность |
|---|---|---|
| `@default(autoincrement())` | **база** (последовательность/`serial`) | у нас так во всех таблицах |
| `@default(uuid())` | **Prisma-клиент** | uuid v4 создаётся в коде, не в базе |
| `@default(cuid())` | **Prisma-клиент** | короткий сортируемый id |
| `@default(now())` | **база** (`DEFAULT CURRENT_TIMESTAMP`) | момент вставки |
| `@default(dbgenerated("…"))` | **база** | любое SQL-выражение: `gen_random_uuid()`, `now() + interval '1 day'` |
| `@updatedAt` | **клиент** | обновляется Prisma при каждом `update` — **не** триггер в базе |

Важное следствие: то, что генерирует **клиент** (`uuid()`, `cuid()`, `@updatedAt`), **не работает**, если строку вставляет не Prisma (скрипт, `psql`, старый код). А `@default(now())` и `autoincrement()` — это настоящие `DEFAULT` в базе: работают для всех.

```prisma
model Example {
  id        Int      @id @default(autoincrement())     // DEFAULT nextval(...)  — работает для любого, кто пишет в таблицу
  uid       String   @unique @default(dbgenerated("gen_random_uuid()"))   // uuid из базы
  createdAt DateTime @default(now()) @db.Timestamptz(3)
  updatedAt DateTime @updatedAt                        // только когда пишет Prisma!
}
```

### why
В унаследованной системе пишут и Prisma, и старый код, и ночные скрипты. Если `updatedAt` обновляет только Prisma, а старый код его не трогает, у тебя «обновлено вчера», когда на самом деле час назад. Знание, **кто** генерирует значение, — это защита от целого класса неочевидных расхождений.

### deep Если не получилось
- **`uuid` в базе пустой, хотя в схеме `@default(uuid())`** — строку вставили в обход Prisma (через `psql` или другой код); используй `dbgenerated("gen_random_uuid()")`, чтобы значение создавала база.
- **Prisma хочет `@db.Uuid`** — для `gen_random_uuid()` в базе нужен тип `uuid`, добавь `@db.Uuid`.

### quiz
- Чем `@default(uuid())` отличается от `@default(dbgenerated("gen_random_uuid()"))` по тому, кто создаёт значение?
- Почему `@updatedAt` опасен в базе, куда пишут не только через Prisma?

### links
- https://www.prisma.io/docs/orm/v7/reference/prisma-schema-reference#default | @default | Prisma 7: @default
- https://www.prisma.io/docs/orm/v7/prisma-migrate/workflows/native-database-functions | функции базы | Prisma 7: Native database functions

## 4.4 Расследование: что значат числа в status | short: Статусы-числа | est: ~55 мин
### intro
**Слова шага:** *`enum`*, *магические числа*, *восстановление смысла по данным*, *корреляции*, *справочник*.

:::tip Если совсем просто
В `status` лежат числа 0–7, а что они значат, знал только программист, который давно уволился. Задача детектива: по косвенным уликам — у каких броней есть доплата, у каких возврат — выяснить, что обозначает каждая цифра. Потом мы закрепим это в справочнике, чтобы никто больше не гадал.
:::

Заказчик пишет: *«в отчёте у нас статусы 0–7, а что это — никто не помнит. Составьте расшифровку»*. Основная идея: смысл статуса виден по тому, что с бронью **происходило**: платила ли, возвращали ли залог, когда начало.

```bash run
psqlr() { docker exec -i rental-pg psql -U postgres -d rental "$@"; }
psqlr <<'SQL'
-- сколько броней в каждом статусе, и какие платежи по ним есть
SELECT b.status,
       count(DISTINCT b.id)                                        AS броней,
       count(*) FILTER (WHERE p.kind = 1)                          AS предоплат,
       count(*) FILTER (WHERE p.kind = 2)                          AS доплат,
       count(*) FILTER (WHERE p.kind = 3)                          AS возвратов
FROM "tbl_Bookings" b
LEFT JOIN "tbl_Payments" p ON p.booking_id = b.id
GROUP BY b.status ORDER BY b.status;

-- движения залога по статусам
SELECT b.status,
       count(*) FILTER (WHERE l.reason = 'hold')   AS удержан,
       count(*) FILTER (WHERE l.reason = 'return') AS возвращён,
       count(*) FILTER (WHERE l.reason = 'keep')   AS оставлен
FROM "tbl_Bookings" b
JOIN "tbl_DepositLog" l ON l.booking_id = b.id
GROUP BY b.status ORDER BY b.status;
SQL
```

### result
```out auto
```

Как читать улики (и проверь это по **своим** числам):

- **0** — нет ни одного платежа: черновик (бронь заведена, не оплачена).
- **1** — есть только предоплата, залога нет, начало в будущем: подтверждена.
- **2** — залог удержан, возврата нет: предмет **выдан** клиенту.
- **3** — предоплата, доплата, залог удержан и возвращён: бронь **завершена** (самый частый статус).
- **4** — предоплата и её возврат: **отменена**.
- **5** — предоплата есть, больше ничего: клиент **не пришёл**.
- **6** — доплата и возврат залога, но поздно (возврат позже срока): **просрочена**.
- **7** — залог удержан, возвращён лишь часть, часть оставлена: предмет **утерян или повреждён**.

Закрепим расшифровку **в коде** (в базе пока числа — enum появится в сессии 10, когда поменяем тип колонки):

```ts
// src/domain/status.ts
export const BookingStatus = {
  DRAFT: 0,       // черновик: не оплачена
  CONFIRMED: 1,   // подтверждена (предоплата)
  ISSUED: 2,      // выдана, залог удержан
  RETURNED: 3,    // завершена: вернули, всё оплачено
  CANCELLED: 4,   // отменена, предоплата возвращена
  NO_SHOW: 5,     // клиент не пришёл
  OVERDUE: 6,     // просрочена
  DAMAGED: 7,     // утеряно или повреждено
} as const

export type BookingStatus = (typeof BookingStatus)[keyof typeof BookingStatus]
```

### why
Эта таблица — страховка от «магических чисел»: пока в коде `status === 3`, никто не помнит, что это значит. `BookingStatus.RETURNED` читается сразу. А главное — вывод получен **из данных**, а не из чьей-то памяти, и его можно проверить запросом. Когда в сессии 10 мы превратим колонку в PostgreSQL-enum, имена возьмём отсюда.

### deep Как ещё можно
В схеме Prisma статусы можно описать как `enum BookingStatus { DRAFT … }`, но у `enum` в базе другой тип, чем `smallint`: сейчас привязать его к существующей колонке нельзя. Поэтому до сессии 10 — константа в коде и `Int` в схеме.

### deep Если не получилось
- **Числа не совпадают с ожидаемыми** — не страшно: на другом наборе данных соотношения иные; важнее логика: статус «не платил» → 0, «вернул залог» → 3 и так далее. Если корреляции неочевидны — проверь запросом, как **распределены даты** (`d_from` в будущем у `1`?).

### quiz
- Каким способом мы восстановили смысл статусов и почему он надёжнее «спросить у коллеги»?
- Почему пока нельзя описать статусы как `enum` в схеме?
- Что даёт константа `BookingStatus` в коде по сравнению с числами?

### links
- https://www.prisma.io/docs/orm/v7/prisma-schema/data-model/models#defining-enums | enum | Prisma 7: Defining enums

## 4.5 Нормальные имена полей: @map для каждой колонки | short: @map полей | est: ~40 мин
### intro
**Слова шага:** *`@map` у поля*, *соглашение camelCase*, *имена, подсказывающие «грязь»*, *`startText`*.

:::tip Если совсем просто
В коде удобно писать `booking.customerId`, а в базе колонка называется `cust_id`. `@map` — табличка у каждого поля. Но у «грязных» колонок мы нарочно даём имена-предупреждения: `startText` вместо `startsAt` — чтобы каждый видел, что там строка, а не дата. Когда почистим (сессия 10), имена станут правильными.
:::

Заменяем модели целиком на версию с нормальными именами (формат: `camelCase` в коде, `@map("старое_имя")` для колонок). Имена «…Text» — намеренное напоминание о проблеме:

```prisma
model Branch {
  id   Int     @id @default(autoincrement())
  name String? @db.VarChar(100)
  city String? @db.VarChar(100)
  tz   String? @db.VarChar(40)

  @@map("tbl_Branches")
}

model Item {
  id             Int     @id @default(autoincrement())
  branchId       Int?    @map("branch_id")
  sku            String? @db.VarChar(30)
  title          String?
  category       String? @db.VarChar(40)
  dailyPriceText String? @map("daily_price")      // text: «450,00», «1 200,00 руб»…
  deposit        Float?                           // double precision — деньги в float!
  active         Int?    @db.SmallInt
  meta           String?                          // JSON внутри text

  @@map("tbl_Items")
}

model Customer {
  id          Int     @id @default(autoincrement())
  name        String? @map("CustName")
  phone       String?
  email       String?
  branchId    Int?    @map("branch_id")
  createdText String? @map("created")             // text: два формата

  @@map("tbl_Customers")
}

model Booking {
  id         Int     @id @default(autoincrement())
  customerId Int?    @map("cust_id")
  itemId     Int?    @map("item_id")
  branchId   Int?    @map("branch_id")
  startText  String? @map("d_from")               // text: три формата
  endText    String? @map("d_to")
  priceText  String? @map("price")                // text: «1 200,00 руб»
  deposit    Float?
  status     Int?    @db.SmallInt                 // 0..7, см. src/domain/status.ts
  note       String?

  @@map("tbl_Bookings")
}

model Payment {
  id        Int     @id @default(autoincrement())
  bookingId Int?    @map("booking_id")
  amount    Float?                                // double precision
  paidText  String? @map("paid")                  // text: два формата
  kind      Int?    @db.SmallInt                  // 1 предоплата, 2 доплата, 3 возврат
  extRef    String? @map("ext_ref")

  @@map("tbl_Payments")
}

model DepositLog {
  id        Int     @id @default(autoincrement())
  bookingId Int?    @map("booking_id")
  delta     Float?
  ts        BigInt?                               // unix-секунды
  reason    String?                               // hold | return | keep

  @@map("tbl_DepositLog")
}
```

```bash run
cd ~/prisma-lab/rentkit
npx prisma format
npx prisma validate
npx prisma generate
```

### result
```out auto
```

**Ничего не поменялось в базе**: `@map` на поле — только соответствие в Prisma. Чтобы убедиться, попроси Prisma сравнить схему с базой (**сверьтесь**: точный текст сообщения):

```bash run
cd ~/prisma-lab/rentkit
npx prisma migrate dev --create-only --name should_be_empty
```

### result
```out auto
```

Ожидаем: «Already in sync, no schema change or pending migration was found» — миграция **не создана**. Если создалась — в схеме есть изменение, затрагивающее базу (проверь, не потерялся ли `@db.SmallInt` или `@map`): удали созданную папку и найди расхождение.

### why
Имя, которое ты видишь тысячу раз в день, определяет, как ты думаешь о данных. `startText` сразу говорит: «тут строка, осторожно»; `startsAt` обманул бы. Одновременно мы не трогаем базу: старый код и старые отчёты по-прежнему видят свои колонки.

### deep Как ещё можно
Соглашение «имена в коде — `camelCase`, в базе — `snake_case`» принято в ТS-мире. Prisma не делает это автоматически: нужно `@map` у каждого поля (или инструмент, который расставит их по всей схеме). У нас имена в базе разнородные — поэтому расставляем вручную.

### deep Если не получилось
- **`migrate dev` создал непустую миграцию** — в схеме поменялся тип или `@db.*`-атрибут. Сравни с выводом `db pull --print` и приведи в соответствие.
- **`migrate dev` просит сбросить базу** — **не соглашайся** (`n`): это drift; разберём в 11.5, а сейчас вернись к предыдущему рабочему состоянию схемы.

### quiz
- Что делает `@map` у поля и почему при этом база не меняется?
- Зачем мы нарочно назвали поле `startText`, а не `startsAt`?
- Как убедиться, что правка схемы не требует миграции?

### links
- https://www.prisma.io/docs/orm/v7/prisma-schema/data-model/database-mapping#map-column-names | маппинг колонок | Prisma 7: Map column names

## 4.6 Генератор клиента и общий модуль db.ts | short: Генератор и db.ts | est: ~40 мин
### intro
**Слова шага:** *`generator`*, *`provider = "prisma-client"`*, *`output`*, *`PrismaClient`*, *driver adapter*, *singleton*.

:::tip Если совсем просто
Клиент — это «деталь, напечатанная по твоему чертежу». Чертёж изменился — деталь нужно **напечатать заново** (`generate`). А собранный экземпляр клиента мы создадим **один раз** в файле `db.ts` и будем импортировать его везде: как одну кассу на всю кофейню, а не новую кассу на каждый заказ.
:::

В `generator` Prisma 7 важные поля: `provider = "prisma-client"` (новый генератор), `output` (обязателен), `previewFeatures` (если нужны предпросмотровые возможности). Проверь шапку схемы:

```prisma
generator client {
  provider = "prisma-client"
  output   = "../src/generated/prisma"
}

datasource db {
  provider = "postgresql"
}
```

(**Сверьтесь:** у генератора `prisma-client` есть дополнительные настройки вывода — формат модулей и расширения импортов; для нашего проекта с `"type": "module"` и `NodeNext` значения по умолчанию должны подойти.)

Теперь общий модуль:

```ts
// src/db.ts
import 'dotenv/config'
import { PrismaPg } from '@prisma/adapter-pg'
import { PrismaClient } from './generated/prisma/client.js'

const adapter = new PrismaPg({ connectionString: process.env.DATABASE_URL! })

export const prisma = new PrismaClient({
  adapter,
  log: [{ emit: 'event', level: 'query' }],     // события запросов; смотреть будем в шаге 5.5
})
```

Проверочный скрипт:

```ts
// src/intro/09-smoke.ts
import { prisma } from '../db.js'

const [branches, items, customers, bookings] = await Promise.all([
  prisma.branch.count(),
  prisma.item.count(),
  prisma.customer.count(),
  prisma.booking.count(),
])
console.log({ branches, items, customers, bookings })
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx prisma generate
npx tsx src/intro/09-smoke.ts
npm run typecheck
```

### result
```out auto
```

Ожидаем `{ branches: 12, items: 4000, customers: 60000, bookings: 300000 }` и чистую проверку типов. Запомни два правила: **`generate` — после каждого изменения схемы**; **`prisma.$disconnect()`** — в скриптах, которые должны завершиться (иначе пул соединений держит процесс открытым).

### why
Один экземпляр `PrismaClient` на процесс — не прихоть. У каждого клиента своя связка соединений: создашь клиент в каждой функции — быстро выберешь все `max_connections` базы (шаг 17.2). Модуль в ES-системе загружается один раз, поэтому `export const prisma` в `db.ts` — готовый singleton.

### deep Команды по частям
`new PrismaPg({ connectionString })` — адаптер к драйверу `pg`: через него идут все запросы. Параметры пула (`max`, `connectionTimeoutMillis`, `idleTimeoutMillis`) передаются сюда же (сессия 17). `process.env.DATABASE_URL!` — восклицательный знак говорит TS «я знаю, что переменная задана»; корректнее проверить её наличие и выбросить понятную ошибку (мы так сделаем в сессии 18).

### deep Если не получилось
- **`Cannot find module './generated/prisma/client.js'`** — клиент не создан или `output` другой: `npx prisma generate` и проверь путь.
- **`PrismaClientInitializationError: … must be a valid adapter`** — в Prisma 7 клиент без адаптера не создаётся: убедись, что передаёшь `adapter`.
- **Процесс не завершается** — не вызван `$disconnect()`.

### quiz
- Когда нужно запускать `prisma generate`?
- Почему `PrismaClient` создают один раз на процесс, а не в каждой функции?
- Для чего скрипту нужен `$disconnect()`?

### links
- https://www.prisma.io/docs/orm/v7/prisma-schema/overview/generators | генераторы | Prisma 7: Generators
- https://www.prisma.io/docs/orm/v7/prisma-client/setup-and-configuration/introduction | настройка клиента | Prisma 7: Introduction to Prisma Client

## 4.7 🔨 Клиент не обновился: типы «старые» | short: 🔨 Забыт generate | est: ~35 мин
### intro
**Слова шага:** *устаревший клиент*, *`prisma generate`*, *ошибка типов после правки схемы*, *`postinstall`*.

:::tip Если совсем просто
Ты перекрасила чертёж, но деталь на станке осталась старой. Код ссылается на новое имя, а клиент о нём не знает — отсюда ошибка «такого поля нет». Лечится одним действием, которое легко забыть: напечатать деталь заново.
:::

Сломаем: переименуй в `schema.prisma` поле `startText` модели `Booking` в `startRaw` (руками, в редакторе: остальное в строке — `@map("d_from")` — не трогай) и **не запускай** `generate`.

```bash run
cd ~/prisma-lab/rentkit
grep -n 'd_from' prisma/schema.prisma
cat > src/intro/10-stale.ts <<'EOF'
import { prisma } from '../db.js'
const b = await prisma.booking.findFirst({ select: { id: true, startRaw: true } })
console.log(b)
await prisma.$disconnect()
EOF
npm run typecheck 2>&1 | head -6
```

### result
```out auto
```

Ожидаем ошибку компиляции вида `Object literal may only specify known properties, and 'startRaw' does not exist in type 'BookingSelect'` — клиент помнит `startText`. Запуск через `tsx` (он не проверяет типы!) упал бы уже в работе: `Unknown field startRaw`. Чиним:

```bash run
cd ~/prisma-lab/rentkit
npx prisma generate
npm run typecheck
npx tsx src/intro/10-stale.ts
```

### result
```out auto
```

Верни прежнее имя (`startText`) и снова запусти `generate`, чтобы дальше работать с сохранённой схемой. **Как не забывать:** (1) добавь в `package.json` скрипт `"postinstall": "prisma generate"` — клиент пересоберётся после `npm install`; (2) добавь `"typecheck": "prisma generate && tsc --noEmit"`; (3) в CI (сессия 18) `generate` — отдельный обязательный шаг. В Prisma 7 после `migrate dev` **`generate` не запускается сам** — это важное отличие от старых версий.

**Приёмка сессии:** схема с нормальными именами и `@map`, `migrate dev --create-only` сообщает, что база и схема в синхроне, клиент генерируется, `npx tsx src/intro/09-smoke.ts` печатает ожидаемые числа, а расшифровка статусов лежит в `src/domain/status.ts`.

### why
«У меня правильный код, а редактор ругается» — в 9 из 10 случаев забыт `generate`. Привычка: поменяла схему — запусти генерацию, потом открывай редактор. В Prisma 7 это особенно важно, потому что автоматического запуска нет.

### deep Если не получилось
- **В `grep` не видно `startRaw`** — поле переименовано не в том месте: ищи в модели `Booking` строку с `@map("d_from")`.
- **Ошибка типов осталась после `generate`** — перезапусти сервер TypeScript в редакторе («Restart TS server»): он мог закешировать старые типы.

### quiz
- Почему после переименования поля в схеме код перестаёт компилироваться?
- Что изменилось в Prisma 7 в отношении автоматического `generate`?
- Как сделать так, чтобы клиент обновлялся после `npm install`?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/setup-and-configuration/generating-prisma-client | генерация клиента | Prisma 7: Generating Prisma Client
