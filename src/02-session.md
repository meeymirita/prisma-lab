# Сессия 2 · TypeScript ровно настолько, насколько нужно
dur: ~4 ч

## 2.1 Что такое TypeScript и как его запускать | short: TypeScript и tsx | est: ~30 мин
### intro
**Слова шага:** *TypeScript*, *тип*, *`tsx`*, *`tsc`*, *`strict`*, *проверка на этапе компиляции*.

:::tip Если совсем просто
TypeScript — это JavaScript с подписями на ящиках. В JS ты можешь положить в ящик «возраст» строку, и узнаешь об этом, когда ящик откроют в работе. В TS ящик подписан («тут число»), и редактор сразу подсвечивает: «ты кладёшь не то». После проверки все подписи стираются, и в работу уходит обычный JavaScript.
:::

Два инструмента, не путать: **`tsc`** — компилятор, который **проверяет** типы (`npx tsc --noEmit`) и, если нужно, переводит в JS; **`tsx`** — запускает `.ts`-файл напрямую, **не проверяя** типы (просто выкидывает подписи). Мы используем оба: `tsx` для запуска, `tsc --noEmit` (скрипт `npm run typecheck`) для проверки.

Создай папку и первый файл (в проекте `~/prisma-lab/rentkit`):

```ts
// src/intro/01-hello.ts
const price: number = 450
const title: string = 'Лыжи горные'
console.log(`${title}: ${price * 3} за три дня`)

// price = 'дорого'   // ← попробуй раскомментировать: tsc скажет «Type 'string' is not assignable to type 'number'»
```

```bash run
cd ~/prisma-lab/rentkit
mkdir -p src/intro
npx tsx src/intro/01-hello.ts
npm run typecheck
```

### result
```out auto
```

`tsx` выведет строку, `typecheck` ничего не скажет (значит, ошибок нет). Теперь раскомментируй последнюю строку: `tsx` **всё равно запустит** файл (подписи он не проверяет), а вот `npm run typecheck` покажет ошибку. Вывод: **типы проверяет только `tsc` (и редактор)**; запуск и проверка — разные вещи.

### why
Эта разница сначала сбивает с толку: «код запустился, значит, правильный». Нет: `tsx` не жалуется на типы. Поэтому в лабе (и в CI, сессия 18) проверка типов — отдельная команда, которую нужно запускать.

### deep Что такое `strict`
В `tsconfig.json` стоит `"strict": true` — это набор строгих проверок: главное из них — `strictNullChecks` (`null` и `undefined` не подмешиваются в любые типы молча). С `strict` TypeScript находит больше ошибок, но и требует больше аккуратности. Для работы с Prisma он нужен: клиент возвращает `T | null`, и без `strict` ты бы этого не заметила.

### quiz
- Чем отличаются `tsc` и `tsx`?
- Почему файл с ошибкой типов может нормально запуститься через `tsx`?
- Что даёт `"strict": true`?

### links
- https://www.typescriptlang.org/docs/handbook/2/basic-types.html | базовые типы | TypeScript: The Basics
- https://www.typescriptlang.org/tsconfig/#strict | strict | TypeScript: strict

## 2.2 Типы данных, объекты, interface и type | short: Типы и объекты | est: ~35 мин
### intro
**Слова шага:** *`string`/`number`/`boolean`*, *массив*, *объект*, *`interface`*, *`type`*, *литеральный тип*, *`Date`*.

:::tip Если совсем просто
Тип объекта — это анкета: какие поля должны быть и какого вида. `interface Booking` — анкета брони: «id — число, клиент — число, начало — дата». Любой объект, подходящий под анкету, считается бронью.
:::

```ts
// src/intro/02-types.ts
interface Booking {
  id: number
  customerId: number
  startsAt: Date
  note?: string            // «?» — поле необязательное
}

type BookingStatus = 'draft' | 'confirmed' | 'issued' | 'returned'   // литеральный тип: только эти значения

const b: Booking = { id: 1, customerId: 42, startsAt: new Date('2026-01-15') }
const list: Booking[] = [b]
let status: BookingStatus = 'confirmed'
// status = 'lost'          // ← ошибка: такого значения нет в BookingStatus

console.log(list.length, b.startsAt.toISOString(), status)
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/intro/02-types.ts
npm run typecheck
```

### result
```out auto
```

Разница `interface` и `type`: для объектов почти одинаковы (`interface` можно «расширять» через `extends`, `type` умеет объединения вроде `'a' | 'b'`). В лабе мы чаще пользуемся `type` и типами, которые **создаёт Prisma** (сессия 5 — `Prisma.BookingGetPayload`): руками писать анкеты почти не придётся.

### why
Prisma сама генерирует тип для каждой модели — тебе не нужно писать `interface Booking` руками. Но понимать, как он выглядит и как читать ошибки вида «Property 'startAt' does not exist on type …», нужно с первого дня.

### deep Как ещё можно
Для набора констант вместо литерального объединения используют `enum` (в Prisma это `enum BookingStatus` в схеме, сессия 4.4). В TS есть и свой `enum`, но в современном коде чаще берут объединение литералов — оно проще и не создаёт кода во время выполнения.

### quiz
- Что означает `note?: string` в `interface Booking`?
- Чем литеральный тип `'draft' | 'confirmed'` лучше обычной `string`?
- Зачем читать сообщения вида «Property … does not exist on type …»?

### links
- https://www.typescriptlang.org/docs/handbook/2/everyday-types.html | типы на каждый день | TypeScript: Everyday Types
- https://www.typescriptlang.org/docs/handbook/2/objects.html | объектные типы | TypeScript: Object Types

## 2.3 Union, null и сужение типов | short: null и сужение | est: ~40 мин
### intro
**Слова шага:** *union (`A | B`)*, *`null`*, *`undefined`*, *сужение (narrowing)*, *`?.`*, *`??`*.

:::tip Если совсем просто
`Booking | null` — это «бронь или ничего». Если попросить у Prisma бронь по номеру, а такой нет, придёт `null`. TypeScript не даст обратиться к полю, пока ты не проверишь: «а оно вообще пришло?» Это похоже на турникет: сначала покажи пропуск, потом проходи.
:::

```ts
// src/intro/03-null.ts
type Booking = { id: number; note: string | null }

function find(id: number): Booking | null {
  return id === 1 ? { id: 1, note: null } : null
}

const b = find(2)
// console.log(b.id)                 // ← ошибка: 'b' is possibly 'null'

if (b === null) {
  console.log('брони нет')            // внутри этой ветки b — null
} else {
  console.log('id', b.id)             // здесь TS уже знает: b — Booking
}

const note = find(1)?.note ?? 'без заметки'   // ?. — безопасное обращение, ?? — значение по умолчанию
console.log(note)
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/intro/03-null.ts
npm run typecheck
```

### result
```out auto
```

Сужение — это когда проверка в коде (`if (b === null)`, `typeof x === 'string'`, `if (x)`) **меняет тип** внутри ветки. Три приёма, которые будут нужны постоянно: `?.` (если слева `null`/`undefined`, вернуть `undefined`, а не упасть), `??` (значение справа — только если слева `null` или `undefined`; в отличие от `||`, не заменяет `0` и `''`), и проверка `if (!x) return`/`throw` в начале функции.

### why
`T | null` — главный повседневный знакомый TypeScript в работе с базой: `findUnique` возвращает «запись или `null`». Если не научиться сужать, в коде появятся восклицательные знаки `b!.id` («поверь мне, не null») — и первая же ночная ошибка в проде. С Prisma лучше пользоваться `findUniqueOrThrow`, который выбрасывает ошибку (шаг 5.2).

### deep Почему `??`, а не `||`
`x || 'по умолчанию'` заменит **любое ложное** значение: `0`, `''`, `false`. Если у предмета цена равна нулю (подарок), `price || 100` вернёт 100 — баг. `price ?? 100` заменит только `null`/`undefined`.

### quiz
- Что означает тип `Booking | null` и почему нельзя сразу обратиться к `b.id`?
- В чём разница между `??` и `||`?
- Что такое сужение типа и какие проверки его запускают?

### links
- https://www.typescriptlang.org/docs/handbook/2/narrowing.html | сужение типов | TypeScript: Narrowing
- https://developer.mozilla.org/ru/docs/Web/JavaScript/Reference/Operators/Nullish_coalescing | оператор ?? | MDN: Nullish coalescing

## 2.4 async/await, Promise и ошибки | short: async/await | est: ~40 мин
### intro
**Слова шага:** *`Promise`*, *`async`/`await`*, *`Promise<T>`*, *`try`/`catch`*, *`unknown`*, *`Promise.all`*.

:::tip Если совсем просто
Запрос в базу — как заказ в кофейне: ты делаешь заказ и получаешь талончик (`Promise`), а напиток приготовят позже. `await` — «подожди у стойки, пока не выдадут». Без `await` ты уйдёшь с талончиком вместо кофе — и в коде вместо данных окажется `Promise { <pending> }`.
:::

```ts
// src/intro/04-async.ts
const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms))

async function loadBooking(id: number): Promise<{ id: number }> {
  await sleep(100)                      // «поход в базу»
  if (id < 0) throw new Error('отрицательный id')
  return { id }
}

async function main() {
  const one = await loadBooking(1)      // ждём результат
  console.log(one)

  try {
    await loadBooking(-1)
  } catch (e) {                         // тип e — unknown, нужно сузить
    console.log(e instanceof Error ? e.message : String(e))
  }

  // три запроса одновременно: ждём все вместе
  const all = await Promise.all([loadBooking(1), loadBooking(2), loadBooking(3)])
  console.log(all.map((b) => b.id))
}

await main()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/intro/04-async.ts
```

### result
```out auto
```

Что запомнить: функция с `async` **всегда** возвращает `Promise`; тип `Promise<{ id: number }>` читается «когда-нибудь вернёт `{ id }`»; в `catch` переменная имеет тип **`unknown`** (в `strict`) — прежде чем читать `e.message`, нужно сузить (`e instanceof Error`) — на этом построена обработка ошибок Prisma (`e instanceof Prisma.PrismaClientKnownRequestError`, сессия 7.6). `Promise.all` запускает запросы **параллельно** и ждёт все — быстрее, чем три `await` подряд.

### why
Каждый вызов Prisma — асинхронный. Забытый `await` — самая частая ошибка новичка: код не падает, а просто ничего не делает вовремя (запись ещё не завершилась, когда программа вышла). Привычка читать тип результата (`Promise<…>`) в редакторе спасает от этого.

### deep Как ещё можно
Верхнеуровневый `await` (как `await main()` выше) работает в ES-модулях — у нас `"type": "module"`. В старом стиле CommonJS так нельзя, и всё оборачивали в `main().catch(...)`.

### quiz
- Что вернёт функция с `async`, даже если она возвращает число?
- Почему переменная в `catch` имеет тип `unknown` и как её сузить?
- Когда `Promise.all` лучше, чем несколько `await` подряд?

### links
- https://www.typescriptlang.org/docs/handbook/2/functions.html | функции | TypeScript: More on Functions
- https://developer.mozilla.org/ru/docs/Learn_web_development/Extensions/Async_JS | асинхронный JS | MDN: Asynchronous JavaScript

## 2.5 Модули: import, export и суффикс .js | short: Модули ESM | est: ~25 мин
### intro
**Слова шага:** *модуль*, *`export`/`import`*, *ESM*, *суффикс `.js`*, *`import type`*.

:::tip Если совсем просто
Модуль — это файл, из которого можно «вынести наружу» функции и типы (`export`) и «принести» их в другой файл (`import`). Папка с модулями — набор готовых деталей, которые собираешь в разные конструкции.
:::

```ts
// src/intro/money.ts
export function format(amount: number): string {
  return amount.toFixed(2).replace('.', ',') + ' руб'
}
export type Money = { amount: number; currency: 'RUB' }
```

```ts
// src/intro/05-modules.ts
import { format, type Money } from './money.js'    // ← суффикс .js, хотя файл money.ts

const m: Money = { amount: 1200.5, currency: 'RUB' }
console.log(format(m.amount))
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/intro/05-modules.ts
```

### result
```out auto
```

Суффикс **`.js`** в импорте — самое странное для новичка: файл называется `money.ts`, а импортируешь `./money.js`. Причина: в ES-модулях Node требует точное имя файла **как оно будет после компиляции** (TypeScript превращает `.ts` в `.js`), поэтому в импорте пишется `.js`; `tsx` и `tsc` понимают это. `import type` (или `type` внутри фигурных скобок) говорит: «это только тип, после компиляции убери» — используется для типов, которые не нужны в рантайме.

### why
Ошибки импорта («Cannot find module», «ERR_MODULE_NOT_FOUND») — первые, что встретит новичок в проекте с `"type": "module"`. Знание про суффикс `.js` и про то, что `tsx` его «понимает», экономит час поисков.

### deep Как ещё можно
Если не хочется писать `.js` везде, можно использовать сборщик или `moduleResolution: "bundler"`. Но для Node-сервера и для CLI Prisma `NodeNext` — самый надёжный вариант, он ведёт себя так же, как реальный Node.

### quiz
- Почему в импорте пишется `.js`, хотя файл называется `.ts`?
- Что делает `import type` и когда он нужен?

### links
- https://www.typescriptlang.org/docs/handbook/modules/reference.html | модули | TypeScript: Modules Reference

## 2.6 Generic'и и утилитарные типы — минимум для Prisma | short: Generic'и и утилиты | est: ~45 мин
### intro
**Слова шага:** *generic (`<T>`)*, *`Pick`*, *`Omit`*, *`Partial`*, *`Record`*, *`typeof`*, *`ReturnType`*, *`Awaited`*.

:::tip Если совсем просто
Generic — это «тип с пропуском». `Array<T>` — «массив чего-то»; `Promise<T>` — «обещание чего-то». Ты подставляешь вместо `T` конкретный тип. Утилитарные типы — готовые «фильтры»: `Pick` оставляет только нужные поля анкеты, `Omit` — вычёркивает лишние, `Partial` делает все поля необязательными.
:::

```ts
// src/intro/06-generics.ts
type Booking = { id: number; customerId: number; note: string; total: number }

type Brief = Pick<Booking, 'id' | 'total'>              // { id; total }
type NoNote = Omit<Booking, 'note'>                      // всё, кроме note
type Patch = Partial<Booking>                            // все поля необязательные (для обновлений)
type ByStatus = Record<'draft' | 'issued', Booking[]>    // { draft: Booking[]; issued: Booking[] }

function first<T>(items: T[]): T | undefined {           // generic-функция: тип результата = тип элемента
  return items[0]
}

const makeRepo = () => ({ find: async (id: number): Promise<Booking | null> => null })
type Repo = ReturnType<typeof makeRepo>                  // «тип того, что возвращает функция»
type Found = Awaited<ReturnType<Repo['find']>>           // Awaited снимает Promise: Booking | null

const x: Brief = { id: 1, total: 100 }
console.log(first([1, 2, 3]), first<string>([]), x)
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/intro/06-generics.ts
npm run typecheck
```

### result
```out auto
```

Это **всё**, что нужно из «продвинутого» TypeScript для лабы: ты будешь видеть `Pick`, `Omit`, `Partial` в подсказках Prisma (`Prisma.BookingUpdateInput` — по сути, `Partial` от модели), и `Awaited<ReturnType<typeof ...>>` — один из способов получить тип результата запроса (шаг 5.6). Если захочется глубже (условные типы, mapped types, `infer`) — это TypeScript-лаба; здесь не нужно.

### why
Prisma выдаёт типы, собранные из таких же кирпичиков, и сообщения об ошибках типов длинные и страшные. Зная `Pick`/`Omit`/`Partial`/`Awaited`, ты читаешь их как текст, а не как заклинания. Если оказывается, что тип выведен «слишком широким» или «слишком узким», это чаще всего про `Partial`, `null` и `Awaited`.

### deep Если не получилось
- **«Type instantiation is excessively deep»** — слишком сложный тип; в лабе такого быть не должно; если встретилось — упрости тип или проверь версию TypeScript (`~6.0`).
- **`first<string>([])` возвращает `undefined`** — так и надо: у пустого массива нет первого элемента, и тип `T | undefined` честно об этом говорит.

### quiz
- Что означает `Array<T>` и что такое `T`?
- Что делают `Pick`, `Omit` и `Partial`?
- Зачем нужен `Awaited<ReturnType<...>>`?

### links
- https://www.typescriptlang.org/docs/handbook/2/generics.html | дженерики | TypeScript: Generics
- https://www.typescriptlang.org/docs/handbook/utility-types.html | утилитарные типы | TypeScript: Utility Types

## 2.7 🔨 «Type X is not assignable to type Y»: читать, а не глушить | short: 🔨 Ошибка типов | est: ~35 мин
### intro
**Слова шага:** *сообщение компилятора*, *`not assignable`*, *`possibly undefined`*, *`as any`* (не надо), *`satisfies`*.

:::tip Если совсем просто
Ошибка типов — не враг, а подсказка, где именно ты ошиблась: «сюда нужно число, а ты даёшь строку». Новичок глушит её словом `any` — это как заклеить лампочку «Check Engine» изолентой: лампа погасла, поломка осталась.
:::

Три типичные ошибки — исправь каждую **без** `any` и без `!`:

```ts
// src/intro/07-errors.ts
type Booking = { id: number; note?: string }

// 1. «Type 'string | undefined' is not assignable to type 'string'»
function shout(note: string) { return note.toUpperCase() }
const b: Booking = { id: 1 }
console.log(shout(b.note))

// 2. «Object is possibly 'undefined'» (noUncheckedIndexedAccess включён в tsconfig)
const ids = [1, 2, 3]
console.log(ids[5].toFixed(2))

// 3. «Property 'startAt' does not exist on type …»
const full = { id: 1, startsAt: new Date() }
console.log(full.startAt)
```

```bash run
cd ~/prisma-lab/rentkit
npm run typecheck 2>&1 | head -20
```

### result
```out auto
```

Разбор: (1) `b.note` может быть `undefined` — нужно либо проверить (`if (b.note) …`), либо дать значение по умолчанию (`shout(b.note ?? '')`); (2) элемента с индексом 5 нет, и TS (с `noUncheckedIndexedAccess`) честно считает результат `number | undefined` — проверь длину или используй `?.`; (3) опечатка в имени поля: `startsAt`, не `startAt` — подсказка редактора её бы поймала. Исправь все три и убедись, что `npm run typecheck` чистый.

**Приёмка сессии:** все файлы в `src/intro/` проходят `npm run typecheck`; ты можешь объяснить, чем `tsx` отличается от `tsc`, что значит `T | null`, и написать функцию с `async`/`await` и обработкой ошибок через `instanceof Error`.

### why
Привычка читать сообщения компилятора окупается в Prisma: типы выводятся из схемы, и **большинство ошибок в запросах** (`where` по несуществующему полю, неверный тип значения) компилятор находит раньше базы. Если глушить `any`, ты теряешь именно то, ради чего взяла ORM.

### deep Как ещё можно: `satisfies`
Оператор `satisfies` проверяет значение на соответствие типу, **не расширяя** его: `const cfg = { port: 5433 } satisfies Config` — тип `cfg` остаётся точным (`{ port: number }`), а компилятор убедился, что он подходит под `Config`. В Prisma так проверяют, например, подготовленные запросы.

### deep Если не получилось
- **Редактор не подсвечивает ошибки** — открой проект как папку `rentkit` (не родительскую) и убедись, что редактор использует версию TypeScript из проекта (`node_modules/typescript`).
- **Ошибок слишком много** — исправляй по одной сверху: часто одна причина тянет за собой десять строк ошибок.

### quiz
- Почему `as any` — плохой способ «починить» ошибку типов?
- Как исправить «Type 'string | undefined' is not assignable to type 'string'» без `!`?
- Что делает оператор `satisfies` и чем он отличается от аннотации типа?

### links
- https://www.typescriptlang.org/docs/handbook/2/everyday-types.html#type-assertions | утверждения типов | TypeScript: Type Assertions
- https://www.typescriptlang.org/docs/handbook/release-notes/typescript-4-9.html#the-satisfies-operator | оператор satisfies | TypeScript 4.9: satisfies
