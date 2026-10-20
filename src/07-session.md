# Сессия 7 · Запись, типы данных, ошибки
dur: ~4 ч

## 7.1 create, update, upsert, delete | short: CRUD записи | est: ~40 мин
### intro
**Слова шага:** *`create`*, *`update`*, *`upsert`*, *`delete`*, *`where` у `update`*, *возвращаемое значение*, *`select` в записи*.

:::tip Если совсем просто
Запись — это четыре глагола: создать, обновить, «создать или обновить» (`upsert`) и удалить. Каждый возвращает **строку в том состоянии, какой она стала** — не нужно перечитывать из базы. Если у тебя на руках не уникальный ключ, а условие — используй `updateMany`/`deleteMany`.
:::

Работаем с «песочницей»: заведём тестовый предмет и будем его менять, не трогая настоящие данные. В `tbl_Items` у `sku` пока нет `unique` — подготовь предмет с заведомо отдельным кодом:

```ts
// src/lessons/07-crud.ts
import { prisma } from '../db.js'

// 1. создать — вернётся созданная строка с id
const item = await prisma.item.create({
  data: { branchId: 1, sku: 'SKU-TEST-1', title: 'Тестовый самокат', category: 'Самокат', dailyPriceText: '500,00', deposit: 1500, active: 1 },
})
console.log('создан', item.id)

// 2. обновить по уникальному ключу
const upd = await prisma.item.update({ where: { id: item.id }, data: { title: 'Самокат (обновлён)', active: 0 } })
console.log('после update:', upd.title, upd.active)

// 3. upsert: если такой sku есть — обновить, иначе создать (sku пока не уникален → upsert по id)
const up = await prisma.item.upsert({
  where: { id: item.id },
  update: { deposit: 2000 },
  create: { sku: 'SKU-TEST-1', title: 'нет такого', category: 'Самокат', active: 1 },
})
console.log('после upsert, залог:', up.deposit)

// 4. удалить
const gone = await prisma.item.delete({ where: { id: item.id } })
console.log('удалён', gone.id)

// 5. «условие» вместо ключа: updateMany и deleteMany возвращают только счётчик { count }
const cnt = await prisma.item.updateMany({ where: { sku: { startsWith: 'SKU-TEST' } }, data: { active: 0 } })
console.log(cnt)
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
SQL_LOG=1 npx tsx src/lessons/07-crud.ts 2>&1 | grep -E 'INSERT|UPDATE|DELETE|BEGIN|COMMIT' | head -12
npx tsx src/lessons/07-crud.ts
```

### result
```out auto
```

Что видно в логе: `INSERT … RETURNING`, `UPDATE … RETURNING`, `DELETE … RETURNING` — **одним запросом**, база возвращает результат сама. `upsert` в PostgreSQL выполняется через `INSERT … ON CONFLICT … DO UPDATE` только когда `where` указывает на уникальный ключ и в `update`/`create` нет вложенных записей; иначе Prisma делает «найти, потом создать/обновить» несколькими запросами (**сверьтесь** по логу) — и тогда он не атомарен.

Ещё два правила: `update` и `delete` по `where` бросают **`P2025`** («запись не найдена»), если ключа нет; `updateMany`/`deleteMany` ничего не бросают — просто вернут `{ count: 0 }`. Чтобы не вернуть лишнее, можно ограничить результат `select`.

### why
Запись — место, где ошибки дороже всего: потерянное обновление, дубль, удалённое не то. Привыкай смотреть в лог не только на `SELECT`, но и на то, из скольких запросов состоит запись и есть ли среди них `BEGIN`/`COMMIT`.

### deep Команды по частям
`delete` возвращает **удалённую** строку (на случай, если нужно её записать в журнал). `update({ where: { id }, data: { deposit: { increment: 100 } } })` — **атомарные** операции над числами (`increment`, `decrement`, `multiply`, `divide`, `set`): значение пересчитывается **в базе**, без чтения и записи в JS (это спасает от потерянных обновлений, сессия 12).

### deep Если не получилось
- **`Record to update not found`** — `P2025`: ключ не существует (или уже удалён предыдущим шагом).
- **`Argument 'sku' … must not be null`** — у `Item.create` обязательные поля определяются схемой; в нашей схеме почти всё необязательное (`?`), но `branchId` в примере ожидается числом.

### quiz
- Что возвращают `update` и `delete` и чем это отличается от `updateMany`?
- Когда `upsert` выполняется как `ON CONFLICT`, а когда — несколькими запросами?
- Что делает `{ increment: 100 }` и в чём его преимущество перед «прочитать, прибавить, записать»?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/queries/crud | CRUD | Prisma 7: CRUD

## 7.2 Вложенные записи: create внутри create, connect | short: Вложенные записи | est: ~40 мин
### intro
**Слова шага:** *вложенная запись*, *`create` внутри `data`*, *`connect`*, *`connectOrCreate`*, *`disconnect`*, *неявная транзакция*.

:::tip Если совсем просто
Хочешь создать клиента **вместе с** его первой бронью. Можно сначала создать клиента, потом бронь с его номером (два запроса и риск остаться с клиентом без брони, если второй упал). Вложенная запись — один вызов: Prisma сама обернёт всё в транзакцию, и случится либо оба, либо ни одного.
:::

```ts
// src/lessons/07-nested.ts
import { prisma } from '../db.js'

// клиент с первой бронью «одним движением» (клиента и бронь создаём вместе)
const created = await prisma.customer.create({
  data: {
    name: 'Тест Вложенный',
    phone: '+79990000001',
    branchId: 1,
    bookings: {
      create: [{ itemId: 1, branchId: 1, startText: '2026-12-01', endText: '2026-12-03', priceText: '900,00 руб', status: 0 }],
    },
  },
  include: { bookings: true },
})
console.log('клиент', created.id, 'броней:', created.bookings.length)

// connect: привязать существующую бронь к клиенту
const another = await prisma.booking.create({ data: { itemId: 2, branchId: 1, status: 0 } })
await prisma.customer.update({
  where: { id: created.id },
  data: { bookings: { connect: { id: another.id } } },
})

// connectOrCreate: найти или создать связанную запись
await prisma.booking.update({
  where: { id: another.id },
  data: { branch: { connectOrCreate: { where: { id: 1 }, create: { name: 'Новый', city: 'Н/Д' } } } },
})

// уборка: брони и клиента (в «песочнице» всё по номерам)
await prisma.booking.deleteMany({ where: { customerId: created.id } })
await prisma.customer.delete({ where: { id: created.id } })
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
SQL_LOG=1 npx tsx src/lessons/07-nested.ts 2>&1 | grep -E 'BEGIN|COMMIT|INSERT|UPDATE' | head -14
```

### result
```out auto
```

В логе вложенное создание — это `BEGIN` … `INSERT` клиента … `INSERT` брони … `COMMIT`: **одна транзакция**. Если вставка брони упадёт (например, нарушится ограничение), клиент тоже не создастся. Три глагола вложенных записей: **`create`** (создать связанную), **`connect`** (привязать существующую по уникальному ключу), **`connectOrCreate`** (привязать, а если нет — создать); есть и `disconnect` (отвязать) и `set` (заменить список привязанных).

### why
Неявная транзакция — главная причина любить вложенные записи: не надо вручную держать «клиент без брони» в голове. Но помни: транзакция удерживает соединение из пула (шаг 12.5), и вложение на десять уровней — это длинная транзакция.

### deep Под капотом: связи без внешних ключей
Наш `relationMode = "prisma"` значит: **привязка идёт только на стороне Prisma** (она записывает `cust_id`), а база не проверяет, что клиент существует. `connect` на несуществующий id Prisma всё же отвергнет (`P2025`, «не найдено» в ходе проверки), но если ключ подставить в обход (raw SQL), база примет сироту — как в наследстве.

### deep Если не получилось
- **`Unknown argument bookings`** — со стороны `Customer` не описана связь `bookings Booking[]` (шаг 6.1) или не запущен `generate`.
- **Остались тестовые строки** — при ошибке в середине скрипта уборка не выполнилась: удали вручную `DELETE FROM "tbl_Customers" WHERE "CustName" LIKE 'Тест Вложенный%'`.

### quiz
- Почему вложенная запись безопаснее двух последовательных `create`?
- Чем `connect` отличается от `connectOrCreate`?
- Что значит «неявная транзакция» в логе?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/queries/relation-queries#nested-writes | вложенные записи | Prisma 7: Nested writes

## 7.3 createMany, updateMany, deleteMany | short: Массовые записи | est: ~35 мин
### intro
**Слова шага:** *`createMany`*, *`createManyAndReturn`*, *`skipDuplicates`*, *`updateMany`*, *`deleteMany`*, *ограничения пакетных операций*.

:::tip Если совсем просто
Пакетная запись — «вставь сразу тысячу строк» одним запросом вместо тысячи отдельных. Быстро, но у такой записи нет некоторых удобств: вложенные записи внутри недоступны, результат по умолчанию — только счётчик.
:::

```ts
// src/lessons/07-many.ts
import { prisma } from '../db.js'

const rows = Array.from({ length: 1000 }, (_, i) => ({
  branchId: 1 + (i % 12), sku: `SKU-BULK-${i}`, title: `Тест ${i}`, category: 'Тест', active: 1,
}))

console.time('одним запросом')
const r = await prisma.item.createMany({ data: rows })
console.timeEnd('одним запросом')
console.log(r)                                    // { count: 1000 }

console.time('по одному')
for (const row of rows.slice(0, 200)) await prisma.item.create({ data: { ...row, sku: row.sku + '-x' } })
console.timeEnd('по одному')

// вернуть созданные строки (PostgreSQL): createManyAndReturn
const back = await prisma.item.createManyAndReturn({
  data: [{ sku: 'SKU-BULK-r1', title: 'R1', category: 'Тест', active: 1 }],
  select: { id: true, sku: true },
})
console.log(back)

console.log(await prisma.item.updateMany({ where: { category: 'Тест' }, data: { active: 0 } }))
console.log(await prisma.item.deleteMany({ where: { category: 'Тест' } }))
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/07-many.ts
```

### result
```out auto
```

Ожидаем: тысяча строк `createMany` — десятки миллисекунд, двести строк по одной — на порядок дольше (и это **при локальной базе**, по сети разница больше). `skipDuplicates: true` пропускает строки, нарушающие уникальность, вместо ошибки (работает с `unique`). `createManyAndReturn` возвращает вставленные строки (на PostgreSQL); `updateMany`/`deleteMany` — только `{ count }`.

### why
Массовые операции — главный способ вставки больших данных (сидирование, импорт). Но у них свои границы: параметров в одном запросе у PostgreSQL ограниченное число (около 65 тысяч), поэтому большие массивы режут на пакеты (сессия 17.5).

### deep Если не получилось
- **`Too many bind variables`** — пакет слишком большой (65 535 параметров на запрос): раздели массив на куски по 1 000–5 000 строк.
- **Тестовые строки остались** — выполнится только последнее `deleteMany`; при ошибке раньше запусти его вручную.

### quiz
- Почему `createMany` быстрее, чем цикл с `create`?
- Что возвращают `createMany` и `createManyAndReturn`?
- Как поступить с массивом больше допустимого числа параметров?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/queries/crud#create-multiple-records | createMany | Prisma 7: Create multiple records

## 7.4 Decimal, BigInt, Json — ловушки типов | short: Ловушки типов | est: ~45 мин
### intro
**Слова шага:** *`Prisma.Decimal`*, *`decimal.js`*, *`bigint`*, *сериализация `BigInt`*, *`Json`*, *`JSON.parse` битой строки*.

:::tip Если совсем просто
Три типа, которые выглядят как «обычные», но ведут себя иначе. Деньги (`Decimal`) нельзя сложить плюсом. `BigInt` нельзя превратить в JSON. А `Json` — это не «любая строка», а настоящая структура: битую строку не прочитать.
:::

```ts
// src/lessons/07-types.ts
import { Prisma } from '../generated/prisma/client.js'
import { prisma } from '../db.js'

// 1. Decimal: приходит из numeric (из raw-запроса), складывать — методами
const [row] = await prisma.$queryRaw<{ total: Prisma.Decimal; n: bigint }[]>`
  SELECT sum(amount::numeric(12,2)) AS total, count(*) AS n FROM "tbl_Payments" WHERE kind = 1 AND booking_id < 1000`
console.log(typeof row!.total, row!.total.toString(), row!.total.plus('0.10').toFixed(2))

// 2. BigInt: count(*) и поля bigint
console.log(typeof row!.n, row!.n)
try {
  JSON.stringify({ n: row!.n })
} catch (e) {
  console.log('JSON.stringify упал:', (e as Error).message)
}
// как сериализовать: заменитель на строку
console.log(JSON.stringify({ n: row!.n }, (_k, v) => (typeof v === 'bigint' ? v.toString() : v)))

// 3. «JSON» в text: parse битой строки
const items = await prisma.item.findMany({ where: { meta: { not: null } }, select: { id: true, meta: true }, take: 4000 })
let bad = 0
for (const it of items) {
  try { JSON.parse(it.meta!) } catch { bad++ }
}
console.log('предметов с битым meta:', bad)

// 4. деньги в number: ошибка накопления
const amounts = (await prisma.payment.findMany({ take: 2000, select: { amount: true } })).map((p) => p.amount ?? 0)
const asNumber = amounts.reduce((s, a) => s + a, 0)
const asDecimal = amounts.reduce((s, a) => s.plus(a), new Prisma.Decimal(0))
console.log('number:', asNumber, ' Decimal:', asDecimal.toString())
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/07-types.ts
```

### result
```out auto
```

Что видим: (1) `typeof row.total` — `object` (это `Decimal`), а не `number`; сложить `+` нельзя, нужно `plus`, `minus`, `times`, `div`; (2) `count(*)` — `bigint` (`2000n`), а `JSON.stringify` с ним выбрасывает `TypeError: Do not know how to serialize a BigInt`; (3) около ста двадцати `meta` не парсятся (мы их заложили в наследство); (4) сумма `number` и `Decimal` может отличаться в хвостовых цифрах — это и есть погрешность двоичных дробей. Поэтому деньги переводим в `numeric` (сессия 10) и пользуемся `Decimal` (сессия 14).

### why
Ловушки типов — самые «тихие» ошибки: код запускается, а в отчёте копейка потерялась или на сервере упал `JSON.stringify` одного ответа из-за `BigInt`. Правило: если число — деньги, у тебя должен быть `Decimal`; если число — `count`/`bigint`, у тебя должна быть явная конвертация (`Number()` или строка) перед выдачей наружу.

### deep Как ещё можно
Чтобы сериализовать `BigInt` везде, иногда добавляют глобальное `BigInt.prototype.toJSON = function () { return this.toString() }`. Это **глобальная** правка прототипа и она скрывает проблему; лучше точечные заменители (как в примере) или DTO (отдельные объекты для ответа).

### deep Если не получилось
- **`Cannot read properties of undefined (reading 'total')`** — запрос вернул пустой массив: измени `booking_id < 1000` на `< 100000`.
- **`typeof row.total` — `string`** — адаптер вернул `numeric` строкой; в Prisma 7 тип `Decimal` приходит из поля модели, а в `$queryRaw` — тип зависит от запроса: используй явное `Prisma.Decimal` или `new Prisma.Decimal(row.total)`.

### quiz
- Почему `Decimal` нельзя складывать оператором `+`?
- Что произойдёт при `JSON.stringify({ n: 10n })` и как этого избежать?
- Почему деньги в `Float`/`number` — плохая идея?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/special-fields-and-types/working-with-json-fields | работа с Json | Prisma 7: Working with Json fields
- https://mikemcl.github.io/decimal.js/ | decimal.js | decimal.js

## 7.5 DateTime и часовые пояса | short: Даты и пояса | est: ~40 мин
### intro
**Слова шага:** *`Date`*, *момент времени*, *`timestamptz`*, *`timestamp`*, *UTC*, *`Intl`*, *часовой пояс филиала*.

:::tip Если совсем просто
Момент времени одинаков для всех на планете: «полдень в Москве» и «19:00 во Владивостоке» — это **один и тот же миг**. Мы храним миг (в UTC), а **показываем** его по-разному: каждому филиалу — по его часам. Путаница начинается, когда в базе лежат «просто даты без пояса» — как наши брони.
:::

```ts
// src/lessons/07-dates.ts
import { prisma } from '../db.js'

// 1. Date в JS — это момент (миллисекунды с 1970 UTC); показать его можно в любом поясе
const moment = new Date('2026-03-29T00:30:00Z')
const fmt = (tz: string) => moment.toLocaleString('ru-RU', { timeZone: tz, dateStyle: 'short', timeStyle: 'short' })
console.log('UTC:', moment.toISOString())
console.log('Москва:', fmt('Europe/Moscow'), '| Владивосток:', fmt('Asia/Vladivostok'))

// 2. что отдаёт база: timestamptz показывается в поясе сессии, Prisma всегда отдаёт Date (UTC)
const [r] = await prisma.$queryRaw<{ a: Date; b: Date }[]>`
  SELECT to_timestamp(1767225600) AS a, timestamp '2026-01-01 00:00' AS b`
console.log(r!.a.toISOString(), r!.b.toISOString())

// 3. unix-секунды из старых колонок: *1000, и это момент, а не «дата»
const withUnix = await prisma.booking.findFirst({ where: { startText: { gte: '1000000000', lte: '9999999999' } }, select: { id: true, startText: true } })
if (withUnix?.startText) {
  const d = new Date(Number(withUnix.startText) * 1000)
  console.log(withUnix.id, d.toISOString())
}
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/07-dates.ts
```

### result
```out auto
```

Три факта: (1) `Date` — всегда момент, у него нет «пояса»: пояс появляется только при форматировании (`toLocaleString`, `Intl`); (2) в PostgreSQL **`timestamptz`** хранит момент (внутри UTC) и показывает в поясе подключения; **`timestamp`** (без `tz`) — «голые» цифры часов, и Prisma сочтёт их **UTC**; (3) наши брони — **дни**: «1 декабря», без времени и пояса. «День» превращается в момент только после выбора пояса — пояса **филиала** (`tz` в `tbl_Branches`): полночь 1 декабря во Владивостоке и в Москве — разные моменты. Об этом сессия 10 (перевод дат) и сессия 13 (диапазоны броней).

### why
Ошибки времени проявляются редко и дорого: бронь «пропадает» на границе суток, возврат засчитывается «вчера», летнее/зимнее время сдвигает час. Если уже сейчас держать в голове разницу «момент ≠ день ≠ часы на стене», позже не придётся переписывать.

### deep Как ещё можно
Для «просто дней» (даты проката, дни рождения) в PostgreSQL есть тип `date` (в Prisma: `DateTime @db.Date`), у которого **нет** времени и пояса — правильное хранилище для «первого декабря». Для моментов (платёж, выдача) — `timestamptz`. Колонки типа `timestamp` без пояса лучше не использовать.

### deep Если не получилось
- **Вместо «Владивосток: …» ошибка про часовой пояс** — Node собран без ICU (редко): используй свежий Node 24 с полным ICU.
- **`withUnix` пуст** — в первых строках нет unix-формата; увеличь выборку или убери `where` и отфильтруй по `/^\d{10}$/` в JS.

### quiz
- Почему `Date` в JS не имеет часового пояса?
- В чём разница между `timestamptz` и `timestamp` в PostgreSQL?
- Почему «первое декабря» нельзя превратить в момент, не зная пояса филиала?

### links
- https://www.postgresql.org/docs/18/datatype-datetime.html | дата и время | PostgreSQL 18: Date/Time Types
- https://developer.mozilla.org/ru/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat | Intl.DateTimeFormat | MDN: Intl.DateTimeFormat

## 7.6 Типизированные ошибки: P2002, P2025, P2003 | short: Коды ошибок | est: ~50 мин
### intro
**Слова шага:** *`PrismaClientKnownRequestError`*, *`code`*, *`P2002` (дубль)*, *`P2025` (не найдено)*, *`P2003` (внешний ключ)*, *`meta`*, *доменная ошибка*.

:::tip Если совсем просто
Когда база говорит «нет», она говорит кодом: «нарушено уникальное», «не нашла», «нет такого ключа». Prisma превращает эти коды в свои (`P2002`, `P2025`…) и выбрасывает ошибку особого типа. Задача разработчика — **поймать** её и перевести на язык приложения: не «P2002: Unique constraint failed», а «предмет с таким кодом уже есть».
:::

Сначала сделаем `sku` уникальным (в наследстве он такой и есть, но не закреплён) — это реальное улучшение схемы, и повод попробовать миграцию:

```prisma
model Item {
  // …
  sku String? @unique @db.VarChar(30)
  // …
}
```

```bash run
cd ~/prisma-lab/rentkit
npx prisma migrate dev --name item_sku_unique
npx prisma generate
```

### result
```out auto
```

Теперь функции с переводом ошибок:

```ts
// src/lib/errors.ts
import { Prisma } from '../generated/prisma/client.js'

export class NotFoundError extends Error { constructor(what: string) { super(`${what}: не найдено`) } }
export class DuplicateError extends Error { constructor(public fields: string[]) { super(`Уже существует: ${fields.join(', ')}`) } }

export function mapDbError(e: unknown): never {
  if (e instanceof Prisma.PrismaClientKnownRequestError) {
    if (e.code === 'P2002') throw new DuplicateError((e.meta?.target as string[] | undefined) ?? [])
    if (e.code === 'P2025') throw new NotFoundError(String(e.meta?.cause ?? 'запись'))
  }
  throw e
}
```

```ts
// src/data/items.ts
import { prisma } from '../db.js'
import { mapDbError } from '../lib/errors.js'

export async function createItem(sku: string, title: string, branchId: number) {
  try {
    return await prisma.item.create({ data: { sku, title, branchId, category: 'Тест', active: 1 } })
  } catch (e) {
    mapDbError(e)
  }
}

export async function renameItem(id: number, title: string) {
  try {
    return await prisma.item.update({ where: { id }, data: { title } })
  } catch (e) {
    mapDbError(e)
  }
}
```

```ts
// src/lessons/07-errors.ts
import assert from 'node:assert/strict'
import { createItem, renameItem } from '../data/items.js'
import { DuplicateError, NotFoundError } from '../lib/errors.js'
import { prisma } from '../db.js'

const a = await createItem('SKU-ERR-1', 'Ошибка 1', 1)
await assert.rejects(() => createItem('SKU-ERR-1', 'Дубль', 1), DuplicateError)
await assert.rejects(() => renameItem(99999999, 'нет'), NotFoundError)
console.log('ошибки переведены верно; id первого:', a?.id)
await prisma.item.deleteMany({ where: { sku: 'SKU-ERR-1' } })
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/07-errors.ts
```

### result
```out auto
```

Три кода, которые встречаются чаще всего: **`P2002`** — нарушено ограничение уникальности (`meta.target` — список полей); **`P2025`** — запись, которую обновляют/удаляют/подключают, не найдена; **`P2003`** — нарушен внешний ключ (родителя нет, либо у родителя есть дети) — возникает **при настоящих внешних ключах** в базе (сессия 11); пока у нас `relationMode = "prisma"`, похожие нарушения Prisma ловит сама (код `P2014`/`P2025` — **сверьтесь**). Полный справочник — раздел «Error reference» документации и наша справка.

### why
Ошибка базы — не «исключение, которое надо проглотить», а нормальный исход: клиент вводит существующий телефон, кладовщик заводит дубль, менеджер открывает уже удалённую бронь. Слой данных обязан превращать их в понятные приложению ответы. Паттерн «ловить `PrismaClientKnownRequestError`, смотреть `code`, бросать свой класс» — основа обработки ошибок во всём остальном курсе.

### deep Если не получилось
- **`e.meta?.target` пуст** — в Prisma 7 с адаптером поле `meta` может содержать другую структуру (**сверьтесь** по `console.log(e.meta)`): подстрой чтение под фактический вид.
- **`P2002` не срабатывает, дубль создан** — `unique` не применён миграцией: `npx prisma migrate status`.

### quiz
- Как отличить «дубль» от «не найдено» в коде по ошибке Prisma?
- Зачем превращать `P2002` в собственный класс ошибки?
- Когда в нашей базе появится код `P2003` и почему сейчас его нет?

### links
- https://www.prisma.io/docs/orm/v7/reference/error-reference | коды ошибок | Prisma 7: Error reference
- https://www.prisma.io/docs/orm/v7/prisma-client/debugging-and-troubleshooting/handling-exceptions-and-errors | обработка исключений | Prisma 7: Handling exceptions and errors

## 7.7 🔨 «Клиент создан дважды» и «цена потерялась» | short: 🔨 Дубль и Decimal | est: ~60 мин
### intro
**Слова шага:** *гонка «проверить, потом создать»*, *`unique`*, *`upsert` и атомарность*, *`number` вместо `Decimal`*, *потеря копеек*.

:::tip Если совсем просто
Две кассирши одновременно спрашивают «есть ли у нас клиент с таким телефоном?» — обе слышат «нет» — и обе заводят. Пока между «проверить» и «создать» есть зазор, гонка возможна. Закрыть её может только база — ограничением уникальности.
:::

*Заказчик:* «Два раза создался один предмет с одинаковым кодом, а в сводке платежей копейки не сходятся с банком».

**Часть 1: дубль.** Воспроизведи гонку на таблице без ограничения — на клиентах (у них `phone` не уникален):

```ts
// src/lessons/07-race.ts
import { prisma } from '../db.js'

async function ensureCustomer(phone: string) {
  const found = await prisma.customer.findFirst({ where: { phone } })   // 1. проверили
  if (found) return found
  return prisma.customer.create({ data: { name: 'Гонка', phone, branchId: 1 } })    // 2. создали
}

await Promise.all(Array.from({ length: 10 }, () => ensureCustomer('+79990001122')))
const n = await prisma.customer.count({ where: { phone: '+79990001122' } })
console.log('создано клиентов с одним телефоном:', n)
await prisma.customer.deleteMany({ where: { phone: '+79990001122' } })
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/07-race.ts
```

### result
```out auto
```

Ожидаем число **больше одного**: десять «одновременных» вызовов все успели «проверить» до того, как кто-нибудь «создал». Так и родились девять тысяч дублей в наследстве. Исправление зависит от того, **есть ли ограничение**: когда оно есть (как `Item.sku`), проигравшие получают **`P2002`**, который мы ловим и переводим в «уже есть»; когда нет — гонку не закрыть вообще. Для клиентов ограничение `unique` по нормализованному телефону мы поставим в сессии 11, **после** слияния дублей (нельзя добавить `unique` в таблицу, где дубли уже есть).

**Часть 2: потерянные копейки.** В шаге 7.4 ты видела расхождение суммы `number` и `Decimal`. Найди в базе платёж, где расхождение особенно заметно, и **почини функцию** `sumPayments(ids)`, которая сейчас делает:

```ts
// src/lessons/07-money.ts — плохая версия
export async function sumPayments(bookingIds: number[]) {
  const rows = await prisma.payment.findMany({ where: { bookingId: { in: bookingIds } }, select: { amount: true } })
  return rows.reduce((s, r) => s + (r.amount ?? 0), 0)        // number!
}
```

Задание: перепиши так, чтобы результат был `Prisma.Decimal` с точностью до копейки, и покажи, на каких данных старая версия ошибается (подбери набор броней, где `number` и `Decimal` расходятся на копейку и более). Подсказка про способ — в «Если не получилось».

**Приёмка сессии:** набор функций записи (`createItem`, `renameItem`, …) переводит коды `P2002` и `P2025` в доменные ошибки (проверено скриптом с `assert.rejects`); `Item.sku` уникален (миграция применена); в `NOTES.md` — описание гонки «проверить–создать» и функция `sumPayments` на `Decimal`.

### why
Обе поломки — про одну идею: **то, что нельзя гарантировать в коде, гарантирует база**. Гонку закрывает ограничение уникальности, неточность денег закрывает точный тип. Если полагаться на «проверку перед записью» и на `number` для денег, рано или поздно ночью это сломается.

### deep Если не получилось
- **Часть 1 не воспроизводится (создан один клиент)** — запросы выполнились подряд из-за малой задержки; увеличь число параллельных вызовов до 50 или добавь `await new Promise(r => setTimeout(r, 5))` между проверкой и созданием.
- **Подсказка к части 2:** сумма берётся методом `Decimal.plus` в цикле (`rows.reduce((s, r) => s.plus(r.amount ?? 0), new Prisma.Decimal(0))`), а сравни результат с `SELECT sum(amount::numeric(12,2))` в `psql` — копейки должны совпасть.
- **`Decimal` не принимает `null`** — приведи `r.amount ?? 0` перед `plus`.

### quiz
- Почему «проверить, а потом создать» не защищает от дубля и что защищает?
- Почему нельзя поставить `unique` на телефон прямо сейчас?
- Что именно ломается, когда деньги суммируются как `number`?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/queries/crud#upsert | upsert | Prisma 7: Upsert
