# Сессия 1 · Азбука и окружение
dur: ~4 ч

## 1.1 Зачем ORM, если есть pg и SQL | short: Зачем ORM | est: ~25 мин
### intro
**Слова шага:** *ORM*, *схема*, *типизированный клиент*, *миграция*, *N+1*, *что ORM скрывает*.

:::tip Если совсем просто
Представь переводчика между тобой и базой. Ты говоришь на TypeScript («дай брони этого клиента»), он переводит на SQL и обратно. Хороший переводчик ловит опечатки до отправки (типы), помнит, что говорилось раньше (миграции) и не даёт сказать лишнего (защита от инъекций). Плохая сторона: ты перестаёшь слышать, что именно он пересказал базе — и однажды выясняется, что на один экран он задал ей триста вопросов.
:::

Раньше, с `pg`, ты писала так:

```ts
// без ORM: строка SQL, результат — any
const { rows } = await pool.query('SELECT * FROM bookings WHERE customer_id = $1', [42])
rows[0].starts_at   // тип any: опечатка в имени поля обнаружится только в работе
```

С Prisma то же самое:

```ts
// с ORM: тип результата выводится из схемы
const bookings = await prisma.booking.findMany({ where: { customerId: 42 } })
bookings[0].startsAt   // тип Date; опечатка startAt не скомпилируется
```

Что получаешь: **типы** (из схемы), **миграции** (изменения базы лежат в Git), **безопасные запросы** (параметры не склеиваются в строку), **подсказки редактора**. Что платишь: **SQL приходится читать в логе** (Prisma строит его сама), **сложное всё равно пишется руками** (`$queryRaw`, сессия 9), **ORM не знает всего, что умеет база** (диапазоны, частичные индексы, RLS — через SQL-миграции).

### why
Эта лаба не агитирует за ORM. Она показывает **обе стороны** на настоящей базе: где Prisma экономит дни (типы, миграции, вложенные записи) и где подводит (N+1, потерянные обновления, невыразимые ограничения). Понимание, что именно делает ORM под капотом, и отличает разработчика, который пользуется Prisma, от того, кто от неё зависит.

### deep Чем Prisma отличается от других ORM
У Active Record (Eloquent в Laravel, Rails) объект сам знает, как сохранить себя; у Data Mapper (Doctrine) есть отдельный менеджер. Prisma — третий путь: ты **не создаёшь классы моделей**, а описываешь схему, и из неё **генерируется клиент** с методами и типами. Результат запроса — обычный объект без методов, поэтому его легко сериализовать и передавать.

### quiz
- Что делает типизированный клиент и чем он лучше `pool.query` из `pg`?
- Назови две вещи, за которые приходится платить при использовании ORM.
- Почему результат запроса Prisma — «обычный объект», а не экземпляр класса?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/setup-and-configuration/introduction | введение в Prisma Client | Prisma 7: Introduction to Prisma Client
- https://www.prisma.io/docs/orm/v7/more/comparisons/prisma-and-typeorm | Prisma и другие ORM | Prisma 7: Prisma and TypeORM

## 1.2 Prisma 7: три части и что изменилось | short: Устройство Prisma | est: ~30 мин
### intro
**Слова шага:** *`schema.prisma`*, *Prisma Client*, *Prisma CLI*, *`prisma.config.ts`*, *driver adapter*, *`generate`*.

:::tip Если совсем просто
Prisma — набор из трёх инструментов под одной крышей. **Чертёж** (`schema.prisma`): ты описываешь, какие у тебя таблицы. **Фабрика** (CLI): по чертежу она печатает деталь — клиент для твоего кода — и составляет инструкции по перестройке базы (миграции). **Деталь** (`PrismaClient`): тот объект, с которым ты работаешь в коде.
:::

```svg
@prisma-parts
```

| Часть | Что делает | Где лежит |
|---|---|---|
| **Схема** | описывает модели, поля, связи, enum | `prisma/schema.prisma` |
| **Конфиг** | адрес базы для CLI, пути, сид | `prisma.config.ts` в корне проекта |
| **CLI** | `db pull`, `migrate`, `generate`, `validate`, `studio` | пакет `prisma` (dev-зависимость) |
| **Клиент** | запросы из кода | генерируется в папку из `output` |
| **Адаптер** | разговаривает с базой по сети | пакет `@prisma/adapter-pg` (драйвер `pg`) |

**Что изменилось в Prisma 7** (проверено на Prisma 7.10; подробности — на страницах «Generating Prisma Client» и «Config API» документации v7):

- Генератор называется **`prisma-client`** (не `prisma-client-js`), и в нём **обязателен `output`** — папка, куда кладётся клиент. Из `node_modules` клиент переехал в твой проект.
- Адрес базы **ушёл из `schema.prisma` в `prisma.config.ts`** (поле `datasource.url`).
- Клиент работает через **driver adapter** (у нас `PrismaPg`): соединением и пулом управляет драйвер `pg`, а не встроенный движок.
- `prisma generate` **не запускается сам** после `migrate dev`, и сид (`db seed`) тоже сам не запускается — только явными командами.
- Переменные из `.env` Prisma сама **не читает**: в конфиге нужен `import 'dotenv/config'`.

### why
Эти изменения объясняют половину «странных» ошибок, которые ты встретишь: «клиент не обновился» (забыт `generate`), «нет подключения к базе» (не подхвачен `.env`), «Cannot find module» (не тот `output`). Если открыть старую статью про Prisma 5 или 6, часть команд и импортов будет другой.

### deep Почему `@prisma/client` всё равно ставится
Пакет `@prisma/client` в Prisma 7 остаётся: в нём лежит рантайм, который генератор использует. Но сам клиент (типы и методы) создаётся уже в твоей папке `output`. Версии `prisma` и `@prisma/client` должны совпадать по мажору — закрепляем обе (шаг 1.4).

### quiz
- Какие три части Prisma ты можешь назвать и чем каждая занимается?
- Где в Prisma 7 лежит адрес базы данных и почему не в `schema.prisma`?
- Что нужно сделать после изменения схемы, чтобы типы в коде обновились?

### links
- https://www.prisma.io/docs/orm/v7/prisma-client/setup-and-configuration/generating-prisma-client | генерация клиента | Prisma 7: Generating Prisma Client
- https://www.prisma.io/docs/orm/v7/reference/prisma-config-reference | prisma.config.ts | Prisma 7: Config API
- https://www.prisma.io/docs/orm/v7/core-concepts/supported-databases/database-drivers | драйверные адаптеры | Prisma 7: Database drivers

## 1.3 PostgreSQL 18 и дамп «наследства» | short: База и дамп | est: ~40 мин
### intro
**Слова шага:** *контейнер*, *том*, *`pg_restore`*, *дамп (custom-формат)*, *`--no-owner`*, *`psql`*.

:::tip Если совсем просто
Дамп — это «упакованная копия чужой базы одним файлом», как архив с чужой квартирой. Мы поднимаем свободную пустую квартиру (PostgreSQL 18 в контейнере) и «распаковываем» в неё копию: мебель (таблицы), жильцов (данные) и всё, что там было нагромождено.
:::

Дамп лежит в хранилище сайта; скачай его в `~/prisma-lab/starter/` (12 МБ). Он получен генератором `tools/legacy_seed.sql` из репозитория лабы — на случай, если захочешь пересоздать его сама (`tools/make_dump.sh`, нужен Docker):

```bash run
mkdir -p ~/prisma-lab/starter && cd ~/prisma-lab
curl -L -o starter/rental-legacy.dump https://meeymirita-files.storage.yandexcloud.net/prisma/rental-legacy.dump
ls -lh starter/rental-legacy.dump
```

### result
```out auto
```

Размер — около 12 МБ. Если `curl` вернул небольшой файл (несколько сотен байт), открой его: это страница с ошибкой, а не дамп. Теперь база:

Поднимаем PostgreSQL 18 (порт **5433**, чтобы не пересечься с базой из PostgreSQL-лабы; том — в `/var/lib/postgresql`, это требование образа 18):

```bash run
mkdir -p ~/prisma-lab/starter && cd ~/prisma-lab
docker run -d --name rental-pg -e POSTGRES_PASSWORD=postgres -p 5433:5432 \
  -v rental-pgdata:/var/lib/postgresql postgres:18 \
  -c shared_preload_libraries=pg_stat_statements
until docker exec rental-pg pg_isready -U postgres >/dev/null 2>&1; do sleep 1; done
docker exec rental-pg psql -U postgres -c 'SELECT version()'
```

### result
```out auto
```

Создаём базу и восстанавливаем дамп. `--no-owner --no-acl` — не пытаемся воссоздать владельцев и права из чужой базы (в нашей их всё равно нет):

```bash run
cd ~/prisma-lab
docker exec rental-pg psql -U postgres -c 'CREATE DATABASE rental'
docker exec -i rental-pg pg_restore -U postgres -d rental --no-owner --no-acl < starter/rental-legacy.dump
docker exec rental-pg psql -U postgres -d rental -c 'ANALYZE'      # восстановление не переносит статистику: без неё планировщик выбирает плохие планы
docker exec rental-pg psql -U postgres -d rental -c '\dt+'
```

### result
```out auto
```

Должно быть **шесть таблиц**: `tbl_Branches`, `tbl_Items`, `tbl_Customers`, `tbl_Bookings`, `tbl_Payments`, `tbl_DepositLog`. Заведи короткую функцию, чтобы не писать длинную команду каждый раз (в zsh):

```bash
psqlr() { docker exec -i rental-pg psql -U postgres -d rental "$@"; }
psqlr -c 'SELECT count(*) FROM "tbl_Bookings"'
```

### why
Дамп — единственная «точка входа»: все 18 сессий работают с этой базой. Поэтому важно, что её можно **воссоздать за минуту** (сбросил контейнер и распаковал заново), если что-то сломалось. Порт 5433 и имя контейнера `rental-pg` дальше предполагаются во всех шагах.

### deep Команды по частям
`docker run -d --name rental-pg -e POSTGRES_PASSWORD=postgres -p 5433:5432 -v rental-pgdata:/var/lib/postgresql postgres:18 -c shared_preload_libraries=pg_stat_statements`: всё после имени образа — параметры самого сервера: расширение `pg_stat_statements` (статистика запросов) должно быть загружено при старте, оно понадобится в шагах 6.3 и 17.4. `-d` — в фоне, `-p 5433:5432` — порт 5433 Mac ведёт на 5432 в контейнере, `-v …:/var/lib/postgresql` — именованный том для данных (если не смонтировать, после удаления контейнера данные пропадут). `pg_restore -d rental --no-owner --no-acl`: читает custom-формат и заливает в существующую базу `rental`. `ANALYZE` после восстановления обязателен: дамп хранит данные, но не статистику распределения, и без неё запросы (особенно самосоединения из шага 3.1) могут выполняться в разы дольше. `< starter/…dump` — файл передаётся в контейнер через стандартный ввод, поэтому нужен `docker exec -i`.

### deep Если не получилось
- **`port is already allocated`** — порт 5433 занят: `docker ps`, останови лишнее или выбери другой порт (и дальше замени его во всех адресах).
- **`database "rental" already exists`** — база уже создана: удали (`DROP DATABASE rental`) или пропусти `CREATE`; дальше разберём в шаге 1.7.
- **`pg_restore: error: input file appears to be a text format dump`** — в `starter/` лежит не custom-дамп, а SQL-файл: восстанавливай `psql -f`.

### quiz
- Зачем в `docker run` том, смонтированный в `/var/lib/postgresql`?
- Что делают флаги `--no-owner` и `--no-acl`?
- Почему дамп передаётся через `docker exec -i … < файл`, а не просто путём к файлу?

### links
- https://www.postgresql.org/docs/18/app-pgrestore.html | pg_restore | PostgreSQL 18: pg_restore
- https://hub.docker.com/_/postgres | образ postgres | Docker Hub: postgres

## 1.4 Node 24 и проект RentKit | short: Проект | est: ~35 мин
### intro
**Слова шага:** *`package.json`*, *`"type": "module"`*, *`tsconfig.json`*, *`tsx`*, *закрепление версий*, *`.env`*.

:::tip Если совсем просто
Заводим «рабочую мастерскую»: пустую папку проекта, куда будем класть схему, код и миграции. Самое важное — записать в `package.json` **точные версии**, чтобы завтра `npm install` не принёс другую Prisma.
:::

Проверим Node и заведём проект:

```bash run
node -v
mkdir -p ~/prisma-lab/rentkit && cd ~/prisma-lab/rentkit
npm init -y
npm pkg set type=module
npm install @prisma/client@7 @prisma/adapter-pg@7 pg dotenv
npm install -D prisma@7 typescript@~6.0 tsx @types/node @types/pg
npx prisma --version
```

### result
```out auto
```

В выводе `prisma --version` в строках `prisma` и `@prisma/client` должна стоять **`7.x.x`**. Если там `8.x` — вы поставили не то: см. «Если не получилось». Файл `tsconfig.json`:

```json file=tsconfig.json
{
  "compilerOptions": {
    "target": "ES2023",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "outDir": "dist"
  },
  "include": ["src", "prisma", "prisma.config.ts"]
}
```

Файл `.env` (в Git **не коммитим**: добавь в `.gitignore` строки `.env`, `node_modules`, `dist`, `src/generated`):

```bash file=.env
DATABASE_URL="postgresql://postgres:postgres@localhost:5433/rental"
```

И `package.json` после правки (проверь, что у `prisma`, `@prisma/client`, `@prisma/adapter-pg` стоят версии **7**; для большей надёжности можно убрать `^` и оставить точные):

```json
{
  "name": "rentkit",
  "type": "module",
  "scripts": { "dev": "tsx", "typecheck": "tsc --noEmit" },
  "dependencies": {
    "@prisma/adapter-pg": "7.x.x",
    "@prisma/client": "7.x.x",
    "dotenv": "^18.0.0",
    "pg": "^8.0.0"
  },
  "devDependencies": {
    "prisma": "7.x.x",
    "tsx": "^4.0.0",
    "typescript": "~6.0.0"
  }
}
```

```bash run hidden
cd ~/prisma-lab/rentkit && npm pkg set scripts.dev=tsx scripts.typecheck="tsc --noEmit"
```

### why
Закрепление версий — не формальность. На npm тег `latest` у `prisma` уже указывает на **Prisma 8**, у которой другая модель работы; через месяц чистая установка без закрепления сломает все команды лабы. Для Prisma 7 документация использует тег **`prisma@prev`** и `@prisma/client@7` — тоже можно, но явный номер надёжнее.

### deep Команды по частям
`npm pkg set type=module` включает ES-модули: `import` вместо `require`, и в относительных импортах нужен суффикс `.js` (даже для `.ts`-файлов; `tsx` и `tsc` это понимают). `tsx` запускает TypeScript напрямую (`npx tsx src/x.ts`), без отдельной компиляции. `typescript@~6.0` — только патчи 6.0 (на npm `typescript` без тега уже 7.x, с ним часть инструментов не работает).

### deep Если не получилось
- **В `prisma --version` стоит 8.x** — удали `node_modules`, `package-lock.json` и поставь с явными версиями: `npm install @prisma/client@7 @prisma/adapter-pg@7 pg dotenv && npm install -D prisma@7`.
- **`npm ERR! ERESOLVE`** — конфликт зависимостей: повтори с `--legacy-peer-deps` и запиши в заметки, какой пакет конфликтует.
- **`node` старше 24** — поставь Node 24 (`brew install node@24` или `nvm install 24`).

### quiz
- Почему мы закрепляем версию Prisma, а не доверяем `latest`?
- Что делает `"type": "module"` и как это меняет импорты?
- Почему `.env` не попадает в Git?

### links
- https://www.prisma.io/docs/orm/v7/prisma-migrate/getting-started | начало работы с Migrate | Prisma 7: Getting started with Migrate
- https://www.prisma.io/docs/orm/v7/reference/system-requirements | системные требования | Prisma 7: System requirements

## 1.5 Первый взгляд на чужую базу | short: Осмотр базы | est: ~40 мин
### intro
**Слова шага:** *`\d`*, *размеры таблиц*, *ключи*, *индексы*, *типы колонок*, *«список болячек»*.

:::tip Если совсем просто
Ты получила ключи от чужой квартиры. Прежде чем что-то менять, пройдись по комнатам: где что лежит, что подозрительно, что сломано. Ничего не трогай и всё записывай — этот список «болячек» станет планом работ на следующие 10 сессий.
:::

Для обзора используем `psql`. Сначала — какие таблицы и колонки:

```bash run
psqlr() { docker exec -i rental-pg psql -U postgres -d rental "$@"; }
psqlr -c '\d "tbl_Bookings"'
psqlr -c '\d "tbl_Customers"'
psqlr -c '\d "tbl_DepositLog"'
```

### result
```out auto
```

Обрати внимание на три вещи уже здесь: у `tbl_Bookings` в колонках `d_from`, `d_to`, `price` стоит `text` (даты и деньги **строкой**!); у `tbl_DepositLog` нет `Primary key`; в `Indexes` у всех таблиц только первичный ключ, а `Foreign-key constraints` нет вообще. Теперь — что лежит в данных:

```bash run
psqlr() { docker exec -i rental-pg psql -U postgres -d rental "$@"; }
psqlr -c 'SELECT d_from, d_to, price, status FROM "tbl_Bookings" ORDER BY id LIMIT 8'
psqlr -c 'SELECT "CustName", phone, email FROM "tbl_Customers" ORDER BY id LIMIT 6'
psqlr -c "SELECT status, count(*) FROM \"tbl_Bookings\" GROUP BY status ORDER BY status"
```

### result
```out auto
```

Записывай в файл `NOTES.md` (рядом с проектом) — по строке на каждую болячку, которую нашла: формат дат, формат денег, числа вместо статусов, нет ключей, нет индексов и так далее. Дальше в шаге 3.1 мы проверим каждую запросами; сейчас важен **взгляд**, а не точность.

### why
Работа с чужой базой начинается с наблюдений, а не с кода. Список болячек потом превратится в миграции; если составить его позже и «по памяти», часть проблем пропадёт и вылезет уже в продакшне.

### deep Если не получилось
- **`relation "tbl_Bookings" does not exist`** — в `psql` имена с большими буквами нужно брать в двойные кавычки: `"tbl_Bookings"`. Без кавычек PostgreSQL приведёт имя к нижнему регистру.
- **Zsh ругается на `!` или `$`** — оборачивай SQL в одинарные кавычки; если внутри нужны одинарные, используй двойные и экранируй `\"`, как во второй команде.

### quiz
- Какие три «болячки» видны уже по `\d`-выводу `tbl_Bookings`?
- Почему имена таблиц приходится брать в двойные кавычки?
- Зачем записывать наблюдения в `NOTES.md`, пока ничего не трогаешь?

### links
- https://www.postgresql.org/docs/18/app-psql.html | psql | PostgreSQL 18: psql

## 1.6 Что обещает лаба и как проходить | short: Как проходить лабу | est: ~20 мин
### intro
**Слова шага:** *жалоба заказчика*, *Production Hell*, *итоговое ТЗ*, *что считать «сделанным»*.

:::tip Если совсем просто
Это короткий инструктаж перед тем, как начать. Правила простые: пробуй сама, потом смотри разбор; не копируй всё подряд; когда застряла, сначала ищи в логе, потом в «Если не получилось», и только потом спрашивай.
:::

Что ждёт дальше, по сессиям:

| Сессии | Тема | Что получится |
|---|---|---|
| 1–3 | вход, TypeScript, аудит базы | схема из `db pull` и baseline |
| 4–9 | схема, запросы, связи, пагинация, raw SQL | типизированный слой чтения |
| 10–11 | чистка данных | типы, ключи, дубли — без простоя |
| 12–14 | транзакции, двойная бронь, деньги | запись без гонок и потерь |
| 15–16 | расширения, мультитенантность | soft delete, аудит, изоляция филиалов |
| 17–18 | эксплуатация, тесты, Hell | нагрузка, CI, пять поломок |
| 19 | итоговое ТЗ | всё вместе по требованиям |

**Жалобы заказчика.** Время от времени шаг начинается цитатой клиента («бронь исчезла»). Это нарочно: в реальной работе тебе не скажут, где ошибка. Алгоритм: **воспроизвести → найти причину → починить → доказать проверкой**.

**Что считать сделанным.** Шаг сделан, когда есть: работающий код/команда, подтверждающий результат (вывод, тест, `EXPLAIN`) и понимание, *почему* оно работает. Вывод без понимания — копипаст.

### why
Лаба рассчитана на 76 часов и на то, что ты будешь *застревать*. Это нормально: сложные темы (изоляция, RLS, миграции без простоя) понимаются, когда сломалось и починилось, а не когда прочитано.

### quiz
- В каком порядке нужно действовать при «жалобе заказчика»?
- Что считается «сделанным» шагом?

## 1.7 🔨 pg_restore: error — не восстанавливается дамп | short: 🔨 pg_restore error | est: ~30 мин
### intro
**Слова шага:** *`role does not exist`*, *владелец объектов*, *`--no-owner`*, *повторное восстановление*, *`DROP DATABASE`*.

:::tip Если совсем просто
Привезли чужую мебель, а на каждой вещи ярлык: «принадлежит Васе». Но у тебя нет Васи — и грузчик (`pg_restore`) отказывается ставить. Решение — сказать: «ярлыки игнорируй».
:::

Сломаем нарочно: восстановим дамп **без** `--no-owner`, в чистую базу, и посмотрим на ошибку. (Если дамп сделан с `--no-owner`, как в нашем `make_dump.sh`, ошибок не будет — тогда воспроизведи поломку на пример «роль не существует» вручную: `docker exec rental-pg psql -U postgres -c "CREATE DATABASE rental2"`, потом восстанови в неё с любым другим пользователем, `-U nobody`.)

```bash run
cd ~/prisma-lab
docker exec rental-pg psql -U postgres -c 'DROP DATABASE IF EXISTS rental2' -c 'CREATE DATABASE rental2'
docker exec -i rental-pg pg_restore -U nobody -d rental2 < starter/rental-legacy.dump 2>&1 | head -5
```

### result
```out auto
```

Ожидаем ошибку вида `FATAL: role "nobody" does not exist` (подключение невозможно) или `must be owner of ...`. Читай её: сначала **что** не нашлось (роль), потом **где** (подключение или создание объекта). Чиним: подключаемся существующим пользователем и просим игнорировать владельцев.

```bash run
cd ~/prisma-lab
docker exec -i rental-pg pg_restore -U postgres -d rental2 --no-owner --no-acl < starter/rental-legacy.dump
docker exec rental-pg psql -U postgres -d rental2 -c 'SELECT count(*) FROM "tbl_Bookings"'
docker exec rental-pg psql -U postgres -c 'DROP DATABASE rental2'
```

### result
```out auto
```

**Приёмка сессии:** в базе `rental` шесть таблиц, `SELECT count(*)` по ним даёт ожидаемые числа (12 филиалов, 4 000 предметов, 60 000 клиентов, 300 000 броней — остальное около: платежей 583 035, записей залога 180 084); версии Prisma в `package.json` закреплены на 7.x; `NOTES.md` содержит список болячек.

### why
Эта ошибка — самая частая при восстановлении чужого дампа: в нём прописаны владельцы и права, которых в твоей базе нет. Если не понимать, что дамп переносит не только данные, но и «ярлыки» владения, легко потратить час на «ошибку подключения», которой нет.

### deep Если не получилось
- **Восстановление «зависло»** — на 300 тыс. броней нужна минута-две; смотри `docker logs rental-pg`. Если дольше — Docker Desktop мало памяти.
- **Ошибка `already exists`** — восстанавливаешь в непустую базу. Либо `DROP DATABASE` и заново, либо флаг `--clean --if-exists`.

### quiz
- Почему при восстановлении чужого дампа нужен `--no-owner`?
- Как отличить ошибку подключения от ошибки создания объекта по тексту?
- Что делает флаг `--clean --if-exists`?

### links
- https://www.postgresql.org/docs/18/app-pgrestore.html | pg_restore | PostgreSQL 18: pg_restore
