# Сессия 12 · Транзакции и гонки
dur: ~4 ч

## 12.1 $transaction: пакетная и интерактивная | short: Два вида транзакций | est: ~40 мин
### intro
**Слова шага:** *транзакция*, *`$transaction([…])`*, *интерактивная `$transaction(async (tx) => …)`*, *`tx`*, *`timeout`*, *`maxWait`*, *откат*.

:::tip Если совсем просто
Транзакция — «всё или ничего»: ты записываешь несколько вещей, и либо записалось всё, либо ничего (как перевод денег: списали **и** зачислили, или оба действия отменены). У Prisma два вида: **пакетная** (заранее известный список запросов отправили вместе) и **интерактивная** (внутри ты читаешь, думаешь и решаешь, что писать дальше).
:::

```ts
// src/lessons/12-tx.ts
import { prisma } from '../db.js'

// 1. пакетная: список заранее известных операций — одной транзакцией
const [c1, c2] = await prisma.$transaction([
  prisma.customer.create({ data: { name: 'Пакет А', phone: '+70000000001', branchId: 1 } }),
  prisma.customer.create({ data: { name: 'Пакет Б', phone: '+70000000002', branchId: 1 } }),
])
console.log('создано:', c1.id, c2.id)

// 2. интерактивная: читаем, решаем, пишем — всё внутри одной транзакции (через tx, не prisma!)
const result = await prisma.$transaction(async (tx) => {
  const a = await tx.customer.findUniqueOrThrow({ where: { id: c1.id } })
  const b = await tx.customer.findUniqueOrThrow({ where: { id: c2.id } })
  if (a.branchId !== b.branchId) throw new Error('филиалы не совпали')      // исключение → откат всей транзакции
  return tx.customer.update({ where: { id: a.id }, data: { name: a.name + ' (+ ' + b.name + ')' } })
}, { maxWait: 2000, timeout: 5000 })
console.log(result.name)

// 3. откат: исключение внутри транзакции отменяет ВСЕ её записи
await prisma.$transaction(async (tx) => {
  await tx.customer.update({ where: { id: c1.id }, data: { name: 'не должно сохраниться' } })
  throw new Error('падаем нарочно')
}).catch((e) => console.log('откат:', e.message))
console.log((await prisma.customer.findUniqueOrThrow({ where: { id: c1.id } })).name)

await prisma.customer.deleteMany({ where: { id: { in: [c1.id, c2.id] } } })
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
SQL_LOG=1 npx tsx src/lessons/12-tx.ts 2>&1 | grep -E 'BEGIN|COMMIT|ROLLBACK|^\w' | head -16
```

### result
```out auto
```

В логе видны `BEGIN` … `COMMIT` у обеих транзакций и `ROLLBACK` у третьей. Разница видов:

| | пакетная `$transaction([…])` | интерактивная `$transaction(async tx => …)` |
|---|---|---|
| Когда | набор операций известен заранее | нужно читать и ветвиться внутри |
| Как | массив запросов Prisma | функция с `tx` (клиент транзакции) |
| Откат | ошибка любого запроса | **любое исключение** в функции |
| Цена | короткая, одна поездка по сети | **держит соединение** всё время работы функции |

Правила интерактивной: (1) внутри — **только `tx`**, не `prisma` (иначе запрос уйдёт вне транзакции); (2) **ничего долгого внутри** (HTTP-вызовы, отправка писем, `sleep`): транзакция держит соединение из пула; (3) у неё есть **`maxWait`** (сколько ждать свободного соединения, по умолчанию 2000 мс) и **`timeout`** (сколько может длиться, по умолчанию 5000 мс); по истечении — откат.

### why
Транзакции — главная причина, ради которой база данных вообще существует. Но у них своя цена: интерактивная транзакция — это занятое соединение и удерживаемые блокировки. Поэтому правило «короткая транзакция, только работа с базой» — не стиль, а условие, при котором система живёт под нагрузкой.

### deep Под капотом
Во вложенной записи (шаг 7.2) Prisma сама открывает такую транзакцию. А явная интерактивная нужна, когда решение зависит от прочитанного: «если баланс достаточен — списать». Именно в таких местах рождаются гонки (шаг 12.2).

### deep Если не получилось
- **`Transaction already closed`** — функция выполнялась дольше `timeout` или внутри использован `prisma`, а не `tx`, и транзакция закончилась раньше последнего запроса.
- **Откат не сработал** — исключение было перехвачено внутри функции (`try/catch` без повторного выброса): транзакция считает, что всё хорошо.

### quiz
- Чем пакетная транзакция отличается от интерактивной и когда нужна каждая?
- Почему внутри интерактивной транзакции нельзя использовать `prisma`, а только `tx`?
- Что делают `maxWait` и `timeout`?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/queries/transactions | транзакции | Prisma 7: Transactions

## 12.2 Потерянное обновление: гонка на счётчике | short: Потерянное обновление | est: ~50 мин
### intro
**Слова шага:** *гонка (race condition)*, *потерянное обновление*, *`READ COMMITTED`*, *читать-изменить-записать*, *бонусные баллы*.

:::tip Если совсем просто
Двое кассиров одновременно начисляют клиенту бонус. Оба смотрят в журнал: «было 100». Один пишет «110», другой тоже «110». Итог: 110, а должно быть 120 — один бонус потерялся. Каждый действовал правильно, но «посмотрел, посчитал, записал» не защищено от того, что между этими шагами кто-то ещё успел вклиниться.
:::

```svg
@lost-update
```

В PostgreSQL-лабе (сессия 5) ты видела это на `pgbench`. Теперь повторим через Prisma. Заведём клиенту счётчик баллов и версию (понадобится в 12.3):

```prisma schema
model Customer {
  // …поля как раньше…
  bonusPoints Int @default(0) @map("bonus_points")
  version     Int @default(0)
}
```

```bash run
cd ~/prisma-lab/rentkit
npx prisma migrate dev --name customer_points_version
npm run generate
```

### result
```out auto
```

Теперь гонка:

```ts
// src/lessons/12-race.ts
import { prisma } from '../db.js'

const c = await prisma.customer.create({ data: { name: 'Гонка баллов', phone: '+70000000100', branchId: 1 } })

// «читать — изменить — записать» в 50 параллельных вызовах
async function addPointsNaive(id: number, points: number) {
  const cur = await prisma.customer.findUniqueOrThrow({ where: { id } })     // 1. прочитали
  await prisma.customer.update({ where: { id }, data: { bonusPoints: cur.bonusPoints + points } })   // 2. записали «старое + points»
}

await Promise.all(Array.from({ length: 50 }, () => addPointsNaive(c.id, 10)))
const after = await prisma.customer.findUniqueOrThrow({ where: { id: c.id } })
console.log('ожидалось 500, получено', after.bonusPoints, '— потеряно', 500 - after.bonusPoints)
await prisma.customer.delete({ where: { id: c.id } })
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/12-race.ts
```

### result
```out auto
```

Ожидаем число **заметно меньше 500** (сколько именно — случайно, при каждом запуске иное): часть обновлений «затёрта» другими. Заметь, что код **выглядит правильно** — и именно поэтому такие ошибки живут в продакшне годами: они проявляются только под параллельной нагрузкой.

### why
Потерянное обновление — первая гонка, которую встречает каждый, кто пишет бэкенд. Она не вызывается «плохими программистами»: достаточно двух запросов в одно время. Понимать механику («между чтением и записью есть щель») — основа всего остального в этой сессии.

### deep Почему база не защитила
Уровень изоляции по умолчанию в PostgreSQL — `READ COMMITTED`: каждый запрос видит данные, зафиксированные к моменту **этого запроса**. Первые 50 `SELECT`-ов видят «100» до того, как кто-то записал «110» — это допустимо на этом уровне. Защищать нужно самой: три способа в шаге 12.3.

### deep Если не получилось
- **Результат ровно 500** — запросы выполнились последовательно из-за малой нагрузки; увеличь число параллельных вызовов до 200 или добавь `await new Promise(r => setTimeout(r, 5))` между чтением и записью.
- **`bonus_points` не существует** — миграция не применена (`migrate status`).

### quiz
- Почему «прочитал, прибавил, записал» теряет обновления при параллельных запросах?
- На каком уровне изоляции по умолчанию работает PostgreSQL и почему он не защищает?
- Почему такие ошибки долго остаются незамеченными?

### links
- https://www.postgresql.org/docs/18/transaction-iso.html | уровни изоляции | PostgreSQL 18: Transaction Isolation

## 12.3 Три способа починки: атомарный increment, версия, FOR UPDATE | short: Починка гонки | est: ~55 мин
### intro
**Слова шага:** *атомарная операция*, *`increment`*, *оптимистичная блокировка*, *поле `version`*, *пессимистичная блокировка*, *`SELECT … FOR UPDATE`*.

:::tip Если совсем просто
Три способа убрать щель. **(1) Не читать вовсе:** сказать базе «прибавь 10» — она сама пересчитает за один шаг. **(2) Проверить версию:** «запиши, только если за это время никто не менял»; если менял — перечитай и повтори. **(3) Закрыть дверь:** «пока я работаю с этой строкой, никто другой её не трогает».
:::

```ts
// src/lessons/12-fix.ts
import { Prisma } from '../generated/prisma/client.js'
import { prisma } from '../db.js'
import { timed } from '../lib/timed.js'

// способ 1: атомарный increment — значение пересчитывается в базе
async function viaIncrement(id: number, points: number) {
  await prisma.customer.update({ where: { id }, data: { bonusPoints: { increment: points } } })
}

// способ 2: оптимистичная блокировка — «если версия не изменилась»
async function viaVersion(id: number, points: number) {
  for (;;) {
    const cur = await prisma.customer.findUniqueOrThrow({ where: { id } })
    const { count } = await prisma.customer.updateMany({
      where: { id, version: cur.version },                       // условие на версию
      data: { bonusPoints: cur.bonusPoints + points, version: { increment: 1 } },
    })
    if (count === 1) return                                      // успели
    // count === 0 → кто-то опередил: перечитываем и пробуем снова
  }
}

// способ 3: пессимистичная блокировка — FOR UPDATE внутри транзакции
async function viaLock(id: number, points: number) {
  await prisma.$transaction(async (tx) => {
    const rows = await tx.$queryRaw<{ bonus_points: number }[]>`SELECT bonus_points FROM "tbl_Customers" WHERE id = ${id} FOR UPDATE`
    await tx.customer.update({ where: { id }, data: { bonusPoints: rows[0]!.bonus_points + points } })
  })
}

for (const [name, fn] of [['increment', viaIncrement], ['версия', viaVersion], ['FOR UPDATE', viaLock]] as const) {
  const c = await prisma.customer.create({ data: { name: 'Баллы ' + name, phone: '+7000000020' + name.length, branchId: 1 } })
  await timed(`${name.padEnd(12)} (50 параллельных)`, () => Promise.all(Array.from({ length: 50 }, () => fn(c.id, 10))))
  const after = await prisma.customer.findUniqueOrThrow({ where: { id: c.id } })
  console.log('  баллов:', after.bonusPoints, after.bonusPoints === 500 ? 'OK' : '← ПОТЕРИ')
  await prisma.customer.delete({ where: { id: c.id } })
}
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/12-fix.ts
```

### result
```out auto
```

Во всех трёх случаях должно быть **ровно 500**. Сравнение способов:

| | атомарный `increment` | оптимистичная версия | `FOR UPDATE` |
|---|---|---|---|
| Идея | «пересчитай в базе» | «проверь, что не менялось, иначе повтори» | «закрой строку, пока работаю» |
| Скорость | лучшая | хорошая при редких конфликтах; при частых — много повторов | хуже: очередь на строку |
| Когда | **числа**: счётчики, суммы, остатки | **сложная логика** над прочитанным; нужно «увидеть» значение | сложная логика + высокий конфликт, строка одна |
| Минус | не подходит, если решение зависит от прочитанного | нужен `version` и цикл повтора | блокировки, риск дедлока (шаг 12.7) |

Первое правило выбора — **если можно выразить операцию атомарно (`increment`, `decrement`), делай так.** Остальные — когда решение зависит от значений, которые нужно прочитать.

### why
Это три базовых инструмента против гонок, и вся остальная защита (Serializable, уникальные индексы, advisory locks) — их варианты. Умение выбрать способ по задаче — часть профессионального вкуса: атомарная операция проста и быстра, но универсальной не бывает.

### deep Команды по частям
`updateMany({ where: { id, version: cur.version }, data: {…} })` возвращает `{ count }`: `1` — обновили, `0` — условие не выполнилось (версия уже другая). Использован `updateMany`, а не `update`, потому что `update` при несовпадении условия бросил бы `P2025`, а нам нужен **счётчик**. `SELECT … FOR UPDATE` блокирует выбранные строки **до конца транзакции**: другие транзакции, желающие их менять или тоже блокировать, ждут.

### deep Если не получилось
- **Везде 500, но «версия» очень медленная** — при 50 параллельных на одну строку конфликтов много: для такой частоты лучше `increment`.
- **`FOR UPDATE` в `$queryRaw` ругается на тип** — нужно `$queryRaw<{…}[]>` с типом; `bonus_points` — `number`.

### quiz
- Почему `increment` не теряет обновления, а «прочитать-прибавить-записать» теряет?
- Как работает оптимистичная блокировка и что означает `count === 0`?
- Когда `FOR UPDATE` предпочтительнее версии?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/queries/transactions#optimistic-concurrency-control | оптимистичный контроль | Prisma 7: Optimistic concurrency control
- https://www.postgresql.org/docs/18/explicit-locking.html#LOCKING-ROWS | блокировки строк | PostgreSQL 18: Row-Level Locks

## 12.4 Serializable и повтор по P2034 | short: Serializable и retry | est: ~55 мин
### intro
**Слова шага:** *`Serializable`*, *write skew*, *ошибка сериализации (`40001`)*, *`P2034`*, *повтор транзакции*, *экспоненциальная пауза*.

:::tip Если совсем просто
Бывает гонка, которую не поймать ни `increment`, ни `FOR UPDATE`: решение зависит сразу от нескольких строк. «У клиента не больше пяти черновиков брони»: два запроса одновременно считают «четыре» и оба создают пятый — итого шесть. `Serializable` — самый строгий режим: база притворяется, что транзакции шли **строго по очереди**, и если не может — **отменяет одну** с ошибкой сериализации. А ты просто **повторяешь** отменённую.
:::

Правило «не больше пяти черновиков» — инвариант, зависящий от **подсчёта** нескольких строк. Сначала без защиты:

```ts
// src/lessons/12-skew.ts
import { Prisma, } from '../generated/prisma/client.js'
import { prisma } from '../db.js'

const LIMIT = 5
async function createDraft(customerId: number, isolation?: Prisma.TransactionIsolationLevel) {
  return prisma.$transaction(async (tx) => {
    const n = await tx.booking.count({ where: { customerId, status: 'DRAFT' } })
    if (n >= LIMIT) return false                                    // лимит
    await tx.booking.create({ data: { customerId, itemId: 1, branchId: 1, status: 'DRAFT', startsAt: new Date(), endsAt: new Date(Date.now() + 86_400_000) } })
    return true
  }, isolation ? { isolationLevel: isolation } : undefined)
}

const c = await prisma.customer.create({ data: { name: 'Лимит черновиков', phone: '+70000000300', branchId: 1 } })
await Promise.allSettled(Array.from({ length: 20 }, () => createDraft(c.id)))
console.log('без защиты, черновиков:', await prisma.booking.count({ where: { customerId: c.id, status: 'DRAFT' } }), '(лимит', LIMIT + ')')

await prisma.booking.deleteMany({ where: { customerId: c.id } })
await prisma.customer.delete({ where: { id: c.id } })
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/12-skew.ts
```

### result
```out auto
```

Ожидаем **больше пяти** — нарушение инварианта. Это **write skew**: транзакции читают одно и то же («четыре»), а пишут **разные** строки, поэтому ни `FOR UPDATE`, ни `increment` их не поймают. Включаем `Serializable` и повторы:

```ts
// src/lib/retry.ts
import { Prisma } from '../generated/prisma/client.js'

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

export async function withRetry<T>(fn: () => Promise<T>, tries = 6): Promise<T> {
  for (let attempt = 1; ; attempt++) {
    try {
      return await fn()
    } catch (e) {
      const conflict = e instanceof Prisma.PrismaClientKnownRequestError && e.code === 'P2034'
      if (!conflict || attempt >= tries) throw e
      await sleep(2 ** attempt * 10 + Math.random() * 25)        // пауза растёт и «дрожит», чтобы повторы не столкнулись снова
    }
  }
}
```

Теперь вызываем с `isolationLevel: Serializable` и обёрткой повтора (измени последние строки скрипта):

```bash run hidden
cd ~/prisma-lab/rentkit && node -e "
const fs=require('fs');const f='src/lessons/12-skew.ts';let s=fs.readFileSync(f,'utf8');
s=s.replace(\"import { prisma } from '../db.js'\",\"import { prisma } from '../db.js'\\nimport { withRetry } from '../lib/retry.js'\");
s=s.replace('() => createDraft(c.id)))','() =>\\n  withRetry(() => createDraft(c.id, Prisma.TransactionIsolationLevel.Serializable))))');
s=s.replace('без защиты, черновиков:','Serializable + retry, черновиков:');
fs.writeFileSync(f,s)"
```

```ts
import { withRetry } from '../lib/retry.js'
// …
await Promise.allSettled(Array.from({ length: 20 }, () =>
  withRetry(() => createDraft(c.id, Prisma.TransactionIsolationLevel.Serializable))))
console.log('Serializable + retry, черновиков:', await prisma.booking.count({ where: { customerId: c.id, status: 'DRAFT' } }))
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/12-skew.ts
```

### result
```out auto
```

Ожидаем ровно **5** (лимит соблюдён); часть вызовов в логе упала с `P2034` и была повторена. **Правила Serializable:** (1) он **не блокирует**, а **отменяет** конфликтующую транзакцию — поэтому повтор **обязателен**; (2) повторять нужно **всю транзакцию целиком**, а не последний запрос; (3) транзакция должна быть **идемпотентной** внутри повтора (без внешних побочных эффектов: писем, платежей во внешней системе); (4) `P2034` означает «write conflict or deadlock» — подходит и для дедлока, повторяют так же.

### why
Serializable — «страховка последней надежды»: когда инвариант зависит от нескольких строк и его не выразить ни ограничением, ни атомарной операцией. Платить за неё приходится повторами (и слегка пониженной пропускной способностью), зато логика остаётся **простой** — ты пишешь код так, как будто параллельности нет.

### deep Как ещё можно
Для инвариантов, которые можно выразить ограничением базы, это лучше: «не более N» часто решается уникальным индексом/триггером/блокировкой родителя (`FOR UPDATE` на клиенте, к которому относятся черновики). Serializable — когда лучше не получается.

### deep Если не получилось
- **Нет `P2034`, но и лимит не соблюдён** — для `Serializable` PostgreSQL может ошибаться «в безопасную сторону» (ложные конфликты), но никогда не пропускает нарушения; проверь, что передан именно `Serializable`.
- **Все повторы исчерпаны** — слишком много конфликтов: уменьши параллельность (20 → 5) или увеличь `tries`.

### quiz
- Что такое write skew и почему `FOR UPDATE` на одной строке его не решает?
- Почему при `Serializable` обязательна обёртка повтора?
- Что нужно учитывать в коде транзакции, которую повторяют?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/queries/transactions#transaction-isolation-level | уровни изоляции | Prisma 7: Transaction isolation level
- https://www.postgresql.org/docs/18/transaction-iso.html#XACT-SERIALIZABLE | Serializable | PostgreSQL 18: Serializable Isolation Level

## 12.5 timeout, maxWait и зависшая транзакция | short: Таймауты | est: ~40 мин
### intro
**Слова шага:** *`maxWait`*, *`timeout`*, *`P2028`*, *пул соединений*, *зависшая транзакция*, *`idle in transaction`*.

:::tip Если совсем просто
Интерактивная транзакция занимает «телефонную линию» (соединение из пула) на всё время. Если внутри неё ты пошла ждать ответ внешнего сервиса, линия занята, а у остальных клиентов очередь. Когда линий больше нет, новый звонок ждёт `maxWait` и затем сдаётся с ошибкой.
:::

Воспроизведём исчерпание пула (в пуле по умолчанию 10 соединений):

```ts
// src/lessons/12-pool.ts
import { prisma } from '../db.js'

const hold = () => prisma.$transaction(async (tx) => {
  await tx.booking.count()
  await new Promise((r) => setTimeout(r, 4000))     // «долгая работа» внутри транзакции — НЕЛЬЗЯ
}, { timeout: 10_000, maxWait: 1500 })

// 15 транзакций одновременно на пул из 10 соединений
const results = await Promise.allSettled(Array.from({ length: 15 }, hold))
const failed = results.filter((r) => r.status === 'rejected') as PromiseRejectedResult[]
console.log('успешно:', results.length - failed.length, ' упало:', failed.length)
console.log(failed[0]?.reason?.code, String(failed[0]?.reason?.message).split('\n')[0])
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/12-pool.ts
```

### result
```out auto
```

Ожидаем: успешно ≈ 10, упало ≈ 5 с кодом **`P2028`** (`Unable to start a transaction in the given time` — не дождались свободного соединения за `maxWait`). А с другой стороны (из `psql`) во время такой нагрузки видны сессии `idle in transaction`:

```bash run
cd ~/prisma-lab/rentkit
(npx tsx src/lessons/12-pool.ts > /tmp/pool.log 2>&1 &)
sleep 2
psqlr() { docker exec -i rental-pg psql -U postgres -d rental -c "$@"; }
psqlr "SELECT state, count(*) FROM pg_stat_activity WHERE datname = 'rental' GROUP BY 1 ORDER BY 2 DESC"
sleep 6
cat /tmp/pool.log
```

### result
```out auto
```

(Скрипт запущен в фоне, а `psql` смотрит на базу через две секунды — пока транзакции «работают»; у себя то же можно сделать в соседнем терминале.) Состояние **`idle in transaction`** — транзакция открыта, но ничего не делает: она держит блокировки и соединение. Это одно из самых вредных состояний в базе: прямое следствие «долгой работы внутри транзакции».

Три рычага защиты: (1) **не делать долгого внутри транзакции** (внешние вызовы — до или после); (2) **`timeout`** — максимальное время жизни транзакции; (3) на стороне базы — **`idle_in_transaction_session_timeout`** (параметр сервера, который сам оборвёт «застрявшую»); о таймаутах запросов — сессия 17.6.

### why
Исчерпание пула из-за транзакций — характерный отказ приложения под нагрузкой: «упало на 200-м запросе», хотя запросы лёгкие. Причина — не нагрузка, а транзакции, которые **удерживают** соединения. Понимание, что транзакция — **ресурс**, а не просто «обёртка», меняет стиль кода.

### deep Если не получилось
- **Упавших нет** — пул больше 10 или скрипт выполняется слишком быстро; увеличь число параллельных до 30 или сократи `maxWait`.
- **Код ошибки не `P2028`** — формулировка и код могут отличаться; смотри `failed[0].reason` целиком (**сверьтесь**).

### quiz
- Что означают `maxWait` и `timeout` у интерактивной транзакции?
- Почему «долгая работа внутри транзакции» опасна для всех остальных запросов?
- Что за состояние `idle in transaction` и чем оно вредно?

### links
- https://www.postgresql.org/docs/18/runtime-config-client.html#GUC-IDLE-IN-TRANSACTION-SESSION-TIMEOUT | idle_in_transaction_session_timeout | PostgreSQL 18: idle_in_transaction_session_timeout

## 12.6 Очередь выдачи на SKIP LOCKED | short: SKIP LOCKED | est: ~60 мин
### intro
**Слова шага:** *очередь задач в таблице*, *`FOR UPDATE SKIP LOCKED`*, *воркеры*, *идемпотентная выдача*, *журнал захватов*.

:::tip Если совсем просто
Несколько сотрудников разбирают очередь заявок «подготовить предмет к выдаче». Если все берут «первую в списке», они схватят одну и ту же. `SKIP LOCKED` — правило: «если заявка уже у кого-то в руках — **пропусти** её и бери следующую». Каждая заявка достаётся ровно одному, и никто не ждёт друг друга.
:::

Заведём очередь (таблицы без моделей Prisma не оставляем — добавим модели):

```prisma schema
model PickupJob {
  id        Int       @id @default(autoincrement())
  bookingId Int       @map("booking_id")
  state     String    @default("new")
  worker    String?
  takenAt   DateTime? @map("taken_at") @db.Timestamptz(3)
  @@index([state, id])
  @@map("pickup_job")
}

model JobClaimLog {
  id      Int    @id @default(autoincrement())
  jobId   Int    @map("job_id")
  worker  String
  @@map("job_claim_log")
}
```

```bash run
cd ~/prisma-lab/rentkit
npx prisma migrate dev --name pickup_queue
npm run generate
psqlr() { docker exec -i rental-pg psql -U postgres -d rental -c "$@"; }
psqlr "INSERT INTO pickup_job (booking_id) SELECT id FROM \"tbl_Bookings\" WHERE status = 'CONFIRMED' ORDER BY id LIMIT 2000"
psqlr "SELECT count(*) AS заданий FROM pickup_job WHERE state = 'new'"
```

### result
```out auto
```

Сначала **неправильные** воркеры — «взять первые десять, потом пометить»:

```ts
// src/lessons/12-queue.ts
import { prisma } from '../db.js'

async function claimNaive(worker: string) {
  const jobs = await prisma.pickupJob.findMany({ where: { state: 'new' }, orderBy: { id: 'asc' }, take: 10 })   // 1. посмотрели
  await prisma.pickupJob.updateMany({ where: { id: { in: jobs.map((j) => j.id) } }, data: { state: 'taken', worker, takenAt: new Date() } }) // 2. «взяли»
  await prisma.jobClaimLog.createMany({ data: jobs.map((j) => ({ jobId: j.id, worker })) })
  return jobs.length
}

// правильно: один запрос, блокировка строк с пропуском занятых, всё внутри UPDATE
async function claimSafe(worker: string) {
  const rows = await prisma.$queryRaw<{ id: number }[]>`
    UPDATE pickup_job SET state = 'taken', worker = ${worker}, taken_at = now()
    WHERE id IN (SELECT id FROM pickup_job WHERE state = 'new' ORDER BY id LIMIT 10 FOR UPDATE SKIP LOCKED)
    RETURNING id`
  await prisma.jobClaimLog.createMany({ data: rows.map((r) => ({ jobId: r.id, worker })) })
  return rows.length
}

async function run(label: string, claim: (w: string) => Promise<number>) {
  await prisma.$executeRaw`UPDATE pickup_job SET state = 'new', worker = NULL, taken_at = NULL`
  await prisma.jobClaimLog.deleteMany()
  await Promise.all(['A', 'B', 'C', 'D'].map(async (w) => { while ((await claim(w)) > 0) { /* пока есть что брать */ } }))
  const dup = await prisma.$queryRaw<{ n: bigint }[]>`SELECT count(*) AS n FROM (SELECT job_id FROM job_claim_log GROUP BY job_id HAVING count(*) > 1) t`
  const total = await prisma.jobClaimLog.count()
  console.log(label.padEnd(14), 'захватов:', total, ' заданий взяли дважды:', Number(dup[0]!.n))
}

await run('наивно', claimNaive)
await run('SKIP LOCKED', claimSafe)
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/12-queue.ts
```

### result
```out auto
```

Ожидаем: у наивных воркеров **дубли** (задания взяты дважды: захватов больше 2 000), у `SKIP LOCKED` — **ровно 2 000** захватов, ни одного дубля. Секрет — в подзапросе: `FOR UPDATE SKIP LOCKED` блокирует выбранные строки **и пропускает** те, что уже заблокированы другим воркером; `UPDATE … RETURNING` выполняется **одним** оператором, поэтому «посмотреть» и «взять» неделимы.

### why
Очередь в обычной таблице PostgreSQL — рабочий паттерн для тысяч задач в секунду, без отдельного брокера. Его основа — `SKIP LOCKED`; без него воркеры либо дублируют работу, либо стоят в очереди друг за другом. Это тот случай, где «знание SQL» напрямую превращается в архитектурное решение.

### deep Как ещё можно
При больших объёмах и сложной маршрутизации берут настоящий брокер (RabbitMQ — отдельная лаба сайта). Но для «пара тысяч задач в час» таблица с `SKIP LOCKED` проще, надёжнее (одна база, одна транзакционность) и дешевле в эксплуатации.

### deep Если не получилось
- **Дубли есть и у `SKIP LOCKED`** — `FOR UPDATE SKIP LOCKED` должен стоять в **подзапросе** внутри того же `UPDATE`; если сначала `SELECT`, потом `UPDATE` отдельно, снова щель.
- **Заданий меньше 2000** — в базе мало броней в статусе `CONFIRMED`; уменьши `LIMIT` или создай задания по другому признаку.

### quiz
- Что делает `SKIP LOCKED` и почему без него воркеры дублируют работу?
- Почему «выбрать» и «пометить» нужно выполнить одним оператором?
- Когда очередь в таблице подходит, а когда нужен брокер?

### links
- https://www.postgresql.org/docs/18/sql-select.html#SQL-FOR-UPDATE-SHARE | FOR UPDATE и SKIP LOCKED | PostgreSQL 18: The Locking Clause

## 12.7 🔨 Дедлок в двух параллельных бронированиях | short: 🔨 Дедлок | est: ~55 мин
### intro
**Слова шага:** *дедлок (взаимная блокировка)*, *порядок блокировок*, *`40P01`*, *`P2034`*, *стабильный порядок*.

:::tip Если совсем просто
Два человека проходят через две узкие двери друг навстречу. Первый занял дверь А и ждёт дверь Б, второй занял Б и ждёт А — оба застряли. База распознаёт тупик и «выгоняет» одного. Лекарство простое: все ходят через двери **в одном порядке** (сначала А, потом Б).
:::

*Заказчик:* «Иногда при одновременном переносе брони между двумя предметами одна из операций падает. Сообщение странное, а повторить — работает».

```ts
// src/lessons/12-deadlock.ts
import { prisma } from '../db.js'

// обновляем два предмета в одной транзакции; воркеры берут их в РАЗНОМ порядке
async function touch(first: number, second: number) {
  await prisma.$transaction(async (tx) => {
    await tx.item.update({ where: { id: first }, data: { active: 1 } })
    await new Promise((r) => setTimeout(r, 200))             // «работа» между двумя блокировками
    await tx.item.update({ where: { id: second }, data: { active: 1 } })
  })
}

const results = await Promise.allSettled([touch(1, 2), touch(2, 1)])
for (const r of results) {
  console.log(r.status, r.status === 'rejected' ? `${(r.reason as any).code}: ${String((r.reason as Error).message).trim().split('\n')[0]}` : '')
}
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/12-deadlock.ts
```

### result
```out auto
```

Ожидаем: одна транзакция успешна, другая отклонена с кодом **`P2034`** (в выводе после кода — только первая строка сообщения Prisma, `Invalid tx.item.update() invocation`; по документации код означает «write conflict or a deadlock») — база обнаружила взаимную блокировку (в логе PostgreSQL — `deadlock detected`, код `40P01`) и отменила одну. Повтор помогает (потому и «повторить — работает»), но лучше устранить причину.

**Твоя задача:** переписать `touch` так, чтобы дедлок был **невозможен**, а не просто повторялся. Условия: тот же результат, поведение для вызывающих то же. Покажи, что `Promise.allSettled([touch(1,2), touch(2,1)])` теперь всегда обе успешны (прогони 20 раз). Подсказка в «Если не получилось».

**Приёмка сессии:** нагрузка из 50 параллельных операций (начисление баллов, выдача, лимит черновиков) не даёт ни дублей, ни потерь (три способа из 12.3, Serializable с повтором из 12.4, очередь без дублей из 12.6); дедлок из 12.7 устранён стабильным порядком; в `NOTES.md` — таблица «задача → какой способ выбран и почему».

### why
Дедлоки не лечатся «повторами» навсегда: они — симптом того, что код берёт блокировки в произвольном порядке. Универсальное лекарство — **стабильный глобальный порядок**: всегда сортируй идентификаторы перед тем, как их блокировать. Тогда цикл ожидания образоваться не может. Повтор (`withRetry`) остаётся подстраховкой.

### deep Если не получилось
- **Подсказка:** сортируй `[first, second]` по возрастанию и обновляй в таком порядке — независимо от того, в каком порядке их передали.
- **Или:** обнови оба предмета одним запросом: `tx.item.updateMany({ where: { id: { in: [first, second] } }, data: { active: 1 } })` — база сама берёт блокировки в своём порядке и дедлока между двумя такими запросами нет.
- **Результат не воспроизводится** — пауза слишком короткая; увеличь `setTimeout` до 500 мс.

### quiz
- Почему возникает дедлок и как его распознаёт база?
- Какой приём устраняет дедлок «в корне», а не повторами?
- Чем помогает единый запрос `updateMany` вместо двух `update`?

### links
- https://www.postgresql.org/docs/18/explicit-locking.html#LOCKING-DEADLOCKS | дедлоки | PostgreSQL 18: Deadlocks
- https://www.prisma.io/docs/orm/v7/reference/error-reference#p2034 | P2034 | Prisma 7: Error reference P2034
