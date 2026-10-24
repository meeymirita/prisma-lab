# Сессия 11 · Чистка данных II: ключи, дубли, команда
dur: ~4 ч

## 11.1 Осиротевшие строки: находим и решаем, что с ними делать | short: Сироты | est: ~45 мин
### intro
**Слова шага:** *осиротевшая строка*, *`LEFT JOIN … IS NULL`*, *заглушка «неизвестный»*, *журнал исправлений*, *решение вместо удаления*.

:::tip Если совсем просто
Сирота — бронь, которая ссылается на клиента или предмет, которых в базе нет. Внешний ключ их бы не пустил, но у нас ключей не было. Прежде чем добавить ключ, нужно решить судьбу каждой сироты: **удалить**, **привязать к заглушке «неизвестный клиент»** или **найти настоящего**. Удалять брони с платежами — нельзя, там деньги.
:::

Сначала найдём всех сирот по всем связям (результат запомни в `NOTES.md`):

```bash run
psqlr() { docker exec -i rental-pg psql -U postgres -d rental "$@"; }
psqlr <<'SQL'
SELECT 'бронь → клиент' AS связь, count(*) AS сирот
FROM "tbl_Bookings" b LEFT JOIN "tbl_Customers" c ON c.id = b.cust_id WHERE b.cust_id IS NOT NULL AND c.id IS NULL
UNION ALL SELECT 'бронь → предмет', count(*)
FROM "tbl_Bookings" b LEFT JOIN "tbl_Items" i ON i.id = b.item_id WHERE b.item_id IS NOT NULL AND i.id IS NULL
UNION ALL SELECT 'бронь → филиал', count(*)
FROM "tbl_Bookings" b LEFT JOIN "tbl_Branches" br ON br.id = b.branch_id WHERE b.branch_id IS NOT NULL AND br.id IS NULL
UNION ALL SELECT 'платёж → бронь', count(*)
FROM "tbl_Payments" p LEFT JOIN "tbl_Bookings" b ON b.id = p.booking_id WHERE p.booking_id IS NOT NULL AND b.id IS NULL
UNION ALL SELECT 'залог → бронь', count(*)
FROM "tbl_DepositLog" d LEFT JOIN "tbl_Bookings" b ON b.id = d.booking_id WHERE d.booking_id IS NOT NULL AND b.id IS NULL;
-- есть ли у броней-сирот платежи (то есть деньги)?
SELECT count(DISTINCT b.id) AS броней_сирот_с_платежами
FROM "tbl_Bookings" b
JOIN "tbl_Payments" p ON p.booking_id = b.id
LEFT JOIN "tbl_Customers" c ON c.id = b.cust_id
WHERE b.cust_id IS NOT NULL AND c.id IS NULL;
SQL
```

### result
```out auto
```

Ожидаем: около полутора тысяч броней без клиента, около девятисот без предмета, платежей и залогов-сирот нет, а у большинства броней-сирот **платежи есть** — значит, удалять их нельзя. Решение (его принимает человек, мы его **записываем**): для клиентов создадим служебную запись «Неизвестный клиент» и привяжем к ней сирот, а для предметов поставим **пустое значение** (`NULL`), исходные значения сохраним в журнале. Почему не «Неизвестный предмет» по аналогии? Девятьсот броней на одном выдуманном предмете оказались бы «заняты» им одновременно и породили бы сотни ложных двойных броней — это мы увидим в сессии 13, когда сделаем проверку занятости (проверено: такой «предмет» дал 673 лишних пересечения из 806). Клиенту «много броней сразу» не вредит, предмету — вредит. Миграция:

Создай пустую миграцию (`npx prisma migrate dev --create-only --name orphans_to_unknown`) и замени содержимое её `migration.sql` на этот SQL (метка времени в имени папки у тебя будет своя):

```bash run hidden
cd ~/prisma-lab/rentkit && npx prisma migrate dev --create-only --name orphans_to_unknown && sleep 1
```

```sql into=prisma/migrations/*_orphans_to_unknown/migration.sql
-- prisma/migrations/<метка>_orphans_to_unknown/migration.sql
CREATE TABLE "orphan_log" (
    "booking_id"  INTEGER PRIMARY KEY,
    "old_cust_id" INTEGER,
    "old_item_id" INTEGER,
    "fixed_at"    TIMESTAMPTZ(3) NOT NULL DEFAULT now()
);

-- служебная запись без привязки к филиалу (branch_id = NULL): тогда миграция проигрывается и на пустой базе (шаг 18.3)
INSERT INTO "tbl_Customers" ("CustName", branch_id, created_at) VALUES ('Неизвестный клиент (архив)', NULL, now());

INSERT INTO "orphan_log" (booking_id, old_cust_id, old_item_id)
SELECT b.id,
       CASE WHEN c.id IS NULL THEN b.cust_id END,
       CASE WHEN i.id IS NULL THEN b.item_id END
FROM "tbl_Bookings" b
LEFT JOIN "tbl_Customers" c ON c.id = b.cust_id
LEFT JOIN "tbl_Items" i ON i.id = b.item_id
WHERE (b.cust_id IS NOT NULL AND c.id IS NULL) OR (b.item_id IS NOT NULL AND i.id IS NULL);

UPDATE "tbl_Bookings" b SET cust_id = (SELECT id FROM "tbl_Customers" WHERE "CustName" = 'Неизвестный клиент (архив)')
WHERE b.id IN (SELECT booking_id FROM "orphan_log" WHERE old_cust_id IS NOT NULL);
UPDATE "tbl_Bookings" b SET item_id = NULL
WHERE b.id IN (SELECT booking_id FROM "orphan_log" WHERE old_item_id IS NOT NULL);
```

Добавь в схему модель для журнала (чтобы Prisma не считала таблицу «лишней»), примени миграцию и перепроверь:

```prisma schema
model OrphanLog {
  bookingId Int      @id @map("booking_id")
  oldCustId Int?     @map("old_cust_id")
  oldItemId Int?     @map("old_item_id")
  fixedAt   DateTime @default(now()) @map("fixed_at") @db.Timestamptz(3)
  @@map("orphan_log")
}
```

```bash run
cd ~/prisma-lab/rentkit
npx prisma migrate dev
psqlr() { docker exec -i rental-pg psql -U postgres -d rental "$@"; }
psqlr -c 'SELECT count(*) AS сирот_после FROM "tbl_Bookings" b LEFT JOIN "tbl_Customers" c ON c.id = b.cust_id LEFT JOIN "tbl_Items" i ON i.id = b.item_id WHERE (b.cust_id IS NOT NULL AND c.id IS NULL) OR (b.item_id IS NOT NULL AND i.id IS NULL)'
psqlr -c 'SELECT count(*) AS в_журнале FROM orphan_log'
```

### result
```out auto
```

Критерий: **сирот — ноль**, в `orphan_log` — столько же строк, сколько нашлось (минус пересечения: бронь могла быть сиротой по обеим связям — это одна строка журнала).

### why
Решение «что делать с испорченными данными» — не техническое, а **деловое**: удалить, исправить или пометить. Задача разработчика — найти, посчитать, предложить и **записать**, что именно сделано, чтобы через год можно было ответить «а что это за „Неизвестный клиент“?».

### deep Если не получилось
- **Сирот больше, чем в первом запросе** — служебные клиент/предмет получили новые `id` — проверь, что `UPDATE` использует подзапрос по имени, а не фиксированный номер.
- **`migrate dev` создал свой SQL, а не мой** — ты применила миграцию не с `--create-only`; пересоздай, поправив файл до применения.

### quiz
- Почему сирот с платежами нельзя просто удалить?
- Что такое журнал исправлений и зачем он нужен?
- Кто принимает решение, что делать с осиротевшими данными?

### links
- https://www.postgresql.org/docs/18/queries-table-expressions.html#QUERIES-FROM | JOIN | PostgreSQL 18: Table Expressions

## 11.2 Внешние ключи на живой таблице: NOT VALID → VALIDATE | short: Внешние ключи | est: ~55 мин
### intro
**Слова шага:** *`FOREIGN KEY`*, *`NOT VALID`*, *`VALIDATE CONSTRAINT`*, *блокировки*, *`ON DELETE`*, *переключение `relationMode`*, *`P2003`*.

:::tip Если совсем просто
Добавить внешний ключ на большую таблицу — значит проверить **каждую строку**. Если сделать это одним махом, таблица на время проверки «замирает». У PostgreSQL есть приём в два шага: сначала поставить ключ **«для будущих записей»** (мгновенно, строки не проверяются) — `NOT VALID`; потом **проверить уже существующее** (`VALIDATE`) — долго, но без остановки записи.
:::

```svg
@fk-two-step
```

Сироты закончились (11.1). Теперь ключи. Первая миграция — «мягкая» (`NOT VALID`):

Создай пустую миграцию (`npx prisma migrate dev --create-only --name fk_not_valid`) и замени содержимое её `migration.sql` на этот SQL (метка времени в имени папки у тебя будет своя):

```bash run hidden
cd ~/prisma-lab/rentkit && npx prisma migrate dev --create-only --name fk_not_valid && sleep 1
```

```sql into=prisma/migrations/*_fk_not_valid/migration.sql
-- prisma/migrations/<метка>_fk_not_valid/migration.sql
ALTER TABLE "tbl_Bookings" ADD CONSTRAINT "tbl_Bookings_cust_id_fkey"   FOREIGN KEY ("cust_id")   REFERENCES "tbl_Customers"("id") ON DELETE SET NULL ON UPDATE CASCADE NOT VALID;
ALTER TABLE "tbl_Bookings" ADD CONSTRAINT "tbl_Bookings_item_id_fkey"   FOREIGN KEY ("item_id")   REFERENCES "tbl_Items"("id")     ON DELETE SET NULL ON UPDATE CASCADE NOT VALID;
ALTER TABLE "tbl_Bookings" ADD CONSTRAINT "tbl_Bookings_branch_id_fkey" FOREIGN KEY ("branch_id") REFERENCES "tbl_Branches"("id")  ON DELETE SET NULL ON UPDATE CASCADE NOT VALID;
ALTER TABLE "tbl_Items"    ADD CONSTRAINT "tbl_Items_branch_id_fkey"    FOREIGN KEY ("branch_id") REFERENCES "tbl_Branches"("id")  ON DELETE SET NULL ON UPDATE CASCADE NOT VALID;
ALTER TABLE "tbl_Customers" ADD CONSTRAINT "tbl_Customers_branch_id_fkey" FOREIGN KEY ("branch_id") REFERENCES "tbl_Branches"("id") ON DELETE SET NULL ON UPDATE CASCADE NOT VALID;
-- деньги не должны исчезать вместе с бронью: RESTRICT
ALTER TABLE "tbl_Payments"   ADD CONSTRAINT "tbl_Payments_booking_id_fkey"   FOREIGN KEY ("booking_id") REFERENCES "tbl_Bookings"("id") ON DELETE RESTRICT ON UPDATE CASCADE NOT VALID;
ALTER TABLE "tbl_DepositLog" ADD CONSTRAINT "tbl_DepositLog_booking_id_fkey" FOREIGN KEY ("booking_id") REFERENCES "tbl_Bookings"("id") ON DELETE RESTRICT ON UPDATE CASCADE NOT VALID;
```

Имена ключей `<таблица>_<колонка>_fkey` совпадают с теми, что дала бы Prisma, — поэтому она потом признает их своими. Вторая миграция — проверка уже существующих строк (отдельным файлом, чтобы её можно было запустить в удобное время):

Создай пустую миграцию (`npx prisma migrate dev --create-only --name fk_validate`) и замени содержимое её `migration.sql` на этот SQL (метка времени в имени папки у тебя будет своя):

```bash run hidden
cd ~/prisma-lab/rentkit && npx prisma migrate dev --create-only --name fk_validate && sleep 1
```

```sql into=prisma/migrations/*_fk_validate/migration.sql
-- prisma/migrations/<метка>_fk_validate/migration.sql
ALTER TABLE "tbl_Bookings"   VALIDATE CONSTRAINT "tbl_Bookings_cust_id_fkey";
ALTER TABLE "tbl_Bookings"   VALIDATE CONSTRAINT "tbl_Bookings_item_id_fkey";
ALTER TABLE "tbl_Bookings"   VALIDATE CONSTRAINT "tbl_Bookings_branch_id_fkey";
ALTER TABLE "tbl_Items"      VALIDATE CONSTRAINT "tbl_Items_branch_id_fkey";
ALTER TABLE "tbl_Customers"  VALIDATE CONSTRAINT "tbl_Customers_branch_id_fkey";
ALTER TABLE "tbl_Payments"   VALIDATE CONSTRAINT "tbl_Payments_booking_id_fkey";
ALTER TABLE "tbl_DepositLog" VALIDATE CONSTRAINT "tbl_DepositLog_booking_id_fkey";
```

Теперь схема: убираем `relationMode = "prisma"` (по умолчанию связи — настоящие ключи) и уточняем `onDelete` у денег:

```prisma schema
datasource db {
  provider = "postgresql"
}
```

```prisma
model Payment {
  // …
  booking Booking? @relation(fields: [bookingId], references: [id], onDelete: Restrict)
}
model DepositLog {
  // …
  booking Booking? @relation(fields: [bookingId], references: [id], onDelete: Restrict)
}
```

```bash run hidden
cd ~/prisma-lab/rentkit && sed -i -E 's/(booking +Booking\? +@relation\(fields: \[bookingId\], references: \[id\])\)/\1, onDelete: Restrict)/' prisma/schema.prisma
```

```bash run
cd ~/prisma-lab/rentkit
npx prisma migrate deploy
npx prisma migrate dev --create-only --name should_be_empty_fk
cat prisma/migrations/*_should_be_empty_fk/migration.sql
rm -r prisma/migrations/*_should_be_empty_fk
npm run generate
```

### result
```out auto
```

Ожидаем: обе миграции применены, а черновик `should_be_empty_fk` пуст (Prisma узнала твои ключи; если в нём появились `DROP CONSTRAINT`/`ADD CONSTRAINT` — сравни имена и `ON DELETE/UPDATE` с тем, что генерирует Prisma). Проверим, что ключи **работают** и что теперь возможен код `P2003`:

```ts
// src/lessons/11-fk.ts
import { Prisma } from '../generated/prisma/client.js'
import { prisma } from '../db.js'

// 1. попытка сослаться на несуществующего клиента: база теперь не пустит
try {
  await prisma.$executeRaw`INSERT INTO "tbl_Bookings" (cust_id, status) VALUES (999999999, 'DRAFT')`
} catch (e) {
  console.log('вставка сироты:', (e as Error).message.trim().split('\n').filter(Boolean).at(-1))
}

// 2. попытка удалить бронь с платежами: RESTRICT → P2003
try {
  await prisma.booking.delete({ where: { id: 1 } })
} catch (e) {
  if (e instanceof Prisma.PrismaClientKnownRequestError) console.log('код:', e.code)
}
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/11-fk.ts
```

### result
```out auto
```

(Файл `11-fk.ts` лежит в `src/lessons`, который мы вывели из проверки типов в шаге 10.6 — `tsx` его всё равно запустит.) Вставка сироты теперь отвергается базой (`violates foreign key constraint`), а удаление брони с платежами даёт **`P2003`** — тот самый код, которого не было в сессии 7.

### why
Внешний ключ — единственный способ, чтобы целостность проверяла **база**, а не «все, кто пишет в неё, должны помнить». Двухшаговый `NOT VALID → VALIDATE` — стандартный рецепт на больших таблицах: новые записи защищены сразу, а проверка старых идёт без остановки работы.

### deep Команды по частям
`ON DELETE SET NULL` — при удалении родителя поле-ссылка у детей становится `NULL` (бронь остаётся без клиента); `RESTRICT` — удаление родителя **запрещено**, пока есть дети; `CASCADE` — дети удаляются вместе с родителем (для денег — опасно). `NOT VALID` — ключ действует для новых и изменённых строк, существующие не проверяются; `VALIDATE CONSTRAINT` — проверяет существующие (берёт слабую блокировку, запись продолжается).

### deep Если не получилось
- **`VALIDATE` падает: `insert or update … violates foreign key constraint`** — остались сироты (шаг 11.1) — найди их запросом и исправь.
- **Prisma хочет пересоздать ключи** — не совпали имена или поведение (`ON UPDATE`): посмотри миграцию `should_be_empty_fk`; **не применяй её**, если она удаляет и создаёт те же ключи; поправь `onDelete/onUpdate` в схеме под те, что в базе.

### quiz
- Зачем делать внешний ключ в два шага и чем отличаются эти шаги?
- Чем `RESTRICT` отличается от `SET NULL` и почему для платежей выбран именно он?
- Какой код ошибки Prisma появляется при нарушении внешнего ключа?

### links
- https://www.postgresql.org/docs/18/sql-altertable.html#SQL-ALTERTABLE-DESC-ADD-TABLE-CONSTRAINT | ADD CONSTRAINT | PostgreSQL 18: ALTER TABLE
- https://www.prisma.io/docs/orm/v7/prisma-schema/data-model/relations/referential-actions | ссылочные действия | Prisma 7: Referential actions

## 11.3 unique, check, NOT NULL: добавляем без долгой блокировки | short: Ограничения | est: ~50 мин
### intro
**Слова шага:** *`CHECK … NOT VALID`*, *`SET NOT NULL`*, *`UNIQUE INDEX`*, *`CONCURRENTLY`*, *дедупликация перед `unique`*.

:::tip Если совсем просто
Ограничения — «правила дома»: «конец брони позже начала», «платёж без суммы не бывает», «один внешний номер платежа — один платёж». Их добавляют так же осторожно, как ключи: сначала для новых, потом проверка старых. А прежде чем требовать уникальности, надо убрать уже существующие дубли.
:::

**Дубли платежей.** В шаге 3.1 мы нашли около трёх тысяч повторных `ext_ref`. Это ретраи шлюза: деньги пришли один раз, строка записана дважды. Решение — оставить **первую** запись, остальные убрать с **журналом**:

Создай пустую миграцию (`npx prisma migrate dev --create-only --name payments_dedupe`) и замени содержимое её `migration.sql` на этот SQL (метка времени в имени папки у тебя будет своя):

```bash run hidden
cd ~/prisma-lab/rentkit && npx prisma migrate dev --create-only --name payments_dedupe && sleep 1
```

```sql into=prisma/migrations/*_payments_dedupe/migration.sql
-- prisma/migrations/<метка>_payments_dedupe/migration.sql
CREATE TABLE "payment_dup_log" AS
SELECT p.*, now() AS removed_at
FROM "tbl_Payments" p
WHERE p.ext_ref IS NOT NULL
  AND EXISTS (SELECT 1 FROM "tbl_Payments" q WHERE q.ext_ref = p.ext_ref AND q.id < p.id);

DELETE FROM "tbl_Payments" p
USING "payment_dup_log" l WHERE p.id = l.id;
```

(Таблица журнала — «просто таблица» без модели Prisma: добавь её в схему как `model PaymentDupLog` с `@@ignore` или оформи полноценной моделью — иначе Prisma предложит её удалить.)

Затем сами ограничения — **в виде `CHECK … NOT VALID` и `UNIQUE`**:

Создай пустую миграцию (`npx prisma migrate dev --create-only --name constraints`) и замени содержимое её `migration.sql` на этот SQL (метка времени в имени папки у тебя будет своя):

```bash run hidden
cd ~/prisma-lab/rentkit && npx prisma migrate dev --create-only --name constraints && sleep 1
```

```sql into=prisma/migrations/*_constraints/migration.sql
-- prisma/migrations/<метка>_constraints/migration.sql

-- конец брони строго позже начала; сумма и залог не отрицательны
ALTER TABLE "tbl_Bookings" ADD CONSTRAINT bookings_period_ck CHECK (ends_at > starts_at) NOT VALID;
ALTER TABLE "tbl_Bookings" ADD CONSTRAINT bookings_money_ck  CHECK (total >= 0 AND deposit >= 0) NOT VALID;
ALTER TABLE "tbl_Bookings" VALIDATE CONSTRAINT bookings_period_ck;
ALTER TABLE "tbl_Bookings" VALIDATE CONSTRAINT bookings_money_ck;

-- NOT NULL без долгой блокировки: сначала проверяемое CHECK-условие, потом SET NOT NULL
ALTER TABLE "tbl_Bookings" ADD CONSTRAINT bookings_nn_ck CHECK (starts_at IS NOT NULL AND ends_at IS NOT NULL AND status IS NOT NULL) NOT VALID;
ALTER TABLE "tbl_Bookings" VALIDATE CONSTRAINT bookings_nn_ck;
ALTER TABLE "tbl_Bookings" ALTER COLUMN starts_at SET NOT NULL, ALTER COLUMN ends_at SET NOT NULL, ALTER COLUMN status SET NOT NULL;
ALTER TABLE "tbl_Bookings" DROP CONSTRAINT bookings_nn_ck;

-- платежи: сумма и дата обязательны, ext_ref уникален
ALTER TABLE "tbl_Payments" ADD CONSTRAINT payments_nn_ck CHECK (amount IS NOT NULL AND paid_at IS NOT NULL) NOT VALID;
ALTER TABLE "tbl_Payments" VALIDATE CONSTRAINT payments_nn_ck;
ALTER TABLE "tbl_Payments" ALTER COLUMN amount SET NOT NULL, ALTER COLUMN paid_at SET NOT NULL;
ALTER TABLE "tbl_Payments" DROP CONSTRAINT payments_nn_ck;
CREATE UNIQUE INDEX "tbl_Payments_ext_ref_key" ON "tbl_Payments"("ext_ref");
```

И в схеме: обязательные поля (`startsAt DateTime`, `endsAt DateTime`, `status BookingStatus`, у платежа `amount Decimal`, `paidAt DateTime`), `@unique` на `extRef` у платежа, а `CHECK` Prisma не описывает (они живут только в SQL; проверено на 7.10: `migrate diff` базы со схемой их не замечает и удалять не предлагает).

```prisma schema hidden
model Booking {
  id         Int            @id @default(autoincrement())
  customerId Int?           @map("cust_id")
  itemId     Int?           @map("item_id")
  branchId   Int?           @map("branch_id")
  startsAt   DateTime       @map("starts_at") @db.Timestamptz(3)
  endsAt     DateTime       @map("ends_at") @db.Timestamptz(3)
  total      Decimal?       @db.Decimal(12, 2)
  deposit    Decimal?       @db.Decimal(12, 2)
  status     BookingStatus
  note       String?

  customer   Customer?    @relation(fields: [customerId], references: [id])
  item       Item?        @relation(fields: [itemId], references: [id])
  branch     Branch?      @relation(fields: [branchId], references: [id])
  payments   Payment[]
  depositLog DepositLog[]

  @@index([customerId])
  @@index([itemId])
  @@index([branchId])
  @@index([branchId, status, id(sort: Desc)], name: "bookings_branch_status_id")
  @@map("tbl_Bookings")
}

model Payment {
  id        Int      @id @default(autoincrement())
  bookingId Int?     @map("booking_id")
  amount    Decimal  @db.Decimal(12, 2)
  paidAt    DateTime @map("paid_at") @db.Timestamptz(3)
  kind      Int?     @db.SmallInt
  extRef    String?  @unique @map("ext_ref")

  booking Booking? @relation(fields: [bookingId], references: [id], onDelete: Restrict)

  @@index([bookingId])
  @@map("tbl_Payments")
}

model PaymentDupLog {
  id        Int?
  bookingId Int?      @map("booking_id")
  amount    Decimal?  @db.Decimal(12, 2)
  paidAt    DateTime? @map("paid_at") @db.Timestamptz(3)
  kind      Int?      @db.SmallInt
  extRef    String?   @map("ext_ref")
  removedAt DateTime? @map("removed_at") @db.Timestamptz(6)

  @@map("payment_dup_log")
  @@ignore
}
```

```bash run
cd ~/prisma-lab/rentkit
npx prisma migrate deploy
npm run generate
psqlr() { docker exec -i rental-pg psql -U postgres -d rental -c "$@"; }
psqlr "SELECT conname, convalidated FROM pg_constraint WHERE conrelid = '\"tbl_Bookings\"'::regclass AND contype IN ('c','f') ORDER BY 1"
psqlr "SELECT count(*) AS дублей_ext_ref FROM (SELECT ext_ref FROM \"tbl_Payments\" GROUP BY 1 HAVING count(*) > 1) t"
```

### result
```out auto
```

Ожидаем: ограничения `…_ck` и ключи со `convalidated = t`; дублей `ext_ref` — 0. Шаблон «`CHECK NOT VALID` → `VALIDATE` → `SET NOT NULL` → `DROP CONSTRAINT`» работает потому, что PostgreSQL, увидев проверенное `CHECK (col IS NOT NULL)`, **не сканирует таблицу повторно** при `SET NOT NULL` (с версии 12). `CREATE UNIQUE INDEX` на большой таблице в продакшне делают с `CONCURRENTLY` — но такая команда **нельзя** выполнять внутри транзакции, а миграция Prisma выполняется одним скриптом: отдельная миграция из одной команды (проверено на 7.10: файл `migration.sql` с одной строкой `CREATE INDEX CONCURRENTLY …` применяется `migrate deploy` без ошибок; несколько команд в одном файле с `CONCURRENTLY` не смешивай).

### why
Ограничения — вторая линия обороны после типов: даже если код ошибётся, база не даст записать абсурд («конец раньше начала»). А аккуратное введение ограничений на живой таблице превращает «страшную» операцию в рутину.

### deep Если не получилось
- **`VALIDATE` падает на `bookings_period_ck`** — в данных встретились брони с `ends_at <= starts_at` (мы искали их в 10.3); реши, что с ними делать (поменять местами, исключить, пометить) и запиши в `NOTES.md`.
- **`SET NOT NULL` долго «висит»** — не было проверенного `CHECK` (шаг пропущен) и PostgreSQL сканирует таблицу под блокировкой; сначала `ADD CONSTRAINT … NOT VALID`, потом `VALIDATE`.
- **Prisma хочет удалить `CHECK`-ограничение** — не должна (Prisma их не видит); если хочет — не применяй миграцию.

### quiz
- Почему перед `UNIQUE` на `ext_ref` пришлось удалять дубли и что мы записали в журнал?
- Как поставить `NOT NULL` на большой таблице без долгой блокировки?
- Что Prisma умеет описывать в схеме из ограничений, а что остаётся только в SQL?

### links
- https://www.postgresql.org/docs/18/sql-altertable.html | ALTER TABLE | PostgreSQL 18: ALTER TABLE
- https://www.postgresql.org/docs/18/ddl-constraints.html | ограничения | PostgreSQL 18: Constraints

## 11.4 Дубли клиентов: нормализация и слияние в транзакции | short: Слияние дублей | est: ~65 мин
### intro
**Слова шага:** *нормализация телефона*, *генерируемая колонка*, *кластер дублей*, *master-запись*, *слияние (merge)*, *журнал слияния*, *`$transaction`*.

:::tip Если совсем просто
Один и тот же человек записан как «+7 912 345-67-89», «8-912-345-67-89» и «ИВАН ИВАНОВ». Для программы это три разных клиента. Слияние — это «объединить личные дела»: выбрать главное дело, перенести в него все бронь и платежи остальных, а лишние дела закрыть — но **записать**, что с чем объединили.
:::

**Шаг 1 — нормализованный телефон** (генерируемая колонка: база сама считает «последние 10 цифр»):

Создай пустую миграцию (`npx prisma migrate dev --create-only --name customer_phone_norm`) и замени содержимое её `migration.sql` на этот SQL (метка времени в имени папки у тебя будет своя):

```bash run hidden
cd ~/prisma-lab/rentkit && npx prisma migrate dev --create-only --name customer_phone_norm && sleep 1
```

```sql into=prisma/migrations/*_customer_phone_norm/migration.sql
-- prisma/migrations/<метка>_customer_phone_norm/migration.sql
ALTER TABLE "tbl_Customers" ADD COLUMN "phone_norm" TEXT
  GENERATED ALWAYS AS (right(regexp_replace("phone", '\D', '', 'g'), 10)) STORED;

CREATE TABLE "customer_merge_log" (
    "dup_id"    INTEGER PRIMARY KEY,
    "master_id" INTEGER NOT NULL,
    "merged_at" TIMESTAMPTZ(3) NOT NULL DEFAULT now()
);
```

```prisma schema
model Customer {
  // …поля как раньше…
  phoneNorm String? @default(dbgenerated()) @map("phone_norm")
}

model CustomerMergeLog {
  dupId    Int      @id @map("dup_id")
  masterId Int      @map("master_id")
  mergedAt DateTime @default(now()) @map("merged_at") @db.Timestamptz(3)

  @@map("customer_merge_log")
}
```

В схему — поле `phoneNorm` у `Customer` и модель `CustomerMergeLog` (по образцу `OrphanLog`), как в блоке выше. Обрати внимание на **`@default(dbgenerated())`** у `phoneNorm`: Prisma не умеет описывать генерируемые колонки, а без этой пометки она считает, что у колонки есть «значение по умолчанию, которого нет в схеме», и в **каждую** следующую миграцию дописывает `ALTER COLUMN "phone_norm" DROP DEFAULT` — а PostgreSQL на генерируемой колонке отвечает ошибкой `column "phone_norm" … is a generated column`, и миграция падает уже на shadow-базе (проверено). Пустое `dbgenerated()` говорит Prisma: «значение по умолчанию задаёт база, не трогай». Поле читай сколько угодно, но **никогда не пиши** — колонку считает база.

**Шаг 2 — найти кластеры** (перед слиянием — посмотри глазами):

```bash run
cd ~/prisma-lab/rentkit
npx prisma migrate deploy
psqlr() { docker exec -i rental-pg psql -U postgres -d rental "$@"; }
psqlr <<'SQL'
SELECT phone_norm, count(*) AS записей, array_agg(id ORDER BY id) AS ids, array_agg("CustName" ORDER BY id) AS names
FROM "tbl_Customers" WHERE phone_norm IS NOT NULL AND phone_norm <> ''
GROUP BY 1 HAVING count(*) > 1 ORDER BY 2 DESC, 1 LIMIT 3;
SELECT count(*) AS клиентов_в_дублях FROM (SELECT 1 FROM "tbl_Customers" WHERE phone_norm <> '' GROUP BY phone_norm HAVING count(*) > 1) t;
SELECT count(*) AS всего_клиентов FROM "tbl_Customers";
SQL
```

### result
```out auto
```

**Шаг 3 — слияние** одной транзакцией (Prisma, интерактивная `$transaction`): кластер целиком, либо ничего. Master — запись с наименьшим `id`.

```ts
// scripts/merge-customers.ts
import { prisma } from '../src/db.js'

const result = await prisma.$transaction(async (tx) => {
  // 1. кто чей дубль
  await tx.$executeRaw`
    INSERT INTO "customer_merge_log" (dup_id, master_id)
    SELECT id, master FROM (
      SELECT id, min(id) OVER (PARTITION BY phone_norm) AS master
      FROM "tbl_Customers" WHERE phone_norm IS NOT NULL AND phone_norm <> ''
    ) m WHERE id <> master
    ON CONFLICT (dup_id) DO NOTHING`

  // 2. master дополняется тем, чего у него нет (email)
  await tx.$executeRaw`
    UPDATE "tbl_Customers" c SET email = COALESCE(c.email, d.email)
    FROM (SELECT l.master_id, max(dc.email) AS email FROM "customer_merge_log" l JOIN "tbl_Customers" dc ON dc.id = l.dup_id GROUP BY l.master_id) d
    WHERE c.id = d.master_id AND c.email IS NULL`

  // 3. брони дублей переезжают на master
  const moved = await tx.$executeRaw`
    UPDATE "tbl_Bookings" b SET cust_id = l.master_id FROM "customer_merge_log" l WHERE b.cust_id = l.dup_id`

  // 4. дубли удаляются
  const removed = await tx.$executeRaw`
    DELETE FROM "tbl_Customers" c USING "customer_merge_log" l WHERE c.id = l.dup_id`
  return { moved, removed }
}, { timeout: 120_000, maxWait: 10_000 })

console.log(result)
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx scripts/merge-customers.ts
psqlr() { docker exec -i rental-pg psql -U postgres -d rental "$@"; }
psqlr <<'SQL'
SELECT count(*) AS клиентов_после FROM "tbl_Customers";
SELECT count(*) AS дублей_после FROM (SELECT 1 FROM "tbl_Customers" WHERE phone_norm <> '' GROUP BY phone_norm HAVING count(*) > 1) t;
SELECT count(*) AS броней_без_клиента FROM "tbl_Bookings" b LEFT JOIN "tbl_Customers" c ON c.id = b.cust_id WHERE b.cust_id IS NOT NULL AND c.id IS NULL;
SELECT count(*) AS в_журнале FROM "customer_merge_log";
SQL
```

### result
```out auto
```

Критерии: дублей после — **ноль**; брони без клиента — **ноль** (внешний ключ из 11.2 не дал бы удалить клиента, у которого остались брони — `ON DELETE SET NULL` обнулил бы ссылки, поэтому порядок `UPDATE → DELETE` важен); число клиентов уменьшилось на размер журнала. **Шаг 4 — уникальность**: теперь телефон можно сделать уникальным:

Создай пустую миграцию (`npx prisma migrate dev --create-only --name customer_phone_unique`) и замени содержимое её `migration.sql` на этот SQL (метка времени в имени папки у тебя будет своя):

```bash run hidden
cd ~/prisma-lab/rentkit && npx prisma migrate dev --create-only --name customer_phone_unique && sleep 1
```

```sql into=prisma/migrations/*_customer_phone_unique/migration.sql
-- prisma/migrations/<метка>_customer_phone_unique/migration.sql
CREATE UNIQUE INDEX "tbl_Customers_phone_norm_key" ON "tbl_Customers"("phone_norm") WHERE "phone_norm" <> '';
```

(В схеме Prisma частичный уникальный индекс не выражается — оставь миграцию SQL-ной; частичные индексы Prisma, как мы видели в 8.5, не удаляет.) Гонку «проверить, потом создать» из 7.7 закрывает именно этот индекс: теперь второй одновременный `create` получит `P2002`.

### why
Слияние дублей — классическая «задача на аккуратность»: легко удалить лишнее, трудно потом восстановить. Единая транзакция гарантирует, что мы не останемся в промежуточном состоянии, а журнал — что можно ответить «кто был кем». Нормализованный телефон, посчитанный **базой** (generated column), надёжнее, чем нормализация в коде: она работает для любого, кто пишет в таблицу.

### deep Как ещё можно
Если нужна «нечёткая» дедупликация (опечатки в именах), используют `pg_trgm` (`similarity()`), но слияние по такому признаку **всегда** требует человека: ошибочное слияние двух разных людей хуже незамеченного дубля. Мы сливаем только по телефону — признаку, который практически однозначен.

### deep Если не получилось
- **Транзакция упала по таймауту** — на 51–60 тысячах строк слияние может занять десятки секунд; увеличь `timeout` (мы поставили 120 000 мс = 2 минуты; по умолчанию — 5 секунд).
- **`column "phone_norm" can only be updated to DEFAULT`** — какой-то код пытается писать генерируемую колонку: убери её из `data` и из `create`.
- **Клиентов осталось слишком много** — нормализация не объединила форматы: проверь `SELECT phone, phone_norm FROM "tbl_Customers" WHERE phone_norm !~ '^[0-9]{10}$' LIMIT 10`.

### quiz
- Почему слияние дублей выполняется в одной транзакции?
- Как переносят данные дубля на «главную» запись и как фиксируют, что с чем объединено?
- Почему уникальный индекс на телефон можно ставить только после слияния?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/queries/transactions#interactive-transactions | интерактивные транзакции | Prisma 7: Interactive transactions
- https://www.postgresql.org/docs/18/ddl-generated-columns.html | генерируемые колонки | PostgreSQL 18: Generated Columns

## 11.5 Drift: база разошлась со схемой | short: Drift | est: ~50 мин
### intro
**Слова шага:** *drift*, *расхождение базы и истории миграций*, *`migrate status`*, *`migrate diff`*, *`migrate resolve`*, *ручная правка «боевой» базы*.

:::tip Если совсем просто
История ремонта говорит «в кухне стоит перегородка», а ты приходишь — перегородки нет, кто-то её снёс без записи в журнале. Это drift: база изменена **мимо** миграций. Prisma замечает расхождение и отказывается идти дальше: «не знаю, чему верить — журналу или реальности».
:::

Воспроизведём типичную причину: кто-то «быстро» поправил базу руками.

```bash run
cd ~/prisma-lab/rentkit
psqlr() { docker exec -i rental-pg psql -U postgres -d rental "$@"; }
psqlr -c 'ALTER TABLE "tbl_Branches" ADD COLUMN manager text'
npx prisma migrate status
echo n | npx prisma migrate dev --name probe 2>&1 | head -20
```

### result
```out auto
```

Ожидаем сообщение вида `Drift detected: Your database schema is not in sync with your migration history` с перечнем отличий (`[+] Added column manager`) и вопрос «**reset the database?**» — мы ответили `n` (в команде выше). **Никогда не соглашайся на reset без осознанного решения**: он удалит данные.

Три выхода (выбирает человек, **по смыслу**):

1. **Откатить ручную правку** — если изменение было ошибочным: `ALTER TABLE "tbl_Branches" DROP COLUMN manager` — и `migrate status` снова чист.
2. **Зафиксировать правку миграцией** — если изменение нужное: опиши его в схеме (`manager String?`), создай миграцию **с тем же SQL** (`migrate dev --create-only`, проверь SQL), а так как в базе колонка уже есть, пометь миграцию **применённой**: `npx prisma migrate resolve --applied <имя>`.
3. **Пересоздать базу** — только для **разработческой** базы, где данных не жалко, и только когда тебе всё равно (`migrate reset`).

Выберем первый выход — правка была ошибочной, откатываем её и проверяем, что Prisma снова довольна:

```bash run
cd ~/prisma-lab/rentkit
psqlr() { docker exec -i rental-pg psql -U postgres -d rental "$@"; }
psqlr -c 'ALTER TABLE "tbl_Branches" DROP COLUMN manager'
npx prisma migrate status
```

### result
```out auto
```

Про drift больше ни слова. Единственное, что `migrate status` ещё сообщает, — миграция `…_customer_phone_unique` из шага 11.4: мы создали её, но не применили (она применится в шаге 11.6 командой `migrate deploy`).

Хочешь посмотреть расхождение **без** `migrate dev`: `npx prisma migrate diff --help` покажет, как сравнить историю/схему/базу (в Prisma 7 источники называются `--from-migrations`, `--from-schema`, `--from-config-datasource`, `--to-…` — проверено по `--help` на 7.10). Именно из-за такого drift в Express-лабе периодически возникала ошибка «Drift detected»: там схему создавали двумя способами (сырой SQL-файл и Prisma) — база и история миграций расходились.

### why
Drift — самое частое «непонятное» сообщение Prisma Migrate, и на него обычно реагируют самым плохим способом («ладно, сбросить»). Теперь ты знаешь, что означает сообщение, чем оно вызвано и **три** осознанных ответа на него.

### deep Как ещё можно
Для командной работы: один процесс, одна дверь — **изменения базы только через миграции**. Для «спасательных» ручных правок на проде заводят правило: ручная правка сразу описывается миграцией и помечается применённой (`resolve --applied`). Так журнал и реальность не расходятся.

### deep Если не получилось
- **`migrate dev` не спросил про reset, а сразу сбросил** — ты не ответила `n`; восстанови базу из дампа (шаги 1.3 и 10.6) и повтори, **внимательно читая вопросы**.
- **`migrate status` чист, а колонка в базе осталась** — ты откатила правку, но не ту колонку; сравни `\d "tbl_Branches"`.

### quiz
- Что такое drift и по какому признаку Prisma его находит?
- Назови три осознанных способа ответить на drift.
- Почему соглашаться на «reset» при drift почти никогда нельзя?

### links
- https://www.prisma.io/docs/orm/v7/prisma-migrate/workflows/troubleshooting | устранение проблем | Prisma 7: Troubleshooting
- https://www.prisma.io/docs/orm/v7/prisma-migrate/understanding-prisma-migrate/limitations-and-known-issues | ограничения | Prisma 7: Limitations and known issues

## 11.6 Команда: две ветки с миграциями и CI | short: Миграции в команде | est: ~55 мин
### intro
**Слова шага:** *две ветки*, *порядок миграций*, *конфликт*, *`migration_lock.toml`*, *`migrate deploy` в CI*, *проверка «схема = миграции»*.

:::tip Если совсем просто
Двое одновременно ремонтируют дом, каждый пишет свой журнал изменений. Потом журналы нужно слить в один. Если один убрал стену, а другой на ней повесил полку — журналы расходятся, и сливать надо руками, с головой. С миграциями то же: две ветки добавляют миграции, и итоговая **история должна применяться по порядку без противоречий**.
:::

Смоделируем: две «ветки» (две папки миграций с разными временами), обе трогают таблицу филиалов. (Сначала `--create-only` создаёт папку с настоящей меткой времени, потом мы пишем в неё SQL.)

```bash run
cd ~/prisma-lab/rentkit
npx prisma migrate dev --create-only --name branch_phone
echo 'ALTER TABLE "tbl_Branches" ADD COLUMN "phone" TEXT;' > prisma/migrations/*_branch_phone/migration.sql
sleep 1
npx prisma migrate dev --create-only --name branch_email
echo 'ALTER TABLE "tbl_Branches" ADD COLUMN "email" TEXT;' > prisma/migrations/*_branch_email/migration.sql
npx prisma migrate deploy
psqlr() { docker exec -i rental-pg psql -U postgres -d rental -c "$@"; }
psqlr '\d "tbl_Branches"'
```

### result
```out auto
```

Миграции применились **в порядке имён папок**. Здесь проблем нет — они независимы. Конфликт возникает, если: (а) две ветки меняют **одно и то же** (оба добавляют колонку с одним именем) — вторая миграция упадёт; (б) **порядок важен** (одна ветка переименовала колонку, вторая её использует); (в) одна ветка создала миграцию с **более ранним временем**, чем уже применённая на «проде» (Prisma скажет, что история «не по порядку»).

Правила команды:

- **Не правим применённые миграции** (контрольная сумма): исправление — новой миграцией.
- **При слиянии веток** пересоздай свою миграцию «поверх» чужих: удали свою папку, подтяни чужие, на чистой dev-базе (`migrate reset`) запусти `migrate dev` заново — Prisma пересоздаст миграцию с актуальным временем и порядком.
- **`migration_lock.toml`** (в `prisma/migrations`) фиксирует тип базы (`provider = "postgresql"`): не удаляй его и коммить в Git.
- **В CI** — только `migrate deploy` (не `dev`): применяет то, что есть, и падает, если что-то не так; плюс проверка, что **схема соответствует истории**: сравнение `migrate diff` должно быть пустым (рабочий вариант с флагами Prisma 7 — в шаге 18.3).

Уборка (убери тестовые колонки и миграции, чтобы они не мешали дальше):

```bash run
cd ~/prisma-lab/rentkit
npx prisma migrate status
cat prisma/migrations/migration_lock.toml
```

### result
```out auto
```

Колонки `phone` и `email` в `tbl_Branches` оставь: в сессиях 12–19 они не используются, но убирать применённые миграции нельзя; если очень хочется убрать — создай новую миграцию `DROP COLUMN`. Чтобы следующая автоматическая миграция не предложила их удалить, опиши их и в схеме:

```prisma schema
model Branch {
  // …поля как раньше…
  phone String?
  email String?
}
```

### why
В одиночной работе миграции — просто список. В команде они — общий журнал, и от дисциплины зависит, соберётся ли он в одну историю. Правило «`dev` у себя, `deploy` везде» плюс «не правим применённое» — минимум, который спасает от большинства командных инцидентов.

### deep Если не получилось
- **`migrate deploy` ругается на историю не по порядку** — одна из миграций имеет время раньше уже применённой; переименуй папку (до применения на общей базе) или пересоздай.
- **`Migration … failed to apply`** — SQL не подходит под текущее состояние (колонка уже есть); открой ошибку и исправь **новой** миграцией, а упавшую пометь `migrate resolve --rolled-back`.

### quiz
- В каком порядке применяются миграции и что делать, если ветка создала миграцию с более ранним временем?
- Почему применённые миграции нельзя править?
- Чем в CI `migrate deploy` отличается от `migrate dev`?

### links
- https://www.prisma.io/docs/orm/v7/prisma-migrate/understanding-prisma-migrate/migration-histories | история миграций | Prisma 7: Migration histories
- https://www.prisma.io/docs/orm/v7/prisma-migrate/workflows/squashing-migrations | схлопывание миграций | Prisma 7: Squashing migrations

## 11.7 🔨 migrate dev предлагает «сбросить базу» | short: 🔨 Предложение reset | est: ~45 мин
### intro
**Слова шага:** *изменённая применённая миграция*, *контрольная сумма*, *`P3006`*, *`P3009`*, *`P3018`*, *осознанный отказ*.

:::tip Если совсем просто
Prisma умеет вежливо сказать «я не понимаю, что случилось — давай сотрём всё и начнём заново». Для учебной базы — смешно, для рабочей — катастрофа. Научись читать **причину** в тексте перед вопросом и не отвечать «да» на автомате.
:::

Сломаем нарочно: добавим комментарий в уже применённую миграцию.

```bash run
cd ~/prisma-lab/rentkit
f=$(ls -d prisma/migrations/*_depositlog_pk | head -1)/migration.sql
cp "$f" /tmp/migration.sql.bak
echo '-- случайный комментарий' >> "$f"
echo n | npx prisma migrate dev --name probe 2>&1 | head -14
```

### result
```out auto
```

```bash run hidden
cd ~/prisma-lab/rentkit && f=$(ls -d prisma/migrations/*_depositlog_pk | head -1)/migration.sql && cp /tmp/migration.sql.bak "$f"
```

Сообщение скажет, что миграция `…_depositlog_pk` **изменена после применения** (контрольная сумма в `_prisma_migrations` не совпадает с файлом) и предложит сбросить базу. **Твоя задача:** (1) ответить на вопрос «а что случилось?» — в одной фразе, своими словами; (2) вернуть файл в исходный вид (`cp /tmp/migration.sql.bak "$f"`) и убедиться, что `migrate status` чист; (3) придумать, **как бы ты внесла эту правку правильно**, если бы комментарий был важной корректировкой (подсказка — в «Если не получилось»).

**Приёмка сессии:** сирот нет, внешние ключи и ограничения на месте и проверены (`convalidated = t`), дублей клиентов и платежей нет (журналы заполнены), `migrate status` — чисто; в `NOTES.md` — таблица «до/после» (клиентов, броней, платежей, сирот, дублей) и описания всех трёх выходов из drift.

### why
Сообщение о reset пугает, потому что похоже на команду. На самом деле это **вопрос**, и ответ почти всегда «нет, давай разберёмся». Умение прочитать причину (`modified after applied`, `drift detected`, `failed migration`) превращает панику в диагностику.

### deep Если не получилось
- **Подсказка к (3):** применённые миграции не редактируют; корректировка — **новая** миграция, которая делает нужное изменение. Если правка нужна только на **dev-базе** и ты уверена — `migrate reset` на dev допустим, но тогда **все разработчики** пересоздают свои базы.
- **Не отвечала `n`, база сброшена** — восстанови `rental` из дампа `starter/rental-before-contract.dump` и повтори сессию с 10.6 (это и есть цена невнимательности).

### quiz
- Что означает сообщение «migration was modified after it was applied»?
- Как правильно внести правку в миграцию, которая уже применена?
- Почему ответ «да» на вопрос о сбросе базы нужно давать осознанно?

### links
- https://www.prisma.io/docs/orm/v7/prisma-migrate/workflows/troubleshooting | устранение проблем | Prisma 7: Troubleshooting
- https://www.prisma.io/docs/orm/v7/reference/error-reference#p3006 | P3006 | Prisma 7: Error reference P3006
