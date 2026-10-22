# Сессия 14 · Деньги: журнал, идемпотентность, сверка
dur: ~4 ч

## 14.1 Деньги — не float: Decimal, округление, сравнение | short: Decimal и деньги | est: ~40 мин
### intro
**Слова шага:** *`Prisma.Decimal`*, *`decimal.js`*, *округление*, *`ROUND_HALF_UP`*, *`toDecimalPlaces`*, *сравнение*, *копейка*.

:::tip Если совсем просто
`0,1 + 0,2` у человека — `0,3`. У компьютера на дробных числах — `0,30000000000000004`. Для расчёта «сколько попросить у клиента» это недопустимо. `Decimal` — это «арифметика на бумаге столбиком»: цифры хранятся как цифры, а не как двоичное приближение. Остаётся одно решение, которое принимает не компьютер, а ты: **как округлять**.
:::

```ts
// src/lessons/14-decimal.ts
import { Prisma } from '../generated/prisma/client.js'

const D = Prisma.Decimal

console.log('number :', 0.1 + 0.2)                                   // 0.30000000000000004
console.log('Decimal:', new D('0.1').plus('0.2').toString())         // 0.3

// деньги — всегда строка → Decimal, никогда не number
const price = new D('1234.50')
const discount = price.times('0.15')                                // 185.175 — три знака после запятой!
console.log('скидка до округления:', discount.toString())
console.log('HALF_UP  :', discount.toDecimalPlaces(2, D.ROUND_HALF_UP).toString())    // 185.18
console.log('HALF_EVEN:', discount.toDecimalPlaces(2, D.ROUND_HALF_EVEN).toString())  // 185.18 (банковское: к чётной цифре)
console.log('FLOOR    :', discount.toDecimalPlaces(2, D.ROUND_FLOOR).toString())       // 185.17

// сравнение: не === (это разные объекты!), а equals / lt / gte
console.log(new D('1.0').equals('1.00'), new D('1.0') === new D('1.00'))   // true false
console.log(price.minus(discount).toFixed(2))                        // 1049.33  (1234.50 − 185.175 = 1049.325 → округлено)
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/14-decimal.ts
```

### result
```out auto
```

Что запомнить:

- **`Decimal` из строки**, а не из числа: `new D('1234.50')`, не `new D(1234.5)` (число уже приблизительное).
- **Результат умножения/деления** может иметь больше двух знаков — **округляй явно** и в **одном месте**, по правилу бизнеса (`ROUND_HALF_UP` — «как в школе»; `ROUND_HALF_EVEN` — «банковское», сглаживает смещение при массовых расчётах).
- **Сравнение** — `equals`, `lt`, `lte`, `gt`, `gte`; операторы `===` и `<` для объектов не работают как для чисел.
- В **JSON и API** — строка (`toFixed(2)`): `Decimal` умеет `toJSON`, но не доверяй формату — делай явно.
- В базе — **`numeric(12,2)`**, и вставка в колонку **округляет по умолчанию до двух знаков**: «лишние» знаки исчезнут молча, поэтому округляй **до** записи.

### why
Деньги — единственная область, где «почти» не бывает. Две копейки на тысяче платежей — это 20 рублей расхождения; на миллионе — 20 тысяч, и бухгалтерия найдёт каждую. Решение «как округляем» — бизнес-правило, а не техническая деталь, и записывать его нужно в **одно** место кода.

### deep Как ещё можно
Многие системы хранят деньги **целыми** (копейки/центы: `Int`/`BigInt`) — арифметика целых точна, а «рубли» получаются делением на 100 при выводе. Это надёжно, но неудобно с процентами и `numeric`. В нашей базе уже `numeric(12,2)`, поэтому `Decimal` — естественный выбор.

### deep Если не получилось
- **`D.ROUND_HALF_UP` — undefined** — в вашей версии Prisma статические константы доступны иначе; импортируй `Decimal` из `decimal.js` напрямую или смотри `Prisma.Decimal` в подсказках редактора (**сверьтесь**).
- **`new D(1234.5)` печатает много знаков** — число уже приблизительное: используйте строку.

### quiz
- Почему `Decimal` создают из строки, а не из числа?
- Чем отличаются `ROUND_HALF_UP` и `ROUND_HALF_EVEN` и кто выбирает правило?
- Почему `new D('1.0') === new D('1.00')` равно `false` и как сравнивать правильно?

### links
- https://mikemcl.github.io/decimal.js/ | decimal.js | decimal.js
- https://www.prisma.io/docs/orm/v7/prisma-client/special-fields-and-types | специальные типы | Prisma 7: Special fields and types

## 14.2 Журнал проводок: двойная запись | short: Ledger | est: ~65 мин
### intro
**Слова шага:** *ledger (журнал проводок)*, *двойная запись*, *счёт*, *проводка*, *дебет и кредит (знак суммы)*, *баланс как сумма*, *`tx_id`*.

:::tip Если совсем просто
В бухгалтерской книге каждая копейка записана **дважды**: откуда ушла и куда пришла. Клиент заплатил 1 000 за прокат — в книге две строки: «+1 000 в кассу» и «−1 000 из „выручки“» (сумма всегда ноль). Остаток на счёте **не хранится** — он считается как сумма всех проводок. Поэтому его невозможно «случайно подправить».
:::

```svg
@ledger-double-entry
```

Заведём счета и проводки. Знак суммы: **плюс** — счёт «получил» (дебет), **минус** — «отдал» (кредит). Сумма всех проводок одной операции (`tx_id`) должна быть **ноль**.

```prisma schema
model LedgerAccount {
  id      Int            @id @default(autoincrement())
  code    String         @unique
  name    String
  entries LedgerEntry[]
  @@map("ledger_account")
}

model LedgerEntry {
  id        Int           @id @default(autoincrement())
  txId      String        @map("tx_id") @db.Uuid
  accountId Int           @map("account_id")
  amount    Decimal       @db.Decimal(12, 2)
  bookingId Int?          @map("booking_id")
  paymentId Int?          @map("payment_id")
  createdAt DateTime      @default(now()) @map("created_at") @db.Timestamptz(3)
  account   LedgerAccount @relation(fields: [accountId], references: [id], onDelete: Restrict)
  @@index([txId])
  @@index([bookingId])
  @@index([accountId])
  @@map("ledger_entry")
}
```

Создадим миграцию без применения и допишем в неё начальные счета:

```bash run hidden
cd ~/prisma-lab/rentkit && npx prisma migrate dev --create-only --name ledger && sleep 1
```

```sql tail=prisma/migrations/*_ledger/migration.sql
-- в созданную `migrate dev --create-only --name ledger` дописать начальные счета
INSERT INTO "ledger_account" (code, name) VALUES
  ('CASH',     'Касса и банк'),
  ('REVENUE',  'Выручка от проката'),
  ('DEPOSITS', 'Залоги клиентов (обязательство)');
ALTER TABLE "ledger_entry" ADD CONSTRAINT ledger_entry_amount_ck CHECK (amount <> 0);
```

```bash run
cd ~/prisma-lab/rentkit
npx prisma migrate dev
npm run generate
```

### result
```out auto
```

Перенесём в журнал **историю**: платежи и движения залога. Скрипт заполняет `ledger_entry` из `tbl_Payments` и `tbl_DepositLog` порциями; для каждой операции создаётся **пара** строк (дебет и кредит) с общим `tx_id`:

```ts
// scripts/backfill-ledger.ts
import { prisma } from '../src/db.js'

const acc = Object.fromEntries((await prisma.ledgerAccount.findMany()).map((a) => [a.code, a.id])) as Record<string, number>

// платежи: предоплата и доплата — деньги пришли (Касса +, Выручка −)
await prisma.$executeRaw`
  WITH p AS (SELECT id, booking_id, amount, paid_at, gen_random_uuid() AS tx FROM "tbl_Payments" WHERE kind IN (1, 2) AND amount > 0)
  INSERT INTO ledger_entry (tx_id, account_id, amount, booking_id, payment_id, created_at)
  SELECT tx, ${acc.CASH}::int, amount, booking_id, id, paid_at FROM p
  UNION ALL SELECT tx, ${acc.REVENUE}::int, -amount, booking_id, id, paid_at FROM p`

// возвраты: Выручка +, Касса −
await prisma.$executeRaw`
  WITH p AS (SELECT id, booking_id, amount, paid_at, gen_random_uuid() AS tx FROM "tbl_Payments" WHERE kind = 3 AND amount > 0)
  INSERT INTO ledger_entry (tx_id, account_id, amount, booking_id, payment_id, created_at)
  SELECT tx, ${acc.REVENUE}::int, amount, booking_id, id, paid_at FROM p
  UNION ALL SELECT tx, ${acc.CASH}::int, -amount, booking_id, id, paid_at FROM p`

// залог принят: Касса +, Залоги −;  возвращён: Залоги +, Касса −;  оставлен: Залоги +, Выручка −
await prisma.$executeRaw`
  WITH d AS (SELECT booking_id, round(abs(delta)::numeric, 2) AS amt, to_timestamp(ts) AS at, reason, gen_random_uuid() AS tx
             FROM "tbl_DepositLog" WHERE delta <> 0 AND booking_id IS NOT NULL)
  INSERT INTO ledger_entry (tx_id, account_id, amount, booking_id, created_at)
  SELECT tx, CASE reason WHEN 'hold' THEN ${acc.CASH}::int ELSE ${acc.DEPOSITS}::int END, amt, booking_id, at FROM d
  UNION ALL
  SELECT tx, CASE reason WHEN 'hold' THEN ${acc.DEPOSITS}::int WHEN 'return' THEN ${acc.CASH}::int ELSE ${acc.REVENUE}::int END, -amt, booking_id, at FROM d`

console.log(await prisma.ledgerEntry.count(), 'проводок')
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx scripts/backfill-ledger.ts
psqlr() { docker exec -i rental-pg psql -U postgres -d rental "$@"; }
psqlr <<'SQL'
-- каждая операция сбалансирована: сумма по tx_id равна нулю
SELECT count(*) AS несбалансированных FROM (SELECT tx_id FROM ledger_entry GROUP BY tx_id HAVING sum(amount) <> 0) t;
-- остатки по счетам — сумма проводок, нигде не хранятся
SELECT a.code, sum(e.amount) AS остаток FROM ledger_entry e JOIN ledger_account a ON a.id = e.account_id GROUP BY a.code ORDER BY 1;
SQL
```

### result
```out auto
```

Ожидаем: **несбалансированных — 0**; остаток `CASH` положительный (деньги в кассе; у нас ≈ +753 млн), `REVENUE` — **отрицательный** (в двойной записи доходы — «кредитовое» сальдо; ≈ −751 млн), `DEPOSITS` — небольшой **отрицательный** (≈ −1,8 млн: залоги, которые ещё лежат у нас и принадлежат клиентам, — мы им должны; знак «минус» у обязательства — норма двойной записи). Баланс `CASH + REVENUE + DEPOSITS` = **ноль** (753 097 202 − 751 278 227 − 1 818 975 = 0): общая сумма всех проводок всегда нулевая — главный признак правильной двойной записи.

### why
Ledger — старейший и самый надёжный способ работы с деньгами: он **добавляется, но не изменяется**. Ошибка исправляется не правкой старой проводки, а новой **компенсирующей**. В результате у каждой копейки есть история «откуда и куда», а остаток невозможно «подогнать».

### deep Если не получилось
- **`несбалансированных > 0`** — в одном из трёх `INSERT` суммы пары не противоположны по знаку; проверь `CASE` для залога: для `hold` пара (`CASH` +, `DEPOSITS` −), для `return` (`DEPOSITS` +, `CASH` −), для `keep` (`DEPOSITS` +, `REVENUE` −).
- **Скрипт долгий** — `INSERT … SELECT` без порций на сотнях тысяч строк допустим для разового переноса; для продолжающегося процесса так делать не стоит.

### quiz
- Что значит «двойная запись» и почему сумма проводок одной операции равна нулю?
- Почему остаток на счёте не хранят, а считают?
- Как в ledger исправляют ошибку в прошлой операции?

### links
- https://en.wikipedia.org/wiki/Double-entry_bookkeeping | двойная запись | Wikipedia: Double-entry bookkeeping

## 14.3 Платёж с идемпотентным ключом | short: Идемпотентный платёж | est: ~50 мин
### intro
**Слова шага:** *идемпотентность*, *идемпотентный ключ*, *`ext_ref`*, *повтор запроса*, *`P2002` как «уже было»*, *атомарная запись платежа и проводок*.

:::tip Если совсем просто
Платёжный шлюз, не получив ответа, **повторит** запрос. Если не защититься, клиент заплатит дважды. Идемпотентность — свойство операции: «сколько раз ни повтори, результат как от одного раза». Приём простой: у каждого платежа есть **уникальный внешний номер** (`ext_ref`); если такой уже есть, второй раз мы ничего не делаем и просто возвращаем то, что записали в первый.
:::

После чистки (шаг 11.3) `ext_ref` уникален. Сделаем функцию записи платежа вместе с проводками **в одной транзакции**:

```ts
// src/data/payments.ts
import { Prisma } from '../generated/prisma/client.js'
import { prisma } from '../db.js'

const D = Prisma.Decimal

export type PaymentInput = { bookingId: number; amount: string; kind: 1 | 2 | 3; extRef: string; paidAt?: Date }

/** Записывает платёж и две проводки (CASH ↔ REVENUE). Повторный вызов с тем же extRef ничего не меняет. */
export async function recordPayment(p: PaymentInput) {
  const amount = new D(p.amount).toDecimalPlaces(2, D.ROUND_HALF_UP)
  if (amount.lte(0)) throw new Error('Сумма должна быть положительной')
  try {
    return await prisma.$transaction(async (tx) => {
      const accounts = Object.fromEntries((await tx.ledgerAccount.findMany({ where: { code: { in: ['CASH', 'REVENUE'] } } })).map((a) => [a.code, a.id]))
      const payment = await tx.payment.create({
        data: { bookingId: p.bookingId, amount, kind: p.kind, extRef: p.extRef, paidAt: p.paidAt ?? new Date() },
      })
      const txId = crypto.randomUUID()
      const sign = p.kind === 3 ? -1 : 1                                  // возврат — обратные знаки
      await tx.ledgerEntry.createMany({ data: [
        { txId, accountId: accounts.CASH!,    amount: amount.times(sign),      bookingId: p.bookingId, paymentId: payment.id },
        { txId, accountId: accounts.REVENUE!, amount: amount.times(-sign),     bookingId: p.bookingId, paymentId: payment.id },
      ] })
      return { payment, repeated: false }
    })
  } catch (e) {
    // тот же extRef уже записан: это ретрай, а не новый платёж
    if (e instanceof Prisma.PrismaClientKnownRequestError && e.code === 'P2002') {
      const existing = await prisma.payment.findUniqueOrThrow({ where: { extRef: p.extRef } })
      return { payment: existing, repeated: true }
    }
    throw e
  }
}
```

```ts
// src/lessons/14-idem.ts
import { recordPayment } from '../data/payments.js'
import { prisma } from '../db.js'

const ref = 'TEST-' + Date.now()
const results = await Promise.all(Array.from({ length: 10 }, () => recordPayment({ bookingId: 1, amount: '150.50', kind: 1, extRef: ref })))
console.log('новых платежей:', results.filter((r) => !r.repeated).length, ' повторов:', results.filter((r) => r.repeated).length)
console.log('записей в payments:', await prisma.payment.count({ where: { extRef: ref } }))
const paymentId = results[0]!.payment.id
console.log('проводок по этому платежу:', await prisma.ledgerEntry.count({ where: { paymentId } }), '(ожидаем 2)')
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/14-idem.ts
```

### result
```out auto
```

Ожидаем: **одна** новая запись и **девять** повторов; в `payments` одна строка с этим `ext_ref`. Главное: платёж и проводки пишутся **одной транзакцией** — если упадёт запись проводки, не останется платежа без проводок (и наоборот), а при повторе `P2002` откатывает **всю** транзакцию, поэтому проводок вторая попытка не добавит.

### why
Идемпотентность — требование не только платёжных систем, но любого API, который можно вызвать повторно (сеть сбоит, клиент нажимает дважды, очередь доставляет «как минимум один раз»). **Уникальное ограничение в базе — единственная защита, не зависящая от остального кода.** Паттерн «записать; при `P2002` вернуть существующее» — универсален.

### deep Как ещё можно
Альтернатива — таблица ключей идемпотентности (`idempotency_key`, `request_hash`, сохранённый ответ), как делают платёжные провайдеры: тогда повтор с **другими** данными под тем же ключом можно отличить и отклонить. Для наших целей достаточно `ext_ref` как внешнего номера операции.

### deep Если не получилось
- **Падает с ошибкой вместо «повтора»** — не `P2002`: проверь, что `ext_ref` действительно уникален (`\d "tbl_Payments"`) и что ты ловишь код именно этого класса ошибки.
- **`findUniqueOrThrow where extRef`** — поле должно быть `@unique` в схеме (шаг 11.3).

### quiz
- Что значит «операция идемпотентна» и почему важно для платежей?
- Почему платёж и проводки записываются одной транзакцией?
- Почему защиту от дубля делают уникальным индексом в базе?

### links
- https://stripe.com/docs/api/idempotent_requests | идемпотентные запросы | Stripe: Idempotent requests

## 14.4 Залог: принять, удержать часть, вернуть | short: Залог | est: ~50 мин
### intro
**Слова шага:** *залог как обязательство*, *частичное удержание*, *проводки в одной транзакции*, *баланс залога по брони = 0*.

:::tip Если совсем просто
Залог — не наши деньги: клиент оставил его в залог, и мы должны вернуть. Поэтому в книге он лежит не в «выручке», а на отдельном счёте «залоги клиентов» (мы **должны**). При возврате счёт обнуляется. Если часть удержали за повреждение — эта часть переезжает в «выручку».
:::

Три операции над залогом, каждая — одна транзакция с проводками:

```ts
// src/data/deposits.ts
import { Prisma } from '../generated/prisma/client.js'
import { prisma } from '../db.js'

const D = Prisma.Decimal
type Tx = Prisma.TransactionClient

async function accounts(tx: Tx) {
  return Object.fromEntries((await tx.ledgerAccount.findMany()).map((a) => [a.code, a.id])) as Record<'CASH' | 'REVENUE' | 'DEPOSITS', number>
}

async function post(tx: Tx, bookingId: number, debit: number, credit: number, amount: Prisma.Decimal) {
  const txId = crypto.randomUUID()
  await tx.ledgerEntry.createMany({ data: [
    { txId, accountId: debit,  amount,            bookingId },     // «+» счёт получил
    { txId, accountId: credit, amount: amount.neg(), bookingId },  // «−» счёт отдал
  ] })
}

/** Баланс залога по брони: сколько мы ещё должны клиенту (деньги в залоге). */
export async function depositBalance(tx: Tx | typeof prisma, bookingId: number): Promise<Prisma.Decimal> {
  const rows = await tx.$queryRaw<{ s: Prisma.Decimal | null }[]>`
    SELECT -sum(e.amount) AS s FROM ledger_entry e JOIN ledger_account a ON a.id = e.account_id
    WHERE a.code = 'DEPOSITS' AND e.booking_id = ${bookingId}`
  return rows[0]?.s ?? new D(0)
}

export async function holdDeposit(bookingId: number, amount: string) {
  const a = new D(amount).toDecimalPlaces(2, D.ROUND_HALF_UP)
  return prisma.$transaction(async (tx) => {
    const acc = await accounts(tx)
    await post(tx, bookingId, acc.CASH, acc.DEPOSITS, a)          // касса +, залоги −
  })
}

export async function settleDeposit(bookingId: number, keep: string) {
  const keepAmt = new D(keep).toDecimalPlaces(2, D.ROUND_HALF_UP)
  return prisma.$transaction(async (tx) => {
    const acc = await accounts(tx)
    const held = await depositBalance(tx, bookingId)               // сколько всего лежит в залоге
    if (keepAmt.gt(held)) throw new Error(`Нельзя удержать ${keepAmt} из залога ${held}`)
    const back = held.minus(keepAmt)
    if (keepAmt.gt(0)) await post(tx, bookingId, acc.DEPOSITS, acc.REVENUE, keepAmt)   // залоги +, выручка −
    if (back.gt(0))    await post(tx, bookingId, acc.DEPOSITS, acc.CASH, back)         // залоги +, касса −
    return { kept: keepAmt, returned: back }
  }, { isolationLevel: Prisma.TransactionIsolationLevel.Serializable })
}
```

```ts
// src/lessons/14-deposit.ts
import { holdDeposit, settleDeposit, depositBalance } from '../data/deposits.js'
import { withRetry } from '../lib/retry.js'
import { prisma } from '../db.js'

const bookingId = 10
await holdDeposit(bookingId, '1000.00')
console.log('залог лежит:', (await depositBalance(prisma, bookingId)).toFixed(2))
console.log(await withRetry(() => settleDeposit(bookingId, '333.33')))             // удержали часть
console.log('залог после возврата:', (await depositBalance(prisma, bookingId)).toFixed(2))   // 0.00
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/14-deposit.ts
```

### result
```out auto
```

Ожидаем: `лежит: 1000.00`, `{ kept: 333.33, returned: 666.67 }` (в сумме ровно тысяча — **копейка не потеряна**: мы считаем «возврат = лежало − удержали», а не `1000 × 2/3`), `после возврата: 0.00`. Обрати внимание на `Serializable` в `settleDeposit`: решение зависит от прочитанного баланса, и параллельная двойная попытка вернуть залог не должна вернуть его дважды (шаг 12.4).

### why
Три правила денежной логики: (1) **считай разницу, а не пропорцию** (`вернуть = всего − удержать`), чтобы остаток не терял копейки при делении; (2) **каждое движение — парная проводка** в одной транзакции; (3) **решение, зависящее от прочитанного баланса, защищено от гонки** (Serializable/блокировка). Нарушение любого — и «деньги не сходятся».

### deep Если не получилось
- **`depositBalance` возвращает `null`/0 после `holdDeposit`** — проводка записана с другим `bookingId`; проверь `SELECT * FROM ledger_entry WHERE booking_id = 10`.
- **`Нельзя удержать …`** — в брони уже была операция по залогу из истории (backfill); выбери бронь без залога или очисти проводки теста.

### quiz
- Почему залог учитывается на отдельном счёте, а не как выручка?
- Почему «вернуть = лежало − удержали», а не доля от суммы?
- Зачем `settleDeposit` выполняется в `Serializable` с повтором?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/queries/transactions | транзакции | Prisma 7: Transactions

## 14.5 Сверка: «деньги не сходятся» и инварианты в базе | short: Сверка и инварианты | est: ~55 мин
### intro
**Слова шага:** *сверка (reconciliation)*, *расхождение*, *инвариант*, *`CONSTRAINT TRIGGER`*, *`DEFERRABLE INITIALLY DEFERRED`*, *баланс ноль*.

:::tip Если совсем просто
Раз в сутки бухгалтерия сверяет «что записали мы» с «что записал банк». Если расходится — ищут, где ошибка. Наша сверка — вопросы, которые **всегда должны давать ноль**: сумма всех проводок, проводки без платежа, платежи без проводок. Лучшие из них мы превратим в **правила базы**, которые не дадут записать абсурд.
:::

Сверка: три запроса, каждый должен вернуть «ничего»:

```bash run
psqlr() { docker exec -i rental-pg psql -U postgres -d rental "$@"; }
psqlr <<'SQL'
-- 1. каждая операция сбалансирована
SELECT tx_id, sum(amount) FROM ledger_entry GROUP BY tx_id HAVING sum(amount) <> 0 LIMIT 5;

-- 2. платёж без проводок (деньги пришли, а в книге нет)
SELECT p.id, p.booking_id, p.amount FROM "tbl_Payments" p
LEFT JOIN ledger_entry e ON e.payment_id = p.id WHERE e.id IS NULL AND p.amount > 0 LIMIT 5;

-- 3. касса = всё принято − всё возвращено по платежам, ± залоги (сверка «книга ↔ платежи»)
SELECT
  (SELECT sum(CASE WHEN kind IN (1,2) THEN amount WHEN kind = 3 THEN -amount END) FROM "tbl_Payments") AS по_платежам,
  (SELECT sum(e.amount) FROM ledger_entry e JOIN ledger_account a ON a.id = e.account_id WHERE a.code = 'CASH' AND e.payment_id IS NOT NULL) AS по_книге_платежи;
SQL
```

### result
```out auto
```

Ожидаем: первые два запроса **пусты**, в третьем числа **равны** (копейка в копейку). Если нет — нашлось расхождение; поиск идёт «сверху вниз»: сначала баланс по операциям, потом наличие проводок, потом суммы.

Теперь превратим первый запрос в **правило базы**: «операцию с несбалансированными проводками записать нельзя». Нужен **отложенный** триггер: проводки одной операции вставляются по очереди, баланс проверяется **в конце транзакции**:

Создай пустую миграцию (`npx prisma migrate dev --create-only --name ledger_balanced`) и замени содержимое её `migration.sql` на этот SQL (метка времени в имени папки у тебя будет своя):

```bash run hidden
cd ~/prisma-lab/rentkit && npx prisma migrate dev --create-only --name ledger_balanced && sleep 1
```

```sql into=prisma/migrations/*_ledger_balanced/migration.sql
-- prisma/migrations/<метка>_ledger_balanced/migration.sql
CREATE FUNCTION ledger_check_balanced() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF (SELECT coalesce(sum(amount), 0) FROM ledger_entry WHERE tx_id = NEW.tx_id) <> 0 THEN
    RAISE EXCEPTION 'ledger: операция % не сбалансирована', NEW.tx_id USING ERRCODE = '23514';
  END IF;
  RETURN NULL;
END $$;

CREATE CONSTRAINT TRIGGER ledger_entry_balanced
  AFTER INSERT ON ledger_entry
  DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION ledger_check_balanced();
```

```bash run
cd ~/prisma-lab/rentkit
npx prisma migrate deploy
cat > src/lessons/14-unbalanced.ts <<'EOF'
import { prisma } from '../db.js'
const acc = await prisma.ledgerAccount.findUniqueOrThrow({ where: { code: 'CASH' } })
try {
  await prisma.ledgerEntry.create({ data: { txId: crypto.randomUUID(), accountId: acc.id, amount: 100, bookingId: 1 } })   // одна нога без пары
  console.log('записано — ПЛОХО')
} catch (e) {
  console.log('отклонено:', String((e as Error).message).split('\n').filter(Boolean).pop())
}
await prisma.$disconnect()
EOF
npx tsx src/lessons/14-unbalanced.ts
```

### result
```out auto
```

Одинокая «нога» проводки отвергается **при фиксации транзакции** (`DEFERRABLE INITIALLY DEFERRED` — проверка откладывается до `COMMIT`, чтобы можно было вставить обе проводки по очереди). Prisma, не знающая о триггере, увидит ошибку базы с кодом `23514` (`check_violation`) — **сверьтесь**, как она обёрнута в вашей версии, так же, как мы изучали в 13.4.

### why
Сверка — инструмент **поиска**, инвариант в базе — инструмент **предотвращения**. Хорошая система использует оба: триггер не даёт записать заведомо неверное, а ночная сверка находит то, что невозможно выразить правилом (расхождение с внешним банком). Сверки не доверяй — **автоматизируй**: она должна запускаться по расписанию и писать в журнал.

### deep Команды по частям
`CONSTRAINT TRIGGER … DEFERRABLE INITIALLY DEFERRED` — триггер, срабатывающий **в конце транзакции**, а не после каждой строки. `FOR EACH ROW` — для каждой вставленной строки (проверка идемпотентна: баланс одной и той же операции проверяется по разу на строку). `RETURN NULL` допустим для `AFTER`-триггера.

### deep Если не получилось
- **Триггер падает на корректных парных вставках** — триггер не отложен (`INITIALLY DEFERRED`), и проверяется после первой строки пары.
- **Миграция не применяется, ссылаясь на `plpgsql`** — язык есть в образе по умолчанию; проверь `\dL` в `psql`.

### quiz
- Зачем триггер сделан отложенным (`DEFERRABLE INITIALLY DEFERRED`)?
- Чем сверка отличается от инварианта в базе и зачем нужны оба?
- Какие три вопроса задаёт сверка книги проводок и что должно получаться?

### links
- https://www.postgresql.org/docs/18/sql-createtrigger.html | CREATE TRIGGER | PostgreSQL 18: CREATE TRIGGER

## 14.6 Аудит: кто, когда и что изменил | short: Аудит | est: ~45 мин
### intro
**Слова шага:** *аудит*, *`audit_log`*, *триггер*, *`to_jsonb(OLD/NEW)`*, *`app.actor`*, *`set_config`*.

:::tip Если совсем просто
Аудит — «камера видеонаблюдения» для данных: любое изменение брони, платежа или залога записывается в журнал вместе со **старым** значением, **новым**, временем и **исполнителем**. Спор «кто поменял статус?» перестаёт быть спором.
:::

Универсальный триггер записывает любую строку «до» и «после» (JSON), а имя исполнителя берёт из параметра сессии `app.actor`, который устанавливает приложение (шаг 16 разовьёт идею):

Создай пустую миграцию (`npx prisma migrate dev --create-only --name audit`) и замени содержимое её `migration.sql` на этот SQL (метка времени в имени папки у тебя будет своя):

```bash run hidden
cd ~/prisma-lab/rentkit && npx prisma migrate dev --create-only --name audit && sleep 1
```

```sql into=prisma/migrations/*_audit/migration.sql
-- prisma/migrations/<метка>_audit/migration.sql
CREATE TABLE "audit_log" (
    "id"         BIGSERIAL PRIMARY KEY,
    "table_name" TEXT NOT NULL,
    "row_id"     TEXT,
    "action"     TEXT NOT NULL,
    "old_row"    JSONB,
    "new_row"    JSONB,
    "actor"      TEXT,
    "at"         TIMESTAMPTZ(3) NOT NULL DEFAULT now()
);
CREATE INDEX "audit_log_table_row_idx" ON "audit_log" ("table_name", "row_id");

CREATE FUNCTION audit_row() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO audit_log (table_name, row_id, action, old_row, new_row, actor)
  VALUES (TG_TABLE_NAME,
          COALESCE((to_jsonb(NEW) ->> 'id'), (to_jsonb(OLD) ->> 'id')),
          TG_OP,
          CASE WHEN TG_OP IN ('UPDATE', 'DELETE') THEN to_jsonb(OLD) END,
          CASE WHEN TG_OP IN ('INSERT', 'UPDATE') THEN to_jsonb(NEW) END,
          current_setting('app.actor', true));
  RETURN NULL;
END $$;

CREATE TRIGGER bookings_audit AFTER INSERT OR UPDATE OR DELETE ON "tbl_Bookings" FOR EACH ROW EXECUTE FUNCTION audit_row();
CREATE TRIGGER payments_audit AFTER INSERT OR UPDATE OR DELETE ON "tbl_Payments" FOR EACH ROW EXECUTE FUNCTION audit_row();
```

Добавь модель `AuditLog` в схему (чтобы таблица не считалась «лишней»; поля `old_row`/`new_row` — `Json?`) и проверь, как выглядит запись:

```prisma schema
model AuditLog {
  id        BigInt   @id @default(autoincrement())
  tableName String   @map("table_name")
  rowId     String?  @map("row_id")
  action    String
  oldRow    Json?    @map("old_row")
  newRow    Json?    @map("new_row")
  actor     String?
  at        DateTime @default(now()) @db.Timestamptz(3)

  @@index([tableName, rowId])
  @@map("audit_log")
}
```

```ts
// src/lessons/14-audit.ts
import { prisma } from '../db.js'

await prisma.$transaction(async (tx) => {
  await tx.$executeRaw`SELECT set_config('app.actor', 'manager:anna', true)`      // true = только до конца транзакции
  await tx.booking.update({ where: { id: 100 }, data: { note: 'клиент просит продлить' } })
})

const rows = await prisma.$queryRaw<{ action: string; actor: string | null; changed: string[] }[]>`
  SELECT action, actor,
         ARRAY(SELECT k FROM jsonb_object_keys(new_row) k WHERE new_row -> k IS DISTINCT FROM old_row -> k) AS changed
  FROM audit_log WHERE table_name = 'tbl_Bookings' AND row_id = '100' ORDER BY id DESC LIMIT 1`
console.log(rows)
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx prisma migrate deploy
npm run generate
npx tsx src/lessons/14-audit.ts
```

### result
```out auto
```

Ожидаем: действие `UPDATE`, исполнитель `manager:anna`, изменённое поле — `note`. Три момента: (1) запись аудита идёт **в той же транзакции**, что и изменение — нет изменения без записи и записи без изменения; (2) исполнитель передаётся **параметром сессии** `app.actor` (`set_config(..., true)` — действует только до конца текущей транзакции — это важно и для пула соединений, шаг 16.4); (3) триггер работает для **любого** писателя, включая `psql` и старый код (где `actor` будет пустым — и это тоже сигнал).

### why
Аудит в приложении можно «забыть» (один из сотни путей записи обойдёт его); аудит в базе — нельзя. Для денег, статусов, прав доступа он обязателен. Цена — место и небольшая нагрузка на запись; если таблица огромная, аудит партиционируют и хранят ограниченное время.

### deep Как ещё можно
Для подробного аудита существуют расширения (`pgaudit`) и CDC-системы. Но для «кто что поменял в этих двух таблицах» триггер с `jsonb` — простое и честное решение.

### deep Если не получилось
- **`actor` пустой** — `set_config` вызван **вне** транзакции с `true` (параметр тут же сбросился) или в другом соединении; проверь, что вызов и `update` внутри одной интерактивной транзакции.
- **`to_jsonb(NEW) ->> 'id'` не находит поле** — у таблицы нет колонки `id`; для таких таблиц передай идентификатор иначе.

### quiz
- Почему аудит триггером надёжнее аудита в коде приложения?
- Что делает `set_config('app.actor', …, true)` и почему важен третий параметр?
- Почему запись аудита должна быть в той же транзакции, что и изменение?

### links
- https://www.postgresql.org/docs/18/plpgsql-trigger.html | триггерные функции | PostgreSQL 18: Trigger Functions
- https://www.postgresql.org/docs/18/functions-admin.html#FUNCTIONS-ADMIN-SET | set_config | PostgreSQL 18: set_config

## 14.7 🔨 «Платёж прошёл дважды при ретрае» и «возврат больше на копейку» | short: 🔨 Дубль и копейка | est: ~60 мин
### intro
**Слова шага:** *жалоба заказчика*, *ключ, зависящий от времени*, *потеря идемпотентности*, *округление долей*, *сверка до копейки*.

:::tip Если совсем просто
Две жалобы бухгалтерии в один день: «клиент заплатил один раз, а в книге два платежа» и «возврат за отмену на копейку больше, чем платили». Обе — следствия мелких ошибок в коде, которые не видны на тестах.
:::

*Бухгалтерия:* «Три платежа за неделю записаны дважды при сетевых сбоях. И по возвратам итог расходится: вернули больше, чем получили, на сумму в несколько копеек за сутки».

Нерабочая версия:

```ts
// src/lessons/14-broken-payment.ts
import { Prisma } from '../generated/prisma/client.js'
import { prisma } from '../db.js'

// шлюз повторяет запрос при сетевом сбое — наш код генерирует ключ САМ при каждой попытке:
export async function chargeBroken(bookingId: number, amount: number) {
  const extRef = `PAY-${bookingId}-${Date.now()}`                  // ← уникален на КАЖДУЮ попытку
  return prisma.payment.create({ data: { bookingId, amount: new Prisma.Decimal(amount), kind: 1, extRef, paidAt: new Date() } })
}

// возврат доли предоплаты: «30 % от 999.99»
export function refundShareBroken(paid: number) {
  return Math.round(paid * 0.3 * 100) / 100                        // ← float и округление «по-школьному» на двоичной дроби
}

// 1. дубли при ретрае
const a = await chargeBroken(1, 150.5)
const b = await chargeBroken(1, 150.5)        // «тот же» платёж повторили
console.log('платежей на одну попытку:', a.id !== b.id ? 2 : 1)

// 2. разница на копейки
const total = [999.99, 1000.01, 0.35, 1.15, 8.345, 12.285].map((x) => refundShareBroken(x))
console.log(total, total.reduce((s, x) => s + x, 0))
await prisma.payment.deleteMany({ where: { extRef: { startsWith: 'PAY-1-' } } })
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/14-broken-payment.ts
```

### result
```out auto
```

**Твоя задача:** (1) объяснить **две** причины: почему ретрай создаёт второй платёж (ключ зависит от времени — у каждой попытки он новый) и откуда копейки (двоичное `float` и `Math.round`); (2) исправить обе: идемпотентный ключ должен приходить **извне** (от шлюза: номер заказа/платежа) или вычисляться **детерминированно** из бизнес-данных (`booking + тип + номер платежа`), никогда не из времени; долю считать на `Decimal` с **явным** правилом округления и **остатком**: «первая часть = `round(доля)`, вторая = `всего − первая`» — сумма частей должна равняться целому; (3) покрыть проверкой: **1 000 платежей с 10 % повторов**, запущенных параллельно, — число записей равно числу **уникальных** ключей, а сумма в `payments` равна сумме в книге проводок до копейки.

**Приёмка сессии:** журнал проводок заполнен и сбалансирован, `recordPayment` идемпотентен (параллельные повторы дают одну запись), залог проходит весь цикл с нулевым остатком, сверка «платежи ↔ книга» даёт ноль, аудит фиксирует исполнителя; на прогоне 1 000 платежей с повторами баланс сходится **до копейки**, числа записаны в `NOTES.md`.

### why
Эти два дефекта — классика денежных багов. Первый («идемпотентный ключ из времени») делает защиту фиктивной; второй («доля на float») тихо копит копейки. Для обоих нужна не «аккуратность», а **конструкция**, которая исключает ошибку: ключ приходит снаружи, а остаток считается вычитанием.

### deep Если не получилось
- **Подсказка к (1):** ключ — `${bookingId}-${kind}-${номер_попытки_платежа_из_заказа}` или внешний `payment_id` шлюза; повтор должен давать **тот же** ключ.
- **Подсказка к (2):** `const first = paid.times('0.3').toDecimalPlaces(2, ROUND_HALF_UP); const rest = paid.minus(first)`.
- **Тест расходится на копейку** — проверь, что в книге `amount` положительная для `kind ∈ {1,2}` и отрицательная для возврата (знаки из `recordPayment`).

### quiz
- Почему идемпотентный ключ не может зависеть от времени запроса?
- Как делить сумму на части без потери копеек?
- Что должен доказать тест «1 000 платежей с повторами»?

### links
- https://stripe.com/docs/api/idempotent_requests | идемпотентные запросы | Stripe: Idempotent requests
