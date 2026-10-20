# Сессия 13 · Двойная бронь: диапазоны и exclusion constraint
dur: ~4 ч

## 13.1 Двойные брони в наследстве: находим пересечения | short: Поиск пересечений | est: ~40 мин
### intro
**Слова шага:** *диапазон (`tstzrange`)*, *оператор `&&`*, *пересечение*, *границы `[)`*, *разбор конфликтов*, *журнал исправлений*.

:::tip Если совсем просто
Расписание переговорной: событие с 10:00 до 11:00 и событие с 10:30 до 11:30 в одну комнату не помещаются. Мы будем хранить время брони как **диапазон** — и спрашивать у PostgreSQL: «пересекаются ли эти два диапазона?» (`&&`). В нашей базе такие пересечения уже случились — найдём их.
:::

Дата начала и конца теперь настоящие `timestamptz` (сессия 10). Диапазон — от начала до **следующей полуночи** дня возврата, границы `[)`: левая включена, правая — нет. Поэтому бронь, которая заканчивается в день возврата, и бронь, которая начинается на следующий день, **не пересекаются**:

```bash run
psqlr() { docker exec -i rental-pg psql -U postgres -d rental "$@"; }
psqlr <<'SQL'
-- сколько пересекающихся пар у одного предмета (отменённые и не пришедшие предмет не занимают)
SELECT count(*) AS пар_пересечений
FROM "tbl_Bookings" a
JOIN "tbl_Bookings" b
  ON a.item_id = b.item_id AND a.id < b.id
 AND tstzrange(a.starts_at, a.ends_at, '[)') && tstzrange(b.starts_at, b.ends_at, '[)')
WHERE a.status NOT IN ('CANCELLED', 'NO_SHOW', 'DRAFT')
  AND b.status NOT IN ('CANCELLED', 'NO_SHOW', 'DRAFT');

-- как они выглядят: первые 5 пар
SELECT a.id AS a_id, b.id AS b_id, a.item_id,
       a.starts_at::date AS a_с, a.ends_at::date AS a_по, b.starts_at::date AS b_с, b.ends_at::date AS b_по,
       a.status AS a_ст, b.status AS b_ст
FROM "tbl_Bookings" a
JOIN "tbl_Bookings" b ON a.item_id = b.item_id AND a.id < b.id
 AND tstzrange(a.starts_at, a.ends_at, '[)') && tstzrange(b.starts_at, b.ends_at, '[)')
WHERE a.status NOT IN ('CANCELLED', 'NO_SHOW', 'DRAFT') AND b.status NOT IN ('CANCELLED', 'NO_SHOW', 'DRAFT')
ORDER BY a.id LIMIT 5;
SQL
```

### result
```out auto
```

Ожидаем порядка **полутораста пар**: в каждой — один и тот же предмет, выданный (или забронированный) двум клиентам на пересекающиеся даты. Это не «ошибка в коде», а реальный инцидент: кому-то пришлось отказать. Нужно принять **деловое решение** по каждой паре; для упражнения примем простое правило: **более позднюю по номеру бронь снимаем** (переводим в `CANCELLED`) и фиксируем в журнале, чтобы менеджеры связались с клиентами.

```sql
-- prisma/migrations/20261022100000_resolve_overlaps/migration.sql
CREATE TABLE "overlap_fix_log" (
    "booking_id"    INTEGER PRIMARY KEY,
    "kept_booking"  INTEGER NOT NULL,
    "old_status"    "BookingStatus" NOT NULL,
    "fixed_at"      TIMESTAMPTZ(3) NOT NULL DEFAULT now()
);

INSERT INTO "overlap_fix_log" (booking_id, kept_booking, old_status)
SELECT DISTINCT ON (b.id) b.id, a.id, b.status
FROM "tbl_Bookings" a
JOIN "tbl_Bookings" b ON a.item_id = b.item_id AND a.id < b.id
 AND tstzrange(a.starts_at, a.ends_at, '[)') && tstzrange(b.starts_at, b.ends_at, '[)')
WHERE a.status NOT IN ('CANCELLED', 'NO_SHOW', 'DRAFT') AND b.status NOT IN ('CANCELLED', 'NO_SHOW', 'DRAFT')
ORDER BY b.id, a.id;

UPDATE "tbl_Bookings" SET status = 'CANCELLED', note = coalesce(note || '; ', '') || 'снята как двойная бронь'
WHERE id IN (SELECT booking_id FROM "overlap_fix_log");
```

Добавь модель журнала в схему (`OverlapFixLog`), создай и применить миграцию, и проверь, что пересечений не осталось:

```bash run
cd ~/prisma-lab/rentkit
npx prisma migrate deploy
psqlr() { docker exec -i rental-pg psql -U postgres -d rental "$@"; }
psqlr -c "SELECT count(*) AS пересечений_осталось FROM \"tbl_Bookings\" a JOIN \"tbl_Bookings\" b ON a.item_id = b.item_id AND a.id < b.id AND tstzrange(a.starts_at, a.ends_at, '[)') && tstzrange(b.starts_at, b.ends_at, '[)') WHERE a.status NOT IN ('CANCELLED','NO_SHOW','DRAFT') AND b.status NOT IN ('CANCELLED','NO_SHOW','DRAFT')"
psqlr -c 'SELECT count(*) AS снято FROM overlap_fix_log'
```

### result
```out auto
```

Критерий: пересечений — **0**, в журнале — столько же строк, сколько было «лишних» броней. **Цепочки:** если три брони пересекаются друг с другом, `DISTINCT ON (b.id)` выберет для каждой «позднейшей» одну парную, и после одного прохода могут остаться ещё пересечения — повторяй проверку до нуля (в наших данных пересечения только парные).

### why
Прежде чем ставить ограничение, нужно **вылечить уже существующее**: база не позволит создать `EXCLUDE`-ограничение, пока в таблице есть нарушения. И решение «какую бронь снять» — деловое, а не техническое: поэтому оно записывается в журнал и передаётся людям.

### deep Команды по частям
`tstzrange(a, b, '[)')` — диапазон моментов; `&&` — «пересекаются»; `DISTINCT ON (b.id)` — для каждой «поздней» брони взять одну запись; `coalesce(note || '; ', '')` — дописать в заметку, не потеряв прежнюю (если заметки нет, `NULL || …` даст `NULL`, поэтому `coalesce`).

### deep Если не получилось
- **Пересечений после миграции больше нуля** — были цепочки из трёх; повтори вставку в журнал и `UPDATE` (в миграции-«доводке», не правя применённую).
- **Тип `"BookingStatus"` не найден в журнале** — тип создан в миграции из шага 10.3; проверь `migrate status`.

### quiz
- Что делает оператор `&&` и в чём смысл границ `[)`?
- Почему «пересекающиеся брони» нужно сначала исправить, а потом ставить ограничение?
- Почему решение, какую бронь снять, фиксируют в журнале?

### links
- https://www.postgresql.org/docs/18/rangetypes.html | диапазонные типы | PostgreSQL 18: Range Types
- https://www.postgresql.org/docs/18/functions-range.html | функции диапазонов | PostgreSQL 18: Range Functions and Operators

## 13.2 Проверка «в коде» не спасает: гонка | short: Гонка при бронировании | est: ~45 мин
### intro
**Слова шага:** *проверка перед вставкой*, *TOCTOU*, *гонка*, *параллельное бронирование*, *демонстрация*.

:::tip Если совсем просто
Кассир смотрит в тетрадь: «на эту неделю самокат свободен» — и пишет «забронировано». Двое кассиров смотрят **одновременно** — оба видят «свободно» — оба пишут. Двойная бронь. «Проверить, потом записать» нельзя разорвать на два шага, если рядом работает кто-то ещё.
:::

Наивная функция бронирования — проверка в коде:

```ts
// src/lessons/13-naive.ts
import { prisma } from '../db.js'

const day = (s: string) => new Date(s + 'T00:00:00Z')

export async function bookNaive(itemId: number, from: string, to: string, customerId = 1) {
  const clash = await prisma.booking.findFirst({
    where: { itemId, status: { in: ['CONFIRMED', 'ISSUED'] }, startsAt: { lt: day(to) }, endsAt: { gt: day(from) } },
  })
  if (clash) return false                                           // занято
  await prisma.booking.create({ data: { itemId, customerId, branchId: 1, status: 'CONFIRMED', startsAt: day(from), endsAt: day(to) } })
  return true
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const item = await prisma.item.create({ data: { sku: 'SKU-RACE-' + Date.now(), title: 'Самокат для гонки', branchId: 1, category: 'Самокат', active: 1 } })
  const results = await Promise.all(Array.from({ length: 30 }, () => bookNaive(item.id, '2031-07-01', '2031-07-04')))
  console.log('«успешных» бронирований одного предмета на одни даты:', results.filter(Boolean).length)
  await prisma.booking.deleteMany({ where: { itemId: item.id } })
  await prisma.item.delete({ where: { id: item.id } })
  await prisma.$disconnect()
}
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/13-naive.ts
```

### result
```out auto
```

Ожидаем число **больше одного**: сколько-то параллельных вызовов увидели «свободно» и успели записать. Результат нарушает главный инвариант прокатной сети. Повторные запуски дают разные числа — типичный признак гонки.

### why
Это та же гонка «проверить — создать» из шага 7.7, но здесь ставка выше: в данных живут **одновременно две брони** на один предмет, и кто-то придёт и не получит его. Подобные дефекты почти не воспроизводятся при ручном тестировании и всплывают в «час пик».

### deep Почему не помогает `Serializable`
Можно обернуть проверку и запись в транзакцию `Serializable` с повтором (шаг 12.4), и она бы сработала. Но это дорогое решение: каждая бронь превращается в повторяемую конкурентную транзакцию. Правило экономнее: если инвариант можно выразить **ограничением** в базе, пусть его гарантирует база — это дешевле и надёжнее (шаг 13.3).

### deep Если не получилось
- **Всегда 1 успешное** — запросы слишком быстрые; увеличь число вызовов до 100 или добавь паузу между проверкой и записью.
- **`Unique constraint failed on sku`** — предыдущий запуск не убрал за собой предмет; удали `SKU-RACE-*` вручную.

### quiz
- Почему «проверить в коде, потом записать» не защищает от двойной брони?
- Почему повторные запуски дают разное число успешных бронирований?
- Какой уровень изоляции мог бы решить задачу и почему мы выберем другой путь?

### links
- https://en.wikipedia.org/wiki/Time-of-check_to_time-of-use | TOCTOU | Wikipedia: Time-of-check to time-of-use

## 13.3 EXCLUDE-ограничение на диапазоне: база сама не пустит пересечение | short: EXCLUDE | est: ~60 мин
### intro
**Слова шага:** *exclusion constraint*, *`EXCLUDE USING gist`*, *`btree_gist`*, *генерируемая колонка `period`*, *`Unsupported("tstzrange")`*, *частичное ограничение*.

:::tip Если совсем просто
`UNIQUE` говорит «двух одинаковых значений быть не может». `EXCLUDE` — обобщение: «двух строк, у которых **предмет совпадает** и **диапазоны пересекаются**, быть не может». Ограничение живёт в базе, проверяется при каждой записи и **не зависит** от того, кто и как пишет (Prisma, `psql`, чужой скрипт). Гонка невозможна: база сама расставит проверки.
:::

```svg
@exclude-constraint
```

Нужны: расширение `btree_gist` (чтобы сравнивать обычное `=` и диапазонное `&&` в одном индексе) и колонка-диапазон. Делаем её **генерируемой** — база сама строит диапазон из `starts_at`/`ends_at`:

```sql
-- prisma/migrations/20261022110000_booking_no_overlap/migration.sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

ALTER TABLE "tbl_Bookings"
  ADD COLUMN "period" tstzrange GENERATED ALWAYS AS (tstzrange("starts_at", "ends_at", '[)')) STORED;

-- один предмет не может быть занят двумя «живыми» бронями на пересекающиеся даты
ALTER TABLE "tbl_Bookings"
  ADD CONSTRAINT "bookings_no_overlap"
  EXCLUDE USING gist ("item_id" WITH =, "period" WITH &&)
  WHERE ("status" IN ('CONFIRMED', 'ISSUED', 'RETURNED', 'OVERDUE', 'DAMAGED'));
```

Условие `WHERE (…)` делает ограничение **частичным**: отменённые, «не пришёл» и черновики предмет не занимают. В схеме Prisma диапазон описывается как `Unsupported` (клиент его не понимает, но **знает, что колонка существует**), и обязательно **необязательным** (`?`) — иначе клиент не сможет создавать брони:

```prisma
model Booking {
  // …
  period Unsupported("tstzrange")?
  // …
}
```

```bash run
cd ~/prisma-lab/rentkit
npx prisma migrate deploy
npx prisma generate
npx prisma migrate dev --create-only --name should_be_empty_exclude
psqlr() { docker exec -i rental-pg psql -U postgres -d rental -c "$@"; }
psqlr "SELECT conname, contype FROM pg_constraint WHERE conname = 'bookings_no_overlap'"
npx tsx src/lessons/13-naive.ts
```

### result
```out auto
```

Ожидаем: миграция применилась (если упала — значит, остались пересечения, шаг 13.1); `migrate dev --create-only` сообщает «Already in sync» (**сверьтесь**: Prisma не должна пытаться удалить `EXCLUDE` и генерируемую колонку; если пытается — не применяй миграцию); **вместо числа > 1 теперь ровно 1 успешная бронь**, остальные упали с нарушением ограничения (мы ещё не умеем красиво его ловить — это шаг 13.4).

### why
Гонку закрыла **база**, а не код: проверка выполняется атомарно внутри команды `INSERT`, а индекс GiST делает её быстрой. Это тот самый выход за пределы схемы Prisma, о котором мы говорили в 8.5: часть ограничений ORM не описывает, но уважает. Правило: **если инвариант можно выразить ограничением, ограничение лучше проверки в коде.**

### deep Команды по частям
`GENERATED ALWAYS AS (…) STORED` — колонка, значение которой база считает сама и хранит (нельзя писать в неё напрямую). `EXCLUDE USING gist (item_id WITH =, period WITH &&)` — «две строки не могут одновременно иметь равный `item_id` и пересекающиеся `period`». `btree_gist` нужен потому, что GiST по умолчанию не умеет оператор `=` для целых чисел. Частичное условие `WHERE` берёт на себя «живые» статусы: перевод брони в `CANCELLED` сразу освобождает предмет.

### deep Если не получилось
- **`ERROR: could not create exclusion constraint … conflicting key value`** — есть пересечения: вернись к 13.1 и найди (`status` в `WHERE` должен совпадать).
- **`generation expression is not immutable`** — в выражении колонки стоит неиммутабельная функция; `tstzrange(timestamptz, timestamptz, text)` иммутабельна — проверь, что ты не добавила `now()` или приведение типов, зависящее от пояса.
- **Prisma просит `Unsupported` обязательным** — поле должно быть `?`.

### quiz
- Чем `EXCLUDE` отличается от `UNIQUE` и что значит «с оператором `&&`»?
- Зачем нужно расширение `btree_gist`?
- Почему колонка `period` описана в схеме Prisma как необязательная `Unsupported`?

### links
- https://www.postgresql.org/docs/18/sql-createtable.html#SQL-CREATETABLE-EXCLUDE | EXCLUDE | PostgreSQL 18: CREATE TABLE — EXCLUDE
- https://www.postgresql.org/docs/18/btree-gist.html | btree_gist | PostgreSQL 18: btree_gist
- https://www.prisma.io/docs/orm/v7/prisma-schema/data-model/unsupported-database-features | неподдерживаемые возможности | Prisma 7: Unsupported database features

## 13.4 Ловим нарушение в клиенте: «предмет занят» | short: Ловим 23P01 | est: ~45 мин
### intro
**Слова шага:** *код `23P01` (exclusion_violation)*, *имя ограничения*, *доменная ошибка*, *определение типа ошибки*, *`e.meta`*.

:::tip Если совсем просто
Когда база отказала, она сообщает **какое именно правило нарушено**: «нарушено ограничение `bookings_no_overlap`». Наша задача — узнать это сообщение в коде и перевести на язык приложения: «предмет уже занят на эти даты». Вопрос в том, **в каком виде** ошибка дойдёт до нас — это зависит от версии Prisma и адаптера, поэтому сначала посмотрим на неё глазами.
:::

Сначала «разведка»: что именно приходит в `catch`.

```ts
// src/lessons/13-error.ts
import { prisma } from '../db.js'

const item = await prisma.item.create({ data: { sku: 'SKU-ERR-' + Date.now(), title: 'Тест ошибки', branchId: 1, category: 'Самокат', active: 1 } })
const mk = () => prisma.booking.create({ data: { itemId: item.id, branchId: 1, status: 'CONFIRMED', startsAt: new Date('2032-01-01T00:00:00Z'), endsAt: new Date('2032-01-03T00:00:00Z') } })
await mk()
try {
  await mk()                                              // та же бронь: нарушит ограничение
} catch (e: any) {
  console.log('класс:', e.constructor.name)
  console.log('code:', e.code)
  console.log('meta:', JSON.stringify(e.meta))
  console.log('message:', String(e.message).split('\n').filter(Boolean).slice(-2).join(' | '))
}
await prisma.booking.deleteMany({ where: { itemId: item.id } })
await prisma.item.delete({ where: { id: item.id } })
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/13-error.ts
```

### result
```out auto
```

Посмотри на вывод и ответь себе: какой класс, какой `code`, где в `meta`/`message` встречается имя `bookings_no_overlap` или код `23P01`. Это **зависит от версии**: Prisma могла обернуть ошибку как «неизвестную» (`PrismaClientUnknownRequestError`) либо как `PrismaClientKnownRequestError` с кодом (например, `P2010` для raw-запросов). Надёжный способ — опираться на **имя ограничения**, которое всегда присутствует в тексте или в данных об ошибке базы. Напиши функцию определения и доменную ошибку:

```ts
// src/lib/errors.ts — дополнить
export class ItemBusyError extends Error {
  constructor(public itemId: number) { super(`Предмет ${itemId} занят на эти даты`) }
}

/** Ограничение bookings_no_overlap нарушено? Проверяем и текст ошибки, и данные драйвера. */
export function isOverlapViolation(e: unknown): boolean {
  const text = [(e as any)?.message, JSON.stringify((e as any)?.meta ?? {})].join(' ')
  return text.includes('bookings_no_overlap') || text.includes('23P01')
}
```

```ts
// src/data/bookings.ts
import { prisma } from '../db.js'
import { ItemBusyError, isOverlapViolation } from '../lib/errors.js'

export async function createBooking(input: { itemId: number; customerId: number; branchId: number; startsAt: Date; endsAt: Date }) {
  try {
    return await prisma.booking.create({ data: { ...input, status: 'CONFIRMED' } })
  } catch (e) {
    if (isOverlapViolation(e)) throw new ItemBusyError(input.itemId)
    throw e
  }
}
```

### result
```out auto
```

(Результат этого блока — вывод `13-error.ts`, повторно запущенного после подстановки функции: класс/код/сообщение у тебя могут отличаться, это ожидаемо.) **Правило:** распознавание ошибки базы вынесено в **одну функцию** (`isOverlapViolation`) — если в Prisma изменится формат, поправим один файл.

### why
Ограничения в базе без аккуратной обработки превращаются в безликие `500 Internal Server Error`. Хорошая система отвечает человеку: «предмет занят на эти даты, выберите другие». Заодно ты видишь общий принцип: **доверяй ограничению, а не проверке; ограничение сообщает, что нарушено, а ты переводишь это в слова.**

### deep Как ещё можно
Для ошибок, которые Prisma не классифицирует, обращаются к `meta.driverAdapterError` или (в raw-запросах) к `e.meta.code` — он содержит исходный код PostgreSQL (`23P01`). **Сверьтесь** с точным видом данных ошибки в вашей версии: напечатай `console.dir(e, { depth: 5 })`.

### deep Если не получилось
- **`isOverlapViolation` не срабатывает** — формат ошибки иной; выведи весь объект (`console.dir`) и подберите признак; не опирайся на локализованный текст сообщения.
- **Вторая бронь прошла** — ограничение не создано или статусы в `WHERE` не включают `CONFIRMED` (шаг 13.3).

### quiz
- Почему мы определяем нарушение по имени ограничения, а не по тексту сообщения PostgreSQL?
- Зачем преобразовывать ошибку базы в доменную (`ItemBusyError`)?
- Где в коде должно жить распознавание таких ошибок и почему в одном месте?

### links
- https://www.postgresql.org/docs/18/errcodes-appendix.html | коды ошибок | PostgreSQL 18: Error Codes (23P01)
- https://www.prisma.io/docs/orm/v7/reference/error-reference#p2010 | P2010 | Prisma 7: Error reference P2010

## 13.5 Часовые пояса филиалов: «день» зависит от того, где ты | short: Дни и часовые пояса | est: ~45 мин
### intro
**Слова шага:** *день филиала*, *`AT TIME ZONE`*, *границы суток*, *момент vs день*, *`tz` в `tbl_Branches`*, *длительность в «днях»*.

:::tip Если совсем просто
«С 1 по 3 декабря» — это три **местных** дня. Для Москвы день 1 декабря начинается в 00:00 по Москве; для Владивостока — в 00:00 по Владивостоку, а это на 7 часов **раньше** по мировому времени. Если сохранить границы в одном поясе для всех, бронь «поплывёт» относительно часов филиала и у кого-то будет «лишний день».
:::

Помощник, который превращает **календарные даты** в **моменты** по поясу филиала — выполняем его в базе, где пояса знают лучше всего:

```ts
// src/lib/branch-day.ts
import { prisma } from '../db.js'

/** Диапазон бронирования по календарным датам филиала: с начала дня from до начала дня после to (включительно). */
export async function branchRange(branchId: number, from: string, to: string): Promise<{ startsAt: Date; endsAt: Date }> {
  const [r] = await prisma.$queryRaw<{ s: Date; e: Date }[]>`
    SELECT (${from}::date::timestamp AT TIME ZONE tz)           AS s,
           ((${to}::date + 1)::timestamp AT TIME ZONE tz)       AS e
    FROM "tbl_Branches" WHERE id = ${branchId}`
  if (!r) throw new Error(`Филиал ${branchId} не найден`)
  return { startsAt: r.s, endsAt: r.e }
}
```

```ts
// src/lessons/13-tz.ts
import { branchRange } from '../lib/branch-day.js'
import { prisma } from '../db.js'

for (const [id, name] of [[1, 'Москва'], [7, 'Владивосток']] as const) {
  const r = await branchRange(id, '2031-12-01', '2031-12-03')
  console.log(name.padEnd(12), r.startsAt.toISOString(), '→', r.endsAt.toISOString(), `(${(r.endsAt.getTime() - r.startsAt.getTime()) / 3_600_000} ч)`)
}
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/13-tz.ts
```

### result
```out auto
```

Ожидаем: у Москвы начало `2031-11-30T21:00:00.000Z` (00:00 МСК = 21:00 UTC предыдущего дня), у Владивостока — `2031-11-30T14:00:00.000Z` (00:00 по Владивостоку = 14:00 UTC); длительность одинакова — **72 часа** (три суток). Моменты разные, дни — те же. Правило: **«день» — понятие места**; перевод в момент всегда идёт через пояс филиала, и этот пояс **хранится в данных** (`tbl_Branches.tz`), а не зашит в код.

Ещё одно следствие: «длительность в днях» для тарифа считай по **местным** суткам, а не по `Math.ceil(часы / 24)`; в странах с переходом на летнее время сутки бывают 23 или 25 часов (в России перевода нет с 2014 года, но код филиалов за границей уже столкнётся).

### why
Ошибки поясов не падают с исключением — они дают **тихо неверные данные**: бронь, которая «закончилась вчера», хотя клиент ещё катается. Единственный надёжный способ — иметь **один** вспомогательный модуль, который превращает дни в моменты, и пользоваться только им.

### deep Команды по частям
`'2031-12-01'::date::timestamp AT TIME ZONE 'Asia/Vladivostok'` — берём календарную дату, делаем из неё «голый» момент 00:00 и **говорим, в каком поясе это местное время**; результат — настоящий момент (`timestamptz`). `($to::date + 1)` — «на следующий день» (правая граница `[)` не включена: бронь включает весь день возврата).

### deep Если не получилось
- **`time zone "Asia/Barnaul" not recognized`** — в вашей сборке PostgreSQL нет такого пояса (базы tzdata); проверь `SELECT name FROM pg_timezone_names WHERE name LIKE 'Asia/Barnaul'`.
- **Одинаковые моменты у Москвы и Владивостока** — `tz` у филиалов пустые или одинаковые; смотри `SELECT id, tz FROM "tbl_Branches"`.

### quiz
- Почему «1 декабря» — это разные моменты в Москве и во Владивостоке?
- Где должен храниться часовой пояс филиала и почему не в коде?
- Что неверно в формуле «длительность в днях = часы / 24»?

### links
- https://www.postgresql.org/docs/18/datatype-datetime.html#DATATYPE-TIMEZONES | часовые пояса | PostgreSQL 18: Time Zones

## 13.6 Доступность: «какие предметы свободны на даты» | short: Свободные предметы | est: ~50 мин
### intro
**Слова шага:** *доступность*, *`NOT EXISTS`*, *anti-join*, *GiST-индекс ограничения*, *TypedSQL*, *`EXPLAIN`*.

:::tip Если совсем просто
Клиент спрашивает: «есть ли в Новосибирске свободные лыжи с 5 по 8 января?» Ответ: «все лыжи филиала, **кроме** тех, у кого есть живая бронь, пересекающаяся с этими датами». «Кроме тех, у кого есть» — это `NOT EXISTS`: самая быстрая форма вопроса «а есть ли хоть одна такая».
:::

Запрос в TypedSQL (диапазоны Prisma-клиент не выразит, поэтому — файл `.sql`):

```sql
-- prisma/sql/freeItems.sql
-- @param {Int} $1:branchId
-- @param {String} $2:category
-- @param {DateTime} $3:startsAt
-- @param {DateTime} $4:endsAt
SELECT i.id, i.sku, i.title
FROM "tbl_Items" i
WHERE i.branch_id = $1
  AND i.category = $2
  AND i.active = 1
  AND NOT EXISTS (
    SELECT 1 FROM "tbl_Bookings" b
    WHERE b.item_id = i.id
      AND b.status IN ('CONFIRMED', 'ISSUED', 'RETURNED', 'OVERDUE', 'DAMAGED')
      AND b.period && tstzrange($3, $4, '[)')
  )
ORDER BY i.id
LIMIT 20
```

```ts
// src/data/availability.ts
import { prisma } from '../db.js'
import { freeItems } from '../generated/prisma/sql/index.js'
import { branchRange } from '../lib/branch-day.js'

export async function findFree(branchId: number, category: string, from: string, to: string) {
  const { startsAt, endsAt } = await branchRange(branchId, from, to)
  return prisma.$queryRawTyped(freeItems(branchId, category, startsAt, endsAt))
}

if (import.meta.url === `file://${process.argv[1]}`) {
  console.log(await findFree(5, 'Лыжи', '2026-01-05', '2026-01-08'))
  await prisma.$disconnect()
}
```

```bash run
cd ~/prisma-lab/rentkit
npx prisma generate --sql
npx tsx src/data/availability.ts
psqlr() { docker exec -i rental-pg psql -U postgres -d rental -c "$@"; }
psqlr "EXPLAIN (ANALYZE) SELECT i.id FROM \"tbl_Items\" i WHERE i.branch_id = 5 AND i.category = 'Лыжи' AND NOT EXISTS (SELECT 1 FROM \"tbl_Bookings\" b WHERE b.item_id = i.id AND b.status IN ('CONFIRMED','ISSUED') AND b.period && tstzrange(now(), now() + interval '3 days', '[)'))"
```

### result
```out auto
```

Что смотреть в плане: подзапрос `NOT EXISTS` должен идти через **индекс ограничения** `bookings_no_overlap` (GiST по `item_id` и `period`): `Index Scan using bookings_no_overlap` или `Bitmap Index Scan`. Один и тот же индекс **и охраняет** уникальность, **и ускоряет** поиск свободных предметов — приятный бонус ограничения. Если в плане `Seq Scan` по броням — условие не совпадает с условием индекса (проверь, что в запросе тот же набор статусов).

### why
Поиск доступности — самый частый запрос системы бронирований, и `NOT EXISTS` против диапазонов — его канонический вид. Типизированный `.sql` файл делает его безопасным (параметры — значения, типы результата из базы), а индекс — быстрым.

### deep Если не получилось
- **`Unknown type DateTime in @param`** — типы в `-- @param` берутся из набора, который поддерживает TypedSQL (`Int`, `String`, `DateTime`, `Boolean`, …); смотри **сверьтесь** список в документации.
- **Пустой список** — все лыжи филиала заняты на эти даты (маловероятно) или `active = 1` не подходит; убери условия по одному.

### quiz
- Почему `NOT EXISTS` обычно лучше, чем `LEFT JOIN … IS NULL` для «нет пересечений»?
- Какой индекс ускоряет проверку пересечения диапазонов?
- Что даёт TypedSQL по сравнению с `$queryRaw<Row[]>` в таком запросе?

### links
- https://www.postgresql.org/docs/18/queries-table-expressions.html#QUERIES-FROM | JOIN и подзапросы | PostgreSQL 18: Table Expressions
- https://www.prisma.io/docs/orm/v7/prisma-client/using-raw-sql/typedsql | TypedSQL | Prisma 7: TypedSQL

## 13.7 🔨 Бронь «исчезает» на границе суток | short: 🔨 Граница суток | est: ~55 мин
### intro
**Слова шага:** *жалоба заказчика*, *сутки в UTC и местные*, *`date_trunc`*, *`AT TIME ZONE`*, *отчёт «за день»*.

:::tip Если совсем просто
Менеджер Владивостока говорит: «Утром первого числа бронь есть в системе, а в отчёте „брони за 1 число“ её нет — вместо этого она в отчёте за 30-е». Для программиста «первое число» — это 1 декабря по мировому времени; для менеджера — по часам филиала. Эти «первые числа» начинаются в разное время.
:::

*Заказчик:* «Отчёт „брони, начинающиеся 1 декабря“ по Владивостоку недосчитывается нескольких броней, а в отчёте за 30 ноября они есть. Бронь на самом деле начинается 1-го в 00:00».

Воспроизведи на данных:

```ts
// src/lessons/13-boundary.ts
import { prisma } from '../db.js'

// «за 1 декабря» наивно: по дате в UTC
const naive = await prisma.$queryRaw<{ n: bigint }[]>`
  SELECT count(*) AS n FROM "tbl_Bookings" WHERE branch_id = 7 AND starts_at::date = date '2025-12-01'`   // ::date берёт пояс СЕССИИ (UTC)
console.log('по UTC-датам:', Number(naive[0]!.n))

// правильно: по местным суткам филиала
const local = await prisma.$queryRaw<{ n: bigint }[]>`
  SELECT count(*) AS n
  FROM "tbl_Bookings" b JOIN "tbl_Branches" br ON br.id = b.branch_id
  WHERE b.branch_id = 7 AND (b.starts_at AT TIME ZONE br.tz)::date = date '2025-12-01'`
console.log('по местным датам:', Number(local[0]!.n))
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/13-boundary.ts
```

### result
```out auto
```

Числа отличаются: брони филиала начинаются в местную полночь (00:00 по Владивостоку = 14:00 UTC **предыдущего** дня), поэтому «по UTC» они попадают в **предыдущую** дату. Ровно это и видит менеджер. **Твоя задача:** найти все места в слое данных, где «дата» берётся из момента без указания пояса филиала (приведение `::date`, `date_trunc('day', …)`, группировка по `starts_at`), и **исправить** их через пояс (`AT TIME ZONE tz`); написать функцию `bookingsStartingOn(branchId, 'YYYY-MM-DD')`, считающую по местным суткам, и проверить на трёх филиалах с разными поясами (Москва, Новосибирск, Владивосток) — числа должны совпасть с суммой по настоящим датам начала.

**Приёмка сессии:** все пересечения в наследстве устранены (журнал), ограничение `bookings_no_overlap` применено; параллельное бронирование (100 вызовов `createBooking` одного предмета на одни даты) даёт **ровно одну** успешную бронь, остальные — `ItemBusyError`; `findFree` отвечает по индексу ограничения; границы суток считаются по поясу филиала (отчёт сверен с «ручным» подсчётом).

### why
Это самый частый вид «тихой» ошибки времени: код правильный, данные правильные, а день в отчёте — не тот. Лечится одной дисциплиной: **любая операция «в днях» делается в поясе филиала, и ни одна — в поясе сессии.**

### deep Если не получилось
- **Числа не отличаются** — выбран филиал в поясе UTC+3 (Москва) при сессии UTC: разница 3 часа, но «полночь МСК» = 21:00 UTC предыдущего дня тоже отличается; проверь именно филиал 7 (Владивосток, UTC+10).
- **Не понимаешь, откуда `::date` берёт пояс** — пояс сессии PostgreSQL (`SHOW timezone`) — в нашем контейнере UTC.
- **Подсказка для функции:** `(starts_at AT TIME ZONE tz)::date` — «локальная дата начала»; для диапазона дат — `starts_at >= начало_дня AND starts_at < начало_следующего` через `branchRange`.

### quiz
- Почему `starts_at::date` даёт «не ту» дату для филиала в другом поясе?
- Как правильно посчитать «брони за день» для филиала?
- Какое одно правило защищает от всей этой группы ошибок?

### links
- https://www.postgresql.org/docs/18/functions-datetime.html#FUNCTIONS-DATETIME-ZONECONVERT | AT TIME ZONE | PostgreSQL 18: AT TIME ZONE
