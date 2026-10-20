# Сессия 16 · Мультитенантность и безопасность
dur: ~4 ч

## 16.1 Как изолировать филиалы: три модели | short: Модели изоляции | est: ~30 мин
### intro
**Слова шага:** *мультитенантность*, *тенант (филиал)*, *колонка `branch_id`*, *схема на тенанта*, *база на тенанта*, *компромиссы*.

:::tip Если совсем просто
В одном здании арендуют офисы несколько фирм. Можно: (1) **одна общая комната** с личными шкафчиками — дёшево, но шкафчики надо надёжно запирать; (2) **отдельный коридор** на каждую фирму — удобнее закрыть, но сложнее содержать; (3) **отдельное здание** — максимально изолировано и максимально дорого.
:::

```svg
@tenant-models
```

| Модель | Что это | Плюсы | Минусы |
|---|---|---|---|
| **Колонка** `branch_id` + RLS | все филиалы в одних таблицах; строка помечена владельцем | просто, дёшево, общие отчёты | изоляция держится на правилах (RLS) и дисциплине |
| **Схема на тенанта** | отдельная схема PostgreSQL (`branch_7.bookings`) | изоляция жёстче, лёгкое удаление тенанта | миграции в десятках схем, Prisma ориентирована на одну |
| **База на тенанта** | отдельная база | предельная изоляция, отдельные бэкапы | дорого, много соединений, сложные общие отчёты |

Наша сеть — **12 филиалов одной компании**, общие отчёты нужны, данные не секретны друг от друга **юридически**, но каждый сотрудник должен видеть **только свой** филиал. Значит, выбор — **колонка + RLS**: в таблицах уже есть `branch_id`, а Row Level Security (PostgreSQL-лаба, сессия 8) заставляет **базу** отфильтровывать чужие строки. Prisma со схемами на тенанта работает хуже (одна схема на `schema.prisma`, поддержка нескольких схем ограничена — страница «Multi-schema»).

### why
Выбор модели изоляции — архитектурное решение, которое трудно изменить потом. «Колонка + RLS» — самый распространённый вариант для компании, где тенанты — подразделения одной организации: простая миграция, общая отчётность и защита, не зависящая от забывчивости разработчика (в отличие от `where: { branchId }` в каждом запросе).

### deep Как ещё можно
Для SaaS с **внешними** клиентами (чужие компании) часто берут схему или базу на клиента: юридически и по требованиям безопасности изоляция должна быть жёстче, чем «правила строк». У нас — внутренний случай.

### quiz
- В чём разница между тремя моделями изоляции?
- Почему для нашей сети выбрана «колонка + RLS»?
- Почему «правильный `where` в каждом запросе» — слабая защита?

### links
- https://www.prisma.io/docs/orm/v7/prisma-schema/data-model/multi-schema | несколько схем | Prisma 7: Multi-schema
- https://www.postgresql.org/docs/18/ddl-rowsecurity.html | RLS | PostgreSQL 18: Row Security Policies

## 16.2 Роль приложения с минимальными правами | short: Роль приложения | est: ~50 мин
### intro
**Слова шага:** *роль*, *`GRANT`/`REVOKE`*, *минимальные привилегии*, *разные пользователи для миграций и приложения*, *append-only таблицы*, *`DEFAULT PRIVILEGES`*.

:::tip Если совсем просто
Сейчас приложение ходит в базу под **суперпользователем** — как повар, у которого ключи от кассы, склада и директорского кабинета. Заведём ему обычный пропуск: он может читать и писать то, что нужно для работы, но **не может** менять устройство базы (создавать и удалять таблицы), стирать журнал платежей и аудит.
:::

Роль — вещь на уровне **кластера**, и пароль в миграцию **не кладём**. Создаём отдельным скриптом (пароль берётся из переменной, не из файла в Git):

```bash run
cd ~/prisma-lab/rentkit
export APP_PW='замени-на-свой-пароль'
psqlr() { docker exec -i rental-pg psql -U postgres -d rental "$@"; }
psqlr -v pw="$APP_PW" <<'SQL'
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'rental_app') THEN
    CREATE ROLE rental_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
  END IF;
END $$;
ALTER ROLE rental_app PASSWORD :'pw';
SQL
echo "роль создана"
```

### result
```out auto
```

Права — **миграцией** (она хранится в Git и повторяется на каждом стенде; защитная проверка не даёт ей упасть там, где роли нет):

```sql
-- prisma/migrations/20261024100000_app_role_grants/migration.sql
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'rental_app') THEN
    RAISE NOTICE 'роль rental_app не создана — права не выданы';
    RETURN;
  END IF;

  GRANT USAGE ON SCHEMA public TO rental_app;
  GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO rental_app;
  GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO rental_app;

  -- служебная таблица Prisma Migrate приложению не нужна
  REVOKE ALL ON "_prisma_migrations" FROM rental_app;

  -- журналы только дописываются: ни правки, ни удаления
  REVOKE UPDATE, DELETE ON "audit_log", "ledger_entry", "orphan_log", "overlap_fix_log" FROM rental_app;

  -- права на будущие таблицы, которые создаст владелец
  ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO rental_app;
  ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO rental_app;
END $$;
```

Подключение приложения — **отдельный адрес** (`.env`): миграции и CLI идут под владельцем (`DATABASE_URL`), рабочий клиент — под `rental_app`:

```bash
# .env
DATABASE_URL="postgresql://postgres:postgres@localhost:5433/rental"                  # CLI и миграции (владелец)
APP_DATABASE_URL="postgresql://rental_app:замени-на-свой-пароль@localhost:5433/rental" # приложение
```

```ts
// src/db.ts — строка подключения к адаптеру
const adapter = new PrismaPg({ connectionString: process.env.APP_DATABASE_URL ?? process.env.DATABASE_URL! })
```

```bash run
cd ~/prisma-lab/rentkit
npx prisma migrate deploy
psqlr() { docker exec -i rental-pg psql -U postgres -d rental "$@"; }
psqlr -c "SELECT has_table_privilege('rental_app', 'tbl_Bookings', 'SELECT') AS читает_брони, has_table_privilege('rental_app', 'ledger_entry', 'DELETE') AS стирает_проводки, has_schema_privilege('rental_app', 'public', 'CREATE') AS создаёт_таблицы"
cat > src/lessons/16-role.ts <<'EOF'
import { prisma } from '../db.js'
console.log('кто я:', (await prisma.$queryRaw<{ u: string }[]>`SELECT current_user AS u`)[0]!.u)
console.log('броней:', await prisma.booking.count())
await prisma.$executeRawUnsafe('CREATE TABLE hack (x int)').catch((e) => console.log('DDL →', String(e.message).split('\n').filter(Boolean).pop()))
await prisma.ledgerEntry.deleteMany().catch((e) => console.log('DELETE проводок →', String(e.message).split('\n').filter(Boolean).pop()))
await prisma.$disconnect()
EOF
npx tsx src/lessons/16-role.ts
```

### result
```out auto
```

Ожидаем: `читает_брони = t`, `стирает_проводки = f`, `создаёт_таблицы = f`; приложение под `rental_app` читает данные, а `CREATE TABLE` и `DELETE FROM ledger_entry` отклоняются (`permission denied`). Обрати внимание: **журналы append-only** обеспечены **правами**, а не «договорённостью в коде» — даже ошибка (или взлом) приложения не сотрёт проводки.

### why
Принцип наименьших привилегий — самая дешёвая защита: если приложение скомпрометировано (инъекция, утёкший токен), ущерб ограничен тем, что разрешено **роли**, а не «всей базе». Разные роли для миграций и работы — стандарт: DDL нужен только деплою.

### deep Если не получилось
- **`permission denied for table …` у рабочего приложения** — после новой миграции таблицы созданы без прав: `DEFAULT PRIVILEGES` действуют только для таблиц **созданных тем же владельцем**; проверь, что миграции запускаются под `postgres`, и перевыдай права `GRANT … ON ALL TABLES`.
- **`password authentication failed`** — пароль в `APP_DATABASE_URL` не совпал; спецсимволы в пароле нужно URL-кодировать.
- **`role "rental_app" does not exist` в CI** — роль создаётся отдельным шагом до миграций (шаг 18.3).

### quiz
- Зачем у приложения и у миграций разные пользователи базы?
- Как сделать таблицу «только дописываемой» для приложения?
- Почему пароль роли не кладут в миграцию?

### links
- https://www.postgresql.org/docs/18/sql-grant.html | GRANT | PostgreSQL 18: GRANT
- https://www.postgresql.org/docs/18/sql-alterdefaultprivileges.html | ALTER DEFAULT PRIVILEGES | PostgreSQL 18: ALTER DEFAULT PRIVILEGES

## 16.3 RLS по филиалу: политики и FORCE | short: RLS по филиалу | est: ~55 мин
### intro
**Слова шага:** *Row Level Security*, *`ENABLE ROW LEVEL SECURITY`*, *`FORCE`*, *политика `USING`/`WITH CHECK`*, *`current_setting`*, *безопасный умолчательный ответ*.

:::tip Если совсем просто
RLS — это «умные очки», которые база надевает на каждый запрос: сквозь них видны только **свои** строки. Очки настраиваются политикой: «показывай строки, у которых `branch_id` равен тому филиалу, который назван в этой сессии». Если филиал не назван — не показывай **ничего** (безопасный умолчательный ответ, а не «всё подряд»).
:::

```sql
-- prisma/migrations/20261024110000_rls_branch/migration.sql

-- идентификатор филиала приложение ставит в параметр сессии app.branch_id; пусто/не задан → NULL → строки не видны
CREATE FUNCTION app_branch() RETURNS integer LANGUAGE sql STABLE AS
  $$ SELECT NULLIF(current_setting('app.branch_id', true), '')::integer $$;

-- «управляющий»: роль «admin» видит всё (для сводных отчётов)
CREATE FUNCTION app_is_admin() RETURNS boolean LANGUAGE sql STABLE AS
  $$ SELECT coalesce(current_setting('app.role', true) = 'admin', false) $$;

ALTER TABLE "tbl_Bookings"  ENABLE ROW LEVEL SECURITY;
ALTER TABLE "tbl_Items"     ENABLE ROW LEVEL SECURITY;
ALTER TABLE "tbl_Customers" ENABLE ROW LEVEL SECURITY;

CREATE POLICY branch_isolation ON "tbl_Bookings"
  USING (app_is_admin() OR branch_id = app_branch())
  WITH CHECK (app_is_admin() OR branch_id = app_branch());
CREATE POLICY branch_isolation ON "tbl_Items"
  USING (app_is_admin() OR branch_id = app_branch())
  WITH CHECK (app_is_admin() OR branch_id = app_branch());
CREATE POLICY branch_isolation ON "tbl_Customers"
  USING (app_is_admin() OR branch_id = app_branch())
  WITH CHECK (app_is_admin() OR branch_id = app_branch());
```

Что здесь: **`USING`** — какие строки **видны** и доступны для `UPDATE`/`DELETE`; **`WITH CHECK`** — какие строки **можно записать** (нельзя вставить бронь чужому филиалу); **`app_branch()` возвращает `NULL`**, если параметр не задан или пуст, а сравнение `branch_id = NULL` **не истинно** — значит, без названного филиала **видны ноль строк**. Это принципиально: забытая настройка даёт «пусто», а не «всё».

Проверим в `psql` от имени приложения:

```bash run
cd ~/prisma-lab/rentkit
npx prisma migrate deploy
psqlr() { docker exec -i rental-pg psql -U rental_app -d rental "$@"; }
export PGPASSWORD='замени-на-свой-пароль'
docker exec -e PGPASSWORD="$PGPASSWORD" -i rental-pg psql -U rental_app -h 127.0.0.1 -d rental <<'SQL'
SELECT count(*) AS без_филиала FROM "tbl_Bookings";
BEGIN; SELECT set_config('app.branch_id', '3', true);
SELECT count(*) AS филиал_3, count(DISTINCT branch_id) AS филиалов_в_выборке FROM "tbl_Bookings"; COMMIT;
BEGIN; SELECT set_config('app.role', 'admin', true);
SELECT count(*) AS как_админ FROM "tbl_Bookings"; COMMIT;
SQL
```

### result
```out auto
```

Ожидаем: `без_филиала = 0` (по умолчанию закрыто!), `филиал_3` ≈ 25 тысяч при `филиалов_в_выборке = 1`, `как_админ = 300000+`. **Важное ограничение RLS:** суперпользователь и владелец таблицы по умолчанию **обходят** политики. Владелец (`postgres`) — суперпользователь, обходит всегда; у обычного владельца таблиц обход отключается `ALTER TABLE … FORCE ROW LEVEL SECURITY`. Поэтому тесты изоляции мы запускаем **под `rental_app`**, а не под владельцем — иначе они «пройдут» зря.

### why
Политика RLS — **единственное место**, где записано правило «кто что видит», и оно действует на **любой** запрос из любого клиента (Prisma, `psql`, отчётная система). Раньше правило жило в сотне `where: { branchId }`. Теперь его нельзя «забыть».

### deep Команды по частям
`USING` фильтрует строки при чтении/изменении/удалении; `WITH CHECK` проверяет **новые** значения при `INSERT/UPDATE`. `STABLE` у функций — подсказка планировщику: значение не меняется внутри запроса, его можно вычислять один раз. `current_setting('app.branch_id', true)` — второй аргумент `true` означает «не падать, если параметр не задан, вернуть `NULL`».

### deep Если не получилось
- **Всегда 0 строк даже с филиалом** — параметр поставлен не в том соединении (вне транзакции с `true`); проверь, что `SELECT set_config` и запрос выполняются в **одной** транзакции.
- **`invalid input syntax for type integer: ""`** — параметр задан пустой строкой, а `app_branch()` не защищена `NULLIF` (в нашей версии защищена).
- **Админ видит 0** — не выполнено `set_config('app.role', 'admin', true)` в той же транзакции.

### quiz
- Чем `USING` отличается от `WITH CHECK` в политике RLS?
- Почему при отсутствии настройки филиала политика должна показывать «ничего», а не «всё»?
- Кого RLS по умолчанию не ограничивает и как это учитывать в тестах?

### links
- https://www.postgresql.org/docs/18/ddl-rowsecurity.html | RLS | PostgreSQL 18: Row Security Policies
- https://www.postgresql.org/docs/18/sql-createpolicy.html | CREATE POLICY | PostgreSQL 18: CREATE POLICY

## 16.4 Филиал в сессии: set_config внутри транзакции через расширение | short: set_config и расширение | est: ~60 мин
### intro
**Слова шага:** *параметр сессии*, *`set_config(..., true)`*, *пул соединений*, *расширение `query` с транзакцией*, *`forBranch(id)`*, *протечка через пул*.

:::tip Если совсем просто
Чтобы очки RLS знали, чей филиал, перед **каждым** запросом нужно «объявить»: «сейчас работает филиал 7». Но у базы есть пул «телефонных линий»: следующий звонок по той же линии **помнит** то, что было сказано до этого. Поэтому объявление должно жить **ровно одну транзакцию** (`true` — «только до конца транзакции»), а не «навсегда на линии».
:::

Расширение `forBranch`: для каждого запроса открывает транзакцию из двух шагов — объявить филиал и выполнить сам запрос:

```ts
// src/extensions/branch-scope.ts
import { Prisma } from '../generated/prisma/client.js'
import { prisma as base } from '../db.js'

type Scope = { branchId?: number; role?: 'admin' }

export function forScope(scope: Scope) {
  return Prisma.defineExtension({
    name: 'branchScope',
    query: {
      $allModels: {
        async $allOperations({ args, query }) {
          const [, , result] = await base.$transaction([
            base.$executeRaw`SELECT set_config('app.branch_id', ${scope.branchId === undefined ? '' : String(scope.branchId)}, true)`,
            base.$executeRaw`SELECT set_config('app.role', ${scope.role ?? ''}, true)`,
            query(args),
          ])
          return result
        },
      },
    },
  })
}

export const scoped = (scope: Scope) => base.$extends(forScope(scope))
```

```ts
// src/lessons/16-scope.ts
import { scoped } from '../extensions/branch-scope.js'
import { prisma } from '../db.js'

const b3 = scoped({ branchId: 3 })
const b7 = scoped({ branchId: 7 })
const admin = scoped({ role: 'admin' })

console.log('без филиала:', await prisma.booking.count())
console.log('филиал 3   :', await b3.booking.count(), '| филиал 7:', await b7.booking.count(), '| админ:', await admin.booking.count())

// запись в чужой филиал блокируется WITH CHECK
await b3.booking.create({ data: { itemId: 1, branchId: 7, status: 'DRAFT' } })
  .catch((e) => console.log('чужой филиал →', String(e.message).split('\n').filter(Boolean).pop()))
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/16-scope.ts
```

### result
```out auto
```

Ожидаем: «без филиала» — 0, «филиал 3» и «филиал 7» — разные числа порядка двадцати пяти тысяч, «админ» — все 300 тысяч+; попытка создать бронь «от филиала 3» для филиала 7 отклонена политикой `WITH CHECK`. Три детали, на которых стоит вся конструкция:

1. **`true` в `set_config`** — «локальный» параметр: живёт до конца **текущей транзакции** и сам исчезает. Если поставить `false`, значение останется на соединении и достанется **следующему** запросу из пула — другому филиалу (протечка, шаг 16.7).
2. **Запрос и `set_config` — в одной транзакции** (`$transaction([...])`), иначе пул может отдать их разным соединениям.
3. **Один `$transaction` на каждый запрос** — для обычных одиночных запросов это нормально; для **интерактивных** транзакций филиал ставится один раз в начале (`await tx.$executeRaw…`), а внутри используется `tx` — делай это вспомогательной функцией `withScope(scope, fn)`.

### why
Это «клей» между приложением и RLS: база не знает, кто вызывает, пока приложение не **скажет** — а сказать нужно так, чтобы не осталось следов в пуле. Мелкие детали (`true`, одна транзакция) — это то, чем отличается работающая изоляция от «работает на моей машине».

### deep Как ещё можно
Вместо параметров сессии можно заводить отдельную **роль базы на каждый филиал** и переключаться командой `SET LOCAL ROLE branch_7` внутри транзакции: тогда ограничения задаются стандартной системой прав, и обмануть их через параметры нельзя. Цена — управление десятками ролей.

### deep Если не получилось
- **`$transaction([...])` с `query(args)` падает типом** — в вашей версии `query(args)` может возвращать не `PrismaPromise`; тогда делай интерактивную транзакцию и вызывай операцию изнутри (**сверьтесь** с примером «Row-level security» в документации Prisma 7).
- **Везде 0 строк** — клиент `base` подключён не под `rental_app`, или политика не включена; проверь `SELECT current_user` и `\d+ "tbl_Bookings"`.

### quiz
- Зачем в `set_config` третий аргумент `true` и что будет, если поставить `false`?
- Почему `set_config` и запрос должны быть в одной транзакции?
- Чем «роль на филиал» отличается от «параметра сессии»?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/client-extensions/extension-examples | примеры расширений (RLS) | Prisma 7: Extension examples
- https://www.postgresql.org/docs/18/functions-admin.html#FUNCTIONS-ADMIN-SET | set_config | PostgreSQL 18: set_config

## 16.5 Права на колонки, секреты и что нельзя логировать | short: Колонки и секреты | est: ~40 мин
### intro
**Слова шага:** *права на колонки*, *`GRANT SELECT (колонки)`*, *персональные данные*, *секреты в `.env`*, *что не писать в лог*, *маскирование параметров*.

:::tip Если совсем просто
У сотрудника отчётного отдела должна быть доступна выручка по клиентам, но **не телефоны и почта**. Права можно выдать **на отдельные колонки**: «вот эти поля — читай, остальные — нет». А вторая «дыра безопасности» — это лог: если в журнале запросов лежат пароли и телефоны, взлом лог-сервера равен взлому базы.
:::

Роль для отчётов — видит клиентов **без** телефонов и почты:

```bash run
psqlr() { docker exec -i rental-pg psql -U postgres -d rental "$@"; }
psqlr <<'SQL'
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'rental_report') THEN CREATE ROLE rental_report LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD 'report-demo'; END IF;
END $$;
GRANT USAGE ON SCHEMA public TO rental_report;
GRANT SELECT ("id", "CustName", "branch_id", "created_at") ON "tbl_Customers" TO rental_report;   -- без phone, email
GRANT SELECT ON "tbl_Bookings" TO rental_report;
SQL
docker exec -e PGPASSWORD=report-demo -i rental-pg psql -U rental_report -h 127.0.0.1 -d rental <<'SQL'
SELECT id, "CustName" FROM "tbl_Customers" LIMIT 1;
SELECT phone FROM "tbl_Customers" LIMIT 1;
SQL
```

### result
```out auto
```

Первый запрос работает, второй — **`permission denied for table tbl_Customers`** (колонка `phone` закрыта). Prisma при обращении через такую роль должна явно перечислять **только разрешённые** поля (`select`): `findMany()` без `select` запросит все колонки и упадёт. Вывод: права на колонки — **договор** между базой и кодом слоя данных.

**Секреты и логи** — правила гигиены:

- **`.env` не коммитится** (`.gitignore`), в репозитории — **`.env.example`** без значений; продакшн-секреты — в хранилище секретов окружения, не в файлах образа.
- **Лог запросов Prisma** (`log: ['query']`, шаг 5.5) печатает **значения параметров**: в `e.params` будут телефоны, суммы, токены. В продакшне либо **выключи** `query`-лог, либо маскируй параметры (в обработчике событий не печатай `e.params`, печатай форму запроса и длительность).
- **Не логируй** `DATABASE_URL`, `process.env` целиком, тела запросов с персональными данными.
- **Ошибки базы** содержат фрагменты данных (`Key (phone)=(…) already exists`) — в ответ клиенту не отдавай, в лог пиши осторожно.

```ts
// src/db.ts — безопасный вариант логирования
if (process.env.SQL_LOG) {
  prisma.$on('query', (e) => {
    const safe = process.env.SQL_LOG === 'params' ? e.params : '[скрыто]'     // значения параметров — только осознанно
    console.log(`[${e.duration}ms] ${e.query}  params: ${safe}`)
  })
}
```

### why
Утечка через логи — одна из самых частых: инженер включил отладочный лог «на минуточку» и забыл, а в нём пароли, телефоны, платёжные данные. Привычка «параметры по умолчанию скрыты» дешёвая и надёжная.

### deep Если не получилось
- **`permission denied for relation tbl_Customers` даже на `id`** — не выдан `SELECT` на колонку `id` или у роли нет `USAGE` на схему.
- **Prisma падает на `findMany()` у роли отчётов** — запрашивай только разрешённые поля через `select`; либо сделай **представление** `customers_report` без чувствительных колонок и дай роли права на него.

### quiz
- Как выдать право на чтение части колонок таблицы?
- Что в логе запросов Prisma — риск для безопасности и как его снизить?
- Что должно быть в репозитории вместо `.env`?

### links
- https://www.postgresql.org/docs/18/sql-grant.html | GRANT на колонки | PostgreSQL 18: GRANT
- https://owasp.org/www-project-top-ten/ | OWASP Top Ten | OWASP: Top Ten

## 16.6 Охота на протечки: тесты изоляции | short: Тесты изоляции | est: ~55 мин
### intro
**Слова шага:** *тест изоляции*, *модель угроз*, *что RLS защищает и от чего нет*, *`SECURITY DEFINER`*, *инъекция против RLS*, *проверка «под приложением»*.

:::tip Если совсем просто
Построили забор — надо попробовать через него перелезть. Тест изоляции — это программа-«взломщик»: для каждой таблицы и операции пробует увидеть или изменить **чужое** и проверяет, что у неё не получилось. Пока «взломщик» не лазил, забор не проверен.
:::

Тест — набор попыток (запускай **под ролью приложения**, через клиент `scoped`):

```ts
// src/lessons/16-isolation-test.ts
import assert from 'node:assert/strict'
import { scoped } from '../extensions/branch-scope.js'
import { prisma } from '../db.js'

const A = scoped({ branchId: 3 })
const B = scoped({ branchId: 7 })

const results: [string, boolean][] = []
const check = (name: string, ok: boolean) => results.push([name, ok])

// — чтение чужого
const aIds = (await A.booking.findMany({ take: 50, select: { id: true, branchId: true } }))
check('A видит только свои брони', aIds.every((b) => b.branchId === 3))
check('A не видит брони B по id', (await A.booking.findFirst({ where: { branchId: 7 } })) === null)
check('связь: A не достаёт клиента B', (await A.customer.findFirst({ where: { branchId: 7 } })) === null)
check('счётчик чужих = 0', (await A.booking.count({ where: { branchId: 7 } })) === 0)

// — изменение/удаление чужого
check('A не обновит бронь B', (await A.booking.updateMany({ where: { branchId: 7 }, data: { note: 'взлом' } })).count === 0)
check('A не удалит бронь B', (await A.booking.deleteMany({ where: { branchId: 7 } })).count === 0)

// — запись в чужой филиал
let denied = false
try { await A.booking.create({ data: { itemId: 1, branchId: 7, status: 'DRAFT' } }) } catch { denied = true }
check('A не создаст бронь в филиале B', denied)

// — raw-запрос тоже под RLS (а вот переопределить параметр — может!)
const rawCount = await A.$queryRaw<{ n: bigint }[]>`SELECT count(*) AS n FROM "tbl_Bookings" WHERE branch_id = 7`
check('raw: чужих броней не видно', Number(rawCount[0]!.n) === 0)

for (const [name, ok] of results) console.log(ok ? '✓' : '✗ ПРОТЕЧКА', name)
assert.ok(results.every(([, ok]) => ok), 'есть протечки')
await prisma.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/16-isolation-test.ts
```

### result
```out auto
```

Ожидаем: все строки с `✓`. Но честный тест включает и **то, от чего RLS не защищает** (модель угроз):

- **Параметр сессии может поставить любой SQL, выполненный под ролью приложения.** Если в коде есть SQL-инъекция (шаг 9.3), атакующий выполнит `SELECT set_config('app.branch_id', '7', false)` и «станет» филиалом 7. **RLS защищает от ошибок в коде («забыли `where`»), но не от полностью скомпрометированного приложения.** Против последнего — защита инъекций (параметры, не склейка) и (где нужно) **разные роли базы** на тенантов.
- **`SECURITY DEFINER`-функции** выполняются с правами **владельца** (в обход RLS): ни одной такой функции без крайней нужды, и с явным `SET search_path` (PostgreSQL-лаба, сессия 8).
- **Представления** по умолчанию выполняются с правами **владельца представления**, а не вызывающего: RLS таблицы под ним не сработает (в PostgreSQL 15+ — опция `security_invoker = true`).
- **Суперпользователь и `BYPASSRLS`** обходят всё — у рабочей роли их быть не должно (мы создали её `NOBYPASSRLS`).

Добавь в тест ещё пару «взломов»: попытку из роли приложения вызвать `set_config('app.branch_id', '7', false)` и увидеть, что она **удаётся** (и запиши в `NOTES.md`, какая защита от этого есть и где она заканчивается).

### why
Безопасность — не «галочка», а **заявленные границы**: что защищено, от чего, и где защита заканчивается. Тест изоляции фиксирует эти границы кодом, и любое изменение (новое расширение, новая таблица без политики) сразу проверяется.

### deep Как ещё можно
Добавь в CI проверку: «у каждой таблицы с `branch_id` включён RLS и есть политика» (запрос к `pg_tables`/`pg_policies`). Новая таблица без политики тогда не пройдёт сборку — так закрывается человеческий фактор.

### deep Если не получилось
- **Тест проходит, а при ручной проверке данные видны** — тест запущен под владельцем (`postgres` обходит RLS): проверь `APP_DATABASE_URL` и `SELECT current_user`.
- **`✗` у `raw`** — запрос идёт мимо расширения `scoped` (вызван на исходном клиенте).

### quiz
- От чего RLS защищает, а от чего — нет?
- Почему тесты изоляции нужно запускать под ролью приложения, а не владельцем?
- Как автоматически поймать новую таблицу без политики RLS?

### links
- https://www.postgresql.org/docs/18/sql-createview.html | представления и security_invoker | PostgreSQL 18: CREATE VIEW
- https://owasp.org/www-community/attacks/SQL_Injection | SQL Injection | OWASP: SQL Injection

## 16.7 🔨 «Филиал Б видит чужие брони» | short: 🔨 Протечка через пул | est: ~60 мин
### intro
**Слова шага:** *жалоба заказчика*, *параметр сессии на соединении*, *`set_config(..., false)`*, *пул размером 1*, *воспроизведение гонки на пуле*.

:::tip Если совсем просто
Телефонная линия «помнит» последнего собеседника. Если оператор филиала А сказал «я из филиала А» и не «положил трубку» по-настоящему, то следующий звонящий, не представившись, **говорит как будто от А**. Так и бывает: параметр остался на соединении, а соединение досталось другому запросу.
:::

*Заказчик:* «Менеджер филиала „Урал“ жалуется: после обеда стали видны брони соседнего филиала. Потом пропало. Причина неизвестна, воспроизвести не удаётся».

Воспроизведи на **нерабочем** варианте расширения (параметр без `true` и без транзакции) и **пуле из одного соединения**, чтобы реплика гарантированно повторилась:

```ts
// src/lessons/16-leak.ts
import { PrismaPg } from '@prisma/adapter-pg'
import { PrismaClient } from '../generated/prisma/client.js'

// пул из ОДНОГО соединения: каждый следующий запрос получает то же соединение
const adapter = new PrismaPg({ connectionString: process.env.APP_DATABASE_URL!, max: 1 })
const raw = new PrismaClient({ adapter })

// НЕРАБОЧАЯ «изоляция»: параметр ставится на соединение и остаётся там навсегда (false)
async function asBranchBroken(id: number) {
  await raw.$executeRaw`SELECT set_config('app.branch_id', ${String(id)}, false)`
  return raw.booking.count()
}

console.log('филиал 3:', await asBranchBroken(3))
console.log('«аноним» без объявления филиала:', await raw.booking.count())     // ← должен видеть 0
await raw.$disconnect()
```

```bash run
cd ~/prisma-lab/rentkit
npx tsx src/lessons/16-leak.ts
```

### result
```out auto
```

Ожидаем: «аноним» видит **то же число**, что филиал 3 — параметр «приклеился» к соединению. С пулом в 10 соединений проявляется **случайно**: зависит от того, какое соединение достанется (поэтому «потом пропало» и «не воспроизвести»). **Твоя задача:** исправить, чтобы ни при каких размерах пула «аноним» не видел ничего, и **доказать** этим же скриптом (с `max: 1`). Условия: параметр живёт ровно одну транзакцию, запрос и объявление — в одной транзакции (твоё расширение из 16.4 уже так делает — убедись, что понимаешь **почему**); дополнительно допиши **второй слой**: пусть безымянный запрос (без объявленного филиала) **не просто видит пусто**, а **падает с ошибкой**, чтобы забытая настройка бросалась в глаза, а не молча давала пустой результат (подсказка: политика/проверка, поднимающая исключение).

**Приёмка сессии:** создана роль `rental_app` без права на DDL и без права стирать журналы; политики RLS включены на `tbl_Bookings`, `tbl_Items`, `tbl_Customers`; расширение `scoped` ставит филиал **внутри транзакции**; набор тестов изоляции из 16.6 проходит под ролью приложения; протечка через пул воспроизведена на `max: 1` и устранена; в `NOTES.md` — модель угроз (от чего защищено, от чего нет).

### why
Эта ошибка — самая опасная в мультитенантных системах: она проявляется **редко и случайно**, потому что зависит от того, какое соединение достанется запросу. Воспроизвести её детерминированно, **уменьшив пул до одного соединения**, — приём, который стоит запомнить: он превращает «плавающий» дефект в стабильный.

### deep Если не получилось
- **Подсказка 1:** `set_config(name, value, true)` («local») сбрасывается по окончании транзакции; без явной транзакции каждый запрос — своя неявная транзакция, и параметр исчезнет раньше, чем выполнится следующий запрос.
- **Подсказка 2:** объяви филиал и выполни запрос в **одной** `$transaction([...])` (как в `forScope`) либо в интерактивной транзакции.
- **Подсказка 3 (второй слой):** в функции `app_branch()` можно бросить исключение, если параметр не задан: `IF … IS NULL THEN RAISE EXCEPTION 'не задан филиал'`; цена — ошибка у всех, кто забыл; польза — забывчивость больше не молчит.
- **`max: 1` и зависание** — запрос внутри интерактивной транзакции ждёт второго соединения; не используй исходный `raw` внутри транзакции, а только `tx`.

### quiz
- Почему протечка через пул проявляется случайно и как её сделать воспроизводимой?
- Чем `set_config(…, true)` отличается от `false` по сроку жизни значения?
- Почему полезно, чтобы «забыли объявить филиал» вызывало ошибку, а не пустой результат?

### links
- https://node-postgres.com/apis/pool | пул node-postgres | node-postgres: Pool
- https://www.prisma.io/docs/orm/v7/prisma-client/client-extensions/extension-examples | примеры расширений (RLS) | Prisma 7: Extension examples
