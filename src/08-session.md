# Сессия 8 · Пагинация, индексы, EXPLAIN
dur: ~4 ч

## 8.1 skip/take на 300 тысячах строк: чем глубже, тем медленнее | short: skip и take | est: ~40 мин
### intro
**Слова шага:** *`skip`*, *`take`*, *`OFFSET`*, *глубокая страница*, *замер времени*, *стабильная сортировка*.

:::tip Если совсем просто
Страница 1 000 000 в книге: чтобы её открыть, нужно **перелистать** 999 999 страниц до неё — даже если читать их не будешь. `OFFSET` в базе делает ровно это: «пропусти N строк» означает «прочитай и выкинь N строк». Чем глубже страница, тем больше выкинуто впустую.
:::

Небольшой помощник для замеров (будет нужен всю сессию):

```ts
// src/lib/timed.ts
export async function timed<T>(label: string, fn: () => Promise<T>): Promise<T> {
  const t0 = performance.now()
  const r = await fn()
  console.log(label.padEnd(40), (performance.now() - t0).toFixed(1).padStart(8), 'ms')
  return r
}
```

```ts
// src/lessons/08-offset.ts
import { prisma } from '../db.js'
import { timed } from '../lib/timed.js'

await prisma.booking.count()                  // прогрев: первый запрос открывает соединение и портит замер
for (const page of [1, 100, 1000, 5000]) {
  await timed(`страница ${page}, сортировка по id`, () =>
    prisma.booking.findMany({ orderBy: { id: 'asc' }, skip: (page - 1) * 50, take: 50 }))
}
// сортировка по неиндексируемому полю: пересортировка всей таблицы
for (const page of [1, 1000]) {
  await timed(`страница ${page}, сортировка по цене-тексту`, () =>
    prisma.booking.findMany({ orderBy: [{ priceText: 'asc' }, { id: 'asc' }], skip: (page - 1) * 50, take: 50 }))
}
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/08-offset.ts
```

### result
```out auto
```

Ожидаем два эффекта: (1) при сортировке по `id` время **растёт с глубиной** (индекс первичного ключа помогает идти по порядку, но пропущенные строки всё равно «прочитываются»); (2) при сортировке по полю **без индекса** база **сортирует все 300 тысяч строк** на каждой странице — и первая страница уже медленная. Числа у тебя будут свои; важна **форма**: линейный рост от глубины (у нас 1,9 → 4,5 → 20 мс; самая первая строка вывода бывает выше — «холодный» запрос: планировщик и кеш ещё не прогреты, на форму не смотри).

### why
Пагинация «страница N из M» — самый частый и самый коварный запрос на административных страницах. На тысяче строк она незаметна, на миллионе — «тормозит страница заказов». Понимать, почему `OFFSET` линеен, — основа выбора между постраничной выборкой и «курсором» (шаг 8.2).

### deep Под капотом
`skip: 49950, take: 50` превращается в `LIMIT 50 OFFSET 49950`. PostgreSQL не умеет «прыгнуть на строку 49951», если порядок не совпадает с индексом: он получает строки по порядку и **отбрасывает** первые 49 950. Даже при совпадающем индексе пропуск идёт по листьям индекса — линейно по числу пропущенных.

### deep Если не получилось
- **Время почти одинаковое на всех страницах** — вся таблица в кэше и индекс по `id` быстрый; увеличь глубину (`5000` → `5800`, ~290 тысяч) или добавь нагрузку на сортировку.
- **Порядок нестабилен** — при сортировке по неуникальному полю без `id` второй колонкой строки на границах страниц могут повторяться или теряться; всегда добавляй уникальный ключ в конец `orderBy`.

### quiz
- Почему время `OFFSET` растёт с номером страницы?
- Зачем во второй колонке `orderBy` ставить `id`?
- Чем сортировка по полю без индекса хуже сортировки по `id`?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/queries/pagination | пагинация | Prisma 7: Pagination
- https://use-the-index-luke.com/no-offset | не используйте OFFSET | Use The Index, Luke: no-offset

## 8.2 Cursor-пагинация: закладка вместо листания | short: Cursor | est: ~45 мин
### intro
**Слова шага:** *`cursor`*, *keyset-пагинация*, *`skip: 1`*, *«следующая страница»*, *компромиссы (нет «страницы №»)*.

:::tip Если совсем просто
Вместо «открой страницу 1 000 000» ты кладёшь закладку: «я остановилась на брони №48 723». Следующую порцию база находит **по закладке** — сразу, без листания: «дай 50 броней после №48 723». Минус: ты не можешь прыгнуть на «страницу 777» — только вперёд-назад от закладки.
:::

```svg
@offset-vs-cursor
```

В Prisma — аргумент `cursor`. Условие: порядок по **уникальному** полю (или по набору полей, оканчивающемуся уникальным):

```ts
// src/lessons/08-cursor.ts
import { prisma } from '../db.js'
import { timed } from '../lib/timed.js'

// 1. cursor в Prisma: «с этого id, не включая его»
async function nextPage(afterId?: number) {
  return prisma.booking.findMany({
    take: 50,
    ...(afterId ? { skip: 1, cursor: { id: afterId } } : {}),
    orderBy: { id: 'asc' },
  })
}

// 2. то же «руками»: keyset через where — работает с любым порядком
async function nextPageKeyset(afterId = 0) {
  return prisma.booking.findMany({ where: { id: { gt: afterId } }, take: 50, orderBy: { id: 'asc' } })
}

let last = 0
await nextPage()                      // прогрев
for (let i = 0; i < 5000; i++) {     // 5000 страниц = 250 000 строк
  const rows = await nextPage(last || undefined)
  if (rows.length < 50) break
  last = rows.at(-1)!.id
  if (i % 1000 === 0) console.log('страница', i + 1, 'cursor =', last)
}

await timed('страница 5000 через cursor', () => nextPage(249_950))
await timed('страница 5000 через keyset', () => nextPageKeyset(249_950))
await timed('страница 5000 через skip',   () => prisma.booking.findMany({ skip: 249_950, take: 50, orderBy: { id: 'asc' } }))
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/08-cursor.ts
```

### result
```out auto
```

Что видно: `cursor` и «ручной» keyset на пятитысячной странице так же быстры, как на первой, а `skip` — заметно медленнее (у нас 0,3 мс у `cursor` и 12,8 мс у `skip`; 8 мс у keyset — «холодный» запрос, на повторе будет доли миллисекунды: числа в миллисекундах шумят, смотри на порядок). В SQL `cursor` превращается в условие `id >= $cursor` (плюс `skip: 1` пропускает саму закладку); ручной keyset — `id > $last`. Для составных порядков (по `startText`, потом `id`) условие keyset выглядит как `(startText, id) > ($a, $b)` — Prisma `cursor` такое умеет частично, и для сложных случаев проще написать условие самой.

Компромиссы: **нет «страницы №»** (только «дальше/назад»); нужен **уникальный** порядок; добавляя/удаляя строки между запросами, ты не получишь «поплывшей» страницы (плюс по сравнению с `OFFSET`).

### why
Курсор — стандартный выбор для бесконечной прокрутки, лент, выгрузок «порциями» (сессия 17.5). Для админок «со страницами по номерам» часто всё равно делают `OFFSET` с ограничением на глубину (не дальше страницы 100) и «ленивым» подсчётом итога (шаг 8.6).

### deep Как ещё можно
Для сортировки по нескольким полям с keyset обычно кодируют курсор в строку (base64 от JSON `{ startText, id }`) и отдают клиенту: «вот токен следующей страницы». В Prisma это — `cursor` (если порядок по уникальному ключу) или ручное условие (`OR`/`AND` для составного ключа).

### deep Если не получилось
- **`Argument cursor … must be a unique field`** — `cursor` принимает только уникальные поля.
- **Дубли строк на стыках страниц** — забыт `skip: 1`: `cursor` по умолчанию **включает** строку закладки.

### quiz
- Чем `cursor`-пагинация быстрее `skip`/`take` на глубоких страницах?
- Зачем нужен `skip: 1` вместе с `cursor`?
- От чего приходится отказаться, выбрав cursor-пагинацию?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/queries/pagination#cursor-based-pagination | cursor-пагинация | Prisma 7: Cursor-based pagination

## 8.3 Читаем EXPLAIN запросов Prisma | short: EXPLAIN | est: ~50 мин
### intro
**Слова шага:** *`EXPLAIN (ANALYZE, BUFFERS)`*, *`Seq Scan`*, *`Index Scan`*, *`Bitmap Heap Scan`*, *стоимость*, *число строк*, *фильтр*.

:::tip Если совсем просто
`EXPLAIN` — это «режиссёрский план» запроса: как база собирается искать ответ. `Seq Scan` — «перебрать всё подряд», `Index Scan` — «открыть оглавление и пойти сразу к нужной странице». Читаем план как рецепт: сверху — итог, ниже — шаги, которые к нему ведут.
:::

Берём SQL из лога Prisma (шаг 5.5) и прогоняем через `EXPLAIN`. Запрос: «брони, где в заметке есть слово „продлить“» — по полю без индекса.

```ts
// src/lessons/08-explain-src.ts
import { prisma } from '../db.js'
await prisma.booking.findMany({ where: { note: { contains: 'продлить' } }, select: { id: true, note: true }, take: 20 })
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
SQL_LOG=1 npx tsx src/lessons/08-explain-src.ts 2>&1 | head -4
psqlr() { docker exec -i rental-pg psql -U postgres -d rental "$@"; }
psqlr -c "EXPLAIN (ANALYZE, BUFFERS) SELECT id, note FROM \"tbl_Bookings\" WHERE note LIKE '%продлить%' LIMIT 20"
psqlr -c "EXPLAIN (ANALYZE, BUFFERS) SELECT id FROM \"tbl_Bookings\" WHERE cust_id = 42"
```

### result
```out auto
```

Как читать вывод (три главные величины в каждой строке):

- **`Seq Scan on "tbl_Bookings"`** — перебор всей таблицы; в первом запросе `Rows Removed by Filter` показывает, сколько строк перебрали и выбросили, пока не набрали 20 подходящих (признак «ищем иголку без индекса»; слово «продлить» встречается часто, поэтому у нас перебор остановился на ≈760 строках, а для редкого слова он шёл бы до конца таблицы);
- **`Index Scan` / `Index Only Scan` / `Bitmap Index Scan`** — поиск по индексу; второй запрос (по `cust_id`) должен использовать индекс `tbl_Bookings_cust_id_idx`, который мы создали в шаге 6.1;
- **`actual time=… rows=… loops=…`** — реальное время и число строк (для каждой ступени); `Buffers: shared hit/read` — сколько страниц взято из кэша и с диска; **`Planning Time` / `Execution Time`** внизу.

Практика: перед любой оптимизацией ищи в плане **самую дорогую ступень** (по `actual time` и числу строк) и спрашивай: «почему здесь нет индекса?»

### why
`EXPLAIN` — единственный надёжный способ узнать, **почему** запрос медленный; всё остальное — догадки. Если лог Prisma показывает запрос, а `EXPLAIN` — как база его выполнила, у тебя есть полная картина. Это та же методика, что в PostgreSQL-лабе, но применённая к SQL, который сгенерировала не ты.

### deep Команды по частям
`EXPLAIN` без `ANALYZE` — только прогноз (ничего не выполняет); `EXPLAIN ANALYZE` — **выполняет** запрос и показывает реальные цифры (осторожно с `UPDATE/DELETE`: оберни в `BEGIN … ROLLBACK`); `BUFFERS` добавляет статистику страниц. Подставляя значения из `params` лога в `$1`, помни про типы: `$1` — это значение, а не строка `'$1'`.

### deep Если не получилось
- **План другой, чем описано** — размер кэша, статистика (`ANALYZE`) и версия PostgreSQL влияют на выбор; главное — найти `Seq Scan`/`Index Scan` и смысл.
- **`syntax error near "$1"`** — в `EXPLAIN` в `psql` подставляй значения вместо `$1…`; параметры работают только в подготовленных запросах.

### quiz
- Что означает `Seq Scan` и когда он оправдан?
- Что показывают `actual time`, `rows` и `loops` в плане?
- Чем `EXPLAIN` отличается от `EXPLAIN ANALYZE` и чем опасен второй для записи?

### links
- https://www.postgresql.org/docs/18/using-explain.html | чтение EXPLAIN | PostgreSQL 18: Using EXPLAIN
- https://www.prisma.io/docs/orm/v7/prisma-client/queries/advanced/query-optimization-performance | оптимизация запросов | Prisma 7: Query optimization

## 8.4 Индексы в схеме: @@index, составные, порядок | short: @@index | est: ~45 мин
### intro
**Слова шага:** *`@@index`*, *составной индекс*, *порядок колонок*, *`sort`*, *`@@unique`*, *миграция индекса*.

:::tip Если совсем просто
Индекс — оглавление книги. Без него, чтобы найти «шиномонтаж», читаешь всю книгу. Составной индекс — оглавление по двум признакам сразу («по городу, потом по улице»): ищет быстро, **если спрашивают с первого признака**; если спросить только про улицу — оглавление не поможет.
:::

Запрос из жизни: «брони филиала в статусе „просрочена“, самые свежие сверху». До индекса:

```bash run
psqlr() { docker exec -i rental-pg psql -U postgres -d rental -c "$@"; }
psqlr "EXPLAIN (ANALYZE) SELECT id FROM \"tbl_Bookings\" WHERE branch_id = 5 AND status = 6 ORDER BY id DESC LIMIT 20"
```

### result
```out auto
```

Индекс по `branch_id` у нас уже есть (шаг 6.1), поэтому планировщик возьмёт его, а потом отфильтрует по `status` и отсортирует. Составной индекс `(branchId, status, id)` проведёт к нужным строкам **сразу и уже в нужном порядке**. Добавим его в схему:

```prisma schema
model Booking {
  // …поля как раньше…
  @@index([customerId])
  @@index([itemId])
  @@index([branchId])
  @@index([branchId, status, id(sort: Desc)], name: "bookings_branch_status_id")   // составной, порядок ↓
}
```

```bash run
cd ~/prisma-lab/rentkit
npx prisma migrate dev --name booking_branch_status_idx
psqlr() { docker exec -i rental-pg psql -U postgres -d rental -c "$@"; }
psqlr "EXPLAIN (ANALYZE) SELECT id FROM \"tbl_Bookings\" WHERE branch_id = 5 AND status = 6 ORDER BY id DESC LIMIT 20"
```

### result
```out auto
```

Ожидаем `Index Only Scan using bookings_branch_status_id` (индекс покрывает всё, что нужно запросу, в таблицу заглядывать не надо) и **почти нулевое** время (у нас ≈0,2 мс против ≈2,6 мс до индекса). Правила составных индексов:

- **Порядок колонок важен.** Индекс `(a, b, c)` помогает запросам по `a`, по `a и b`, по `a, b, c` — но **не** запросу по одному `b`.
- Сначала колонки, по которым **равенство** (`branchId = 5`, `status = 6`), потом — по которым **диапазон/сортировка** (`id DESC`).
- Лишние индексы **замедляют запись** (каждый `INSERT`/`UPDATE` обновляет все индексы) и занимают место: на каждый — реальный запрос.
- В схеме: `@@index([a, b])`, `@@unique([a, b])`, `sort: Desc` для порядка, `name:` для читаемого имени, `type: Hash`/`Gin`/`Brin` для других типов (**сверьтесь**: какие типы индексов поддерживает схема в вашей версии).

### why
Индекс — самый дешёвый способ ускорить чтение, но у него своя цена и свои условия применимости. Привычка: не «добавь индексы на всё», а «возьми запрос, посмотри план, подбери индекс под него, проверь план снова».

### deep Как ещё можно
Покрывающий индекс (`INCLUDE`), частичный (`WHERE status = 6`), по выражению (`lower(email)`) — в схему Prisma не ложатся целиком; их создают ручной SQL-миграцией (шаг 8.5).

### deep Если не получилось
- **Планировщик не берёт индекс** — таблица мала (читает целиком быстрее), статистика устарела (`ANALYZE "tbl_Bookings"`), либо условие не совпадает с началом индекса (см. шаг 8.7).
- **`migrate dev` хочет пересоздать другие индексы** — разошлись имена индексов в схеме и в базе; посмотри текст миграции перед применением.

### quiz
- Почему порядок колонок в составном индексе важен?
- Какие колонки ставят в начало составного индекса и почему?
- Чем плохи «лишние» индексы?

### links
- https://www.prisma.io/docs/orm/v7/prisma-schema/data-model/indexes | индексы | Prisma 7: Indexes
- https://www.postgresql.org/docs/18/indexes-multicolumn.html | составные индексы | PostgreSQL 18: Multicolumn Indexes

## 8.5 Чего схема не выразит: GIN, частичные, по выражению | short: Индексы через SQL | est: ~50 мин
### intro
**Слова шага:** *GIN*, *`pg_trgm`*, *частичный индекс*, *индекс по выражению*, *ручная SQL-миграция*, *`--create-only`*, *drift индексов*.

:::tip Если совсем просто
Обычный индекс отвечает на «равно» и «больше/меньше». Для поиска «содержит слово» нужен другой (триграммный: режет текст на кусочки по три буквы). Для «только просроченные» — частичный (индекс только на часть строк, поэтому крошечный). Эти индексы в схеме Prisma не описать — их делают **руками**, но через ту же систему миграций.
:::

Задача: поиск клиентов по части имени (`contains`, без учёта регистра — то, что делает `mode: 'insensitive'` в Prisma) и быстрый список просроченных броней. Создаём пустую миграцию и пишем SQL сами:

```bash run
cd ~/prisma-lab/rentkit
npx prisma migrate dev --create-only --name custom_indexes
ls prisma/migrations | tail -2
cat prisma/migrations/*_custom_indexes/migration.sql
```

### result
```out auto
```

Prisma создала папку с **пустым** `migration.sql` (одна строка-комментарий `-- This is an empty migration.`) — так и задумано: файл твой, и ты вписываешь в него свой SQL (метка времени в имени папки у тебя будет другая):

```sql into=prisma/migrations/*_custom_indexes/migration.sql
-- prisma/migrations/<метка>_custom_indexes/migration.sql
-- триграммный поиск «содержит» по имени клиента (ILIKE '%иван%')
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX "customers_name_trgm" ON "tbl_Customers" USING gin ("CustName" gin_trgm_ops);

-- частичный индекс: только просроченные брони (мало строк → маленький и быстрый)
CREATE INDEX "bookings_overdue" ON "tbl_Bookings" ("branch_id", "id" DESC) WHERE "status" = 6;

-- индекс по выражению: поиск по нормализованному телефону (последние 10 цифр)
CREATE INDEX "customers_phone10" ON "tbl_Customers" (right(regexp_replace("phone", '\D', '', 'g'), 10));
```

```bash run
cd ~/prisma-lab/rentkit
npx prisma migrate deploy
psqlr() { docker exec -i rental-pg psql -U postgres -d rental -c "$@"; }
psqlr "EXPLAIN (ANALYZE) SELECT id FROM \"tbl_Customers\" WHERE \"CustName\" ILIKE '%иван%' LIMIT 10"
psqlr "EXPLAIN (ANALYZE) SELECT id FROM \"tbl_Bookings\" WHERE status = 6 AND branch_id = 5 ORDER BY id DESC LIMIT 20"
```

### result
```out auto
```

Здесь мы применили миграцию командой `migrate deploy` (она только применяет готовые миграции и ни о чём не спрашивает). Обычный `migrate dev` на этом месте тоже применил бы её — но дальше ещё и сравнил бы схему с базой (об этом сразу ниже).

**Важная проверка.** Эти индексы Prisma-схема не описывает. Убедись, что следующая автоматическая миграция **не пытается их удалить** — создадим её с `--create-only` и посмотрим внутрь:

```bash run
cd ~/prisma-lab/rentkit
npx prisma migrate dev --create-only --name drift_check
cat prisma/migrations/*_drift_check/migration.sql
rm -r prisma/migrations/*_drift_check
psqlr() { docker exec -i rental-pg psql -U postgres -d rental -c "$@"; }
psqlr "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' AND indexname IN ('bookings_overdue', 'customers_phone10', 'customers_name_trgm')"
```

### result
```out auto
```

**Сюрприз.** Частичный индекс `bookings_overdue` и индекс по выражению `customers_phone10` Prisma не трогает — она их просто не понимает и пропускает. А вот **триграммный GIN-индекс** `customers_name_trgm` она *понимает* (тип индекса `Gin` и класс операторов можно описать в схеме), видит, что в схеме его нет, и в черновике миграции стоит `DROP INDEX "customers_name_trgm"`. Если бы мы нажали Enter в `migrate dev` — индекс исчез бы молча. Поэтому папку-черновик мы удалили (`rm -r`), а индекс **описываем в схеме** — тогда схема и база совпадают:

```prisma schema
model Customer {
  // …поля как раньше…
  @@index([name(ops: raw("gin_trgm_ops"))], type: Gin, map: "customers_name_trgm")
}
```

Повтори проверку — теперь черновик должен быть пустым (индексы `bookings_overdue` и `customers_phone10` по-прежнему на месте):

```bash run
cd ~/prisma-lab/rentkit
npx prisma migrate dev --create-only --name drift_check
cat prisma/migrations/*_drift_check/migration.sql
rm -r prisma/migrations/*_drift_check
```

### result
```out auto
```

Правило: **после любой ручной SQL-миграции с индексом или ограничением делай `migrate dev --create-only` и читай черновик.** Если внутри `DROP INDEX`/`DROP CONSTRAINT` — не применяй: удали папку-черновик и опиши объект в схеме (если Prisma его умеет) либо оставь как есть (если её не волнует, как с частичным индексом и индексом по выражению). Подробнее о том, что умеет схема, — страница «PostgreSQL extensions» в документации.

### why
Здесь проходит граница возможностей ORM: схема Prisma — подмножество того, что умеет PostgreSQL. Знать, как выйти за эту границу **не ломая** процесс миграций, — одно из главных практических умений. Вся история базы по-прежнему в `prisma/migrations`, просто часть SQL написана руками.

### deep Команды по частям
`CREATE INDEX … USING gin (col gin_trgm_ops)` — GIN-индекс с классом операторов «триграммы» из расширения `pg_trgm`: ускоряет `LIKE '%…%'` и `ILIKE`. `WHERE "status" = 6` после `CREATE INDEX` — **частичный** индекс: строки с другими статусами в него не попадают. Индекс по выражению используется, если в запросе то же выражение **буква в букву**.

### deep Если не получилось
- **`extension "pg_trgm" is not available`** — в образе `postgres:18` расширение есть (contrib); если ты ставила базу иначе, установи пакет `postgresql-contrib`.
- **`permission denied to create extension`** — нужны права суперпользователя (у нас `postgres`).
- **План не использует GIN-индекс** — выборка слишком широкая (имя «Иван» у трети клиентов): индекс помогает при селективных условиях.

### quiz
- Для каких запросов нужен триграммный GIN-индекс и чем он отличается от B-tree?
- Что такое частичный индекс и чем он выгоден?
- Как убедиться, что ручной индекс не «сломает» следующие миграции Prisma?

### links
- https://www.postgresql.org/docs/18/pgtrgm.html | pg_trgm | PostgreSQL 18: pg_trgm
- https://www.prisma.io/docs/orm/v7/prisma-schema/postgresql-extensions | расширения PostgreSQL | Prisma 7: PostgreSQL extensions
- https://www.prisma.io/docs/orm/v7/prisma-migrate/workflows/customizing-migrations | ручные миграции | Prisma 7: Customizing migrations

## 8.6 count на больших таблицах: цена и приблизительные счётчики | short: count и «всего» | est: ~30 мин
### intro
**Слова шага:** *`count`*, *полный проход*, *приблизительное число*, *`reltuples`*, *«всего страниц»*, *ленивый подсчёт*.

:::tip Если совсем просто
«Сколько всего броней?» кажется простым вопросом. Но база не хранит «итого» заранее: чтобы ответить точно, она **пересчитывает** строки — на миллионе это отдельная операция. Для «приблизительно 300 тысяч» есть дешёвый способ: спросить статистику.
:::

```ts
// src/lessons/08-count.ts
import { prisma } from '../db.js'
import { timed } from '../lib/timed.js'

await prisma.item.count()                                        // прогрев соединения
await timed('count() всех броней', () => prisma.booking.count())
await timed('count() с условием без индекса', () => prisma.booking.count({ where: { note: { not: null } } }))
await timed('count() с условием по индексу', () => prisma.booking.count({ where: { branchId: 5, status: 6 } }))

// приблизительно — из статистики планировщика (мгновенно)
const estimate = await timed('оценка из pg_class', async () => {
  const [r] = await prisma.$queryRaw<{ estimate: bigint }[]>`SELECT reltuples::bigint AS estimate FROM pg_class WHERE relname = 'tbl_Bookings'`
  return r!.estimate
})
console.log('  ≈', estimate)
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/08-count.ts
```

### result
```out auto
```

Ожидаем: `count()` целой таблицы — порядка десяти миллисекунд (PostgreSQL читает таблицу или индекс целиком; на миллионе строк это уже сотни), `count` с условием по индексу — быстрый (доли миллисекунды), оценка из `pg_class` — **мгновенно**, но приблизительно (точность зависит от свежести статистики: `ANALYZE`/автовакуум). Практика для интерфейсов со страницами: не считать «всего» на каждый запрос; показывать «≈ 300 тыс.», или считать один раз и кешировать, или вообще отказаться от «страница X из Y» в пользу «дальше».

### why
`count` — одна из самых частых скрытых причин медленных страниц: «нарисуем и общее число страниц» превращается в полный проход таблицы на каждый показ. Знание цены операции помогает выбирать между точностью и скоростью осознанно.

### deep Если не получилось
- **Оценка `-1`** — статистика ещё не собрана; выполни `ANALYZE "tbl_Bookings"` (`reltuples` обновится).
- **`relation … does not exist` в `pg_class`** — имя с большими буквами хранится как есть: `relname = 'tbl_Bookings'` (в апострофах, без кавычек).

### quiz
- Почему точный `count` на большой таблице нельзя считать «бесплатным»?
- Как получить приблизительное число строк мгновенно?
- Как обойтись без «всего страниц» в интерфейсе?

### links
- https://wiki.postgresql.org/wiki/Slow_Counting | медленный count | PostgreSQL Wiki: Slow Counting

## 8.7 🔨 Индекс есть в схеме, а планировщик его не берёт | short: 🔨 Индекс не работает | est: ~55 мин
### intro
**Слова шага:** *ведущий `%` в `LIKE`*, *`ILIKE` и B-tree*, *функция над колонкой*, *несовпадение типов*, *индекс, который «не виден»*.

:::tip Если совсем просто
Оглавление есть, а читатель всё равно листает книгу: потому что вопрос задан так, что оглавление не подходит. «Найди все фамилии на „и“» оглавление решит, а «найди фамилии, в которых где-то есть „ив“» — нет. Индекс работает только на тот вопрос, под который построен.
:::

*Заказчик:* «Поиск клиента по фамилии медленный, хотя на фамилию индекс повесили».

Воспроизведи: индекс на имя (B-tree) и поиск «без учёта регистра» из Prisma.

```prisma schema
model Customer {
  // …поля как раньше…
  name String? @map("CustName")
  @@index([name])
}
```

```bash run
cd ~/prisma-lab/rentkit
npx prisma migrate dev --name customer_name_idx
cat > src/lessons/08-noindex.ts <<'EOF'
import { prisma } from '../db.js'
await prisma.customer.findMany({ where: { name: { equals: 'иван иванов', mode: 'insensitive' } }, take: 5 })
await prisma.customer.findMany({ where: { name: { contains: 'ван' } }, take: 5 })
await prisma.customer.findMany({ where: { name: { startsWith: 'Иван' } }, take: 5 })
await prisma.$disconnect()
EOF
SQL_LOG=1 npx tsx src/lessons/08-noindex.ts 2>&1 | grep -E 'LIKE|ILIKE|=' | head -6
```

### result
```out auto
```

Три запроса — три разных SQL: `equals` с `insensitive` → **`ILIKE`** (без учёта регистра), `contains` → `LIKE '%ван%'` (**ведущий** `%`), `startsWith` → `LIKE 'Иван%'`. Прогони каждый через `EXPLAIN ANALYZE` в `psql` и посмотри, какой использует индекс `tbl_Customers_CustName_idx`. Ожидаем: только `startsWith` (B-tree умеет искать по началу строки — и то если колонка в подходящем collation: **сверьтесь**; иначе нужен `text_pattern_ops`).

**Твоя задача:** добиться, чтобы **все три** работали по индексам. Условия: схему менять можно, ручной SQL-миграцией — тоже; поведение запросов не менять. Подсказки — в «Если не получилось».

**Приёмка сессии:** список броней с фильтрами и «следующая страница» через cursor отвечает ≤ 50 мс на пятитысячной странице; ключевые запросы имеют планы с индексом (приложи три `EXPLAIN` к `NOTES.md`); поиск клиента по имени (`contains`/`insensitive`) отрабатывает по триграммному индексу; миграции чистые (`migrate status`).

### why
Индекс, который не используется, — вреден: занимает место и замедляет запись. Причины «не берёт» почти всегда одни: ведущий `%`, функция над колонкой (`lower(name)`, `ILIKE`), несовпадение типов, устаревшая статистика. Научившись видеть их в SQL из лога, перестаёшь «добавлять индексы наугад».

### deep Если не получилось
- **Подсказка 1:** `contains` и `ILIKE` ускоряет **триграммный GIN-индекс** (шаг 8.5): он уже создан для `CustName` — смотри, использует ли его `EXPLAIN` для первых двух запросов.
- **Подсказка 2:** обычный B-tree не помогает при `ILIKE`; индекс по `lower("CustName")` помог бы запросу `lower(name) = $1`, но Prisma `equals + insensitive` генерирует `ILIKE`, поэтому триграмма подходит лучше.
- **Подсказка 3:** для `startsWith` и локалей, отличных от `C`, B-tree по умолчанию может не работать с `LIKE 'Иван%'`; помогает индекс с `text_pattern_ops` (SQL-миграцией).
- **Планировщик всё равно выбирает Seq Scan** — слишком много строк подходит (`«Иван»` — каждый десятый); сделай запрос более селективным (`Иван Петров`).

### quiz
- Почему `ILIKE` не использует обычный B-tree индекс по колонке?
- Какой SQL генерирует `contains`, `startsWith` и `equals` с `insensitive`?
- Что делать, если индекс есть, но планировщик его не берёт?

### links
- https://www.postgresql.org/docs/18/indexes-opclass.html | классы операторов | PostgreSQL 18: Operator Classes
- https://www.postgresql.org/docs/18/pgtrgm.html | pg_trgm | PostgreSQL 18: pg_trgm
