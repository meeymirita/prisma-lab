# Сессия 6 · Связи и N+1
dur: ~4 ч

## 6.1 Связи в схеме без внешних ключей: relationMode | short: Связи и relationMode | est: ~50 мин
### intro
**Слова шага:** *`@relation`*, *`fields` и `references`*, *связь 1:N*, *`relationMode`*, *эмуляция ссылочной целостности*, *`@@index`*.

:::tip Если совсем просто
Связь «бронь принадлежит клиенту» в обычной базе держится на внешнем ключе: база сама следит, чтобы клиент существовал. У нашего «наследства» таких ключей нет, а часть броней вообще ссылается на несуществующих клиентов. Prisma умеет описать связь **только на своей стороне** (`relationMode = "prisma"`): запросы со связями работают, а следить за целостностью приходится самой Prisma, а не базе.
:::

Раньше `db pull` не создал связей, потому что их нет в базе. Опишем их сами. Сначала режим связей в `datasource` — «без ключей на стороне базы»:

```prisma schema
datasource db {
  provider     = "postgresql"
  relationMode = "prisma"
}
```

Затем связи. В каждой связи две стороны: **скалярное поле** (`customerId`) и **поле-связь** (`customer`); связь описывается атрибутом `@relation(fields: [...], references: [...])` на стороне, где лежит ключ.

```prisma schema
model Branch {
  // …поля как раньше…
  items     Item[]
  customers Customer[]
  bookings  Booking[]
}

model Customer {
  // …поля как раньше…
  branch   Branch?   @relation(fields: [branchId], references: [id])
  bookings Booking[]
  @@index([branchId])
}

model Item {
  // …поля как раньше…
  branch   Branch?   @relation(fields: [branchId], references: [id])
  bookings Booking[]
  @@index([branchId])
}

model Booking {
  // …поля как раньше…
  customer   Customer?    @relation(fields: [customerId], references: [id])
  item       Item?        @relation(fields: [itemId], references: [id])
  branch     Branch?      @relation(fields: [branchId], references: [id])
  payments   Payment[]
  depositLog DepositLog[]
  @@index([customerId])
  @@index([itemId])
  @@index([branchId])
}

model Payment {
  // …поля как раньше…
  booking Booking? @relation(fields: [bookingId], references: [id])
  @@index([bookingId])
}

model DepositLog {
  // …поля как раньше…
  booking Booking? @relation(fields: [bookingId], references: [id])
  @@index([bookingId])
}
```

```bash run
cd ~/prisma-lab/rentkit
npx prisma format
npx prisma validate
npx prisma generate
npx prisma migrate dev --create-only --name relations_indexes
cat prisma/migrations/*_relations_indexes/migration.sql
```

### result
```out auto
```

Что здесь происходит: (1) `relationMode = "prisma"` не создаёт внешних ключей на уровне базы — не должно быть ни `FOREIGN KEY` в миграции, ни падений на сиротах; (2) при этом `@@index` на каждом поле связи **обязателен по рекомендации Prisma** (в этом режиме нет индексов, которые обычно создаются вместе с ключом) — и именно эти индексы появятся в созданной миграции (`CREATE INDEX`); (3) поля-связи (`customer`, `branch`…) в базе **не существуют** — это только описание для клиента.

Открой созданный `migration.sql` и убедись: там только `CREATE INDEX`, никаких `FOREIGN KEY`. Если всё так — примени его (`npx prisma migrate dev`), иначе не применяй и найди причину.

```bash run hidden
cd ~/prisma-lab/rentkit && npx prisma migrate deploy && npx prisma generate
```

### why
Это принципиальный выбор: **связь в схеме ≠ ограничение в базе**. Пока у нас сироты (бронь без клиента) и нет ключей, база разрешает нарушать целостность, а Prisma — нет, но только для тех, кто пишет через неё. Настоящие внешние ключи появятся после чистки (сессия 11), тогда `relationMode` вернётся к значению по умолчанию. А индексы под них полезны уже сейчас: большая часть запросов в наследстве идёт по `cust_id` и `item_id`.

### deep Под капотом: чем отличается эмуляция
При `relationMode = "prisma"` ссылочные действия (`onDelete: Cascade`, `SetNull`, `Restrict`) выполняет **клиент Prisma**: перед удалением клиента он сам делает дополнительные запросы к броням. Это медленнее и **не защищает**, если кто-то удалит строку мимо Prisma. Правило: если можно иметь внешние ключи в базе — держите их там (`relationMode = "foreignKeys"`, по умолчанию).

### deep Если не получилось
- **Предупреждение «relation field … should have an index»** — не хватает `@@index` на скалярном поле связи; добавь.
- **В созданной миграции есть `FOREIGN KEY`** — `relationMode` не сработал (опечатка в `datasource`) или схема не пересобрана: `npx prisma validate`.
- **`Error validating … the relation fields … must reference a unique field`** — `references` указывает на неуникальное поле; у нас везде ссылка на `id`.

### quiz
- Чем связь в схеме Prisma отличается от внешнего ключа в базе?
- Что даёт `relationMode = "prisma"` и чего он не гарантирует?
- Зачем при `relationMode = "prisma"` нужны `@@index` на полях связи?

### links
- https://www.prisma.io/docs/orm/v7/prisma-schema/data-model/relations/relation-mode | relationMode | Prisma 7: Relation mode
- https://www.prisma.io/docs/orm/v7/prisma-schema/data-model/relations/one-to-many-relations | связи 1:N | Prisma 7: One-to-many relations

## 6.2 include и вложенный select | short: include | est: ~40 мин
### intro
**Слова шага:** *`include`*, *вложенный `select`*, *вложенный `where`*, *`_count`*, *сколько SQL — один вызов*.

:::tip Если совсем просто
`include` — «принеси бронь **вместе** с её клиентом и платежами». Один вызов в коде, а запросов в базу может быть несколько — вот это и надо научиться замечать.
:::

```ts
// src/lessons/06-include.ts
import { prisma } from '../db.js'

// 1. бронь + клиент + предмет
const one = await prisma.booking.findFirst({
  where: { id: 1000 },
  include: { customer: true, item: { select: { title: true, category: true } } },
})
console.log(one?.customer?.name, one?.item?.title)

// 2. один-ко-многим: клиент и его брони с платежами (вложенный include)
const cust = await prisma.customer.findUnique({
  where: { id: 42 },
  include: { bookings: { take: 3, include: { payments: true } } },
})
console.log(cust?.bookings.map((b) => [b.id, b.payments.length]))

// 3. вложенный select вместо include: точный состав
const slim = await prisma.booking.findMany({
  where: { branchId: 1 },
  take: 3,
  select: { id: true, customer: { select: { id: true, name: true } }, _count: { select: { payments: true } } },
})
console.log(slim)
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
SQL_LOG=1 npx tsx src/lessons/06-include.ts 2>&1 | grep -c 'SELECT' || true
SQL_LOG=1 npx tsx src/lessons/06-include.ts 2>&1 | grep -E '^\S*\[|FROM' | head -20
```

### result
```out auto
```

Сосчитай запросы в логе. По умолчанию Prisma загружает связи **отдельными запросами**: сначала основной (`tbl_Bookings`), потом по списку id связанных (`tbl_Customers WHERE id IN (...)`, `tbl_Items WHERE id IN (...)`). Каждый уровень вложенности — ещё запрос. Поэтому «один вызов» ≠ «один запрос».

Отличия `include` и вложенного `select`: `include` берёт **все скалярные поля** модели плюс указанные связи; вложенный `select` — только то, что ты перечислила. `_count` в `select` считает связанные строки одним запросом без загрузки самих связей. **Сирот** (брони без клиента) Prisma вернёт как `customer: null`; поэтому в схеме связь помечена `Customer?`.

### why
Связи — сердце ORM, и именно здесь прячутся самые частые проблемы производительности. Научиться видеть «сколько запросов на самом деле ушло» — первое, ради чего читать лог (шаг 5.5). Дальше — как сократить их число.

### deep Как ещё можно
Во вложенных связях можно писать `where`, `orderBy`, `take`: «клиент и его последние три брони»: `include: { bookings: { orderBy: { id: 'desc' }, take: 3 } }`. При `take` внутри связи Prisma может грузить связи через отдельный запрос с оконными функциями (**сверьтесь** с логом) — следи за SQL.

### deep Если не получилось
- **`customer` всегда `null`** — `customerId` у этой брони указывает на несуществующего клиента (сирота) или связь описана не по тому полю.
- **TypeScript ругается, что `payments` не существует** — после правки схемы не запущен `prisma generate`.

### quiz
- В чём разница между `include` и вложенным `select`?
- Сколько запросов в базу делает вызов с вложенным `include` по умолчанию?
- Как Prisma возвращает сироту (бронь с несуществующим клиентом)?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/queries/relation-queries | запросы по связям | Prisma 7: Relation queries

## 6.3 N+1: пишем нарочно и считаем запросы | short: N+1 | est: ~45 мин
### intro
**Слова шага:** *N+1*, *цикл с запросом внутри*, *`pg_stat_statements`*, *счётчик запросов*, *`calls`*.

:::tip Если совсем просто
Представь: нужно узнать имена пяти клиентов. Можно **один раз** спросить базу «дай мне этих пятерых» (1 запрос). А можно сначала спросить «дай список», а потом **пять раз** — «а как зовут первого? второго?..» (1 + 5 = 6 запросов). На пяти — смешно. На пяти тысячах — база задыхается. В коде это выглядит невинно: цикл и `await` внутри.
:::

```svg
@n-plus-one
```

Напишем «наивный» отчёт: последние 200 броней с названием предмета и именем клиента — и посчитаем запросы. Сначала подключим расширение, которое считает запросы со стороны базы:

```bash run
psqlr() { docker exec -i rental-pg psql -U postgres -d rental "$@"; }
psqlr -c 'CREATE EXTENSION IF NOT EXISTS pg_stat_statements'
psqlr -c 'SELECT pg_stat_statements_reset()'
```

### result
```out auto
```

Теперь «красивый» цикл и счётчик на стороне клиента:

```ts
// src/lessons/06-n1.ts
import { prisma } from '../db.js'

let queries = 0
prisma.$on('query', () => { queries++ })

console.time('N+1')
const bookings = await prisma.booking.findMany({ orderBy: { id: 'desc' }, take: 200 })
const rows = []
for (const b of bookings) {
  const customer = b.customerId ? await prisma.customer.findUnique({ where: { id: b.customerId } }) : null
  const item = b.itemId ? await prisma.item.findUnique({ where: { id: b.itemId } }) : null
  rows.push({ id: b.id, customer: customer?.name, item: item?.title })
}
console.timeEnd('N+1')
console.log(`строк: ${rows.length}, запросов к базе: ${queries}`)
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/06-n1.ts
psqlr() { docker exec -i rental-pg psql -U postgres -d rental "$@"; }
psqlr -c "SELECT calls, round(total_exec_time::numeric, 1) AS ms, left(query, 70) AS query FROM pg_stat_statements WHERE query ILIKE '%tbl_%' ORDER BY calls DESC LIMIT 4"
```

### result
```out auto
```

Ожидаем: **1 + 200 + 200 = 401 запрос** на 200 строк отчёта, а `pg_stat_statements` покажет два запроса с `calls` около 200 (по клиентам и по предметам) — база честно посчитала, сколько раз её дёргали. В коде же всего **один цикл**. Теперь вырастим масштаб мысленно: на странице в 5 000 строк это 10 001 запрос — каждый с накладными расходами сети и разбора.

### why
N+1 — самая частая и самая невидимая проблема ORM. На маленьких данных она не заметна, на реальных превращает страницу в минуту ожидания. Красота «цикл + `await`» — это ловушка: код выглядит так же, как правильный. Спасает только **счётчик запросов** (мы поставили его в тесты: «на эту функцию — не больше трёх запросов»).

### deep Команды по частям
`prisma.$on('query', () => { queries++ })` — подписка на событие запроса; увеличиваем счётчик при каждом SQL. `pg_stat_statements` — расширение PostgreSQL: хранит для каждого **нормализованного** запроса (значения заменены на `$1`) число вызовов и суммарное время. `pg_stat_statements_reset()` — обнулить статистику перед замером.

### deep Если не получилось
- **`relation "pg_stat_statements" does not exist`** — контейнер запущен без `-c shared_preload_libraries=pg_stat_statements` (шаг 1.3): пересоздай контейнер с этим параметром (данные в томе сохранятся) и повтори `CREATE EXTENSION`.
- **Запросов в логе меньше, чем ожидалось** — `findUnique` в одном тике может объединяться (**сверьтесь**: у Prisma есть автоматическая пакетизация одинаковых `findUnique`); для обучения используй разные поля или сравни `calls`.

### quiz
- Почему N+1 на малых данных не заметен?
- Что считает `pg_stat_statements` и чем он дополняет счётчик на стороне клиента?
- Как мы поймали N+1: по коду или по числу запросов?

### links
- https://www.postgresql.org/docs/18/pgstatstatements.html | pg_stat_statements | PostgreSQL 18: pg_stat_statements
- https://www.prisma.io/docs/orm/v7/prisma-client/queries/advanced/query-optimization-performance | оптимизация запросов | Prisma 7: Query optimization

## 6.4 Лечение: include, relationLoadStrategy join против query | short: join или query | est: ~45 мин
### intro
**Слова шага:** *`include` вместо цикла*, *`relationLoadStrategy`*, *`join`*, *`query`*, *`previewFeatures = ["relationJoins"]`*, *`LATERAL JOIN`*.

:::tip Если совсем просто
Лечение N+1 — спросить всё сразу. У Prisma два способа: **«query»** — задать несколько запросов подряд (по одному на связь) и склеить результат у себя; **«join»** — отправить базе **один** запрос с соединением, и она сама склеит. Первое проще для базы, второе — меньше поездок по сети.
:::

Первое лечение — не гонять запросы по одному:

```ts
// src/lessons/06-cure.ts
import { prisma } from '../db.js'

let queries = 0
prisma.$on('query', () => { queries++ })

console.time('include')
const rows = await prisma.booking.findMany({
  orderBy: { id: 'desc' },
  take: 200,
  include: { customer: { select: { name: true } }, item: { select: { title: true } } },
})
console.timeEnd('include')
console.log(rows.length, 'строк,', queries, 'запроса к базе')
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/06-cure.ts
```

### result
```out auto
```

```bash run hidden
cd ~/prisma-lab/rentkit && grep -q relationJoins prisma/schema.prisma || sed -i 's|provider = "prisma-client"|provider = "prisma-client"\n  previewFeatures = ["relationJoins"]|' prisma/schema.prisma && sed -i "s/  take: 200,/  take: 200,\n  relationLoadStrategy: 'join',/" src/lessons/06-cure.ts && npx prisma generate
```

Вместо 401 запроса — **три** (основной, клиенты `IN (...)`, предметы `IN (...)`). Второе лечение — «соединение на стороне базы». Для него в Prisma 7 нужна **предпросмотровая возможность** (**сверьтесь**: на момент написания `relationLoadStrategy` документирован как Preview): добавь в `generator` `previewFeatures = ["relationJoins"]`, затем `npx prisma generate` и попроси стратегию в запросе:

```ts
const rows = await prisma.booking.findMany({
  orderBy: { id: 'desc' },
  take: 200,
  relationLoadStrategy: 'join',     // 'join' | 'query' (по умолчанию 'query')
  include: { customer: { select: { name: true } }, item: { select: { title: true } } },
})
```

```bash run
cd ~/prisma-lab/rentkit
SQL_LOG=1 npx tsx src/lessons/06-cure.ts 2>&1 | grep -c 'FROM'
```

### result
```out auto
```

При `join` в логе остаётся **один** запрос — с `LEFT JOIN LATERAL` и агрегированием связанных строк в JSON. Сравни: `query` — три простых запроса и склейка в Node; `join` — один сложный запрос и склейка в PostgreSQL.

| | `query` (по умолчанию) | `join` |
|---|---|---|
| число запросов | по одному на уровень связи | один |
| нагрузка | на клиента и сеть | на базу |
| хорошо, когда | связей много, данные большие, список `IN` не огромный | связей мало, нужна одна поездка, малая задержка сети |
| плохо, когда | много уровней вложенности | широкие строки дублируются в соединении, огромные выборки |

Выбор — **по замеру**, а не «потому что так модно»: сравни `duration` из лога для обоих режимов на своей базе.

### why
Видишь, насколько разное поведение скрывается за одним `include`: от этого зависит и скорость, и нагрузка на базу. Если не знать про стратегию, можно годами «оптимизировать» не то. Привычка — сначала цифры (число запросов и время), потом правки.

### deep Если не получилось
- **`Unknown argument relationLoadStrategy`** — не включён `previewFeatures = ["relationJoins"]` или не запущен `generate`.
- **`join` медленнее `query`** — на ширине в десятки колонок и большом числе строк соединение дублирует данные; смотри `EXPLAIN` и сравнивай.

### quiz
- Сколько запросов делает `include` вместо цикла и почему именно столько?
- Чем отличаются стратегии `join` и `query`?
- Как выбрать стратегию — теоретически или замером?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/queries/relation-queries#relation-load-strategies-preview | стратегии загрузки | Prisma 7: Relation load strategies
- https://www.prisma.io/docs/orm/v7/reference/preview-features/client-preview-features | preview-возможности | Prisma 7: Client preview features

## 6.5 Фильтрация по связям: some, every, none | short: Фильтры по связям | est: ~40 мин
### intro
**Слова шага:** *`some`*, *`every`*, *`none`*, *`is`/`isNot`*, *`EXISTS`*, *цена вложенного условия*.

:::tip Если совсем просто
Бывает нужно найти не «брони», а «клиентов, у которых **есть** просроченная бронь» — условие по другой таблице. `some` — «хотя бы одна подходит», `every` — «все подходят», `none` — «ни одна не подходит». Для «один-к-одному/к-одному» — `is` и `isNot`.
:::

```ts
// src/lessons/06-relfilter.ts
import { prisma } from '../db.js'

// клиенты, у которых есть хотя бы одна просроченная бронь
const overdue = await prisma.customer.findMany({
  where: { bookings: { some: { status: 6 } } },
  select: { id: true, name: true },
  take: 5,
})
console.log(overdue)

// предметы, по которым не было ни одной брони (мёртвый склад)
const dead = await prisma.item.count({ where: { bookings: { none: {} } } })
console.log('предметов без броней:', dead)

// брони, у которых поле клиента пустое (NULL) — не путать с «сиротами»!
const noCustomer = await prisma.booking.count({ where: { customer: { is: null } } })
console.log('броней с пустым cust_id:', noCustomer)
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
SQL_LOG=1 npx tsx src/lessons/06-relfilter.ts 2>&1 | grep -E 'EXISTS|NOT|IS NULL|LEFT JOIN' | head -8
npx tsx src/lessons/06-relfilter.ts
```

### result
```out auto
```

В SQL это `EXISTS (SELECT … WHERE …)` / `NOT EXISTS` — подзапрос на каждую строку: на больших таблицах без индексов по полю связи (мы добавили их в 6.1: `@@index([customerId])`) работает медленно. Проверь `EXPLAIN` запроса про «мёртвый склад» (`NOT EXISTS`): с индексом из 6.1 это `Nested Loop Anti Join` и `Index Only Scan using "tbl_Bookings_item_id_idx"` — около 4 мс на все 4 000 предметов; без индекса по `item_id` планировщику пришлось бы просматривать таблицу броней целиком (в сессии 8 сравним на своей базе). В нашей базе у каждого предмета есть хотя бы одна бронь, поэтому ответ — `0`.

**Осторожно: это не «сироты».** `customer: { is: null }` в SQL превращается в `WHERE cust_id IS NULL` (посмотри в логе): находятся только брони, у которых **поле клиента пустое**. Их у нас `0`. А вот полторы тысячи **осиротевших** броней из шага 3.1 — те, где `cust_id` заполнен, но такого клиента нет, — этот фильтр **не видит**: для Prisma со `relationMode = "prisma"` связь «не найдена» и «не указана» — разные вещи. Настоящих сирот ищут соединением (`LEFT JOIN … WHERE c.id IS NULL` — тот самый запрос из 3.1; через Prisma — `$queryRaw`, сессия 9).

### why
Фильтры по связям красивы и компактны, но превращаются в подзапросы, стоимость которых легко недооценить. Поэтому после каждого такого фильтра смотри план: если есть `Seq Scan` по большой таблице внутри `SubPlan`, нужен индекс (сессия 8).

### deep Если не получилось
- **`Unknown argument some`** — связь `bookings` не описана на стороне `Customer` (нет поля-списка `Booking[]`); добавь обратную сторону.
- **Результат пустой** — условие `status: 6` не выполняется ни у кого; проверь распределение статусов запросом (шаг 5.4).

### quiz
- Что делают `some`, `every`, `none` и во что они превращаются в SQL?
- Почему такие фильтры бывают медленными без индекса по полю связи?
- Почему фильтр `customer: { is: null }` не находит «сирот» (броней с несуществующим клиентом) и как их найти?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/queries/relation-queries#filter-on-absence-of--records | фильтр по связям | Prisma 7: Relation queries
- https://www.prisma.io/docs/orm/v7/prisma-client/queries/filtering-and-sorting | фильтры | Prisma 7: Filtering and sorting

## 6.6 Когда include превращается в монстра | short: Глубокие include | est: ~35 мин
### intro
**Слова шага:** *глубокая вложенность*, *раздувание результата*, *`take` во вложении*, *когда переходить на raw*.

:::tip Если совсем просто
`include` — как матрёшка: клиент → брони → платежи → ... Каждая вложенность умножает число строк. На трёх уровнях ты рискуешь принести тысячи строк ради нескольких цифр. Тогда проще сказать базе напрямую: «посчитай итог» и принести одну строку.
:::

Задача: «для 50 клиентов вывести число броней и общую сумму платежей». Наивный вариант:

```ts
// src/lessons/06-monster.ts
import { prisma } from '../db.js'

console.time('deep include')
const customers = await prisma.customer.findMany({
  take: 50,
  include: { bookings: { include: { payments: true } } },
})
const report = customers.map((c) => ({
  id: c.id,
  bookings: c.bookings.length,
  paid: c.bookings.flatMap((b) => b.payments).reduce((s, p) => s + (p.amount ?? 0), 0),
}))
console.timeEnd('deep include')
console.log(report.slice(0, 3), 'строк загружено в память:', customers.reduce((n, c) => n + c.bookings.length, 0))
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/06-monster.ts
```

### result
```out auto
```

Нужны **два числа на клиента**, а принесены **все брони и все платежи** — десятки тысяч объектов, суммируем в JS. Это неправильное разделение труда: база умеет считать сама. Три выхода, по возрастанию «серьёзности»: (1) `_count` для числа (`select: { _count: { select: { bookings: true } } }`) — считает на стороне базы; (2) `groupBy` по платежам (если суммировать нужно без клиента); (3) **сырой SQL** (`$queryRaw`) с `JOIN` и `GROUP BY` — для итогов по нескольким таблицам сразу (сессия 9). Правило: если из вложенности нужны **итоги**, а не строки, — не включай её целиком.

### why
`include` — для показа объекта целиком (карточка брони с клиентом и предметом). Для отчётов, итогов, дашбордов — агрегаты в базе. Умение вовремя перейти с «красивого» запроса на агрегацию — признак зрелого использования ORM.

### deep Если не получилось
- **Скрипт упал по памяти / очень долго** — загружено слишком много; уменьши `take` до 10 или добавь `select` с минимумом полей.
- **`reduce` ругается на `null`** — `amount` типа `number | null`: используй `?? 0`, как в примере (шаг 2.3).

### quiz
- Почему глубокий `include` для отчёта — плохая идея?
- Какие три способа посчитать итоги без загрузки всех строк?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/queries/aggregation-grouping-summarizing#count-relations | count по связям | Prisma 7: Count relations

## 6.7 🔨 «Список клиентов грузится 12 секунд» | short: 🔨 N+1 в проде | est: ~60 мин
### intro
**Слова шага:** *жалоба заказчика*, *N+1 внутри функции*, *замер по логу*, *как доказать исправление*.

:::tip Если совсем просто
Заказчик жалуется на «тормоза» страницы, а причину в коде не видно — всё выглядит прилично. Находишь по логу: какой запрос повторяется сотнями. Чинишь. И **доказываешь** числом, что стало быстрее.
:::

*Заказчик:* «Страница „Клиенты и их последний платёж“ грузится по 10–12 секунд. Раньше работала быстрее. Что вы там сделали?»

Разработчик до тебя написал:

```ts
// src/lessons/06-slow.ts
import { prisma } from '../db.js'

export async function customersWithLastPayment(limit = 100) {
  const customers = await prisma.customer.findMany({ take: limit, orderBy: { id: 'asc' } })
  return Promise.all(
    customers.map(async (c) => {
      const last = await prisma.payment.findFirst({
        where: { booking: { customerId: c.id } },
        orderBy: { id: 'desc' },
      })
      return { id: c.id, name: c.name, lastPaid: last?.amount ?? null }
    }),
  )
}

console.time('slow')
const rows = await customersWithLastPayment(100)
console.timeEnd('slow')
console.log(rows.length)
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
SQL_LOG=1 npx tsx src/lessons/06-slow.ts 2>&1 | tail -6
```

### result
```out auto
```

**Твоя задача** — найти причину и исправить. Подсказки лежат в «Если не получилось», а не здесь. Требования: (1) число запросов к базе — **не больше трёх** на 100 клиентов; (2) время — **заметно меньше**: у нас на ноутбуке исходный вариант занял около 135 мс (база рядом, сеть почти бесплатна), а правильный — около 25 мс; на удалённой базе, где каждый запрос — поездка по сети на 1–5 мс и очередь в пуле из 10 соединений, разница вырастает до секунд, как и в жалобе; (3) результат тот же; (4) докажи числами: «было N запросов и T мс, стало M и t».

```ts file=src/lessons/06-fast.ts hidden
import { prisma } from '../db.js'

let queries = 0
prisma.$on('query', () => { queries++ })

export async function customersWithLastPayment(limit = 100) {
  const customers = await prisma.customer.findMany({ take: limit, orderBy: { id: 'asc' } })
  const bookings = await prisma.booking.findMany({
    where: { customerId: { in: customers.map((c) => c.id) } },
    select: { id: true, customerId: true },
  })
  const owner = new Map(bookings.map((b) => [b.id, b.customerId]))
  const payments = await prisma.payment.findMany({
    where: { bookingId: { in: bookings.map((b) => b.id) } },
    select: { id: true, bookingId: true, amount: true },
    orderBy: { id: 'desc' },
  })
  const last = new Map<number, number | null>()
  for (const p of payments) {
    const cid = owner.get(p.bookingId ?? -1)
    if (cid != null && !last.has(cid)) last.set(cid, p.amount)
  }
  return customers.map((c) => ({ id: c.id, name: c.name, lastPaid: last.get(c.id) ?? null }))
}

console.time('fast')
const rows = await customersWithLastPayment(100)
console.timeEnd('fast')
console.log(rows.length, 'строк,', queries, 'запроса')
await prisma.$disconnect()
```

```bash run hidden
cd ~/prisma-lab/rentkit && npx tsx src/lessons/06-fast.ts && npx tsx src/lessons/06-slow.ts | tail -3
```

**Приёмка сессии:** схема со связями (без внешних ключей) и индексами по полям связи применена миграцией `relations_indexes`; N+1 в 6.3 воспроизведён и вылечен через `include`; в 6.7 «последний платёж клиента» собирается тремя запросами или меньше; в `NOTES.md` записаны цифры «до» и «после».

### why
Эта жалоба — прототип сотен реальных. В коде всё выглядит аккуратно, `Promise.all` даже распараллеливает запросы — и от этого хуже: сто одновременных запросов насыщают пул (10 соединений!) и каждый ждёт своей очереди. Привычка перед исправлением **измерить** (запросы, время) и после — **доказать**, избавляет от «вроде стало лучше».

### deep Если не получилось
- **Подсказка 1:** сколько запросов ушло? Запросов `findFirst` ровно столько, сколько клиентов, и каждый — с вложенным `where` по связи (JOIN/EXISTS).
- **Подсказка 2:** нужен один запрос за **всеми** платежами этих клиентов сразу (`where: { booking: { customerId: { in: ids } } }`), а «последний» выберешь в памяти или через `distinct`/`groupBy` — сравни варианты.
- **Подсказка 3:** `groupBy` по `bookingId` с `_max: { id: true }` даёт номер последнего платежа на бронь за один запрос; платёж → бронь → клиент собираешь в `Map`.
- **Время всё равно большое** — смотри `EXPLAIN` запроса из лога: есть ли `Seq Scan` по `tbl_Payments`? Индекс по `booking_id` мы создали в 6.1 — применена ли миграция (`migrate status`)?

### quiz
- Почему `Promise.all` с запросом внутри `map` не лечит N+1, а может ухудшить положение?
- Как доказать числами, что исправление помогло?
- Что мы проверяем, если после исправления запросов стало меньше, а время почти не изменилось?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/queries/advanced/query-optimization-performance | оптимизация запросов | Prisma 7: Query optimization and performance
