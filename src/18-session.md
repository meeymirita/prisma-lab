# Сессия 18 · Тесты, поставка и Production Hell
dur: ~4 ч

## 18.1 Тесты слоя данных на настоящей базе: шаблонная база | short: Vitest и шаблон БД | est: ~55 мин
### intro
**Слова шага:** *тест на настоящей базе*, *Vitest*, *шаблонная база (`TEMPLATE`)*, *отдельная база на файл тестов*, *`globalSetup`/`setupFiles`*, *почему не мок*.

:::tip Если совсем просто
Слой данных нельзя проверить «подставной» базой: ограничения, триггеры, RLS, `EXCLUDE` и `ON CONFLICT` существуют **только в настоящем PostgreSQL**. Но тесты не должны портить рабочую базу и мешать друг другу. Приём: один раз готовим **эталонную пустую базу** со всем устройством (таблицы, ограничения, триггеры), а на каждый файл тестов **мгновенно копируем** её командой `CREATE DATABASE … TEMPLATE`.
:::

```svg
@test-template-db
```

**Шаг 1 — эталонная база.** Только устройство (без данных), включая права и политики:

```bash run
psqlr() { docker exec -i rental-pg psql -U postgres "$@"; }
psqlr -c 'DROP DATABASE IF EXISTS rental_template'
psqlr -c 'CREATE DATABASE rental_template'
docker exec rental-pg pg_dump -U postgres -d rental --schema-only | docker exec -i rental-pg psql -U postgres -d rental_template -v ON_ERROR_STOP=1 -q
psqlr -d rental_template -c 'SELECT count(*) AS таблиц FROM information_schema.tables WHERE table_schema = $$public$$'
```

### result
```out auto
```

**Шаг 2 — Vitest.** Установка и конфигурация:

```bash run
cd ~/prisma-lab/rentkit
npm install -D vitest
mkdir -p test
```

### result
```out auto
```

```ts
// vitest.config.ts
import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    include: ['test/**/*.test.ts', 'hell/test/**/*.test.ts'],
    setupFiles: ['test/setup.ts'],
    pool: 'forks',                 // отдельные процессы: у каждого файла свои подключения и своя база
    testTimeout: 30_000,
  },
})
```

```ts
// test/setup.ts — выполняется перед КАЖДЫМ файлом тестов, до импорта кода
import 'dotenv/config'
import { Client } from 'pg'
import { afterAll } from 'vitest'

const admin = process.env.DATABASE_URL!.replace(/\/[^/?]+(\?|$)/, '/postgres$1')   // подключение к служебной базе
const dbName = `rental_test_${process.pid}_${Date.now()}`

const c = new Client({ connectionString: admin })
await c.connect()
await c.query(`CREATE DATABASE "${dbName}" TEMPLATE rental_template`)
await c.end()

// код слоя данных (db.ts) прочитает адреса уже после этого
process.env.DATABASE_URL = process.env.DATABASE_URL!.replace(/\/[^/?]+(\?|$)/, `/${dbName}$1`)
if (process.env.APP_DATABASE_URL) process.env.APP_DATABASE_URL = process.env.APP_DATABASE_URL.replace(/\/[^/?]+(\?|$)/, `/${dbName}$1`)

afterAll(async () => {
  const { prisma } = await import('../src/db.js')
  await prisma.$disconnect()
  const d = new Client({ connectionString: admin })
  await d.connect()
  await d.query(`DROP DATABASE IF EXISTS "${dbName}" WITH (FORCE)`)
  await d.end()
})
```

Первый тест (проверяет двойную бронь — тот же инвариант, что в 13.3, но **как автоматический тест**):

```ts
// test/factories.ts — «фабрики» минимальных данных
import { prisma } from '../src/db.js'

let n = 0
export const uniq = () => `${Date.now()}-${++n}`

export async function makeBranch(tz = 'Europe/Moscow') {
  return prisma.branch.create({ data: { name: 'Тест ' + uniq(), city: 'Тест', tz } })
}
export async function makeItem(branchId: number) {
  return prisma.item.create({ data: { branchId, sku: 'T-' + uniq(), title: 'Тестовый предмет', category: 'Тест', active: 1 } })
}
export async function makeCustomer(branchId: number) {
  return prisma.customer.create({ data: { branchId, name: 'Клиент ' + uniq(), phone: '+7999' + String(Math.floor(Math.random() * 1e7)).padStart(7, '0') } })
}
```

```ts
// test/booking-overlap.test.ts
import { describe, expect, it } from 'vitest'
import { createBooking } from '../src/data/bookings.js'
import { ItemBusyError } from '../src/lib/errors.js'
import { makeBranch, makeCustomer, makeItem } from './factories.js'

describe('двойная бронь', () => {
  it('параллельные брони одного предмета на одни даты: успех ровно один', async () => {
    const b = await makeBranch(), item = await makeItem(b.id), cust = await makeCustomer(b.id)
    const input = { itemId: item.id, customerId: cust.id, branchId: b.id, startsAt: new Date('2040-01-01T00:00:00Z'), endsAt: new Date('2040-01-04T00:00:00Z') }
    const results = await Promise.allSettled(Array.from({ length: 50 }, () => createBooking(input)))
    expect(results.filter((r) => r.status === 'fulfilled')).toHaveLength(1)
    expect(results.filter((r) => r.status === 'rejected' && r.reason instanceof ItemBusyError)).toHaveLength(49)
  })

  it('соседние, но не пересекающиеся брони допускаются', async () => {
    const b = await makeBranch(), item = await makeItem(b.id), cust = await makeCustomer(b.id)
    const day = (d: string) => new Date(d + 'T00:00:00Z')
    await createBooking({ itemId: item.id, customerId: cust.id, branchId: b.id, startsAt: day('2041-02-01'), endsAt: day('2041-02-03') })
    await expect(createBooking({ itemId: item.id, customerId: cust.id, branchId: b.id, startsAt: day('2041-02-03'), endsAt: day('2041-02-05') })).resolves.toBeDefined()
  })
})
```

```bash run
cd ~/prisma-lab/rentkit
npx vitest run test/booking-overlap.test.ts
```

### result
```out auto
```

Ожидаем: два теста зелёные; в `psql` после них **нет** баз `rental_test_*` (`\l`): `afterAll` удаляет временную базу. **Почему так, а не мок:** мок `prisma.booking.create` проверил бы лишь, что код вызывает `create`, но не то, что **база** запретила пересечение; параллельный тест на 50 вызовов показывает гонку, которую никакой мок не воспроизведёт.

### why
Тесты слоя данных — самая ценная часть набора: именно здесь живут инварианты. Шаблонная база делает их **быстрыми** (копирование крошечной базы — десятки миллисекунд) и **независимыми** (каждый файл — свои данные, можно запускать параллельно).

### deep Команды по частям
`CREATE DATABASE x TEMPLATE y` копирует базу целиком на уровне файлов — гораздо быстрее, чем применять миграции к пустой; условие — к шаблону **никто не подключён** в момент копирования. `DROP DATABASE … WITH (FORCE)` обрывает чужие подключения (PostgreSQL 13+). `pool: 'forks'` — каждый файл тестов в своём процессе, поэтому `process.env` и `PrismaClient` у каждого свои.

### deep Если не получилось
- **`source database "rental_template" is being accessed by other users`** — открыто подключение к шаблону (`psql`, Studio): закрой.
- **Тесты видят данные из рабочей `rental`** — переменные не подменены: `test/setup.ts` должен выполняться **до** импорта `db.ts`; проверь `setupFiles`.
- **Права `permission denied` в тесте** — шаблон создан без прав (`--no-acl`) или роль `rental_app` не создана: пересоздай шаблон командой из шага 1.

### quiz
- Почему слой данных тестируют на настоящей базе, а не на моке?
- Что даёт `TEMPLATE` по сравнению с применением миграций на каждый тест?
- Почему `setupFiles` должен выполняться до импорта `db.ts`?

### links
- https://vitest.dev/config/ | конфигурация Vitest | Vitest: Config
- https://www.prisma.io/docs/orm/v7/prisma-client/testing/integration-testing | интеграционные тесты | Prisma 7: Integration testing

## 18.2 Тесты инвариантов: деньги, изоляция, soft delete | short: Набор тестов | est: ~55 мин
### intro
**Слова шага:** *инвариант*, *тест «на обход»*, *счётчик операций*, *проверка идемпотентности*, *пять тестовых файлов*.

:::tip Если совсем просто
Хороший набор тестов — не «проверка, что функция вернула число», а **список обещаний системы**: «не бывает двойной брони», «деньги сходятся», «филиал А не видит филиал Б», «удалённый клиент не вернётся». Каждое обещание — один тест, и каждое можно нарушить только осознанно, увидев красный цвет.
:::

Напиши ещё четыре тестовых файла (по образцу 18.1). Опорные точки:

```ts
// test/payments.test.ts — идемпотентность и баланс
import { describe, expect, it } from 'vitest'
import { recordPayment } from '../src/data/payments.js'
import { prisma } from '../src/db.js'
import { makeBranch, makeCustomer, makeItem } from './factories.js'

describe('платежи', () => {
  it('1 000 платежей с 10 % повторов: записей = числу уникальных ключей, баланс сходится до копейки', async () => {
    const b = await makeBranch(), item = await makeItem(b.id), cust = await makeCustomer(b.id)
    const booking = await prisma.booking.create({ data: { itemId: item.id, customerId: cust.id, branchId: b.id, status: 'CONFIRMED', startsAt: new Date('2042-01-01'), endsAt: new Date('2042-01-02') } })
    await prisma.ledgerAccount.createMany({ data: [{ code: 'CASH', name: 'Касса' }, { code: 'REVENUE', name: 'Выручка' }, { code: 'DEPOSITS', name: 'Залоги' }], skipDuplicates: true })

    const refs = Array.from({ length: 1000 }, (_, i) => `T-${booking.id}-${i}`)
    const calls = [...refs, ...refs.slice(0, 100)]                                    // 100 повторов
    await Promise.all(calls.map((extRef, i) => recordPayment({ bookingId: booking.id, amount: (1 + (i % 97) / 100).toFixed(2), kind: 1, extRef })))

    const payments = await prisma.payment.findMany({ where: { bookingId: booking.id } })
    expect(payments).toHaveLength(1000)
    const [{ cash }] = await prisma.$queryRaw<{ cash: string }[]>`SELECT sum(e.amount)::text AS cash FROM ledger_entry e JOIN ledger_account a ON a.id = e.account_id WHERE a.code = 'CASH' AND e.booking_id = ${booking.id}`
    const expected = payments.reduce((s, p) => s.plus(p.amount!), new (await import('../src/generated/prisma/client.js')).Prisma.Decimal(0))
    expect(cash).toBe(expected.toFixed(2))
  })
})
```

Остальные три — по твоему плану (а список обязательных «обещаний» ниже — минимальный):

- **`test/isolation.test.ts`** — под ролью `rental_app` через `scoped(...)`: набор проверок из шага 16.6 (чтение, изменение, удаление, запись в чужой филиал, raw); **и** тест на протечку через пул (`max: 1`, шаг 16.7).
- **`test/soft-delete.test.ts`** — пять «боковых входов» из 15.7: каждый — отдельный `it`, **красный, пока не закрыт**.
- **`test/ledger.test.ts`** — несбалансированная проводка отклоняется триггером; залог проходит цикл «принять → удержать → вернуть» с нулевым остатком; возврат доли не теряет копейки.
- **`test/query-count.test.ts`** — `listBookingCards` делает **не больше трёх операций** (через расширение `timing`, шаг 15.2): защита от возврата N+1.

```bash run
cd ~/prisma-lab/rentkit
npx vitest run 2>&1 | tail -25
```

### result
```out auto
```

Критерий: **все файлы зелёные**, время полного прогона — в пределах минуты, после прогона не остаётся баз `rental_test_*`. Правила хороших тестов данных: (1) **один тест — одно обещание**, имя — на языке бизнеса; (2) тесты **независимы** (свои данные через фабрики, а не общие фикстуры); (3) **параллельные** сценарии проверяются **параллельным** запуском, а не последовательным; (4) тесты изоляции — **под ролью приложения**; (5) для каждого найденного дефекта сначала пишется **красный** тест, потом исправление.

### why
Набор из этих обещаний — «страховой полис»: рефакторинг, обновление Prisma, добавление расширения — всё проверяется за минуту. Особенно ценны тесты «на обход»: они ловят не ошибки в коде, а **дыры в правилах**.

### deep Если не получилось
- **Тест платежей медленный** — 1 100 параллельных транзакций на пул из 10 соединений идут пачками; уменьши до 300 или подними пул в тестовом окружении.
- **`ledger_account` дублируется** — `skipDuplicates` работает с уникальным `code` (он у нас `@unique`); если ошибка — таблица не из шаблона.

### quiz
- Почему «один тест — одно обещание» и как формулировать названия?
- Зачем параллельные сценарии в тестах запускать параллельно?
- Какой тест обязательно пишется до исправления найденного дефекта?

### links
- https://vitest.dev/guide/ | руководство Vitest | Vitest: Guide
- https://www.prisma.io/docs/orm/v7/prisma-client/testing/unit-testing | модульные тесты | Prisma 7: Unit testing

## 18.3 CI: пустая база, миграции с нуля, тесты | short: CI | est: ~55 мин
### intro
**Слова шага:** *CI*, *GitHub Actions*, *`services: postgres`*, *`migrate deploy` на пустой базе*, *проверка «схема = история»*, *роль в CI*.

:::tip Если совсем просто
CI — «робот-контролёр»: при каждом изменении поднимает **с нуля** чистую базу, проигрывает всю историю миграций, запускает тесты. Если история миграций где-то «ломается» на пустой базе (потому что у тебя на ноутбуке всё работало «по случайности»), робот это покажет раньше, чем коллега.
:::

Прежде чем писать конфигурацию, проверь то же руками — **вся ли история проигрывается на пустой базе**:

```bash run
cd ~/prisma-lab/rentkit
psqlr() { docker exec -i rental-pg psql -U postgres "$@"; }
psqlr -c 'DROP DATABASE IF EXISTS rental_ci'
psqlr -c 'CREATE DATABASE rental_ci'
DATABASE_URL="postgresql://postgres:postgres@localhost:5433/rental_ci" npx prisma migrate deploy 2>&1 | tail -15
```

### result
```out auto
```

Ожидаем: все миграции применились без ошибок. Если одна **упала** — это ровно та проблема, которую ловит CI: миграция неявно рассчитана на данные, которых в пустой базе нет (например, вставка в таблицу с внешним ключом на запись, существующую только в рабочей базе — поэтому в шаге 11.1 служебные записи созданы без привязки к филиалу). **Правило:** история миграций должна проигрываться на **пустой** базе. Исправление упавшей миграции допустимо **только** пока она не применена на общих базах; иначе — новая миграция поверх.

Рабочий процесс CI (GitHub Actions; **не запускалось**, проверяется при первом коммите):

```yaml
# .github/workflows/ci.yml
name: ci
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:18
        env: { POSTGRES_PASSWORD: postgres, POSTGRES_DB: rental }
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U postgres" --health-interval 5s --health-timeout 5s --health-retries 10
    env:
      DATABASE_URL: postgresql://postgres:postgres@localhost:5432/rental
      APP_DATABASE_URL: postgresql://rental_app:ci-only-password@localhost:5432/rental
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 24, cache: npm }
      - run: npm ci
      - run: npx prisma generate
      - name: Роль приложения (только для CI)
        run: psql "$DATABASE_URL" -c "CREATE ROLE rental_app LOGIN PASSWORD 'ci-only-password' NOSUPERUSER NOBYPASSRLS"
      - run: npx prisma migrate deploy                       # вся история с нуля
      - name: Схема совпадает с базой после миграций
        run: npx prisma migrate diff --from-config-datasource --to-schema prisma/schema.prisma --exit-code   # 0 — совпало, 2 — есть различия
      - name: Эталонная база для тестов
        run: |
          psql "$DATABASE_URL" -c "CREATE DATABASE rental_template"
          pg_dump "$DATABASE_URL" --schema-only | psql "postgresql://postgres:postgres@localhost:5432/rental_template" -q
      - run: npm run typecheck
      - run: npx vitest run
```

Что здесь важно: (1) **`migrate deploy`, а не `dev`** — CI ничего не придумывает и не спрашивает; (2) **роль приложения** создаётся отдельным шагом (пароль — **только для CI**, а не рабочий; настоящие пароли — в секретах репозитория); (3) шаг **«схема совпадает с базой после миграций»**: `migrate diff --from-config-datasource --to-schema … --exit-code` (флаги Prisma 7 — по справочнику CLI) завершается кодом `2`, если кто-то изменил `schema.prisma` и забыл создать миграцию; **сверьтесь**, что ручные объекты (частичные индексы, `EXCLUDE`, триггеры), которых Prisma не описывает, не дают ложного расхождения; (4) **`prisma generate`** — отдельный обязательный шаг (в Prisma 7 автоматически не вызывается); (5) для TypedSQL нужен `prisma generate --sql` **после** `migrate deploy` — базе нужно существовать при генерации.

### why
Робот-контролёр защищает от трёх классов поломок: «забыл закоммитить миграцию», «миграция работает только у меня» и «после обновления зависимостей что-то поплыло». Единственная цена — потраченное один раз время на настройку.

### deep Если не получилось
- **Проигрывание на пустой базе падает на миграции из шага 10.x** — в пустой базе нет данных для `UPDATE … WHERE`: такие команды просто ничего не обновят; ошибки быть не должно; смотри текст ошибки.
- **`role "rental_app" does not exist` в миграции с правами** — роль создаётся шагом **до** `migrate deploy` (защитная проверка в миграции 16.2 обработает и отсутствие роли).
- **`migrate diff` возвращает различия при чистой истории** — база содержит объекты, которых нет в схеме Prisma (частичные индексы, `EXCLUDE`, генерируемые колонки, триггеры); убедись, что различия — только они, и вынеси проверку в виде «нет `DROP COLUMN`/`DROP TABLE` в выводе `--script`».

### quiz
- Зачем в CI проигрывать миграции на пустой базе?
- Что проверяет шаг «схема совпадает с историей» и какую ошибку он ловит?
- Почему в CI используется `migrate deploy`, а не `migrate dev`?

### links
- https://docs.github.com/en/actions/use-cases-and-examples/using-containerized-services/creating-postgresql-service-containers | PostgreSQL в Actions | GitHub Docs: PostgreSQL service containers
- https://www.prisma.io/docs/orm/v7/prisma-client/deployment/deploy-database-changes-with-prisma-migrate | деплой миграций | Prisma 7: Deploy database changes

## 18.4 Образ приложения: generate при сборке, миграции отдельно | short: Docker-образ | est: ~45 мин
### intro
**Слова шага:** *многоступенчатая сборка*, *`prisma generate` при сборке*, *миграции отдельным шагом*, *health-check*, *непривилегированный пользователь*.

:::tip Если совсем просто
Образ — «запаянная коробка» с приложением. Сборка проходит в мастерской (там есть инструменты: компилятор, `prisma` CLI), а в рабочую коробку кладётся только готовое. Миграции выполняются **не при запуске коробки**, а отдельным «монтажным» шагом выкатки — иначе десять копий приложения одновременно полезут менять базу.
:::

```dockerfile
# Dockerfile
FROM node:24-slim AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY prisma ./prisma
COPY prisma.config.ts tsconfig.json ./
COPY src ./src
RUN npx prisma generate && npx tsc -p tsconfig.build.json     # клиент создаётся при сборке образа

FROM node:24-slim AS run
WORKDIR /app
ENV NODE_ENV=production
COPY package*.json ./
RUN npm ci --omit=dev && npm cache clean --force
COPY --from=build /app/dist ./dist
USER node
EXPOSE 3100
HEALTHCHECK --interval=10s --timeout=3s --retries=3 CMD node -e "fetch('http://localhost:3100/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "dist/server.js"]
```

`tsconfig.build.json` — отдельная конфигурация сборки (без тестов и уроков):

```json
{
  "extends": "./tsconfig.json",
  "compilerOptions": { "outDir": "dist", "rootDir": "src", "noEmit": false },
  "include": ["src/db.ts", "src/server.ts", "src/data", "src/lib", "src/extensions", "src/generated", "src/client.ts"],
  "exclude": ["src/lessons", "src/intro"]
}
```

Эндпоинт проверки здоровья — база должна отвечать (в `src/server.ts`):

```ts
if (url.pathname === '/health') {
  await prisma.$queryRaw`SELECT 1`                       // если база недоступна — упадёт и вернёт 500
  return send(res, 200, { ok: true })
}
```

**Миграции при выкатке — отдельный шаг**, а не `CMD`:

```bash
# релизный шаг (один раз за выкатку, не на каждой копии приложения)
docker run --rm --env-file .env.release rentkit-tools npx prisma migrate deploy
```

(Для этого нужен либо образ со стадией `tools` и `prisma` CLI, либо запуск `migrate deploy` из CI до обновления копий.) Что надо учесть: (1) **`prisma` (CLI) — dev-зависимость**, а в рабочий образ идёт только клиент и адаптер (`--omit=dev`); (2) папка **`src/generated`** должна быть собрана в `dist` (поэтому `generate` — **до** `tsc`); (3) если используешь TypedSQL — `prisma generate --sql` на сборке требует доступной базы (в CI она есть); (4) **миграции — до** обновления копий приложения, а изменения схемы — **совместимые** (expand/contract, сессия 10), иначе старая копия сломается на новой схеме.

```bash run
cd ~/prisma-lab/rentkit
cat > tsconfig.build.json <<'EOF'
{
  "extends": "./tsconfig.json",
  "compilerOptions": { "outDir": "dist", "rootDir": "src", "noEmit": false },
  "include": ["src/db.ts", "src/server.ts", "src/data", "src/lib", "src/extensions", "src/generated", "src/client.ts"],
  "exclude": ["src/lessons", "src/intro"]
}
EOF
npx prisma generate && npx tsc -p tsconfig.build.json && ls dist | head
```

### result
```out auto
```

### why
Две частые ошибки образов с Prisma: (1) забытый `generate` — приложение падает при старте «Cannot find module generated/prisma»; (2) миграции в `CMD` — при масштабировании 5 копий одновременно запускают `migrate deploy`, и одна из них (или все) получают блокировки и ошибки. Разделение «сборка → миграция → запуск» снимает обе.

### deep Если не получилось
- **`tsc` ругается на `import.meta`/ESM** — в сборочном `tsconfig` должны быть `module: NodeNext`, `moduleResolution: NodeNext` (унаследованы из основного).
- **Образ не стартует: нет `DATABASE_URL`** — `dotenv/config` читает `.env` из рабочей папки; в продакшне переменные задаются окружением контейнера, `.env` в образ **не** копируется.

### quiz
- Почему миграции не должны выполняться в `CMD` образа?
- Когда выполняется `prisma generate` и почему до компиляции TypeScript?
- Что значит «совместимые» изменения схемы для выкатки без простоя?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/deployment/deploy-prisma | деплой Prisma | Prisma 7: Deploy Prisma
- https://docs.docker.com/build/building/multi-stage/ | многоступенчатая сборка | Docker: Multi-stage builds

## 18.5 Наблюдаемость: события запросов, метрики, трассировка | short: Наблюдаемость | est: ~45 мин
### intro
**Слова шага:** *метрики слоя данных*, *медленные запросы*, *OpenTelemetry*, *трассировка*, *`@prisma/instrumentation`*, *что собирать и чего не собирать*.

:::tip Если совсем просто
Когда запрос «тормозит» в продакшне, спрашивать «а что именно» некого — нужны цифры, которые собирались **заранее**: сколько запросов, какой процент медленных, какой запрос самый долгий. Метрики — «приборная панель», трассировка — «чёрный ящик» одного запроса: из каких шагов он состоял.
:::

**Уровень 1 — свои метрики** (расширение `timing` из 15.2 + маленький `/metrics`):

```ts
// src/server.ts — добавить
import { timing, type QueryStats } from './extensions/timing.js'
export const stats: QueryStats = { count: 0, totalMs: 0, slow: [] }
const db = prisma.$extends(timing(stats, 100))          // использовать db вместо prisma в эндпоинтах

if (url.pathname === '/metrics') {
  const text = [
    `db_operations_total ${stats.count}`,
    `db_operation_ms_total ${Math.round(stats.totalMs)}`,
    `db_slow_operations_total ${stats.slow.length}`,
  ].join('\n')
  res.writeHead(200, { 'content-type': 'text/plain' }); return void res.end(text + '\n')
}
```

Формат строк `имя значение` понимает Prometheus (подключается так же, как в Kubernetes-лабе, сессия 11).

**Уровень 2 — трассировка OpenTelemetry.** Prisma умеет создавать **span'ы** (отрезки времени) для каждой операции и каждого SQL-запроса; они складываются в трассу запроса. В Prisma 7 это делается через пакет `@prisma/instrumentation` (**сверьтесь** с документацией «OpenTelemetry tracing»: состав пакетов и подключение менялись):

```ts
// src/tracing.ts — подключается ПЕРВЫМ, до остального кода
import { NodeSDK } from '@opentelemetry/sdk-node'
import { ConsoleSpanExporter } from '@opentelemetry/sdk-trace-node'
import { PrismaInstrumentation } from '@prisma/instrumentation'

const sdk = new NodeSDK({
  traceExporter: new ConsoleSpanExporter(),              // для обучения — в консоль; в проде — OTLP-экспортёр
  instrumentations: [new PrismaInstrumentation()],
})
sdk.start()
```

```bash run
cd ~/prisma-lab/rentkit
npm install @opentelemetry/sdk-node @opentelemetry/sdk-trace-node @prisma/instrumentation
cat > src/lessons/18-trace.ts <<'EOF'
import '../tracing.js'
import { prisma } from '../db.js'
await prisma.booking.findMany({ take: 2, include: { customer: true } })
await prisma.$disconnect()
EOF
npx tsx src/lessons/18-trace.ts 2>&1 | grep -E "name:|duration" | head -12
```

### result
```out auto
```

Ожидаем: span'ы вида `prisma:client:operation` (вызов `findMany`) и вложенные `prisma:engine:db_query` (отдельные SQL-запросы) с длительностью. Суть трассировки: видно, **из чего состоит** медленный запрос и **где** ушло время — в сети, в самой базе, в сборке результата.

**Что собирать и чего — нет:** собирай **число и длительность** операций, коды ошибок, медленные запросы; **не пиши** значения параметров (телефоны, суммы, токены — шаг 16.5), тела запросов, `DATABASE_URL`. Медленные запросы логируй **формой** (имя операции, модель, время), а подробности — по необходимости и с маскированием.

### why
Наблюдаемость — условие того, чтобы жить с системой после выпуска: без неё каждая проблема — «детективное расследование по слухам». А принципы «числа — да, значения — нет» защищают заодно и от утечки данных через мониторинг.

### deep Если не получилось
- **`Cannot find module '@prisma/instrumentation'`** — пакет не установлен или имя изменилось; смотри актуальную страницу документации.
- **Span'ов нет** — `tracing.ts` должен подключаться **первым** (до `db.ts`), иначе клиент создаётся без инструментирования.

### quiz
- Чем метрики отличаются от трассировки и когда нужна каждая?
- Что нельзя писать в логи и метрики слоя данных?
- Почему `tracing.ts` нужно импортировать первым?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/observability-and-logging/opentelemetry-tracing | трассировка | Prisma 7: OpenTelemetry tracing
- https://opentelemetry.io/docs/languages/js/ | OpenTelemetry для JS | OpenTelemetry: JavaScript

## 18.6 Prisma в NestJS и Express: как это выглядит | short: Nest и Express | est: ~35 мин
### intro
**Слова шага:** *`PrismaService`*, *жизненный цикл*, *`onModuleInit`/`onModuleDestroy`*, *graceful shutdown*, *где применяются сессии лабы в Nest и Express*.

:::tip Если совсем просто
Всё, что ты сделала в слое данных, не привязано к фреймворку. Фреймворк лишь решает: **где создать** клиент, **когда подключить**, **когда закрыть**. В NestJS это «сервис» с жизненным циклом, в Express — модуль и обработчик остановки.
:::

**NestJS** (подробно — лаба NestJS): клиент оборачивают в провайдер и привязывают к жизненному циклу приложения.

```ts
// prisma.service.ts (NestJS, Prisma 7 с адаптером)
import { Injectable, OnModuleDestroy, OnModuleInit } from '@nestjs/common'
import { PrismaPg } from '@prisma/adapter-pg'
import { PrismaClient } from './generated/prisma/client.js'

@Injectable()
export class PrismaService extends PrismaClient implements OnModuleInit, OnModuleDestroy {
  constructor() {
    super({ adapter: new PrismaPg({ connectionString: process.env.APP_DATABASE_URL ?? process.env.DATABASE_URL!, max: 10, connectionTimeoutMillis: 3_000 }) })
  }
  async onModuleInit() { await this.$connect() }          // фиксируем подключение при старте: ошибка видна сразу
  async onModuleDestroy() { await this.$disconnect() }    // закрываем пул при остановке
}
```

```ts
// main.ts
const app = await NestFactory.create(AppModule)
app.enableShutdownHooks()                                  // вызывать onModuleDestroy при SIGTERM
```

**Express**: клиент — модуль-singleton (как наш `db.ts`), остановка — обработчик сигналов.

```ts
const server = app.listen(3000)
process.on('SIGTERM', () => server.close(async () => { await prisma.$disconnect(); process.exit(0) }))
```

Как связаны эти лабы с этой: **Express-лаба (сессия 13)** вводит Prisma «в первом приближении» на проекте ShareBox; **NestJS** и **GraphQL** используют ту же схему подключений. Здесь ты прошла полную глубину — всё, что вы там делали «в одну строку» (`include`, `$transaction`, ошибки `P2002`), теперь понятно изнутри. Расширения (`$extends`) в Nest оформляют провайдером, который отдаёт **расширенный** клиент; `set_config` для RLS вызывается в перехватчике запросов (interceptor) по данным пользователя.

### why
Фреймворк должен быть тонкой оболочкой вокруг слоя данных, а не его владельцем: тогда тесты (18.1) запускаются без Nest, а миграция на другой фреймворк не требует переписывания запросов.

### deep Если не получилось
- **Соединения не закрываются при остановке** — не включены `enableShutdownHooks()` (Nest) или нет обработчика `SIGTERM` (Express); при `docker stop` процесс получит `SIGKILL` через 10 секунд.
- **`PrismaClient` не принимает `adapter`** — не та версия клиента: проверь, что `@prisma/client@7`.

### quiz
- Для чего `$connect()` в `onModuleInit` и `$disconnect()` в `onModuleDestroy`?
- Почему слой данных лучше держать независимым от фреймворка?
- Где в приложении на Nest выставляется филиал для RLS?

### links
- https://docs.nestjs.com/recipes/prisma | Prisma в NestJS | NestJS: Prisma recipe
- https://www.prisma.io/docs/orm/v7/prisma-client/setup-and-configuration/databases-connections/connection-management | управление соединениями | Prisma 7: Connection management

## 18.7 🔨 Production Hell: слой данных с пятью поломками | short: 🔨 Production Hell | est: ~90 мин
### intro
**Слова шага:** *многослойная поломка*, *диагностика без подсказок*, *красные тесты как задание*, *доказательство исправления*.

:::tip Если совсем просто
Теперь без подсказок, где что сломано. Тебе передали «релиз» слоя данных: набор функций и тестов, часть тестов красные. В коде **пять независимых дефектов**, каждый из которых ты уже встречала в этой лабе — но здесь они замаскированы под обычный код. Инструменты: логи запросов, `EXPLAIN`, `psql`, миграции, тесты. Правило: **чинить код, а не тест**.
:::

Создай папку `hell/` (в корне `rentkit`) с «релизом». Файлы — **как есть**, без правок:

```ts
// hell/src/cards.ts
import { prisma } from '../../src/db.js'

export async function listBookingCards(branchId: number, limit = 100) {
  const bookings = await prisma.booking.findMany({ where: { branchId, status: 'CONFIRMED' }, orderBy: { id: 'desc' }, take: limit })
  const cards = []
  for (const b of bookings) {
    const customer = b.customerId ? await prisma.customer.findUnique({ where: { id: b.customerId } }) : null
    const item = b.itemId ? await prisma.item.findUnique({ where: { id: b.itemId } }) : null
    cards.push({ id: b.id, customer: customer?.name ?? null, item: item?.title ?? null })
  }
  return cards
}
```

```ts
// hell/src/points.ts
import { prisma } from '../../src/db.js'

export async function awardPoints(customerId: number, points: number) {
  const c = await prisma.customer.findUniqueOrThrow({ where: { id: customerId } })
  await prisma.customer.update({ where: { id: customerId }, data: { bonusPoints: c.bonusPoints + points } })
}
```

```ts
// hell/src/import.ts
import { prisma } from '../../src/db.js'

export async function importEvents(bookingIds: number[]) {
  await Promise.all(bookingIds.map((id) =>
    prisma.$transaction(async (tx) => {
      await tx.eventLog.create({ data: { bookingId: id, kind: 'import' } })
      await new Promise((r) => setTimeout(r, 300))          // «обращение к внешнему справочнику»
    })))
}
```

```ts
// hell/src/scope.ts
import { prisma } from '../../src/db.js'

export async function countBookingsAs(branchId: number | null) {
  if (branchId !== null) await prisma.$executeRaw`SELECT set_config('app.branch_id', ${String(branchId)}, false)`
  return prisma.booking.count()
}
```

```ts
// hell/src/schema-check.ts — пятая поломка живёт в базе, а не в коде: см. test/schema.test.ts
```

Тесты — **требования**; они красные, и твоя задача — сделать их зелёными, не меняя сами тесты:

```ts
// hell/test/hell.test.ts
import { execSync } from 'node:child_process'
import { describe, expect, it } from 'vitest'
import { Client } from 'pg'
import { prisma } from '../../src/db.js'
import { listBookingCards } from '../src/cards.js'
import { awardPoints } from '../src/points.js'
import { importEvents } from '../src/import.js'
import { countBookingsAs } from '../src/scope.js'
import { makeBranch, makeCustomer, makeItem } from '../../test/factories.js'

describe('production hell', () => {
  it('1. карточки броней: не больше 3 запросов на 100 броней', async () => {
    const b = await makeBranch(), cust = await makeCustomer(b.id), item = await makeItem(b.id)
    for (let i = 0; i < 40; i++) {
      await prisma.booking.create({ data: { branchId: b.id, customerId: cust.id, itemId: (await makeItem(b.id)).id, status: 'CONFIRMED', startsAt: new Date(2050, 0, 1 + i), endsAt: new Date(2050, 0, 2 + i) } })
    }
    let queries = 0
    prisma.$on('query', () => { queries++ })
    const cards = await listBookingCards(b.id)
    expect(cards).toHaveLength(40)
    expect(queries).toBeLessThanOrEqual(3)
  })

  it('2. баллы: 50 параллельных начислений по 10 дают ровно 500', async () => {
    const b = await makeBranch(), cust = await makeCustomer(b.id)
    await Promise.all(Array.from({ length: 50 }, () => awardPoints(cust.id, 10)))
    expect((await prisma.customer.findUniqueOrThrow({ where: { id: cust.id } })).bonusPoints).toBe(500)
  })

  it('3. схема: в базе нет колонок и таблиц, которых нет в схеме Prisma (нет дрейфа)', async () => {
    // сравниваем БАЗУ со схемой: «migrate status» смотрит только на таблицу истории и дрейфа не увидит
    const sql = execSync('npx prisma migrate diff --from-config-datasource --to-schema prisma/schema.prisma --script', { env: process.env, encoding: 'utf8' })
    expect(sql).not.toMatch(/DROP COLUMN|DROP TABLE/)
  })

  it('4. импорт 20 событий укладывается в разумное время при пуле из 3 соединений', async () => {
    const t0 = Date.now()
    await importEvents(Array.from({ length: 20 }, (_, i) => i + 1))
    expect(Date.now() - t0).toBeLessThan(3_000)
  }, 15_000)

  it('5. безымянный запрос не видит чужих броней', async () => {
    await countBookingsAs(3)                               // филиал 3 «поработал» на этом соединении…
    const anonymous = await countBookingsAs(null)          // …а теперь аноним (без объявленного филиала)
    expect(anonymous).toBe(0)
  })
})
```

Дефект №3 вносится в базу тестового окружения **до** прогона — скрипт подготовки (запускай его **после** создания эталонной базы и **до** `vitest`; смысл — тебе не сообщается, где именно «подправили» базу):

```bash run
psqlr() { docker exec -i rental-pg psql -U postgres "$@"; }
psqlr -d rental_template -c 'ALTER TABLE "tbl_Branches" ADD COLUMN IF NOT EXISTS "legacy_note" text'
```

```bash run
cd ~/prisma-lab/rentkit
DB_POOL_MAX=3 npx vitest run hell 2>&1 | tail -40
```

### result
```out auto
```

**Задание:** довести **все пять** тестов до зелёного, не меняя `hell/test/hell.test.ts`; для каждого — записать в `NOTES.md` три строки: **симптом**, **причина**, **почему именно это исправление** (и какая сессия объясняла идею). Инструменты: лог запросов (`SQL_LOG=1`), `EXPLAIN`, `psql`, `migrate status`/`diff`, `pg_stat_activity`. Правила: чинить в `hell/src/*` и (для №3) в миграциях/схеме; **не** отключать проверки (`it.skip`), **не** увеличивать таймауты в тестах.

**Приёмка сессии:** набор тестов из 18.1–18.2 зелёный; CI-конфигурация написана и описана (первый прогон — на вашем репозитории); образ собирается (`generate` до `tsc`); метрики и трассировка подключены; пять дефектов «Hell» исправлены, у каждого есть объяснение в `NOTES.md`.

### why
Это итоговый тренажёр по всему курсу: N+1 (сессия 6), потерянное обновление (12), дрейф схемы (11), исчерпание пула (17) и протечка через пул (16). Умение узнавать **знакомую поломку в незнакомом коде** — то, ради чего всё это писалось: в реальной работе тебя не предупредят, что именно сломано.

### deep Если не получилось
- **Подсказка к №1:** сколько запросов делает цикл? Достаточно `include` с `select` (или пары запросов `IN`).
- **Подсказка к №2:** способ, который не читает значение вообще (сессия 12.3).
- **Подсказка к №3:** `migrate diff --from-config-datasource --to-schema prisma/schema.prisma --script` покажет различие (`migrate status` дрейфа не видит — он смотрит только на историю); решение зависит от смысла колонки: убрать её (если ошибка) или описать миграцией и пометить применённой (шаг 11.5). Не забудь, что тест смотрит на **тестовую** базу, созданную из шаблона.
- **Подсказка к №4:** что делает транзакция, пока «обращается к справочнику»? (шаг 17.7).
- **Подсказка к №5:** второй слой защиты из 16.7: параметр — только внутри транзакции (`true`), либо через `scoped`.
- **№4 не воспроизводится** — установлен ли `DB_POOL_MAX=3` для процесса тестов; `db.ts` читает его при создании клиента.

### quiz
- Назови пять дефектов этого «релиза» и сессию, где каждый разбирался.
- Почему в задании нельзя менять тесты и ставить `it.skip`?
- Как отличить «ошибку в коде» от «ошибки в базе» при диагностике?

### links
- https://vitest.dev/guide/ | руководство Vitest | Vitest: Guide
