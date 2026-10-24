# Сессия 9 · Raw SQL и TypedSQL
dur: ~4 ч

## 9.1 Когда Prisma не хватает: окна, CTE, LATERAL | short: Где ORM не хватает | est: ~40 мин
### intro
**Слова шага:** *оконная функция*, *`CTE (WITH)`*, *`LATERAL`*, *`FILTER`*, *`rank()`*, *«отчёт, а не объект»*.

:::tip Если совсем просто
Prisma прекрасно приносит **объекты** («бронь с клиентом»). Но бухгалтерия просит **таблицы-итоги**: «топ-3 клиента по выручке в каждом филиале», «нарастающая сумма по месяцам». Для таких вопросов у SQL есть свои слова — окна, CTE, LATERAL, — и у Prisma их нет. Тогда ты пишешь запрос сама, а Prisma лишь отправляет его и типизирует ответ.
:::

Три отчёта, которые Prisma-клиентом не выразить (проверь их сначала в `psql` — отладка SQL идёт быстрее там):

```bash run
psqlr() { docker exec -i rental-pg psql -U postgres -d rental "$@"; }
psqlr <<'SQL'
-- 1. оконная функция: топ-3 клиента по выручке в каждом филиале
WITH revenue AS (
  SELECT b.branch_id, b.cust_id, sum(p.amount::numeric) AS total
  FROM "tbl_Payments" p JOIN "tbl_Bookings" b ON b.id = p.booking_id
  WHERE p.kind IN (1, 2) AND b.cust_id IS NOT NULL
  GROUP BY b.branch_id, b.cust_id
), ranked AS (
  SELECT *, rank() OVER (PARTITION BY branch_id ORDER BY total DESC) AS rnk FROM revenue
)
SELECT branch_id, cust_id, round(total, 2) AS total, rnk FROM ranked WHERE rnk <= 3 ORDER BY branch_id, rnk LIMIT 9;

-- 2. последний платёж каждой из первых 5 броней: LATERAL
SELECT b.id, lp.amount, lp.kind
FROM "tbl_Bookings" b
CROSS JOIN LATERAL (SELECT amount, kind FROM "tbl_Payments" p WHERE p.booking_id = b.id ORDER BY p.id DESC LIMIT 1) lp
WHERE b.id <= 5;

-- 3. FILTER: возвраты и поступления одной строкой по филиалу
SELECT b.branch_id,
       round(sum(p.amount) FILTER (WHERE p.kind IN (1, 2))::numeric, 0) AS поступления,
       round(sum(p.amount) FILTER (WHERE p.kind = 3)::numeric, 0)        AS возвраты
FROM "tbl_Payments" p JOIN "tbl_Bookings" b ON b.id = p.booking_id
GROUP BY b.branch_id ORDER BY 1 LIMIT 5;
SQL
```

### result
```out auto
```

Что здесь: **`WITH … AS`** (CTE) — именованный подзапрос, как «временная таблица на время запроса»; **`rank() OVER (PARTITION BY … ORDER BY …)`** — нумерация внутри группы (оконная функция: строки не схлопываются, как в `GROUP BY`); **`CROSS JOIN LATERAL`** — подзапрос, который может ссылаться на колонки строки слева (на каждую бронь свой «последний платёж»); **`FILTER`** — условие внутри агрегата. Ничего из этого Prisma Client не умеет — ни `groupBy`, ни `include` не заменят.

### why
Умение вовремя выйти в SQL — граница между «пользуюсь ORM» и «умею с ней работать». Правило: **объекты — через Prisma, отчёты и итоги — через SQL.** Если ты тащишь в JS десять тысяч строк, чтобы сгруппировать их там, SQL написать быстрее и в сто раз дешевле.

### deep Как ещё можно
Если один и тот же сложный запрос нужен во многих местах, его можно оформить как **представление** (`VIEW`) в базе — Prisma умеет описывать представления (страница «Views» в документации; возможность `views` включается в `previewFeatures`).

### deep Если не получилось
- **`column "branch_id" does not exist`** — алиас внутри CTE: проверь, что колонка выбрана в `SELECT` предыдущего блока.
- **Запрос работает долго** — это нормально на 583 тысячах платежей без подходящих индексов; нас интересует корректность, скорость — в сессии 17.

### quiz
- Чем оконная функция отличается от `GROUP BY` по результату?
- Что делает `CROSS JOIN LATERAL` и когда он нужен?
- Почему итоговые отчёты лучше считать в SQL, а не в JS?

### links
- https://www.postgresql.org/docs/18/tutorial-window.html | оконные функции | PostgreSQL 18: Window Functions
- https://www.postgresql.org/docs/18/queries-with.html | WITH | PostgreSQL 18: WITH Queries

## 9.2 $queryRaw и tagged template | short: $queryRaw | est: ~40 мин
### intro
**Слова шага:** *`$queryRaw`*, *`$executeRaw`*, *tagged template (шаблонный литерал)*, *параметр*, *обобщённый тип результата*.

:::tip Если совсем просто
`$queryRaw` — «послать базе готовый SQL и получить таблицу обратно». Главное правило: значения вставляй **только через `${...}`** внутри шаблонной строки — тогда Prisma передаст их базе **отдельно** от текста запроса и ничего не склеится.
:::

```ts
// src/lessons/09-raw.ts
import { Prisma } from '../generated/prisma/client.js'
import { prisma } from '../db.js'

type Row = { branch_id: number; cust_id: number; total: Prisma.Decimal; rnk: bigint }

const minRank = 3
const rows = await prisma.$queryRaw<Row[]>`
  WITH revenue AS (
    SELECT b.branch_id, b.cust_id, sum(p.amount::numeric) AS total
    FROM "tbl_Payments" p JOIN "tbl_Bookings" b ON b.id = p.booking_id
    WHERE p.kind IN (1, 2) AND b.cust_id IS NOT NULL AND b.branch_id = ${1}
    GROUP BY b.branch_id, b.cust_id
  ), ranked AS (
    SELECT *, rank() OVER (PARTITION BY branch_id ORDER BY total DESC) AS rnk FROM revenue
  )
  SELECT branch_id, cust_id, total, rnk FROM ranked WHERE rnk <= ${minRank} ORDER BY rnk`

for (const r of rows) console.log(r.branch_id, r.cust_id, r.total.toFixed(2), Number(r.rnk))

// запись: $executeRaw возвращает число затронутых строк
const n = await prisma.$executeRaw`UPDATE "tbl_Items" SET active = 1 WHERE id = ${1} AND active <> 1`
console.log('обновлено строк:', n)
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
SQL_LOG=1 npx tsx src/lessons/09-raw.ts 2>&1 | tail -14
npm run typecheck
```

### result
```out auto
```

В логе значения `${1}` и `${minRank}` идут **параметрами** (`$1`, `$2`) — в тексте запроса их нет. Тип результата ты **объявляешь сама** (`<Row[]>`): Prisma не знает, что вернёт произвольный SQL, и доверяет тебе. Значит, тип может **врать** (ошибёшься в имени колонки — TS не заметит); исправлять это — TypedSQL (шаг 9.5).

Запомни: `$queryRaw` — для `SELECT`; `$executeRaw` — для `INSERT/UPDATE/DELETE` и DDL (возвращает число затронутых строк); `rank()` возвращает `bigint`, поэтому в типе `rnk: bigint`, `sum(numeric)` — `Prisma.Decimal` (шаг 7.4).

### why
Сырой SQL в Prisma — не «обходной путь», а штатный инструмент. Но он берёт ответственность на тебя: типы результата, имена колонок, нормализацию. Поэтому его место — небольшие, хорошо описанные функции слоя данных (`getTopCustomers`, `monthlyRevenue`), а не россыпь по коду.

### deep Команды по частям
`prisma.$queryRaw<Row[]>\`…\`` — вызов **шаблонным литералом** без скобок (это не обычный вызов `$queryRaw(\`…\`)` со строкой!). Именно такая форма даёт защиту: `${…}` превращаются в параметры. Если передать готовую строку в скобках, будет ошибка или (для `Unsafe`-версии) дыра (шаг 9.3).

### deep Если не получилось
- **`Invalid prisma.$queryRaw() invocation: … column "rnk" … not found`** — опечатка в алиасе: тип `Row` не проверяется компилятором, ошибка видна только при запуске.
- **`${1}` не работает в `LIMIT`/идентификаторах** — параметрами можно передавать **значения**, но не **имена** таблиц и колонок (они подставляются отдельным способом — `Prisma.raw`, шаг 9.4, с белым списком).

### quiz
- Чем `$queryRaw` отличается от `$executeRaw`?
- Почему важна именно форма вызова с обратными кавычками (tagged template)?
- Кто отвечает за правильность типа результата в `$queryRaw<Row[]>`?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/using-raw-sql/raw-queries | сырые запросы | Prisma 7: Raw queries

## 9.3 Инъекция: рассматриваем атаку на своём стенде | short: SQL-инъекция | est: ~45 мин
### intro
**Слова шага:** *SQL-инъекция*, *`$queryRawUnsafe`*, *склейка строки*, *параметризованный запрос*, *экранирование*.

:::tip Если совсем просто
Представь, что отвечаешь на письма по бланку: «Пришлите данные клиента по имени ___». Если в пропуск подставят не имя, а «Иванов; и заодно отдайте список всех паролей», а ты **слепо** выполнишь написанное, получится беда. Инъекция — именно это: данные, которые база приняла за часть команды. Параметры — это перегородка: «что вписано в пропуск — только данные, никогда не команда».
:::

Рассмотрим атаку **на своём стенде**. Функция поиска клиента по имени с двумя реализациями:

```ts
// src/lessons/09-injection.ts
import { prisma } from '../db.js'

// ПЛОХО: имя вклеено в текст запроса
async function unsafeSearch(name: string) {
  return prisma.$queryRawUnsafe<{ id: number; CustName: string; phone: string | null }[]>(
    `SELECT id, "CustName", phone FROM "tbl_Customers" WHERE "CustName" = '${name}' LIMIT 5`)
}

// ХОРОШО: имя — параметр
async function safeSearch(name: string) {
  return prisma.$queryRaw<{ id: number; CustName: string; phone: string | null }[]>`
    SELECT id, "CustName", phone FROM "tbl_Customers" WHERE "CustName" = ${name} LIMIT 5`
}

const attack = "x' OR '1'='1"       // «имя», которое меняет смысл запроса
console.log('unsafe :', (await unsafeSearch(attack)).length, 'строк  ← вернулись клиенты, хотя имя „x“ не существует')
console.log('safe   :', (await safeSearch(attack)).length, 'строк')

// ещё хуже: запрос, который прячет второй
const attack2 = "x'; SELECT pg_sleep(2); --"
console.time('unsafe sleep')
await unsafeSearch(attack2).catch((e) => console.log('ошибка:', (e as Error).message.split('\n')[0]))
console.timeEnd('unsafe sleep')
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
SQL_LOG=1 npx tsx src/lessons/09-injection.ts 2>&1 | grep -v '^  params' | tail -12
```

### result
```out auto
```

Ожидаем: в «плохой» версии `OR '1'='1'` превращается в часть условия — вернулись **строки** (а в реальной системе — все клиенты, включая чужих); в «хорошей» — 0 строк: строка `x' OR '1'='1` ищется как **имя**. Второй пример показывает, что инъекция может **выполнять произвольные команды**: вторая команда (`pg_sleep(2)`) **отработала** — `unsafe sleep` занял ≈2 секунды, а потом `$queryRawUnsafe` споткнулся об устройство ответа (`Cannot read properties of undefined (reading 'map')`). Ошибка в консоли не значит, что атака не удалась: команда уже выполнена. На месте `pg_sleep` мог стоять `DROP TABLE` или `UPDATE`.

Взгляни в лог: у безопасной версии запрос с `$1`, у небезопасной — **готовый текст со вклеенной строкой**. Поэтому правило, которое не нарушают: **значения — только параметры.** Если нужно подставить **имя колонки или направление сортировки**, делается это иначе — через белый список (шаг 9.4).

### why
SQL-инъекция живёт в списках самых частых уязвимостей десятилетиями, и ORM от неё не спасает, если выйти в `Unsafe`-методы или склеить строку. Это как раз тот случай, где **знать, как ломают**, важнее, чем знать, как защищаться: тогда в ревью виден запах — `${…}` внутри обычных кавычек.

### deep Как ещё можно
Защита от инъекций не заменяет **прав доступа**: даже при ошибке в коде роль приложения (сессия 16) не должна иметь права удалять таблицы или читать чужое. Принцип «глубокой защиты»: корректный код + минимальные права + RLS.

### deep Если не получилось
- **Обе версии возвращают 0 строк** — проверь, что `attack` содержит апостроф `'`, и что в базе есть клиенты (`SELECT count(*) FROM "tbl_Customers"`).
- **Вторая атака не «спит» две секунды** — драйвер или версия вернули ошибку раньше выполнения; воспроизведи первую атаку (она надёжнее) и посмотри в лог.

### quiz
- Почему параметр защищает от инъекции, а склейка строки — нет?
- В каком случае безопасный `$queryRaw` всё равно не поможет с подстановкой?
- Как «права роли» и корректный код дополняют друг друга?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/using-raw-sql/raw-queries#sql-injection | инъекции в raw-запросах | Prisma 7: Raw queries — SQL injection
- https://owasp.org/www-community/attacks/SQL_Injection | SQL Injection | OWASP: SQL Injection

## 9.4 Prisma.sql, Prisma.join, Prisma.raw — динамические запросы без дыр | short: Динамический SQL | est: ~45 мин
### intro
**Слова шага:** *`Prisma.sql`*, *`Prisma.join`*, *`Prisma.empty`*, *`Prisma.raw`*, *белый список*, *динамические условия*.

:::tip Если совсем просто
Бывает, что запрос собирается из частей: «если выбран филиал — добавь условие, если выбрана дата — добавь ещё». Склеивать строки нельзя. Prisma даёт «кирпичики SQL» (`Prisma.sql`), которые можно складывать друг с другом, и параметры при этом остаются параметрами.
:::

```ts
// src/lessons/09-dynamic.ts
import { Prisma } from '../generated/prisma/client.js'
import { prisma } from '../db.js'

type Filter = { branchId?: number; statuses?: number[]; sortBy?: 'id' | 'price' }

// направление и имя колонки нельзя передать параметром — только из белого списка:
const SORT_COLUMNS = { id: Prisma.sql`b.id`, price: Prisma.sql`b.price` } as const

export async function searchBookings({ branchId, statuses, sortBy = 'id' }: Filter) {
  const conditions: Prisma.Sql[] = []
  if (branchId !== undefined) conditions.push(Prisma.sql`b.branch_id = ${branchId}`)
  if (statuses?.length) conditions.push(Prisma.sql`b.status IN (${Prisma.join(statuses)})`)

  const where = conditions.length ? Prisma.sql`WHERE ${Prisma.join(conditions, ' AND ')}` : Prisma.empty

  return prisma.$queryRaw<{ id: number; status: number | null }[]>`
    SELECT b.id, b.status FROM "tbl_Bookings" b
    ${where}
    ORDER BY ${SORT_COLUMNS[sortBy]} DESC
    LIMIT 5`
}

console.log(await searchBookings({}))
console.log(await searchBookings({ branchId: 3, statuses: [6, 7] }))
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
SQL_LOG=1 npx tsx src/lessons/09-dynamic.ts 2>&1 | grep -E 'SELECT|params|^\[' | head -8
npm run typecheck
```

### result
```out auto
```

Кирпичики: **`Prisma.sql\`…\``** — фрагмент SQL с параметрами; **`Prisma.join([a, b, c])`** — список значений через запятую (`IN (1, 2, 3)` — каждое значение параметром) или, со вторым аргументом, список фрагментов (`a AND b`); **`Prisma.empty`** — пустой фрагмент («ничего не добавлять»); **`Prisma.raw('текст')`** — вставка **непроверенного текста** (опасно, нужна для идентификаторов; **только** из белого списка). Именно поэтому сортировка идёт через словарь `SORT_COLUMNS`: пользователь выбирает ключ, а не вводит имя колонки.

### why
Фильтры по запросу пользователя — самое частое место, где появляется склейка строк. Эти «кирпичики» позволяют собрать любой запрос динамически и при этом ни разу не вклеить внешнее значение в текст. Привычка №1: «имя колонки — из словаря, значение — параметром».

### deep Как ещё можно
Если фильтры сложные и их много, часто используют конструктор запросов (Kysely) поверх той же базы — он типизирует динамику лучше. Но для нашего размера `Prisma.sql` вполне достаточно.

### deep Если не получилось
- **`Prisma.join` с пустым массивом** — `IN ()` синтаксически неверен: поэтому в коде есть проверка `statuses?.length`.
- **`ORDER BY` не меняется** — `Prisma.sql` фрагмент нужно вставлять как `${...}` внутри шаблонного литерала, а не склеивать плюсом.

### quiz
- Чем `Prisma.join` отличается от `array.join(',')` по безопасности?
- Почему направление и имя колонки сортировки нельзя передать параметром?
- Когда уместен `Prisma.raw` и как его использовать безопасно?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/using-raw-sql/raw-queries#building-raw-queries-separate-from-queries | Prisma.sql | Prisma 7: Building raw queries
- https://www.prisma.io/docs/orm/v7/reference/prisma-client-reference | справочник клиента | Prisma 7: Client API reference

## 9.5 TypedSQL: файл .sql становится функцией с типами | short: TypedSQL | est: ~50 мин
### intro
**Слова шага:** *TypedSQL*, *`previewFeatures = ["typedSql"]`*, *`prisma generate --sql`*, *`$queryRawTyped`*, *типы параметров*, *`-- @param`*.

:::tip Если совсем просто
В шаге 9.2 тип результата ты **заявляла сама**, и он мог соврать. TypedSQL убирает «веру на слово»: ты пишешь SQL в отдельном файле, Prisma **сама спрашивает у базы**, какие колонки и каких типов вернёт запрос, и делает из файла типизированную функцию. Ошибся в названии колонки — получишь ошибку при `generate`, а не в проде.
:::

В Prisma 7.10 TypedSQL — **предпросмотровая** возможность (проверено: без `typedSql` в `previewFeatures` команда `prisma generate --sql` отвечает «`typedSql` preview feature needs to be enabled»). Включаем:

```prisma schema
generator client {
  provider        = "prisma-client"
  output          = "../src/generated/prisma"
  previewFeatures = ["relationJoins", "typedSql"]
}
```

Создай папку `prisma/sql` и файл с запросом (имя — валидный JS-идентификатор, оно станет именем функции):

```sql
-- prisma/sql/topCustomers.sql
-- @param {Int} $1:branchId
-- @param {Int} $2:limit
SELECT b.cust_id AS "customerId",
       count(DISTINCT b.id)              AS "bookings",
       round(sum(p.amount::numeric), 2)  AS "revenue"
FROM "tbl_Bookings" b
JOIN "tbl_Payments" p ON p.booking_id = b.id AND p.kind IN (1, 2)
WHERE b.branch_id = $1 AND b.cust_id IS NOT NULL
GROUP BY b.cust_id
ORDER BY revenue DESC
LIMIT $2
```

```ts
// src/lessons/09-typedsql.ts
import { prisma } from '../db.js'
import { topCustomers } from '../generated/prisma/sql.js'

const rows = await prisma.$queryRawTyped(topCustomers(1, 5))
for (const r of rows) console.log(r.customerId, r.bookings, r.revenue.toFixed(2))   // типы выведены из базы!
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx prisma generate --sql
ls src/generated/prisma | grep sql
npx tsx src/lessons/09-typedsql.ts
npm run typecheck
```

### result
```out auto
```

`prisma generate --sql` подключается к базе, **описывает** запрос (через `PREPARE`) и генерирует функцию `topCustomers(branchId, limit)` с типами `{ customerId: number | null; bookings: bigint | null; revenue: Decimal | null }` (`null` везде, потому что агрегат над пустой группой может вернуть `NULL`). Параметры тоже типизированы: передашь строку вместо числа — ошибка компиляции. Если запрос неверен (нет таблицы, опечатка в колонке), **`generate --sql` упадёт** — ошибка обнаружена на этапе сборки.

Условия: миграции должны быть **применены** до генерации (запрос проверяется на настоящей базе); имя файла `.sql` — идентификатор; расположение папки можно менять через `typedSql: { path }` в `prisma.config.ts`. Импорт — из файла `sql.ts` рядом с клиентом (`../generated/prisma/sql.js`; рядом лежит папка `sql/` с файлом на каждый запрос). Путь проверен на Prisma 7.10: с генератором `prisma-client` индекса `sql/index` нет, а `…/sql/index.js` из старых статей даёт `Cannot find module`.

**Ловушка, на которой спотыкаются все.** Обычная `npx prisma generate` (без `--sql`) пересоздаёт папку клиента и **стирает `sql.ts`**: после неё любой импорт `../generated/prisma/sql.js` падает с `Cannot find module`, а `tsc` — с `TS2307`. С TypedSQL клиент надо генерировать **всегда** с флагом `--sql`. Чтобы не помнить об этом, заведём скрипт `npm run generate` (с этого шага — только он; `generate --sql` требует папку `prisma/sql`, поэтому до TypedSQL он не годился):

```bash run
cd ~/prisma-lab/rentkit
npm pkg set scripts.generate="prisma generate --sql"
npm run generate
```

### result
```out auto
```

### why
TypedSQL — лучшее из двух миров: полный SQL и настоящие типы. Для отчётов, которые меняются редко и должны не врать, это основной способ. Минус — предпросмотровый статус (формат может поменяться) и необходимость базы при генерации — важно для CI (сессия 18).

### deep Если не получилось
- **`Unknown generator preview feature typedSql`** — старая версия Prisma; проверь `npx prisma --version` (7.x) и закрепление версии.
- **`generate --sql` падает на подключении** — нет доступа к базе (`.env`, контейнер не запущен) — для TypedSQL подключение обязательно.
- **В `revenue` не `Decimal`** — тип выводится из базы: `round(numeric)` → `Decimal`; если приводишь к `float8`, придёт `number`.

### quiz
- Чем TypedSQL лучше `$queryRaw<Row[]>` по типам результата?
- Какое требование к базе есть при `prisma generate --sql`?
- Что произойдёт, если в `.sql` файле опечатка в имени колонки?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/using-raw-sql/typedsql | TypedSQL | Prisma 7: TypedSQL
- https://www.prisma.io/docs/orm/v7/reference/preview-features/client-preview-features | preview-возможности | Prisma 7: Client preview features

## 9.6 Смешиваем raw и клиента: BigInt, Decimal, null | short: Raw и клиент вместе | est: ~35 мин
### intro
**Слова шага:** *raw + клиент в одной транзакции*, *приведение типов результата*, *DTO*, *`BigInt` из `count`*, *функция слоя данных*.

:::tip Если совсем просто
Хороший слой данных не показывает, кто вернул данные — клиент или сырой SQL. Снаружи это функция `getTopCustomers(branchId)` с понятным типом. Внутри — как удобнее. Задача шага — «обернуть» сырой результат так, чтобы `bigint` и `Decimal` не просочились дальше.
:::

```ts
// src/data/reports.ts
import { prisma } from '../db.js'
import { topCustomers } from '../generated/prisma/sql.js'

// DTO — понятный наружу тип: числа и строки, ничего «специального»
export type TopCustomer = { customerId: number; name: string | null; bookings: number; revenue: string }

export async function getTopCustomers(branchId: number, limit = 5): Promise<TopCustomer[]> {
  const rows = await prisma.$queryRawTyped(topCustomers(branchId, limit))
  const ids = rows.map((r) => r.customerId).filter((x): x is number => x !== null)
  const names = new Map((await prisma.customer.findMany({ where: { id: { in: ids } }, select: { id: true, name: true } })).map((c) => [c.id, c.name]))

  return rows
    .filter((r) => r.customerId !== null)
    .map((r) => ({
      customerId: r.customerId!,
      name: names.get(r.customerId!) ?? null,
      bookings: Number(r.bookings),                    // bigint → number (счётчики безопасно умещаются)
      revenue: r.revenue?.toFixed(2) ?? '0.00',        // Decimal → строка: деньги не превращаем в number
    }))
}

console.log(await getTopCustomers(1))
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/data/reports.ts
npm run typecheck
```

### result
```out auto
```

Правила «чистой границы»: **счётчики** (`bigint`) — в `number` (они мал́ы), **деньги** (`Decimal`) — в строку (или оставить `Decimal` внутри, но наружу — строка, чтобы не потерять точность в JSON), **`null`** — явно обработать, **`BigInt` в JSON** — никогда. Функция возвращает DTO, а не «сырую» строку базы. Смешивание raw и клиента (здесь — имена клиентов через `findMany`) — обычная практика: запрос-итог плюс «обогащение» объектами.

### why
Тип «чистого» слоя данных — его главное качество: код, который его вызывает, не должен знать, что внутри был `bigint`. Если `BigInt` или `Decimal` утекают наружу — через месяц кто-то сделает `JSON.stringify` и получит 500 в проде.

### deep Если не получилось
- **`revenue?.toFixed` — ошибка типа** — `revenue` приходит как `Decimal | null`; проверь тип в подсказке.
- **Имена не находятся** — `findMany` по `in: ids` вернёт только существующих клиентов (сироты → `name: null`).

### quiz
- Почему DTO лучше, чем возвращать результат raw-запроса как есть?
- Как поступают с `bigint` из `count` и с `Decimal` при отдаче наружу?
- Что значит «обогащение» результата raw-запроса объектами?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/special-fields-and-types | специальные типы | Prisma 7: Special fields and types

## 9.7 🔨 Отчёт «топ-10 клиентов по выручке» ломается на BigInt и Decimal | short: 🔨 BigInt в JSON | est: ~55 мин
### intro
**Слова шага:** *жалоба заказчика*, *`TypeError: Do not know how to serialize a BigInt`*, *`Decimal` в JSON*, *округление*, *сверка сумм*.

:::tip Если совсем просто
Отчёт работает у разработчика — а в API отдаёт ошибку 500. Причина: пока цифры «просто печатались в консоль», типы не мешали; как только их отправили как JSON, вылезло всё, о чём мы говорили.
:::

*Заказчик:* «Отчёт „Топ-10 клиентов по выручке за период“ в личном кабинете выдаёт ошибку. В консоли у разработчика всё работало. И ещё: выручка в отчёте не совпадает с банком на пару копеек».

Нерабочая версия отчёта (воспроизводит жалобу):

```ts
// src/lessons/09-broken-report.ts
import { Prisma } from '../generated/prisma/client.js'
import { prisma } from '../db.js'

export async function revenueReport(since: string) {
  return prisma.$queryRaw<{ customer_id: number; bookings: bigint; revenue: Prisma.Decimal }[]>`
    SELECT b.cust_id AS customer_id, count(DISTINCT b.id) AS bookings, sum(p.amount) AS revenue
    FROM "tbl_Payments" p JOIN "tbl_Bookings" b ON b.id = p.booking_id
    WHERE p.kind IN (1, 2) AND b.cust_id IS NOT NULL AND p.paid >= ${since}
    GROUP BY b.cust_id ORDER BY revenue DESC LIMIT 10`
}

const rows = await revenueReport('2025-01-01')
console.log(JSON.stringify(rows))          // ← отправка в API
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/09-broken-report.ts 2>&1 | head -6
```

### result
```out auto
```

**Твоя задача:** (1) объяснить, откуда ошибка и **две** причины, почему выручка «на пару копеек» не сходится с банком (подсказка: `sum(p.amount)` берётся из `float8`, а `p.paid` — **текст** с двумя форматами даты; обрати внимание, что фильтр `p.paid >= '2025-01-01'` — это сравнение **строк**!); (2) переписать отчёт так, чтобы он: возвращал DTO без `bigint`/`Decimal` наружу, суммировал деньги точно (`::numeric(12,2)`), правильно учитывал платежи в обоих форматах даты, и проходил проверку сверки с `psql`: `SELECT sum(amount::numeric(12,2)) …` за тот же период; (3) покрыть DTO типом.

**Приёмка сессии:** три отчёта на окнах/CTE (топ клиентов по филиалам, нарастающая выручка по месяцам, последний платёж брони через LATERAL), **один из них через TypedSQL**; безопасный динамический поиск броней через `Prisma.sql`; пример инъекции воспроизведён и закрыт; «топ-10» отдаёт валидный JSON, суммы сверены с `psql` до копейки (запиши в `NOTES.md` числа «до» и «после»).

### why
Это прототип нетривиальной боли многих проектов: сырой запрос «вроде работает», пока не дойдёт до сериализации, а деньги в `float8` расходятся с банком. Умение **доказать** сверкой, что отчёт верен, отличает отчёт для себя от отчёта для бухгалтерии.

### deep Если не получилось
- **Подсказка 1 (ошибка):** `JSON.stringify` не знает `bigint`; `Prisma.Decimal` умеет `toJSON` (вернёт строку), поэтому ломается именно `bookings`.
- **Подсказка 2 (даты):** нормализуй `paid` (`CASE`: формат `DD.MM.YYYY HH24:MI` и `YYYY-MM-DD HH24:MI:SS`), как в шаге 3.1, и сравнивай даты, а не строки.
- **Подсказка 3 (копейки):** приводи к `numeric(12,2)` **до** суммирования, а не после; сравни результат с `float8`-суммой — расхождение появится на хвостовых цифрах.

### quiz
- Почему `JSON.stringify` падает на `bigint`, а `Decimal` — нет?
- Чем плохо сравнение дат как строк при смешанных форматах?
- Как доказать, что отчёт верен: какую проверку сделать?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/special-fields-and-types | специальные типы | Prisma 7: Special fields and types
