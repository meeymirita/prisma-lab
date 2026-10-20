# Сессия 5 · Клиент и чтение
dur: ~4 ч

## 5.1 Клиент с адаптером: соединение, пул, закрытие | short: Клиент и пул | est: ~35 мин
### intro
**Слова шага:** *`PrismaClient`*, *driver adapter*, *пул соединений*, *`$connect`*, *`$disconnect`*, *`pg_stat_activity`*.

:::tip Если совсем просто
Клиент — это администратор, а соединения с базой — телефонные линии, которые у него есть. Он берёт свободную линию, звонит, получает ответ и возвращает линию. Линий немного (по умолчанию 10), и если звонков больше — остальные ждут. Увидим это своими глазами: посмотрим из базы, сколько линий занято.
:::

Клиент из `src/db.ts` соединяется с базой **лениво** — при первом запросе (или явно через `$connect()`). Посмотрим, как пул выглядит со стороны базы:

```ts
// src/lessons/05-pool.ts
import { prisma } from '../db.js'

await prisma.$connect()
await Promise.all(Array.from({ length: 5 }, () => prisma.booking.count()))   // 5 запросов одновременно
await new Promise((r) => setTimeout(r, 300))

const rows = await prisma.$queryRaw<{ state: string; n: bigint }[]>`
  SELECT coalesce(state, 'без состояния') AS state, count(*) AS n
  FROM pg_stat_activity
  WHERE datname = 'rental' AND pid <> pg_backend_pid()
  GROUP BY 1`
console.log(rows)
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
mkdir -p src/lessons
npx tsx src/lessons/05-pool.ts
```

### result
```out auto
```

В выводе — несколько соединений в состоянии `idle` (простаивают после запросов) — это и есть пул. Размер пула по умолчанию у адаптера `pg` — **10** (`max`); это значение драйвера, а не Prisma. Менять его (и таймауты) нужно в конструкторе адаптера (`new PrismaPg({ connectionString, max: 20 })`) — разберём в сессии 17.

### why
Пул — это одно из главных мест, где разработчик с ORM не может не знать, что под капотом. Если приложение запускают в пяти экземплярах по 10 соединений, а у базы `max_connections = 100`, то пять — безобидно, а двадцать — уже нет. С этим мы будем работать в сессии 17; здесь важно увидеть, что **соединения реальны** и их видно со стороны базы.

### deep Команды по частям
`prisma.$connect()` — явно открыть соединение сразу (иначе оно открывается при первом запросе). `prisma.$disconnect()` — закрыть пул; без него скрипт не завершится. В долгоживущем сервере `$disconnect()` вызывают при остановке процесса (graceful shutdown). `$queryRaw` — сырой запрос (подробно в сессии 9); `pg_stat_activity` — системное представление: все подключения к базе.

### deep Если не получилось
- **Пусто или одно соединение** — запросы выполнились слишком быстро и соединение переиспользовалось; увеличь нагрузку (`length: 20`) или добавь в запрос `pg_sleep(0.2)`.
- **`typeof n` — `bigint`** — `count(*)` приходит как `bigint`; для вывода преобразуй `Number(n)`.

### quiz
- Что такое пул соединений и каков его размер по умолчанию в адаптере `pg`?
- Когда `PrismaClient` открывает соединение, если не вызвать `$connect()`?
- Зачем скрипту `$disconnect()`?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/setup-and-configuration/databases-connections/connection-pool | пул соединений | Prisma 7: Connection pool
- https://www.prisma.io/docs/orm/v7/prisma-client/setup-and-configuration/databases-connections/connection-management | управление соединениями | Prisma 7: Connection management

## 5.2 findMany, findFirst, findUnique и where | short: Чтение и where | est: ~50 мин
### intro
**Слова шага:** *`findMany`*, *`findFirst`*, *`findUnique`*, *`findUniqueOrThrow`*, *`where`*, *операторы `contains`, `in`, `gte`*, *`AND`/`OR`/`NOT`*, *`orderBy`*, *`take`*.

:::tip Если совсем просто
`findMany` — «дай все, что подходят», `findFirst` — «дай первую подходящую», `findUnique` — «дай ту единственную по уникальному ключу». У `where` свои слова-условия: «содержит», «в списке», «больше или равно». Результат всегда типизирован: `findUnique` вернёт «запись или `null`».
:::

```ts
// src/lessons/05-read.ts
import { prisma } from '../db.js'

// 1. по уникальному ключу: запись или null
const one = await prisma.customer.findUnique({ where: { id: 1 } })
console.log(one?.name ?? 'нет такого')

// 2. «или выбросить»: тип без null, ошибка, если нет
const mustExist = await prisma.branch.findUniqueOrThrow({ where: { id: 1 } })
console.log(mustExist.city)

// 3. фильтры: содержит (без учёта регистра), в списке, сравнения
const list = await prisma.customer.findMany({
  where: {
    name: { contains: 'иван', mode: 'insensitive' },
    branchId: { in: [1, 2, 3] },
    NOT: { email: null },
  },
  orderBy: { id: 'asc' },
  take: 3,
})
console.log(list.map((c) => `${c.id} ${c.name} ${c.phone}`))

// 4. первая бронь клиента с большим залогом
const first = await prisma.booking.findFirst({
  where: { customerId: 42, deposit: { gte: 1000 } },
  orderBy: { id: 'desc' },
})
console.log(first?.id, first?.status)

// 5. OR и вложенная логика
const either = await prisma.booking.count({
  where: { OR: [{ status: 6 }, { status: 7 }], branchId: 5 },
})
console.log('проблемные в филиале 5:', either)

await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/05-read.ts
npm run typecheck
```

### result
```out auto
```

Ключевые правила:

- **`findUnique`** принимает **только уникальные поля** (`id`, `@unique`, составной ключ) — иначе ошибка типов. `findFirst` — для всего остального.
- **`findUniqueOrThrow` / `findFirstOrThrow`** — сразу бросают исключение (`P2025`, «запись не найдена»), а тип результата **не содержит `null`** — удобнее, чем проверка в каждой функции.
- **Условия:** `equals` (по умолчанию), `not`, `in`, `notIn`, `lt/lte/gt/gte`, `contains/startsWith/endsWith` (для текста; `mode: 'insensitive'` — без учёта регистра), `AND/OR/NOT`.
- **`orderBy`** — массив, если сортировка по нескольким полям: `orderBy: [{ branchId: 'asc' }, { id: 'desc' }]`; **`take`** — сколько вернуть; без него `findMany` вернёт **всё** (опасно на 300 тысячах строк!).

Попробуй «грязную» фильтрацию по тексту — и увидишь последствия формата дат в базе:

```ts
// год «2025» по строке: сработает только для формата гггг-мм-дд
const wrong = await prisma.booking.count({ where: { startText: { startsWith: '2025' } } })
```

### why
`where` на Prisma — это тот же SQL `WHERE`, но с проверкой типов. Главная ловушка, которую показывает последний пример, — **типы не спасают от грязных данных**: Prisma честно выполнит `LIKE '2025%'` по строке, но дата `15.01.2025` и `1736899200` под этот фильтр не попадут. Поэтому чистка из сессии 10 — не косметика.

### deep Под капотом
Prisma строит SQL по твоему объекту: `where: { name: { contains: 'иван', mode: 'insensitive' } }` превращается в `WHERE "CustName" ILIKE $1` с параметром `%иван%`. Условие `NOT: { email: null }` — в `WHERE NOT ("email" IS NULL)`. Увидим это глазами в шаге 5.5.

### deep Если не получилось
- **`Type '{ name: string }' is not assignable to 'CustomerWhereUniqueInput'`** — `findUnique` принимает только уникальные поля; используй `findFirst` или добавь `@unique` в схему.
- **`take` не задан, скрипт «завис»** — ты запросила все 300 тысяч броней; добавь `take` или `where`.

### quiz
- Чем `findUnique` отличается от `findFirst` и какие поля принимает?
- Зачем нужен `findUniqueOrThrow` и что он вернёт по типу?
- Почему фильтр `startsWith: '2025'` по текстовой дате даёт неверный результат?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/queries/crud | CRUD | Prisma 7: CRUD
- https://www.prisma.io/docs/orm/v7/prisma-client/queries/filtering-and-sorting | фильтры и сортировка | Prisma 7: Filtering and sorting

## 5.3 select и omit: вернуть только нужное | short: select и omit | est: ~30 мин
### intro
**Слова шага:** *`select`*, *`omit`*, *форма результата*, *`SELECT *` против списка колонок*, *вложенный `select`*.

:::tip Если совсем просто
По умолчанию Prisma приносит **всю строку целиком** — как официант, который уносит со стола всё, когда просили только вилку. `select` — «принеси только это», `omit` — «принеси всё, кроме этого». Меньше полей — меньше трафика и быстрее ответ.
:::

```ts
// src/lessons/05-select.ts
import { prisma } from '../db.js'

// только нужные поля: тип результата сужается автоматически
const brief = await prisma.booking.findMany({
  where: { customerId: 42 },
  select: { id: true, status: true, startText: true },
  take: 3,
})
console.log(brief)          // тип: { id: number; status: number | null; startText: string | null }[]

// всё, кроме одного поля
const noMeta = await prisma.item.findFirst({ omit: { meta: true } })
console.log(noMeta?.title)

// select нельзя смешивать с include на одном уровне
// await prisma.booking.findMany({ select: {...}, include: {...} })   // ← ошибка типов
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/05-select.ts
npm run typecheck
```

### result
```out auto
```

`select` меняет и **тип результата** (в нём только выбранные поля), и **SQL** (в `SELECT` — только эти колонки). Правило: если поле не нужно вызывающей стороне — не запрашивай его; особенно текстовые поля большого размера (`meta`, `note`) и поля, которые нельзя светить наружу (пароли, внутренние отметки).

### why
Привычка «брать всё» — частая причина медленных запросов: каждая лишняя колонка едет по сети и разбирается в JS. А в ответах API лишнее поле может оказаться утечкой. `select` и `omit` — простой способ быть явной в том, что отдаёшь.

### deep Как ещё можно
`omit` можно задать **глобально** при создании клиента (`new PrismaClient({ omit: { customer: { email: true } } })`) — тогда поле не вернётся нигде, пока явно не попросишь `omit: { email: false }`. Удобно для чувствительных полей (**сверьтесь** с синтаксисом в вашей версии).

### quiz
- В чём разница между `select` и `omit`?
- Как `select` влияет на тип результата и на SQL?
- Почему нельзя использовать `select` и `include` на одном уровне запроса?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/queries/select-fields | select | Prisma 7: Select fields
- https://www.prisma.io/docs/orm/v7/prisma-client/queries/excluding-fields | omit | Prisma 7: Excluding fields

## 5.4 count, aggregate, groupBy | short: Агрегаты | est: ~40 мин
### intro
**Слова шага:** *`count`*, *`aggregate`*, *`_sum`/`_avg`/`_min`/`_max`*, *`groupBy`*, *`having`*, *`distinct`*.

:::tip Если совсем просто
Агрегат — это «итог по куче строк»: сколько всего, какая сумма, какое среднее. `groupBy` — «сделай итог отдельно для каждой группы»: сколько броней в каждом статусе, сколько залога в каждой категории.
:::

```ts
// src/lessons/05-aggregate.ts
import { prisma } from '../db.js'

// 1. сколько всего и с условием
console.log(await prisma.booking.count(), await prisma.booking.count({ where: { status: 3 } }))

// 2. агрегаты по числовому полю
const dep = await prisma.item.aggregate({
  _avg: { deposit: true },
  _min: { deposit: true },
  _max: { deposit: true },
  where: { active: 1 },
})
console.log(dep)

// 3. группировка: брони по статусам
const byStatus = await prisma.booking.groupBy({
  by: ['status'],
  _count: { _all: true },
  orderBy: { status: 'asc' },
})
console.log(byStatus)

// 4. группировка с фильтром по результату (HAVING): филиалы с более чем 25 тысячами броней
const big = await prisma.booking.groupBy({
  by: ['branchId'],
  _count: { _all: true },
  having: { branchId: { _count: { gt: 25000 } } },
})
console.log(big.length)

// 5. уникальные значения
const cats = await prisma.item.findMany({ distinct: ['category'], select: { category: true } })
console.log(cats.map((c) => c.category))
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/05-aggregate.ts
```

### result
```out auto
```

Что запомнить: у `groupBy` обязательно `by` и хотя бы один агрегат (`_count`, `_sum`, …); `orderBy` и `having` могут ссылаться только на поля из `by` или на агрегаты; `_count: { _all: true }` — это `COUNT(*)`. Для выражений, которые Prisma не умеет (`SUM(price)` с приведением текста к числу, оконные функции), придётся переходить на `$queryRaw` (сессия 9).

### why
Агрегаты — частый пример того, где ORM выручает без потери скорости: `groupBy` — это один SQL с `GROUP BY` на стороне базы, а не «загрузи всё и посчитай в JS». Если ты считаешь в JS, значит, что-то делаешь не так.

### deep Команды по частям
`aggregate` возвращает один объект с вложенными `_avg`, `_min`, `_max`; `groupBy` возвращает **массив** — по строке на группу. `distinct` в `findMany` — это не `SELECT DISTINCT`: Prisma может реализовать его **в памяти клиента** (**сверьтесь** — зависит от версии и запроса), поэтому для настоящей уникальности на больших данных надёжнее `groupBy`.

### deep Если не получилось
- **`Property '_sum' does not exist`** — в `aggregate` суммировать можно только числовые поля; текстовое `priceText` в сумму не пойдёт (приведи тип в raw-запросе или почисти данные, сессия 10).
- **Ошибка `orderBy` в `groupBy`** — можно сортировать только по полям из `by` или агрегатам.

### quiz
- Чем `aggregate` отличается от `groupBy` по форме результата?
- Что делает `having` в `groupBy`?
- Почему суммировать текстовое поле цены в `aggregate` нельзя?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/queries/aggregation-grouping-summarizing | агрегации | Prisma 7: Aggregation, grouping, and summarizing

## 5.5 Лог запросов: читаем SQL, который шлёт Prisma | short: Лог SQL | est: ~45 мин
### intro
**Слова шага:** *`log`*, *`emit: 'event'`*, *`$on('query')`*, *параметры `$1`*, *длительность*, *сравнение с ручным SQL*.

:::tip Если совсем просто
Переводчик между тобой и базой — Prisma. Чтобы убедиться, что он ничего не напутал, нужен «диктофон»: запись каждой фразы, которую он сказал базе, и сколько база думала над ответом. Включаем диктофон — и учимся слушать.
:::

В `src/db.ts` у нас уже включены события `query`. Добавим вывод — по переменной окружения `SQL_LOG` (чтобы не засорять вывод всегда):

```ts
// src/db.ts — дополнить после создания клиента
if (process.env.SQL_LOG) {
  prisma.$on('query', (e) => {
    console.log(`\x1b[36m[${e.duration}ms]\x1b[0m ${e.query}\n  params: ${e.params}`)
  })
}
```

```ts
// src/lessons/05-log.ts
import { prisma } from '../db.js'

await prisma.booking.findMany({
  where: { customerId: 42, status: { in: [3, 4] } },
  select: { id: true, startText: true },
  orderBy: { id: 'desc' },
  take: 2,
})

await prisma.customer.findMany({ where: { name: { contains: 'иван', mode: 'insensitive' } }, take: 1 })
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
SQL_LOG=1 npx tsx src/lessons/05-log.ts
```

### result
```out auto
```

Первый запрос превратится примерно в:

```sql
SELECT "public"."tbl_Bookings"."id", "public"."tbl_Bookings"."d_from"
FROM "public"."tbl_Bookings"
WHERE ("public"."tbl_Bookings"."cust_id" = $1 AND "public"."tbl_Bookings"."status" IN ($2,$3))
ORDER BY "public"."tbl_Bookings"."id" DESC LIMIT $4 OFFSET $5
```

(**Сверьтесь** с точным видом: он зависит от версии; важно, что видны **только выбранные колонки**, условия идут **параметрами** `$1…`, а имена — настоящие, из `@map`.) Второй — `WHERE "CustName" ILIKE $1`. Обрати внимание на `duration`: время на стороне базы и драйвера, в миллисекундах.

Теперь возьми любой запрос из лога и выполни его вручную в `psql` с настоящими значениями — и сравни с тем, что бы написала ты:

```bash run
psqlr() { docker exec -i rental-pg psql -U postgres -d rental "$@"; }
psqlr -c 'EXPLAIN (ANALYZE, BUFFERS) SELECT id, d_from FROM "tbl_Bookings" WHERE cust_id = 42 AND status IN (3,4) ORDER BY id DESC LIMIT 2'
```

### result
```out auto
```

Увидишь **`Seq Scan`** по 300 тысячам строк (индексов, кроме первичного, нет!) — а с `ORDER BY id DESC LIMIT 2` планировщик может пройти по индексу первичного ключа и отфильтровать на ходу. Подробно EXPLAIN — в сессии 8; сейчас важно, что **лог + `EXPLAIN` вместе** — главный инструмент разработчика с ORM.

### why
Правило, которое экономит часы: **если запрос медленный или результат странный, первым делом читай SQL.** Prisma не «магия»: каждый вызов превращается в вполне понятный запрос. А N+1 (шаг 6.3) вообще виден только в логе — в коде это один красивый цикл.

### deep Как ещё можно
`log: ['query']` (без `event`) печатает запросы прямо в консоль без обработчика. Событийный вариант удобнее: можно складывать запросы в файл, считать их число (`e.query`), мерить `e.duration`. Для трассировки на уровне операций есть OpenTelemetry (сессия 18). Подробности про `params`: в логе параметры показываются **значениями** — не пиши такой лог в прод-логи с паролями (сессия 16.5).

### deep Если не получилось
- **Ничего не печатается** — переменная `SQL_LOG` не передана, или в `new PrismaClient` нет `log: [{ emit: 'event', level: 'query' }]`.
- **`Property '$on' does not exist`** — клиент создан без `log` с `emit: 'event'`: тип `$on('query')` доступен только если событие объявлено при создании.

### quiz
- Как включить вывод SQL-запросов, которые Prisma отправляет в базу?
- Почему в логе видны `$1`, `$2`, а не значения прямо в тексте запроса?
- Зачем сравнивать SQL из лога с ручным `EXPLAIN`?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/observability-and-logging/logging | логирование | Prisma 7: Logging
- https://www.prisma.io/docs/orm/v7/prisma-client/debugging-and-troubleshooting/debugging | отладка | Prisma 7: Debugging

## 5.6 Тип результата: Prisma.BookingGetPayload и друзья | short: Типы результата | est: ~35 мин
### intro
**Слова шага:** *`Prisma.BookingGetPayload`*, *`Prisma.validator`*, *`Awaited<ReturnType<…>>`*, *вывод типа из запроса*, *типы входа*.

:::tip Если совсем просто
Результат запроса зависит от `select`/`include`, и тип у него свой каждый раз. Чтобы не писать его руками, просим Prisma назвать тип по тому же запросу. Как сфотографировать готовое блюдо и по фото записать рецепт, а не наоборот.
:::

```ts
// src/lessons/05-types.ts
import { Prisma } from '../generated/prisma/client.js'
import { prisma } from '../db.js'

// 1. Тип по описанию запроса: что вернётся при таком select
const briefSelect = { id: true, status: true, startText: true } satisfies Prisma.BookingSelect
type BookingBrief = Prisma.BookingGetPayload<{ select: typeof briefSelect }>

async function listBrief(customerId: number): Promise<BookingBrief[]> {
  return prisma.booking.findMany({ where: { customerId }, select: briefSelect })
}

// 2. Тип по готовой функции
type Listed = Awaited<ReturnType<typeof listBrief>>        // BookingBrief[]
type One = Listed[number]

// 3. Тип входа: условия поиска
function byStatus(status: number): Prisma.BookingWhereInput {
  return { status }
}

const items: Listed = await listBrief(42)
console.log(items[0] satisfies One | undefined, byStatus(3))
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/05-types.ts
npm run typecheck
```

### result
```out auto
```

Три инструмента: **`Prisma.<Model>GetPayload<{ select | include }>`** — тип результата по описанию запроса; **`Prisma.<Model>WhereInput`, `…CreateInput`, `…UpdateInput`** — типы входных данных для условий и записи; **`Awaited<ReturnType<typeof fn>>`** — тип результата уже написанной функции (из шага 2.6). Знак `satisfies` проверяет, что объект — корректный `BookingSelect`, но **не расширяет** его тип: `briefSelect` остаётся точным `{ id: true; status: true; … }`, и `GetPayload` получает точные ключи.

### why
Типизированные функции слоя данных (`listBrief`) — главный результат использования Prisma. Если возвращаемый тип описан вручную, он со временем разойдётся со схемой; если выведен из запроса — расходиться нечему.

### deep Если не получилось
- **`Type 'true' is not assignable …`** — в `select` значение должно быть `true`/`false`/вложенный объект; опечатка в имени поля даёт ошибку с перечислением допустимых.
- **Тип стал слишком широким (`boolean`)** — объект `select` объявлен без `satisfies`/`as const`, и TS расширил `true` до `boolean`; используй `satisfies Prisma.BookingSelect`.

### quiz
- Как получить тип результата запроса с конкретным `select`?
- Чем `satisfies` помогает при описании объекта `select`?
- Что делает `Awaited<ReturnType<typeof listBrief>>`?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/type-safety | типобезопасность | Prisma 7: Type safety
- https://www.prisma.io/docs/orm/v7/prisma-client/type-safety/operating-against-partial-structures-of-model-types | частичные типы | Prisma 7: Operating against partial structures of model types

## 5.7 🔨 «В списке броней не хватает полей» | short: 🔨 Нет нужных полей | est: ~40 мин
### intro
**Слова шага:** *жалоба заказчика*, *`select` без нужного поля*, *`undefined` в результате*, *ошибка при `omit`*.

:::tip Если совсем просто
Заказчик пишет, что в новом отчёте «нет колонки с заметкой». Код как будто верный, ошибок нет. Но поле в ответ **не попросили** — и оно не пришло.
:::

*Заказчик:* «Мы вывели список броней клиента, а заметка менеджера (`note`) у всех пустая — хотя в базе она есть. Хотели ещё показать залог, и его тоже нет».

Воспроизведи:

```ts
// src/lessons/05-complaint.ts
import { prisma } from '../db.js'

const list = await prisma.booking.findMany({
  where: { note: { not: null } },
  select: { id: true, status: true },
  take: 3,
})
for (const b of list) {
  console.log(b.id, (b as any).note, (b as any).deposit)   // as any — «обход» типов!
}
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
SQL_LOG=1 npx tsx src/lessons/05-complaint.ts 2>&1 | head -12
```

### result
```out auto
```

Поля `note` и `deposit` — `undefined`: `select` их не содержит, и в SQL их нет (смотри лог!). Парадокс: компилятор **не сказал ни слова** — потому что мы сами «заглушили» его через `as any` (см. шаг 2.7). Без `as any` код не скомпилировался бы: `Property 'note' does not exist on type { id: number; status: number | null }`. Исправь: добавь поля в `select`, убери `as any`, и убедись, что `npm run typecheck` чистый:

```bash run
cd ~/prisma-lab/rentkit
sed -i.bak 's/select: { id: true, status: true },/select: { id: true, status: true, note: true, deposit: true },/; s/(b as any).note, (b as any).deposit/b.note, b.deposit/' src/lessons/05-complaint.ts && rm src/lessons/05-complaint.ts.bak
SQL_LOG=1 npx tsx src/lessons/05-complaint.ts 2>&1 | head -12
npm run typecheck
```

### result
```out auto
```

**Приёмка сессии:** пять отчётов, каждый — запросом Prisma **и** с найденным в логе SQL и его временем: (1) число броней по статусам (`groupBy`); (2) пять клиентов с наибольшим числом броней (`groupBy` + `orderBy` по `_count` + `take`); (3) средний залог по категориям снаряжения (`groupBy` по `category`); (4) число просроченных броней (статус 6) по филиалам; (5) десять последних броней с заметкой (`select` + `where`). К каждому — строка в `NOTES.md`: «SQL был такой, время такое, лишних полей нет».

### why
Баг «поле не пришло» — самый невинный, но показывает общий принцип: **типы и лог — твои две проверки**. Типы говорят, что тебе доступно; лог — что реально отправлено в базу. Если обходишь типы через `any`, остаётся только лог, а это уже поздно.

### deep Если не получилось
- **`sed` на Mac ругается** — запусти его с `-i.bak` как в примере (создаёт копию) или правь файл вручную.
- **Не получается отчёт (2) через `groupBy`** — для сортировки по агрегату используй `orderBy: { _count: { id: 'desc' } }`, группировку — `by: ['customerId']`.

### quiz
- Почему при `as any` ошибка «поле не пришло» остаётся незамеченной до запуска?
- Как по логу запросов убедиться, что поле действительно не запрошено?
- Чем `select`, не содержащий нужного поля, отличается от `omit` этого поля по результату?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/queries/select-fields | select | Prisma 7: Select fields
