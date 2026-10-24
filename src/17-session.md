# Сессия 17 · Эксплуатация: пул, нагрузка, большие данные
dur: ~4 ч

## 17.1 Пул соединений: размер, таймауты и арифметика | short: Пул и max_connections | est: ~45 мин
### intro
**Слова шага:** *пул*, *`max`*, *`connectionTimeoutMillis`*, *`idleTimeoutMillis`*, *`max_connections`*, *очередь ожидания*, *арифметика соединений*.

:::tip Если совсем просто
У базы есть ограниченное число «телефонных линий» (`max_connections`, по умолчанию 100). Каждый запущенный экземпляр приложения берёт себе несколько линий (размер пула). Пять экземпляров по 10 линий — 50 из 100, нормально. Десять экземпляров — все 100, а миграциям и админу линий уже не осталось. И ещё ловушка: у драйвера `pg` ожидание свободной линии **по умолчанию бесконечно**.
:::

```svg
@connection-pool
```

Параметры пула передаются в адаптер (все — настройки драйвера `pg`; значения по умолчанию в Prisma 7 при адаптере — по документации «Connection pool»: **`max = 10`**, **`connectionTimeoutMillis = 0`** (то есть без ограничения), **`idleTimeoutMillis = 10 000`**):

```ts
// src/db.ts — сборка адаптера с явными параметрами
const adapter = new PrismaPg({
  connectionString: process.env.APP_DATABASE_URL ?? process.env.DATABASE_URL!,
  max: Number(process.env.DB_POOL_MAX ?? 10),                    // размер пула
  connectionTimeoutMillis: Number(process.env.DB_CONNECT_TIMEOUT_MS ?? 3_000),   // сколько ждать свободного соединения
  idleTimeoutMillis: 10_000,                                      // закрывать простаивающие
})
```

```bash run hidden
cd ~/prisma-lab/rentkit && node -e "
const fs=require('fs');let s=fs.readFileSync('src/db.ts','utf8');
s=s.replace('new PrismaPg({ connectionString: process.env.APP_DATABASE_URL ?? process.env.DATABASE_URL! })','new PrismaPg({\n  connectionString: process.env.APP_DATABASE_URL ?? process.env.DATABASE_URL!,\n  max: Number(process.env.DB_POOL_MAX ?? 10),\n  connectionTimeoutMillis: Number(process.env.DB_CONNECT_TIMEOUT_MS ?? 3_000),\n  idleTimeoutMillis: 10_000,\n})');
fs.writeFileSync('src/db.ts',s)"
```

Увидим очередь за соединениями на крошечном пуле:

```ts
// src/lessons/17-pool.ts
import 'dotenv/config'                             // скрипт не импортирует db.ts — .env читаем сами
import { PrismaPg } from '@prisma/adapter-pg'
import { PrismaClient } from '../generated/prisma/client.js'

const make = (max: number, wait: number) => new PrismaClient({ adapter: new PrismaPg({ connectionString: process.env.DATABASE_URL!, max, connectionTimeoutMillis: wait }) })

for (const [label, wait] of [['без таймаута ожидания', 0], ['таймаут 800 мс', 800]] as const) {
  const prisma = make(2, wait)                                                // всего 2 соединения
  const t0 = Date.now()
  const r = await Promise.allSettled(Array.from({ length: 6 }, () => prisma.$queryRaw`SELECT 1 FROM pg_sleep(0.5)`))   // 6 запросов по 0,5 с
  const ok = r.filter((x) => x.status === 'fulfilled').length
  console.log(label.padEnd(24), `успешно ${ok}/6, всего ${Date.now() - t0} мс`)
  await prisma.$disconnect()
}
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/17-pool.ts
```

### result
```out auto
```

Ожидаем: без таймаута ожидания все шесть запросов выполняются, но **по очереди** по два (около 1,5 с); с таймаутом 800 мс часть запросов **падает** с ошибкой «timeout exceeded when trying to connect» — сервис быстро отвечает ошибкой вместо того, чтобы копить очередь. **Арифметика соединений:** `число процессов × max` на все экземпляры приложения (и воркеры, и cron-задачи) плюс запас для админа и миграций (≈10) **не должно превышать** `max_connections` базы (`SHOW max_connections`). Если не хватает — не увеличивай `max_connections` вслепую (каждое соединение — отдельный процесс PostgreSQL с памятью), а ставь **пулер** (PgBouncer, шаг 17.3).

### why
Пул — самое «невидимое» место, которое роняет приложения под нагрузкой. Размер, таймауты и число экземпляров нужно считать **заранее**, а не подбирать, когда «упало». Ограничение ожидания (`connectionTimeoutMillis`) — это ещё и вопрос культуры: быстро упавший запрос лучше «зависшего» на минуту.

### deep Команды по частям
`SHOW max_connections` — предел сервера. `SELECT count(*) FROM pg_stat_activity` — сколько занято. Простой совет по размеру пула: больше процессоров базы × 2–4 обычно не ускоряет, а замедляет (конкуренция за ядра); «десять» для небольшой нагрузки — разумный старт.

### deep Если не получилось
- **Все запросы падают, даже с `wait: 0`** — не хватает соединений на самой базе; проверь `docker logs rental-pg` на `too many clients`.
- **Разницы между двумя режимами нет** — `pg_sleep` слишком короткий или `max` не 2; проверь параметры.

### quiz
- Что произойдёт с запросами, если соединений в пуле меньше, чем параллельных запросов, и таймаута ожидания нет?
- Как посчитать, сколько соединений нужно всем экземплярам приложения?
- Почему не стоит просто увеличить `max_connections` в базе?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/setup-and-configuration/databases-connections/connection-pool | пул соединений | Prisma 7: Connection pool
- https://node-postgres.com/apis/pool | Pool | node-postgres: Pool

## 17.2 Один PrismaClient на процесс: «too many clients» | short: Singleton клиента | est: ~40 мин
### intro
**Слова шага:** *singleton*, *повторное создание клиента*, *горячая перезагрузка*, *`FATAL: sorry, too many clients already`*, *`globalThis`*.

:::tip Если совсем просто
Каждый `new PrismaClient()` приносит свой пул линий. Если клиент создаётся в каждой функции или при каждой горячей перезагрузке dev-сервера, линии заканчиваются, и база кричит «слишком много клиентов». Правило простое: **один клиент на процесс**, и создаётся он один раз.
:::

Воспроизведём ошибку:

```ts
// src/lessons/17-clients.ts
import 'dotenv/config'
import { PrismaPg } from '@prisma/adapter-pg'
import { PrismaClient } from '../generated/prisma/client.js'

const clients = Array.from({ length: 15 }, () => new PrismaClient({ adapter: new PrismaPg({ connectionString: process.env.DATABASE_URL!, max: 10 }) }))
// каждому клиенту — по 10 одновременных запросов: 150 соединений на базу со 100 линиями
const results = await Promise.allSettled(clients.flatMap((c) => Array.from({ length: 10 }, () => c.$queryRaw`SELECT 1 FROM pg_sleep(1)`)))
const failed = results.filter((r) => r.status === 'rejected') as PromiseRejectedResult[]
console.log('упало:', failed.length, ' пример:', String(failed[0]?.reason?.message).split('\n').filter(Boolean).at(-1))
await Promise.allSettled(clients.map((c) => c.$disconnect()))
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/17-clients.ts
```

### result
```out auto
```

Ожидаем ошибки вида `sorry, too many clients already` (или `remaining connection slots are reserved…`) — суммарный пул превысил предел базы. Лечение — **единственный экземпляр**. Модуль в ES-системе загружается один раз, поэтому экспорт `prisma` из `db.ts` — уже singleton. Но есть два случая, где модуль **загружается повторно**: **горячая перезагрузка** dev-сервера (каждый рестарт создаёт нового клиента, а старый не закрыт) и **serverless**-среды. Классический приём — прикрепить клиент к `globalThis`:

```ts
// src/db.ts — защита от повторного создания при горячей перезагрузке
import 'dotenv/config'
import { PrismaPg } from '@prisma/adapter-pg'
import { PrismaClient } from './generated/prisma/client.js'

const globalForPrisma = globalThis as unknown as { prisma?: PrismaClient }

function createClient() {
  const adapter = new PrismaPg({ connectionString: process.env.APP_DATABASE_URL ?? process.env.DATABASE_URL!, max: 10, connectionTimeoutMillis: 3_000 })
  return new PrismaClient({ adapter, log: [{ emit: 'event', level: 'query' }] })
}

export const prisma = globalForPrisma.prisma ?? createClient()
if (process.env.NODE_ENV !== 'production') globalForPrisma.prisma = prisma
```

### why
Эта ошибка заметна, когда приложение стабильно работает неделю, а потом при деплое «по кругу» растёт число соединений. Правило «один клиент на процесс» должно быть так же очевидно, как «одна дверь в здание». Заодно: **закрывай клиент при остановке** (`SIGTERM` → `$disconnect`), иначе соединения повисают до таймаута на стороне базы.

### deep Как ещё можно
В serverless (облачные функции) каждый вызов может создавать новый процесс, и пул на процесс становится проблемой. Тогда используют **внешний пулер** (PgBouncer, шаг 17.3) или Prisma Accelerate (платный облачный пулер, в лабе не рассматривается).

### deep Если не получилось
- **Ошибки не воспроизводятся** — на твоей базе `max_connections` выше 100 или запросы слишком быстрые; сократи `max_connections` (`ALTER SYSTEM SET max_connections = 30` с перезапуском контейнера) или увеличь число клиентов.
- **База не принимает соединения после опыта** — клиенты не закрылись; перезапусти контейнер (`docker restart rental-pg`).

### quiz
- Почему повторное создание `PrismaClient` приводит к `too many clients`?
- Как защититься от создания второго клиента при горячей перезагрузке?
- Что нужно делать с клиентом при остановке процесса?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/setup-and-configuration/databases-connections/connection-management | управление соединениями | Prisma 7: Connection management
- https://www.prisma.io/docs/orm/v7/prisma-client/setup-and-configuration/databases-connections | соединения с базой | Prisma 7: Database connections

## 17.3 PgBouncer: пулер перед базой | short: PgBouncer | est: ~45 мин
### intro
**Слова шага:** *PgBouncer*, *режим `transaction`*, *`max_prepared_statements`*, *прямой URL для миграций*, *`set_config` и пулер*.

:::tip Если совсем просто
PgBouncer — это «диспетчер» между приложениями и базой. Приложения подключаются к нему сотнями, а он держит перед базой десяток настоящих линий и **раздаёт их по одной транзакции**: открылась транзакция — дал линию, закончилась — забрал и выдал следующему. Так сотни клиентов обходятся десятком соединений.
:::

Что нужно знать (проверено на Prisma 7.10 с адаптером `pg` и PgBouncer 1.26.1; подробности — страница «PgBouncer» документации Prisma и документация самого PgBouncer):

- **Режим пула — `transaction`**: линия закрепляется за клиентом на время транзакции. Для Prisma Client это обязательное условие надёжной работы.
- **Подготовленные запросы:** Prisma использует prepared statements; в PgBouncer **версии 1.21+** рекомендуется задать **`max_prepared_statements` больше нуля** (иначе возможны ошибки `prepared statement "…" does not exist`/`already exists`). В нашей проверке (адаптер `pg`, Prisma 7.10, PgBouncer 1.26.1) 60 параллельных запросов прошли и при `max_prepared_statements = 0`: драйвер `pg` шлёт безымянные подготовленные запросы; настройку всё равно оставь больше нуля — на случай других драйверов и версий. Для версий PgBouncer ниже 1.21 в строке подключения добавляют `?pgbouncer=true` (для новых версий — **не** добавляют).
- **Миграции — только по прямому соединению** (мимо пулера): схема-движок Prisma Migrate использует одно соединение и не дружит с режимом `transaction`. В Prisma 7 это значит: `prisma.config.ts` указывает **прямой** URL (`DIRECT_URL`), а клиент приложения — адрес пулера (`APP_DATABASE_URL`).
- **Сессионное состояние теряется между транзакциями.** Наш `set_config('app.branch_id', …, true)` (**локальный**) — **безопасен**, потому что живёт внутри одной транзакции. А `set_config(…, false)` и `SET` (сессионные) в режиме `transaction` **не работают** — линия достанется другому клиенту. Ещё одна причина, почему в 16.4 мы выбрали `true`.

Схема подключения (пример для Compose; образ `edoburu/pgbouncer` с этими переменными запускался на PgBouncer 1.26.1 — сверяй имена переменных с документацией выбранного образа):

```yaml
# compose.pgbouncer.yaml — фрагмент
services:
  pgbouncer:
    image: edoburu/pgbouncer:latest
    environment:
      DB_HOST: rental-pg           # адрес настоящей базы в сети Docker
      DB_USER: rental_app
      DB_PASSWORD: замени-на-свой-пароль
      POOL_MODE: transaction
      AUTH_TYPE: scram-sha-256     # PostgreSQL 18 хранит пароли в scram; с md5 по умолчанию будет «server login failed: wrong password type»
      MAX_CLIENT_CONN: "500"       # сколько клиентов принимать
      DEFAULT_POOL_SIZE: "10"      # сколько настоящих линий к базе
      MAX_PREPARED_STATEMENTS: "100"   # для Prisma, версия 1.21+
    ports: ["6432:5432"]
```

```bash nofile
# .env
APP_DATABASE_URL="postgresql://rental_app:…@localhost:6432/rental"     # приложение → PgBouncer
DIRECT_URL="postgresql://postgres:postgres@localhost:5433/rental"       # миграции → база напрямую
```

```ts
// prisma.config.ts — миграции и CLI идут напрямую
export default defineConfig({
  schema: 'prisma/schema.prisma',
  migrations: { path: 'prisma/migrations' },
  datasource: { url: env('DIRECT_URL') },
})
```

### result
Шаг обзорный: ты настраиваешь конфигурацию и проверяешь её на соответствие правилам выше. Мы проверили её запуском на отдельной базе: 60 параллельных запросов через PgBouncer заняли на стороне базы ровно 5 соединений (по размеру пула PgBouncer, мы брали `DEFAULT_POOL_SIZE: 5`), транзакционный `set_config(…, true)` сработал, а сессионный `set_config(…, false)` остался на серверном соединении и был виден следующему запросу — именно та протечка, о которой шаг 16.7. Если решишь запустить у себя — убедись, что (1) приложение подключается к `6432`, (2) миграции идут на `5433`, (3) `psql` показывает, что к базе открыто ~10 соединений, пока клиентов — сотни.

### why
Пулер — стандартная часть продакшн-схемы: он снимает проблему «много экземпляров приложения × пул» и экономит память базы. Но у него свои правила (режим, подготовленные запросы, миграции), и без знания их возникают загадочные ошибки. Хорошая новость: ты уже сделала главное — выбрала транзакционные параметры сессии.

### deep Если не получилось
- **`prepared statement "s0" already exists`** — режим `transaction` без поддержки prepared statements в пулере: включи `max_prepared_statements` (PgBouncer ≥ 1.21) или добавь `pgbouncer=true` для старых версий.
- **Миграции зависают через пулер** — используй прямой URL для CLI.

### quiz
- В каком режиме PgBouncer работает с Prisma и почему?
- Почему миграции выполняют в обход пулера?
- Почему `set_config(..., true)` работает через PgBouncer, а `false` — нет?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/setup-and-configuration/databases-connections/pgbouncer | PgBouncer | Prisma 7: PgBouncer
- https://www.pgbouncer.org/config.html | конфигурация PgBouncer | PgBouncer: Configuration

## 17.4 Нагрузка: autocannon и pg_stat_statements | short: Нагрузочный тест | est: ~60 мин
### intro
**Слова шага:** *нагрузочный тест*, *`autocannon`*, *RPS*, *p95*, *ошибки*, *`pg_stat_statements`*, *замер «до и после»*.

:::tip Если совсем просто
«Работает» — не то же самое, что «выдержит». Нагрузочный тест — репетиция часа пик: сотни одновременных посетителей, и мы смотрим, сколько запросов в секунду система обрабатывает, как быстро отвечает **самым медленным пяти процентам** (p95) и нет ли ошибок. Потом исправляем узкое место и повторяем замер — чтобы доказать улучшение числом.
:::

Тест нагружает ваш HTTP-слой — маленький сервер (не часть лабы про веб, просто «оболочка» вокруг слоя данных). Сначала помощник интерактивной области видимости (нужен серверу, потому что RLS закрыт по умолчанию):

```ts append=src/extensions/branch-scope.ts
// src/extensions/branch-scope.ts — добавить
export async function withScope<T>(scope: Scope, fn: (tx: Prisma.TransactionClient) => Promise<T>): Promise<T> {
  return base.$transaction(async (tx) => {
    await tx.$executeRaw`SELECT set_config('app.branch_id', ${scope.branchId === undefined ? '' : String(scope.branchId)}, true)`
    await tx.$executeRaw`SELECT set_config('app.role', ${scope.role ?? ''}, true)`
    return fn(tx)
  })
}
```

```ts
// src/server.ts
import http from 'node:http'
import { prisma } from './db.js'
import { withScope } from './extensions/branch-scope.js'

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url ?? '/', 'http://x')
  try {
    if (url.pathname === '/booking') {                                    // GET /booking?id=123 — одна запись
      const id = Number(url.searchParams.get('id'))
      const b = await withScope({ role: 'admin' }, (tx) => tx.booking.findUnique({ where: { id }, select: { id: true, status: true, total: true } }))
      return send(res, 200, b)
    }
    if (url.pathname === '/search') {                                     // GET /search?q=иван — поиск клиента по части имени
      const q = url.searchParams.get('q') ?? ''
      const rows = await withScope({ role: 'admin' }, (tx) => tx.customer.findMany({ where: { name: { contains: q, mode: 'insensitive' } }, take: 10, select: { id: true, name: true } }))
      return send(res, 200, rows)
    }
    if (url.pathname === '/branch-report') {                              // GET /branch-report?branch=5 — тяжёлый отчёт
      const branch = Number(url.searchParams.get('branch'))
      const rows = await withScope({ role: 'admin' }, (tx) => tx.booking.groupBy({ by: ['status'], where: { branchId: branch }, _count: { _all: true } }))
      return send(res, 200, rows)
    }
    send(res, 404, { error: 'not found' })
  } catch (e) {
    send(res, 500, { error: String((e as Error).message).split('\n')[0] })
  }
})

const send = (res: http.ServerResponse, code: number, body: unknown) => { res.writeHead(code, { 'content-type': 'application/json' }); res.end(JSON.stringify(body, (_k, v) => (typeof v === 'bigint' ? v.toString() : v))) }

server.listen(3100, () => console.log('слушаю :3100'))
process.on('SIGTERM', async () => { server.close(); await prisma.$disconnect() })
```

```bash run
cd ~/prisma-lab/rentkit
npm install -D autocannon
(npx tsx src/server.ts > /tmp/rentkit-server.log 2>&1 &)
sleep 3
psqlr() { docker exec -i rental-pg psql -U postgres -d rental -c "$@"; }
psqlr 'SELECT pg_stat_statements_reset()' >/dev/null
for p in "booking?id=12345" "search?q=%D0%B8%D0%B2%D0%B0%D0%BD" "branch-report?branch=5"; do
  echo "== /$p"
  npx autocannon -c 40 -d 8 --json "http://127.0.0.1:3100/$p" 2>/dev/null | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{const r=JSON.parse(s);console.log("RPS",Math.round(r.requests.average),"p50",r.latency.p50,"p99",r.latency.p99,"non2xx",r.non2xx,"errors",r.errors)})'
done
psqlr "SELECT calls, round(total_exec_time::numeric) AS total_ms, round(mean_exec_time::numeric, 2) AS mean_ms, left(query, 70) AS query FROM pg_stat_statements WHERE query ILIKE '%tbl_%' ORDER BY total_exec_time DESC LIMIT 5"
```

### result
```out auto
```

Три эндпоинта — три разных профиля: **`/booking`** (поиск по ключу — очень быстрый), **`/search`** (поиск по имени — зависит от триграммного индекса из 8.5), **`/branch-report`** (агрегат по филиалу — зависит от индекса `branch_id`/`status`). В `pg_stat_statements` сверху — запрос, который **больше всего съел времени в сумме**: именно с него и начинают оптимизацию. Запиши цифры в таблицу «**до**» (RPS, p99, ошибки, самый «дорогой» запрос).

**Оптимизируй** то, что показала статистика: проверь `EXPLAIN` самого «дорогого» запроса, добавь индекс (шаг 8.4–8.5), проверь размер пула (17.1), ограничения на транзакции — и **повтори замер** («**после**»). Критерий: рост RPS или падение p99 **подтверждены числами**, ошибок `non2xx = 0`.

```bash run
pkill -f "tsx src/server.ts" || true
```

### why
Без замера любая «оптимизация» — догадка. Связка «нагрузка → `pg_stat_statements` → `EXPLAIN` → правка → повторная нагрузка» — главный рабочий цикл разработчика, отвечающего за производительность: на основе фактов, а не ощущений.

### deep Команды по частям
`-c 40` — 40 одновременных соединений, `-d 8` — 8 секунд. p50/p99 — задержка, ниже которой укладываются 50 % / 99 % запросов; **p99 важнее среднего**: именно он определяет, как себя чувствуют «невезучие» пользователи. `total_exec_time` в `pg_stat_statements` — суммарное время запроса за всё время: «дорогой» запрос может быть быстрым, но частым.

### deep Если не получилось
- **`autocannon` показывает 100 % ошибок** — сервер не запущен или упал: `cat /tmp/rentkit-server.log`.
- **`non2xx` > 0 с «не найден филиал»** — RLS закрыт (`withScope` не вызван) или клиент под `rental_app` без прав; проверь логи сервера.
- **Ноутбук греется** — нагрузка тяжёлая для локальной машины; уменьши `-c` до 20 и `-d` до 5.

### quiz
- Почему p99 важнее среднего времени ответа?
- Как `pg_stat_statements` помогает выбрать, что оптимизировать?
- Что должно быть в отчёте «до/после», чтобы его можно было считать доказательством?

### links
- https://github.com/mcollina/autocannon | autocannon | GitHub: autocannon
- https://www.postgresql.org/docs/18/pgstatstatements.html | pg_stat_statements | PostgreSQL 18: pg_stat_statements

## 17.5 Большие данные: сидирование миллиона строк и обход выборки порциями | short: Миллион строк | est: ~55 мин
### intro
**Слова шага:** *сидирование*, *`createMany` против `INSERT … SELECT generate_series`*, *`COPY`*, *порции (batch)*, *обход таблицы по курсору*, *память*.

:::tip Если совсем просто
Миллион строк в базу можно занести тремя способами: **по одной** (часы), **пачками через ORM** (десятки секунд), **командой самой базы** (секунды). Другая сторона — **прочитать** миллион строк: не «всё в память», а порциями по пять тысяч, как грузить фуру по паллетам.
:::

Нужна большая таблица. Журнал событий выдачи (1 000 000 строк):

```prisma schema
model EventLog {
  id        BigInt   @id @default(autoincrement())
  bookingId Int      @map("booking_id")
  kind      String
  at        DateTime @default(now()) @db.Timestamptz(3)
  @@index([bookingId])
  @@map("event_log")
}
```

```bash run
cd ~/prisma-lab/rentkit
npx prisma migrate dev --name event_log
npm run generate
cat > src/lessons/17-seed.ts <<'EOF'
import { prisma } from '../db.js'
import { timed } from '../lib/timed.js'

const N = 100_000          // для сравнения способов — 100 тысяч, не миллион

await prisma.$executeRaw`DELETE FROM event_log`           // TRUNCATE рабочей роли не выдан (16.2) — стираем DELETE-ом

await timed('createMany, пачки по 5 000', async () => {
  for (let lo = 0; lo < N; lo += 5000) {
    await prisma.eventLog.createMany({ data: Array.from({ length: 5000 }, (_, i) => ({ bookingId: 1 + ((lo + i) % 300000), kind: 'issue' })) })
  }
})
await prisma.$executeRaw`DELETE FROM event_log`

await timed('INSERT … SELECT generate_series', () =>
  prisma.$executeRaw`INSERT INTO event_log (booking_id, kind) SELECT 1 + (g % 300000), 'issue' FROM generate_series(1, ${N}) g`)

console.log('строк в таблице:', await prisma.eventLog.count())
await prisma.$disconnect()
EOF
npx tsx src/lessons/17-seed.ts
```

### result
```out auto
```

Ожидаем: `createMany` пачками — секунды, `INSERT … SELECT generate_series` — **в разы и десятки раз быстрее** (у нас ≈3,4 с против ≈0,2 с, то есть примерно 17×) (данные рождаются внутри базы, без поездок по сети и разбора параметров). Для **внешних** данных (CSV из файла) самый быстрый способ — `COPY` (`\copy` в `psql`, либо `pg-copy-streams` из Node). Правила выбора: **данные уже в базе или генерируются** — `INSERT … SELECT`; **данные приходят из приложения** — `createMany` пачками по 1–5 тысяч строк (не больше 65 535 параметров на запрос); **файл** — `COPY`.

Теперь **обход** миллиона строк порциями (потоковой выборки у Prisma нет — берём по ключу):

```ts
// src/lessons/17-walk.ts
import { prisma } from '../db.js'

await prisma.$executeRaw`DELETE FROM event_log`
await prisma.$executeRaw`INSERT INTO event_log (booking_id, kind) SELECT 1 + (g % 300000), 'issue' FROM generate_series(1, 1000000) g`

const BATCH = 5000
let lastId = 0n, processed = 0, peakMb = 0
for (;;) {
  const rows = await prisma.eventLog.findMany({ where: { id: { gt: lastId } }, orderBy: { id: 'asc' }, take: BATCH, select: { id: true, bookingId: true } })
  if (rows.length === 0) break
  processed += rows.length                      // «обработка» порции
  lastId = rows.at(-1)!.id
  peakMb = Math.max(peakMb, Math.round(process.memoryUsage().heapUsed / 1e6))
}
console.log(`обработано ${processed} строк, пик памяти ~${peakMb} МБ`)
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/17-walk.ts
```

### result
```out auto
```

Ожидаем: **миллион строк обработан, пик памяти — порядка ста мегабайт** (у нас ~108 МБ: это сам Node с клиентом и одна порция, а не весь миллион). Приём — keyset-обход из шага 8.2: `where id > lastId order by id take N`. Читать «всё сразу» (`findMany()` без `take`) на такой таблице — классический способ уронить приложение по памяти.

### why
Объёмы данных — граница, на которой наивный код перестаёт работать: сидирование «циклом create» занимало бы часы, а «загрузить всё и обработать» не помещалось бы в память. Знание трёх способов вставки и одного способа обхода покрывает 95 % практических случаев.

### deep Как ещё можно
Для ещё более тяжёлых выгрузок (десятки миллионов строк, экспорт в файл) используют **серверные курсоры** (`DECLARE … CURSOR`) через драйвер `pg` напрямую (`pg-cursor`/`pg-query-stream`) — Prisma их не предоставляет. Это уже выход за пределы ORM, как и `COPY`.

### deep Если не получилось
- **`createMany` падает на параметрах** — пачка слишком велика (5 000 строк × 2 колонки = 10 000 параметров — допустимо; 40 000 строк — нет).
- **Пик памяти большой** — случайно взят `findMany` без `take` или в порции слишком много колонок.

### quiz
- В каком случае какой из трёх способов вставки выбрать?
- Почему обход миллиона строк делают порциями по ключу, а не одним `findMany`?
- Что такое keyset-обход и почему он не замедляется на глубине?

### links
- https://www.postgresql.org/docs/18/sql-copy.html | COPY | PostgreSQL 18: COPY
- https://www.prisma.io/docs/orm/v7/prisma-client/queries/crud#create-multiple-records | createMany | Prisma 7: Create multiple records

## 17.6 Таймауты и отмена: запрос, который «завис» | short: Таймауты запросов | est: ~40 мин
### intro
**Слова шага:** *`statement_timeout`*, *`lock_timeout`*, *`idle_in_transaction_session_timeout`*, *`SET LOCAL`*, *код `57014`*, *защита от «залипших» запросов*.

:::tip Если совсем просто
Бывает, что один запрос «завис» — ждёт блокировки или считает что-то чудовищное — и держит соединение, пока не накопятся остальные. Таймауты — это «будильники»: если запрос не уложился за N секунд, база **сама его отменяет**. Это единственная защита от того, чего ты не предвидела.
:::

Три «будильника» PostgreSQL (задаются на роль, на сессию или на транзакцию):

| Параметр | Что отменяет |
|---|---|
| `statement_timeout` | любой **запрос**, который выполняется дольше N |
| `lock_timeout` | ожидание **блокировки** дольше N (вместо вечного ожидания) |
| `idle_in_transaction_session_timeout` | сессию, которая открыла транзакцию и **ничего не делает** дольше N (шаг 12.5) |

Выдадим их рабочей роли **навсегда** и проверим:

```bash run
psqlr() { docker exec -i rental-pg psql -U postgres -d rental -c "$@"; }
psqlr "ALTER ROLE rental_app SET statement_timeout = '5s'"
psqlr "ALTER ROLE rental_app SET lock_timeout = '3s'"
psqlr "ALTER ROLE rental_app SET idle_in_transaction_session_timeout = '15s'"
cat > src/lessons/17-timeout.ts <<'EOF'
import { prisma } from '../db.js'

const t0 = Date.now()
await prisma.$queryRaw`SELECT pg_sleep(10)`.catch((e) => console.log('отменён через', Date.now() - t0, 'мс:', String(e.message).split('\n').filter(Boolean).pop()))

// для конкретного тяжёлого отчёта — своё ограничение «только на эту транзакцию»
await prisma.$transaction(async (tx) => {
  await tx.$executeRaw`SET LOCAL statement_timeout = '500ms'`
  await tx.$queryRaw`SELECT pg_sleep(2)`
}).catch((e) => console.log('отчёт отменён:', String(e.message).split('\n').filter(Boolean).pop()))
await prisma.$disconnect()
EOF
npx tsx src/lessons/17-timeout.ts
```

### result
```out auto
```

Ожидаем: первый запрос оборван через ~5 секунд ошибкой `canceling statement due to statement timeout` (код `57014`; через `$queryRaw` она приходит как `Raw query failed. Code: 57014`, как в выводе выше), второй — через 0,5 с. **Два уровня ограничения:** по умолчанию — для роли (общая страховка), для особых запросов — `SET LOCAL` в транзакции (**только на неё**: `LOCAL` сбрасывается в конце, поэтому не протекает в пул). Отдельно от них у Prisma свои таймауты **интерактивной транзакции** (`timeout`, `maxWait`) — они работают на стороне клиента и не заменяют серверных.

### why
Таймаут — обязательный пояс безопасности. Без него один «залипший» запрос или забытая блокировка превращается в каскад: соединения заняты, очередь растёт, сервис «падает», хотя база формально жива.

### deep Если не получилось
- **Запрос не отменяется** — настройки роли применяются к **новым** сессиям; пул держит старые соединения: перезапусти скрипт (новое соединение), а в проде — перезапусти пул.
- **`SET LOCAL` не работает** — вне транзакции он ничего не делает (предупреждение «can only be used in transaction blocks»): только внутри `$transaction`.

### quiz
- Чем `statement_timeout` отличается от `lock_timeout`?
- Почему `SET LOCAL` безопаснее `SET` при работе с пулом?
- Чем серверные таймауты отличаются от `timeout` интерактивной транзакции Prisma?

### links
- https://www.postgresql.org/docs/18/runtime-config-client.html | клиентские параметры | PostgreSQL 18: Client Connection Defaults

## 17.7 🔨 «Приложение упало на 200-м запросе» | short: 🔨 Пул исчерпан | est: ~65 мин
### intro
**Слова шага:** *жалоба заказчика*, *исчерпание пула*, *зависшая интерактивная транзакция*, *внешний вызов внутри транзакции*, *`idle in transaction`*, *`maxWait`*.

:::tip Если совсем просто
Сервис нормально работает на 50 запросах, а на 200 «замирает» и перестаёт отвечать даже на простые. Нагрузка не безумная, база не перегружена — а запросы выстроились в очередь. Причина — в коде, где-то держат линию слишком долго.
:::

*Заказчик:* «Ночью при рассылке напоминаний сервис встал на несколько минут. База спокойна, процессор не загружен. После перезапуска всё как обычно».

Добавим в `src/server.ts` «рассылку» — типичный вид этой ошибки:

```ts splice=src/server.ts@send\(res,\s404
// src/server.ts — добавить ветку
if (url.pathname === '/remind') {                                       // POST-подобный: отправить напоминание и записать, что отправили
  const id = Number(url.searchParams.get('id'))
  const result = await prisma.$transaction(async (tx) => {              // ← интерактивная транзакция держит соединение…
    const b = await tx.booking.findUnique({ where: { id } })
    await new Promise((r) => setTimeout(r, 2000))                       // ← …пока мы «отправляем письмо» во внешнюю систему
    return tx.eventLog.create({ data: { bookingId: id, kind: 'remind' } })
  })
  return send(res, 200, { ok: true, event: String(result.id) })
}
```

Воспроизведи (нагрузка на `/remind` идёт в фоне; в середине смотрим, что делает база, и пробуем «простой» эндпоинт):

```bash run
cd ~/prisma-lab/rentkit
(npx tsx src/server.ts > /tmp/rentkit-server.log 2>&1 &)
sleep 3
(npx autocannon -c 30 -d 10 --json "http://127.0.0.1:3100/remind?id=1" 2>/dev/null > /tmp/remind.json &)
sleep 4
psqlr() { docker exec -i rental-pg psql -U postgres -d rental -c "$@"; }
psqlr "SELECT state, count(*) FROM pg_stat_activity WHERE datname = 'rental' GROUP BY 1 ORDER BY 2 DESC"
npx autocannon -c 5 -d 3 --json "http://127.0.0.1:3100/booking?id=1" 2>/dev/null | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{const r=JSON.parse(s);console.log("простой эндпоинт при этом: RPS",Math.round(r.requests.average),"p99",r.latency.p99,"non2xx",r.non2xx)})'
sleep 5
node -e 'const r=JSON.parse(require("fs").readFileSync("/tmp/remind.json","utf8"));console.log("/remind: RPS",Math.round(r.requests.average),"p99",r.latency.p99,"non2xx",r.non2xx,"timeouts",r.timeouts)'
pkill -f "tsx src/server.ts" || true
```

### result
```out auto
```

Ожидаем: `/remind` даёт **единицы запросов в секунду** (30 параллельных на пул из 10 соединений, каждый держит линию 2 секунды), а главное — **простой эндпоинт `/booking` в это время тоже тормозит или падает**: линий не осталось. Во время нагрузки в `pg_stat_activity` — **`idle in transaction`**: транзакции открыты, но ничего не делают. Исправь: (1) **вынеси «отправку письма» за пределы транзакции** (до или после), оставив внутри только операции с базой; (2) задай **`maxWait`/`timeout`** транзакции и `connectionTimeoutMillis` пула, чтобы перегрузка проявлялась **быстрой ошибкой**, а не общим зависанием; (3) подтверди числами: `/remind` и `/booking` **не мешают** друг другу.

**Приёмка сессии:** пул и таймауты заданы осознанно (параметры в `db.ts`, арифметика соединений записана), клиент — singleton с защитой от горячей перезагрузки, нагрузочный отчёт «до/после» с числами (RPS, p99, ошибки) и найденным по `pg_stat_statements` самым дорогим запросом, миллион строк обработан порциями с пиком памяти в десятки МБ, серверные таймауты выданы рабочей роли, `/remind` исправлен.

### why
Это та же ошибка, что мы видели в шаге 12.5, но в «боевой» обёртке и с цифрами. Правило одно: **транзакция — только база.** Любое ожидание сети, диска, внешнего сервиса — вне транзакции. Следствие второго порядка: перегрузка должна проявляться **быстрой и понятной ошибкой**, а не «общей слабостью» всего сервиса — за этим и нужны таймауты.

### deep Если не получилось
- **Эффекта «замирает» нет** — на твоей машине пул оказался больше нагрузки; уменьши `DB_POOL_MAX=3` и повтори.
- **Подсказка:** отправку письма (`setTimeout`) перенеси **до** `$transaction`; результат отправки передай внутрь; если письмо — часть успеха операции, делай **два шага**: записать «собираемся отправлять» → отправить → записать «отправлено» (каждая запись — своя короткая транзакция).
- **`idle in transaction` не видно** — выполняй запрос к `pg_stat_activity` **во время** нагрузки, в соседнем терминале.

### quiz
- Почему долгая интерактивная транзакция роняет даже несвязанные эндпоинты?
- Какие три меры защищают от исчерпания пула?
- Как правильно вставить внешний вызов в операцию, которая меняет данные?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/queries/transactions#interactive-transactions | интерактивные транзакции | Prisma 7: Interactive transactions
