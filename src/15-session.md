# Сессия 15 · Расширения клиента
dur: ~4 ч

## 15.1 Зачем расширения и из чего они состоят | short: Что такое $extends | est: ~35 мин
### intro
**Слова шага:** *`$extends`*, *расширение клиента*, *`query`*, *`result`*, *`model`*, *`client`*, *`Prisma.defineExtension`*, *замена middleware `$use`*.

:::tip Если совсем просто
Расширение — это «надстройка» над клиентом, как фильтр на объективе: клиент остаётся тем же, но каждый запрос теперь проходит через твой фильтр. Он может **перехватить запрос** (дописать условие, замерить время), **добавить поле** в результат (`isOverdue`), **добавить метод** модели (`booking.cancel()`) или метод самого клиента.
:::

```svg
@extension-layers
```

У расширения четыре «компонента» (можно использовать любые из них):

| Компонент | Что делает | Пример |
|---|---|---|
| **`query`** | перехватывает операции (`findMany`, `update`, …) и может менять аргументы и результат | soft delete, замер времени, повтор |
| **`result`** | добавляет **вычисляемые поля** к результатам модели | `isOverdue`, `days` |
| **`model`** | добавляет **свои методы** к модели | `prisma.booking.cancel(id)` |
| **`client`** | добавляет методы **всему клиенту** | `prisma.$asActor('anna')` |

Раньше для перехвата использовали middleware (`prisma.$use(...)`); в Prisma 7 его **нет** (проверено: `typeof prisma.$use` равно `undefined`) — всё делается расширениями. Каждый вызов `$extends` возвращает **новый клиент**, а исходный остаётся прежним — расширения можно **цеплять** друг за другом.

```ts
// src/lessons/15-hello.ts
import { Prisma } from '../generated/prisma/client.js'
import { prisma } from '../db.js'

const withHello = Prisma.defineExtension({
  name: 'hello',
  query: { $allModels: { async $allOperations({ model, operation, args, query }) {
    console.log(`→ ${model}.${operation}`)
    return query(args)                      // выполнить сам запрос
  } } },
})

const db = prisma.$extends(withHello)
await db.branch.findMany({ take: 1 })
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/15-hello.ts
```

### result
```out auto
```

`query(args)` — вызов исходной операции; всё, что до него, — перехват «на входе», всё, что после, — «на выходе». `Prisma.defineExtension` оформляет расширение отдельным **переиспользуемым** модулем (с именем — оно видно в сообщениях об ошибках).

### why
Расширения — центральное место для **сквозных** требований: фильтр удалённых, аудит, замеры, права. Без них каждое требование пришлось бы повторять в каждой функции слоя данных — и, как всегда с повторением, где-то забыть.

### deep Как ещё можно
Расширения могут быть **общими** для проектов (пакеты `@prisma/…`/сторонние: кеш, шифрование полей, RBAC). Раздел «Shared extensions» документации перечисляет готовые; здесь пишем свои, чтобы понять механику.

### deep Если не получилось
- **`prisma.$use is not a function`** — в Prisma 7 middleware нет: используй `$extends` с компонентом `query`.
- **Запросы не печатаются** — вызвала исходный `prisma`, а не расширенный `db`: расширение возвращает **новый** клиент.

### quiz
- Назови четыре компонента расширения и что делает каждый.
- Почему `$extends` возвращает новый клиент, а не меняет существующий?
- Для чего нужен вызов `query(args)` внутри перехватчика?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/client-extensions | расширения клиента | Prisma 7: Client extensions
- https://www.prisma.io/docs/orm/v7/prisma-client/client-extensions/query | компонент query | Prisma 7: query extension

## 15.2 query: замеряем время и логируем медленные запросы | short: Замеры в query | est: ~40 мин
### intro
**Слова шага:** *`$allOperations`*, *`$allModels`*, *замер*, *медленный запрос*, *счётчик запросов*, *повтор (`retry`)*.

:::tip Если совсем просто
Вместо того чтобы вешать секундомер на каждую функцию, повесим один на **дверь** — любой запрос проходит мимо и фиксируется: сколько заняло, какая модель, какая операция. Заодно получаем счётчик запросов для проверки N+1 (шаг 6.3).
:::

```ts
// src/extensions/timing.ts
import { Prisma } from '../generated/prisma/client.js'

export type QueryStats = { count: number; totalMs: number; slow: { op: string; ms: number }[] }

export function timing(stats: QueryStats, slowMs = 100) {
  return Prisma.defineExtension({
    name: 'timing',
    query: {
      $allModels: {
        async $allOperations({ model, operation, args, query }) {
          const t0 = performance.now()
          try {
            return await query(args)
          } finally {
            const ms = performance.now() - t0
            stats.count++
            stats.totalMs += ms
            if (ms > slowMs) stats.slow.push({ op: `${model}.${operation}`, ms: Math.round(ms) })
          }
        },
      },
    },
  })
}
```

```ts
// src/lessons/15-timing.ts
import { prisma } from '../db.js'
import { timing, type QueryStats } from '../extensions/timing.js'

const stats: QueryStats = { count: 0, totalMs: 0, slow: [] }
const db = prisma.$extends(timing(stats, 20))

await db.booking.findMany({ take: 200, include: { customer: true } })            // 2 запроса
await db.customer.findMany({ where: { name: { contains: 'иван', mode: 'insensitive' } }, take: 5 })
await db.booking.count({ where: { note: { contains: 'продлить' } } })           // медленный: Seq Scan
console.log({ count: stats.count, totalMs: Math.round(stats.totalMs), slow: stats.slow })
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/15-timing.ts
```

### result
```out auto
```

Ожидаем: `count` = 3 (расширение видит **операции Prisma**, а не SQL — `include` считается одной операцией), в `slow` — операция, которая дольше 20 мс. Именно здесь удобно держать **счётчик для тестов**: «эта функция делает не больше N операций» (шаг 18.2). Отличие от лога запросов (5.5): расширение видит уровень **операций** и **аргументов**, лог — уровень SQL.

### why
Замеры «на двери» дают единую точку наблюдения без правки десятков функций: можно выводить в лог, отправлять в метрики, предупреждать о медленных запросах. Это основа наблюдаемости (шаг 18.5).

### deep Как ещё можно
Через `query` можно реализовать **повтор** операций по `P2034` (шаг 12.4), но делай это осторожно: повторять нужно **транзакцию целиком**, а перехватчик на уровне одной операции этого не знает. Повтор лучше оставить явной обёрткой `withRetry`.

### deep Если не получилось
- **`count` равен 0** — запросы шли через исходный `prisma`, а не через `db`.
- **`slow` пуст** — порог слишком высок; уменьши `slowMs` до 5.

### quiz
- Чем замер в расширении отличается от лога запросов Prisma?
- Почему `finally` в перехватчике — правильное место для замера?
- Почему повтор по `P2034` нельзя надёжно делать в перехватчике одной операции?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/client-extensions/query | query | Prisma 7: query extension

## 15.3 Soft delete: «удалено», но не стёрто | short: Soft delete | est: ~55 мин
### intro
**Слова шага:** *soft delete*, *`deletedAt`*, *фильтр «живых»*, *перехват `findMany`/`findFirst`/`count`*, *запрет настоящего `delete`*, *метод `softDelete`*.

:::tip Если совсем просто
В корзине Windows файл не стёрт, а лишь помечен «удалён» — его можно вернуть. «Мягкое удаление» делает то же с данными: вместо `DELETE` ставим отметку `deletedAt`, а все остальные запросы **не показывают** помеченное. Достоинство — ничего не теряется и история ссылается на «удалённого» клиента без обрывов. Риск — **забыть фильтр** в каком-нибудь запросе: тогда «удалённое» вернётся.
:::

Добавим колонку клиентам и предметам:

```prisma schema
model Customer {
  // …поля как раньше…
  deletedAt DateTime? @map("deleted_at") @db.Timestamptz(3)
  @@index([deletedAt])
}
model Item {
  // …поля как раньше…
  deletedAt DateTime? @map("deleted_at") @db.Timestamptz(3)
  @@index([deletedAt])
}
```

```bash run
cd ~/prisma-lab/rentkit
npx prisma migrate dev --name soft_delete_columns
npm run generate
```

### result
```out auto
```

Расширение: **автоматически** добавляет условие «`deletedAt` пуст» ко всем чтениям этих моделей и **запрещает настоящий `delete`**:

```ts
// src/extensions/soft-delete.ts
import { Prisma } from '../generated/prisma/client.js'

const SOFT_MODELS = new Set(['Customer', 'Item'])

// добавить «живость» к условию, сохранив прочие условия вызывающего
const alive = (args: any) => ({ ...args, where: { ...(args?.where ?? {}), deletedAt: null } })

export const softDelete = Prisma.defineExtension({
  name: 'softDelete',
  query: {
    $allModels: {
      async findMany({ model, args, query }) { return query(SOFT_MODELS.has(model) ? alive(args) : args) },
      async findFirst({ model, args, query }) { return query(SOFT_MODELS.has(model) ? alive(args) : args) },
      async findFirstOrThrow({ model, args, query }) { return query(SOFT_MODELS.has(model) ? alive(args) : args) },
      async findUnique({ model, args, query }) { return query(SOFT_MODELS.has(model) ? alive(args) : args) },
      async findUniqueOrThrow({ model, args, query }) { return query(SOFT_MODELS.has(model) ? alive(args) : args) },
      async count({ model, args, query }) { return query(SOFT_MODELS.has(model) ? alive(args) : args) },
      async aggregate({ model, args, query }) { return query(SOFT_MODELS.has(model) ? alive(args) : args) },
      async groupBy({ model, args, query }) { return query(SOFT_MODELS.has(model) ? alive(args) : args) },
      async delete({ model, args, query }) {
        if (SOFT_MODELS.has(model)) throw new Error(`${model}: настоящее удаление запрещено, используйте softDelete()`)
        return query(args)
      },
      async deleteMany({ model, args, query }) {
        if (SOFT_MODELS.has(model)) throw new Error(`${model}: настоящее удаление запрещено`)
        return query(args)
      },
    },
  },
  model: {
    customer: {
      async softDelete(id: number) {
        const ctx = Prisma.getExtensionContext(this)
        return (ctx as any).update({ where: { id }, data: { deletedAt: new Date() } })
      },
    },
  },
})
```

```ts
// src/lessons/15-soft.ts
import { prisma } from '../db.js'
import { softDelete } from '../extensions/soft-delete.js'

const db = prisma.$extends(softDelete)
const c = await db.customer.create({ data: { name: 'Мягко удаляемый', phone: '+70000000400', branchId: 1 } })
console.log('живых с этим id:', await db.customer.count({ where: { id: c.id } }))        // 1
await db.customer.softDelete(c.id)
console.log('после softDelete :', await db.customer.count({ where: { id: c.id } }))        // 0
console.log('findUnique       :', await db.customer.findUnique({ where: { id: c.id } }))   // null
console.log('«настоящая» база :', await prisma.customer.count({ where: { id: c.id } }))    // 1: строка на месте
await db.customer.delete({ where: { id: c.id } }).catch((e) => console.log('delete →', e.message))
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/15-soft.ts
```

### result
```out auto
```

Ожидаем: `1 → 0 → null`, а через исходный `prisma` строка видна (`1`), и настоящий `delete` отвергнут. **Всё работает без правок остального кода**: любой `db.customer.findMany(...)` сам станет «только живые». Именно в этом ценность перехвата — и в этом же риск: перехват охватывает **только то, что мы перечислили**. Что осталось за кадром — шаг 15.7.

### why
Мягкое удаление — требование любой системы, где клиентов нельзя «стереть» (бухгалтерия, юридические сроки хранения, ссылки из старых платежей). Расширение делает его **единым правилом** вместо сотни `where: { deletedAt: null }`, которые рано или поздно кто-то забудет написать.

### deep Команды по частям
`Prisma.getExtensionContext(this)` — достаёт модель, к которой относится метод (нужно, чтобы вызвать `update` из метода модели). `findUnique` с дополнительным условием `deletedAt: null` работает, потому что Prisma разрешает к уникальному ключу добавлять **неуникальные фильтры** (расширенный `where` для `findUnique`). Метод `softDelete` описан в `model: { customer: … }` — ключ — имя модели **с маленькой буквы**.

### deep Если не получилось
- **`Type … deletedAt does not exist`** — клиент не пересоздан после миграции: `npm run generate`.
- **`softDelete is not a function`** — метод вызван у исходного `prisma`, а не у расширенного `db`.

### quiz
- Чем soft delete лучше настоящего удаления и какой у него главный риск?
- Почему расширение запрещает `delete` для мягко удаляемых моделей?
- Что даёт `Prisma.getExtensionContext(this)` внутри метода модели?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/client-extensions/model | компонент model | Prisma 7: model extension
- https://www.prisma.io/docs/orm/v7/prisma-client/client-extensions/shared-extensions | готовые расширения | Prisma 7: Shared extensions

## 15.4 result: вычисляемые поля | short: Вычисляемые поля | est: ~40 мин
### intro
**Слова шага:** *`result`*, *`needs`*, *`compute`*, *вычисляемое поле*, *`isOverdue`*, *`days`*, *типизация вычисляемых полей*.

:::tip Если совсем просто
Иногда нужно показывать то, чего в таблице нет, но что вытекает из её полей: «брони просрочена?» (конец позже текущей даты **и** статус «выдана»), «сколько дней». Вместо того чтобы считать это в каждом месте, объявим **вычисляемое поле**: оно будет появляться в результатах запросов, как обычная колонка, и будет типизировано.
:::

```ts
// src/extensions/computed.ts
import { Prisma } from '../generated/prisma/client.js'

const DAY = 86_400_000

export const computed = Prisma.defineExtension({
  name: 'computed',
  result: {
    booking: {
      days: {
        needs: { startsAt: true, endsAt: true },                       // какие поля нужны для вычисления
        compute(b) { return b.startsAt && b.endsAt ? Math.round((b.endsAt.getTime() - b.startsAt.getTime()) / DAY) : null },
      },
      isOverdue: {
        needs: { endsAt: true, status: true },
        compute(b) { return b.status === 'ISSUED' && b.endsAt !== null && b.endsAt.getTime() < Date.now() },
      },
    },
    customer: {
      initials: {
        needs: { name: true },
        compute(c) { return (c.name ?? '').split(/\s+/).map((w) => w[0]?.toUpperCase() ?? '').join('') },
      },
    },
  },
})
```

```ts
// src/lessons/15-result.ts
import { prisma } from '../db.js'
import { computed } from '../extensions/computed.js'

const db = prisma.$extends(computed)
const b = await db.booking.findFirstOrThrow({ where: { status: 'ISSUED' }, select: { id: true, days: true, isOverdue: true } })
console.log(b)                                                           // тип: { id: number; days: number | null; isOverdue: boolean }
const c = await db.customer.findFirstOrThrow()
console.log(c.name, '→', c.initials)
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/15-result.ts
npm run typecheck
```

### result
```out auto
```

`days`, `isOverdue` и `initials` приходят в результате как обычные поля, **типизированы**, а их можно даже запрашивать в `select`. Важные детали: (1) поле **вычисляется на стороне клиента** при получении строки — в базе его нет, и **фильтровать по нему в `where` нельзя** (для этого условие пишется явно); (2) `needs` — список полей, которые подгружаются **автоматически**, если ты выбрала вычисляемое поле через `select`; (3) вычисление выполняется для **каждой** строки — не клади в `compute` тяжёлое.

### why
Вычисляемые поля убирают дублирование бизнес-логики: «просрочена ли бронь» определено в **одном** месте. Менеджеру, API и отчёту нужно одно и то же поведение. Как всегда с «единственным местом», его легко проверить тестом.

### deep Как ещё можно
Для того, что нужно фильтровать и сортировать (например, «просроченные»), вычисляемое поле не годится: используй явное условие или **представление/генерируемую колонку** в базе. Вычисляемое поле — для показа, не для запросов.

### deep Если не получилось
- **`isOverdue` всегда `false`** — статус не `ISSUED` или `endsAt` в будущем (демо-данные до 2026-09); создай бронь со статусом `ISSUED` и `endsAt` в прошлом.
- **`Property 'days' does not exist`** — используешь исходный `prisma`, а не `db`.

### quiz
- Для чего нужен `needs` в вычисляемом поле?
- Почему по вычисляемому полю нельзя фильтровать в `where`?
- Как вычисляемое поле влияет на тип результата запроса?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/client-extensions/result | компонент result | Prisma 7: result extension

## 15.5 model и client: свои методы | short: Методы модели | est: ~40 мин
### intro
**Слова шага:** *`model`*, *`client`*, *метод модели*, *бизнес-операция*, *`$asActor`*, *инкапсуляция правил*.

:::tip Если совсем просто
`booking.cancel(id)` читается лучше, чем «обнови статус на `CANCELLED`, допиши заметку, проверь, что бронь не выдана». Метод модели — это «кнопка» для бизнес-операции: правила заключены внутри, снаружи — понятное имя.
:::

```ts
// src/extensions/booking-methods.ts
import { Prisma } from '../generated/prisma/client.js'

export const bookingMethods = Prisma.defineExtension({
  name: 'bookingMethods',
  model: {
    booking: {
      /** Отменить бронь: только «подтверждённую» и только до выдачи. */
      async cancel(id: number, reason: string) {
        const ctx = Prisma.getExtensionContext(this) as any
        const { count } = await ctx.updateMany({
          where: { id, status: { in: ['DRAFT', 'CONFIRMED'] } },          // условие внутри — защита от гонки
          data: { status: 'CANCELLED', note: reason },
        })
        if (count === 0) throw new Error(`Бронь ${id} нельзя отменить (не найдена или уже выдана)`)
      },
    },
  },
  client: {
    /** Выполнить функцию в транзакции от имени сотрудника — для аудита (шаг 14.6). */
    async $asActor<T>(actor: string, fn: (tx: Prisma.TransactionClient) => Promise<T>): Promise<T> {
      const base = Prisma.getExtensionContext(this) as any
      return base.$transaction(async (tx: Prisma.TransactionClient) => {
        await tx.$executeRaw`SELECT set_config('app.actor', ${actor}, true)`
        return fn(tx)
      })
    },
  },
})
```

```ts
// src/lessons/15-methods.ts
import { prisma } from '../db.js'
import { bookingMethods } from '../extensions/booking-methods.js'

const db = prisma.$extends(bookingMethods)
const b = await db.booking.create({ data: { itemId: 3, branchId: 1, status: 'CONFIRMED', startsAt: new Date('2033-01-01'), endsAt: new Date('2033-01-02') } })
await db.$asActor('manager:anna', async (tx) => { await tx.booking.update({ where: { id: b.id }, data: { note: 'проверка' } }) })
await db.booking.cancel(b.id, 'передумал')
console.log((await db.booking.findUniqueOrThrow({ where: { id: b.id } })).status)               // CANCELLED
await db.booking.cancel(b.id, 'ещё раз').catch((e) => console.log(e.message))                    // уже отменена: ошибка
await prisma.booking.deleteMany({ where: { id: b.id } }).catch(() => {})
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/15-methods.ts
```

### result
```out auto
```

Заметь, **как** защищена отмена от гонки: условие `status IN (DRAFT, CONFIRMED)` стоит **внутри `updateMany`**, а не в отдельной проверке перед ним — приём из шага 12.3 (оптимистичная блокировка): либо обновили, либо `count = 0`. Метод `$asActor` соединяет расширения с аудитом из 14.6: `set_config` вызывается внутри транзакции, и триггер увидит исполнителя.

### why
Методы модели собирают **правила предметной области** в одном месте и под понятными именами. Остальной код вызывает `booking.cancel(id)` и не знает, что внутри условие, статусы, заметка. Это тот же принцип, что у «слоя данных» из первой сессии: снаружи — язык бизнеса.

### deep Если не получилось
- **`ctx.updateMany is not a function`** — `this` внутри метода должен быть доступен: вызывай метод как `db.booking.cancel(...)`, а не отделяя его от модели.
- **`$asActor` не видит `$transaction`** — используй `Prisma.getExtensionContext(this)` (в `client`-методе это исходный клиент).

### quiz
- Почему условие по статусу при отмене лучше поставить внутрь `updateMany`, а не проверять отдельно?
- Чем компонент `client` отличается от `model`?
- Как `$asActor` связан с аудитом из шага 14.6?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/client-extensions/client | компонент client | Prisma 7: client extension
- https://www.prisma.io/docs/orm/v7/prisma-client/client-extensions/extension-examples | примеры расширений | Prisma 7: Extension examples

## 15.6 Типы расширенного клиента и цепочка $extends | short: Типы расширений | est: ~45 мин
### intro
**Слова шага:** *цепочка расширений*, *тип расширенного клиента*, *`ReturnType`*, *`Prisma.TransactionClient`*, *расширения и транзакции*, *ограничения*.

:::tip Если совсем просто
Каждое расширение даёт новый клиент с новым **типом**. Чтобы передавать такой клиент в функции, нужно уметь называть его тип. Не пугайся «страшных» типов в подсказках: всё сводится к одной строке — «тип того, что вернул `$extends`».
:::

Сборка итогового клиента в одном месте и тип для функций:

```ts
// src/client.ts
import { prisma } from './db.js'
import { softDelete } from './extensions/soft-delete.js'
import { computed } from './extensions/computed.js'
import { bookingMethods } from './extensions/booking-methods.js'

export const db = prisma
  .$extends(softDelete)
  .$extends(computed)
  .$extends(bookingMethods)

/** Тип полностью расширенного клиента — для параметров функций и тестов. */
export type Db = typeof db
```

```ts
// src/data/customers.ts
import type { Db } from '../client.js'

// функция работает с «расширенным» клиентом — и сама не знает, какие там расширения
export async function activeCustomers(db: Db, branchId: number) {
  return db.customer.findMany({ where: { branchId }, select: { id: true, name: true, initials: true }, take: 10 })
}
```

```bash run
cd ~/prisma-lab/rentkit
cat > src/lessons/15-chain.ts <<'EOF'
import { db } from '../client.js'
import { activeCustomers } from '../data/customers.js'
console.log(await activeCustomers(db, 1))
await db.$disconnect()
EOF
npx tsx src/lessons/15-chain.ts
npm run typecheck
```

### result
```out auto
```

Что нужно знать о расширениях и транзакциях и о других ограничениях (поведение проверено на Prisma 7.10):

- **Интерактивная транзакция на расширенном клиенте** (`db.$transaction(async (tx) => …)`): `tx` содержит **те же расширения** (`query`, `result`, `model`): проверено — `tx.customer.findMany` внутри `db.$transaction` фильтрует удалённых так же, как снаружи. Но всё равно проверь это запросом внутри своей транзакции, если расширения у тебя нестандартные.
- **Порядок цепочки важен:** расширения `query` выполняются **в порядке добавления** (первое — самое внешнее); если расширение `softDelete` подставляет `where`, а следующее `query` его читает, то увидит уже изменённые аргументы.
- **Типы:** `Prisma.TransactionClient` — это тип `tx` у **исходного** клиента; у расширенного свой тип (называй `Parameters<Parameters<Db['$transaction']>[0]>[0]` или используй `Db` напрямую).
- **Производительность типов:** каждое расширение усложняет вывод типов; если редактор «задумывается», вынеси сборку клиента в отдельный файл (как `client.ts`) и экспортируй готовый тип.
- **Raw-запросы расширения `query` не затрагивают**: `$queryRaw` идёт мимо — фильтр удалённых в нём нужно писать самой.

### why
Видимость такого рода «сквозных» правил — и их границ — критична: если ты не знаешь, что `$queryRaw` обходит фильтр, soft delete будет «протекать» именно через отчёты. Правило: **любое сквозное правило должно быть либо в базе (RLS, ограничение), либо проверено тестом на обход.**

### deep Если не получилось
- **«Type instantiation is excessively deep»** — слишком длинная цепочка с большим числом моделей; вынеси `Db` в один тип, используй его вместо вывода в каждом файле.
- **`Property '$transaction' …`** — вызывай на `db`, а не на отдельном расширении.

### quiz
- Как выразить тип клиента, прошедшего три `$extends`?
- Что нужно проверить про расширения внутри `$transaction`?
- Какие запросы расширения `query` не затрагивают и что с этим делать?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/client-extensions/type-utilities | типовые утилиты | Prisma 7: Type utilities
- https://www.prisma.io/docs/orm/v7/prisma-client/client-extensions | расширения клиента | Prisma 7: Client extensions

## 15.7 🔨 Soft delete «протекает» | short: 🔨 Протечка soft delete | est: ~60 мин
### intro
**Слова шага:** *жалоба заказчика*, *обход фильтра*, *вложенный `include`*, *`_count`*, *raw-запросы*, *тесты на обход*.

:::tip Если совсем просто
Мы повесили на дверь «охранника», который не пускает «удалённых». Но в здании есть боковые входы: через связанные таблицы, через счётчики, через прямой SQL. Настоящая проверка — не «охранник стоит», а **«попробуй обойти»**.
:::

*Заказчик:* «Мы удалили клиента „Иванов“ — он пропал из списка. Но в отчёте по броням его имя всё равно есть, в статистике он посчитан, а в выгрузке для бухгалтерии — тоже».

Воспроизведи **пять** «боковых входов» (клиент `c` помечен `softDelete`, у него есть бронь):

```ts
// src/lessons/15-leaks.ts
import assert from 'node:assert/strict'
import { db } from '../client.js'
import { prisma } from '../db.js'

const c = await prisma.customer.create({ data: { name: 'Протечка Тест', phone: '+70000000500', branchId: 1 } })
const b = await prisma.booking.create({ data: { customerId: c.id, itemId: 4, branchId: 1, status: 'CONFIRMED', startsAt: new Date('2034-01-01'), endsAt: new Date('2034-01-02') } })
await db.customer.softDelete(c.id)

const leaks: string[] = []
const check = (name: string, ok: boolean) => { if (!ok) leaks.push(name) }

// 1. прямые чтения — защищены
check('findMany',   (await db.customer.findMany({ where: { id: c.id } })).length === 0)
check('findUnique', (await db.customer.findUnique({ where: { id: c.id } })) === null)
check('count',      (await db.customer.count({ where: { id: c.id } })) === 0)

// 2. боковые входы
const viaInclude = await db.booking.findUniqueOrThrow({ where: { id: b.id }, include: { customer: true } })
check('include клиента из брони', viaInclude.customer === null)

const viaCount = await db.branch.findMany({ where: { id: 1 }, select: { _count: { select: { customers: true } } } })
const realAlive = await prisma.customer.count({ where: { branchId: 1, deletedAt: null } })
check('_count по связи', viaCount[0]!._count.customers === realAlive)

const viaRaw = await db.$queryRaw<{ n: bigint }[]>`SELECT count(*) AS n FROM "tbl_Customers" WHERE id = ${c.id}`
check('$queryRaw', Number(viaRaw[0]!.n) === 0)

const viaRelFilter = await db.booking.count({ where: { customer: { is: { name: 'Протечка Тест' } } } })
check('фильтр по связи', viaRelFilter === 0)

console.log(leaks.length ? 'ПРОТЕКАЕТ: ' + leaks.join(', ') : 'протечек нет')

await prisma.booking.delete({ where: { id: b.id } })
await prisma.customer.delete({ where: { id: c.id } })
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/15-leaks.ts
```

### result
```out auto
```

Ожидаем: **протекают** как минимум `include клиента из брони`, `_count по связи`, `$queryRaw`, `фильтр по связи` — прямые чтения защищены, а «боковые» нет. **Твоя задача:** закрыть все (или обосновать, почему какие-то закрыть нельзя) и показать **тестом** (этот же скрипт должен печатать «протечек нет»). Варианты на выбор: (а) расширить `query` — для `include`/`select` вложенных связей подставлять `where: { deletedAt: null }` (для связи «к одному» это работает: проверено на 7.10, `include: { customer: { where: { deletedAt: null } } }` вернул `customer: null` для удалённого клиента) или фильтровать результат; (б) для `_count` и фильтров по связи — переписать условия; (в) для `$queryRaw` — договорённость «в raw-запросах условие `deleted_at IS NULL` пишем сами» + тест, ловящий забытое; (г) **самый надёжный** — перенести правило **в базу**: представление `customers_alive` или политика RLS (сессия 16), и тогда обойти нечем.

**Приёмка сессии:** расширенный клиент `db` собран цепочкой (`softDelete`, `computed`, `bookingMethods`), покрыт тестом на обход (все пять «боковых входов» закрыты или явно описаны как исключения), вычисляемые поля типизированы, метод `booking.cancel` защищён от гонки, `$asActor` пишет исполнителя в аудит; в `NOTES.md` — таблица «какое правило где живёт: в расширении или в базе — и почему».

### why
Soft delete — не «одно расширение», а **сквозное правило**, и сквозные правила дырявы, пока их проверяет только код, который их же и реализует. Из 15.7 ты выносишь рабочий вывод: что **критично** (утечка чужих данных, показ удалённого клиента в договоре) — доверяй базе (RLS, представления, ограничения); что **удобно** (скрыть удалённое в обычных списках) — расширению.

### deep Если не получилось
- **Подсказка про `include`:** вложенный `include: { customer: true }` не проходит через `query.customer.findMany` — расширение `query` для модели `Booking` получает `args.include`, который можно изменить на `{ customer: { where: { deletedAt: null } } }` (для связей «к одному» условие допустимо; проверено на 7.10); либо проще — убрать «удалённого» из результата в `result`-расширении.
- **Подсказка про `_count`:** в `select._count.select.customers` можно передать `{ where: { deletedAt: null } }` — Prisma поддерживает фильтры в `_count` по связям (проверено на 7.10: `_count: { select: { customers: { where: { deletedAt: null } } } }` считает только живых).
- **Подсказка про базу:** `CREATE VIEW customers_alive AS SELECT * FROM "tbl_Customers" WHERE deleted_at IS NULL` и политика на `tbl_Customers` — тогда ни один обходной путь не покажет удалённого (но раздай права правильно, сессия 16).

### quiz
- Назови минимум три «боковых входа», через которые soft delete «протекает».
- Почему такие правила нужно проверять тестами «на обход», а не «на работу»?
- Какие правила лучше перенести в базу и почему?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/client-extensions/query | query | Prisma 7: query extension
- https://www.postgresql.org/docs/18/ddl-rowsecurity.html | RLS | PostgreSQL 18: Row Security Policies
