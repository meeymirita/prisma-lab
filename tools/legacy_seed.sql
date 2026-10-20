-- Генератор «наследства»: чужая база прокатной сети «Прокат снаряжения» (RentKit).
-- ⚠ НЕ ЗАПУСКАЛСЯ (20.10.2026): написан вместе с методичкой, прогон и сверка чисел — в очереди на проверку.
--
-- Запуск (см. make_dump.sh):  psql -U postgres -d rental -v ON_ERROR_STOP=1 -f tools/legacy_seed.sql
-- Детерминированный: setseed() и арифметика от номера строки — каждый запуск даёт одну и ту же базу.
--
-- Что намеренно «грязное» (каждая болячка — отдельный урок методички):
--   * ни одного внешнего ключа; в части броней cust_id, item_id висят в пустоту;
--   * даты броней — text в трёх форматах (дд.мм.гггг, гггг-мм-дд, unix-секунды);
--   * цены — text вида «1 200,00 руб», «1200.00», «1200,0»; залоги — float8;
--   * status — smallint 0..7 без справочника;
--   * имена вроде "tbl_Bookings", "CustName", d_from;
--   * дубли клиентов: тот же телефон в разных форматах, ФИО в разном регистре;
--   * около 150 пар пересекающихся броней одного предмета (двойная бронь уже случилась);
--   * meta — JSON внутри text, часть битая;
--   * tbl_DepositLog — без первичного ключа;
--   * повторные платежи (одинаковый ext_ref);
--   * кроме первичных ключей, индексов нет;
--   * подключение под суперпользователем (одна роль «владелец»).

SELECT setseed(0.2026);

DROP TABLE IF EXISTS "tbl_DepositLog", "tbl_Payments", "tbl_Bookings", "tbl_Customers", "tbl_Items", "tbl_Branches" CASCADE;
DROP TABLE IF EXISTS _bk;

-- ───────────── филиалы (12) ─────────────
CREATE TABLE "tbl_Branches" (
    id      serial PRIMARY KEY,
    name    varchar(100),
    city    varchar(100),
    tz      varchar(40)
);
INSERT INTO "tbl_Branches" (name, city, tz) VALUES
    ('Центр',          'Москва',          'Europe/Moscow'),
    ('Север',          'Санкт-Петербург', 'Europe/Moscow'),
    ('Волга',          'Казань',          'Europe/Moscow'),
    ('Урал',           'Екатеринбург',    'Asia/Yekaterinburg'),
    ('Сибирь',         'Новосибирск',     'Asia/Novosibirsk'),
    ('Байкал',         'Иркутск',         'Asia/Irkutsk'),
    ('Тихий',          'Владивосток',     'Asia/Vladivostok'),
    ('Юг',             'Сочи',            'Europe/Moscow'),
    ('Красная Поляна', 'Сочи',            'Europe/Moscow'),
    ('Алтай',          'Барнаул',         'Asia/Barnaul'),
    ('Карелия',        'Петрозаводск',    'Europe/Moscow'),
    ('Домбай',         'Домбай',          'Europe/Moscow');

-- ───────────── снаряжение (4000) ─────────────
CREATE TABLE "tbl_Items" (
    id          serial PRIMARY KEY,
    branch_id   int,
    sku         varchar(30),
    title       text,
    category    varchar(40),
    daily_price text,          -- «450,00», «1 200,00 руб», «450.0»
    deposit     float8,
    active      smallint,
    meta        text           -- JSON внутри строки, местами битый
);

INSERT INTO "tbl_Items" (branch_id, sku, title, category, daily_price, deposit, active, meta)
SELECT
    1 + (g % 12),
    'SKU-' || lpad(g::text, 5, '0'),
    cat || ' ' || (100 + g % 90),
    cat,
    CASE g % 3
        WHEN 0 THEN price::text || ',00'
        WHEN 1 THEN CASE WHEN price >= 1000
                         THEN (price / 1000)::text || ' ' || lpad((price % 1000)::text, 3, '0') || ',00 руб'
                         ELSE price::text || ',00 руб' END
        ELSE price::text || '.0'
    END,
    price * 3.0 + (g % 7) * 0.01,
    CASE WHEN g % 40 = 0 THEN 0 ELSE 1 END,
    CASE
        WHEN g % 50 = 0 THEN NULL
        WHEN g % 33 = 0 THEN '{"size":"' || (ARRAY['S','M','L','XL'])[1 + g % 4] || '","color":"red"'   -- битый JSON: нет «}»
        ELSE '{"size":"' || (ARRAY['S','M','L','XL'])[1 + g % 4] || '","color":"' || (ARRAY['red','blue','green','black'])[1 + (g / 4) % 4] || '"}'
    END
FROM (
    SELECT g,
           (ARRAY['Лыжи','Сноуборд','Велосипед','Палатка','Рюкзак','Шлем','Спальник','Самокат'])[1 + g % 8] AS cat,
           round((ARRAY[900,1100,700,600,300,200,350,400])[1 + g % 8] * (1 + (g % 5) * 0.1))::int AS price
    FROM generate_series(1, 4000) AS g
) s;

-- ───────────── клиенты (60 000, около 15 % — дубли) ─────────────
CREATE TABLE "tbl_Customers" (
    id          serial PRIMARY KEY,
    "CustName"  text,
    phone       text,
    email       text,
    branch_id   int,
    created     text            -- «2024-03-05 12:30» или «05.03.2024»
);

INSERT INTO "tbl_Customers" ("CustName", phone, email, branch_id, created)
SELECT
    CASE WHEN g % 5 = 0 THEN upper(name) WHEN g % 7 = 0 THEN lower(name) ELSE name END,
    CASE g % 4
        WHEN 0 THEN '+7' || d
        WHEN 1 THEN '8' || d
        WHEN 2 THEN '+7 (' || substr(d, 1, 3) || ') ' || substr(d, 4, 3) || '-' || substr(d, 7, 2) || '-' || substr(d, 9, 2)
        ELSE '8-' || substr(d, 1, 3) || '-' || substr(d, 4, 3) || '-' || substr(d, 7, 4)
    END,
    CASE WHEN g % 10 = 0 THEN NULL ELSE 'user' || p || '@example.test' END,
    1 + (g % 12),
    CASE WHEN g % 3 = 0 THEN to_char(date '2023-01-01' + (g % 1000), 'DD.MM.YYYY')
         ELSE to_char(timestamp '2023-01-01 09:00' + (g % 1000) * interval '1 day' + (g % 600) * interval '1 minute', 'YYYY-MM-DD HH24:MI') END
FROM (
    SELECT g, p,
           (ARRAY['Иван','Пётр','Анна','Мария','Олег','Елена','Сергей','Ольга','Дмитрий','Наталья'])[1 + p % 10]
             || ' ' ||
           (ARRAY['Иванов','Петров','Сидоров','Смирнов','Кузнецов','Попов','Волков','Соколов','Лебедев','Козлов'])[1 + (p / 10) % 10] AS name,
           '9' || lpad(((p::bigint * 7919) % 1000000000)::text, 9, '0') AS d
    FROM (
        SELECT g,
               CASE WHEN g <= 51000 THEN g ELSE 1 + ((g::bigint * 7919) % 51000)::int END AS p   -- g > 51000: чей-то дубль
        FROM generate_series(1, 60000) AS g
    ) t
) s
ORDER BY g;

-- ───────────── вспомогательная таблица броней (удаляется в конце) ─────────────
-- Предмет i получает свои брони подряд по слотам k = 0..74 по 18 дней; длительность ≤ 7 дней, сдвиг ≤ 9 дней → пересечений нет.
CREATE TABLE _bk AS
SELECT
    g,
    CASE WHEN g % 200 = 0 THEN 60000 + g ELSE 1 + ((g::bigint * 31) % 60000)::int END AS cust_id,        -- сироты: клиента нет
    CASE WHEN g % 333 = 0 THEN 4000 + g ELSE it END AS item_id,                                            -- сироты: предмета нет
    CASE WHEN g % 97 = 11 THEN 1 + ((it + 5) % 12) ELSE 1 + (it % 12) END AS branch_id,                    -- ~1 % с «чужим» филиалом
    (date '2023-01-01' + ((CASE WHEN g % 2000 = 7 AND k > 0 THEN k - 1 ELSE k END) * 18 + (g % 10)))::date AS d_from,
    ((date '2023-01-01' + ((CASE WHEN g % 2000 = 7 AND k > 0 THEN k - 1 ELSE k END) * 18 + (g % 10)))
        + (g % 7))::date AS d_to,                                                                          -- d_to — день возврата (включительно)
    round(((ARRAY[900,1100,700,600,300,200,350,400])[1 + it % 8] * (1 + (it % 5) * 0.1)) * (1 + (g % 7)))::numeric AS total,
    CASE
        WHEN k = 74 THEN 1                    -- будущие: подтверждены
        WHEN k = 73 AND g % 3 = 0 THEN 2      -- выданы
        WHEN g % 20 = 0 THEN 4                -- отменены
        WHEN g % 50 = 1 THEN 5                -- не пришли
        WHEN g % 97 = 0 THEN 6                -- просрочены
        WHEN g % 143 = 0 THEN 7               -- утеряны / повреждены
        WHEN g % 61 = 2 THEN 0                -- черновики
        ELSE 3                                -- возвращены
    END AS status
FROM (
    SELECT g, 1 + ((g - 1) % 4000) AS it, (g - 1) / 4000 AS k
    FROM generate_series(1, 300000) AS g
) b;

-- ───────────── брони (300 000) ─────────────
CREATE TABLE "tbl_Bookings" (
    id         serial PRIMARY KEY,
    cust_id    int,
    item_id    int,
    branch_id  int,
    d_from     text,            -- «05.03.2024» | «2024-03-05» | «1709596800»
    d_to       text,
    price      text,            -- «1 200,00 руб» | «1200.00» | «1200,0»
    deposit    float8,
    status     smallint,        -- 0..7, смысл знает только старый код
    note       text
);

INSERT INTO "tbl_Bookings" (cust_id, item_id, branch_id, d_from, d_to, price, deposit, status, note)
SELECT
    cust_id, item_id, branch_id,
    CASE WHEN g % 20 < 3 THEN extract(epoch FROM d_from::timestamp)::bigint::text           -- 15 %: unix-секунды
         WHEN g % 20 < 12 THEN to_char(d_from, 'DD.MM.YYYY')                              -- 45 %: дд.мм.гггг
         ELSE to_char(d_from, 'YYYY-MM-DD') END,                                          -- 40 %: гггг-мм-дд
    CASE WHEN g % 20 < 3 THEN extract(epoch FROM d_to::timestamp)::bigint::text
         WHEN g % 20 < 12 THEN to_char(d_to, 'DD.MM.YYYY')
         ELSE to_char(d_to, 'YYYY-MM-DD') END,
    CASE g % 3
        WHEN 0 THEN CASE WHEN total >= 1000
                         THEN floor(total / 1000)::bigint::text || ' ' || lpad((total % 1000)::bigint::text, 3, '0') || ',00 руб'
                         ELSE total::bigint::text || ',00 руб' END
        WHEN 1 THEN total::bigint::text || '.00'
        ELSE total::bigint::text || ',0'
    END,
    total * 0.5 + (g % 11) * 0.01,
    status,
    CASE WHEN g % 40 = 3 THEN 'клиент попросил продлить' WHEN g % 90 = 5 THEN 'выдано без залога' END
FROM _bk
ORDER BY g;

-- ───────────── платежи (порядка полумиллиона) ─────────────
CREATE TABLE "tbl_Payments" (
    id          serial PRIMARY KEY,
    booking_id  int,
    amount      float8,
    paid        text,           -- «2024-03-05 12:30:00» или «05.03.2024 12:30»
    kind        smallint,       -- 1 предоплата, 2 доплата, 3 возврат
    ext_ref     text            -- внешний номер платежа; при повторе приходит тот же
);

-- предоплата 30 % (всё, кроме черновиков)
INSERT INTO "tbl_Payments" (booking_id, amount, paid, kind, ext_ref)
SELECT g, total * 0.3 + (g % 5) * 0.001,
       CASE WHEN g % 10 = 0 THEN to_char(d_from - 3, 'DD.MM.YYYY') || ' 12:30'
            ELSE to_char((d_from - 3)::timestamp + interval '12 hours 30 minutes', 'YYYY-MM-DD HH24:MI:SS') END,
       1, 'PAY-' || g || '-1'
FROM _bk WHERE status <> 0 ORDER BY g;

-- доплата 70 % (вернули, просрочили, утеряли)
INSERT INTO "tbl_Payments" (booking_id, amount, paid, kind, ext_ref)
SELECT g, total * 0.7 - (g % 5) * 0.001,
       to_char((d_to)::timestamp + interval '18 hours', 'YYYY-MM-DD HH24:MI:SS'),
       2, 'PAY-' || g || '-2'
FROM _bk WHERE status IN (3, 6, 7) ORDER BY g;

-- возврат предоплаты по отменённым
INSERT INTO "tbl_Payments" (booking_id, amount, paid, kind, ext_ref)
SELECT g, total * 0.3 + (g % 5) * 0.001,
       to_char((d_from - 1)::timestamp + interval '10 hours', 'YYYY-MM-DD HH24:MI:SS'),
       3, 'PAY-' || g || '-3'
FROM _bk WHERE status = 4 ORDER BY g;

-- повторы (ретрай платёжного шлюза): те же ext_ref, ~1 % предоплат
INSERT INTO "tbl_Payments" (booking_id, amount, paid, kind, ext_ref)
SELECT booking_id, amount, paid, kind, ext_ref
FROM "tbl_Payments" WHERE kind = 1 AND booking_id % 97 = 0;

-- ───────────── движение залогов (без первичного ключа!) ─────────────
CREATE TABLE "tbl_DepositLog" (
    booking_id  int,
    delta       float8,
    ts          bigint,         -- unix-секунды
    reason      text            -- hold | return | keep
);

INSERT INTO "tbl_DepositLog" (booking_id, delta, ts, reason)
SELECT g, (total * 0.5), extract(epoch FROM d_from::timestamp)::bigint, 'hold'
FROM _bk WHERE g % 3 = 0 AND status IN (2, 3, 6, 7);

INSERT INTO "tbl_DepositLog" (booking_id, delta, ts, reason)
SELECT g, -(total * 0.5), extract(epoch FROM d_to::timestamp)::bigint + 64800, 'return'
FROM _bk WHERE g % 3 = 0 AND status IN (3, 6);

INSERT INTO "tbl_DepositLog" (booking_id, delta, ts, reason)
SELECT g, -(total * 0.25), extract(epoch FROM d_to::timestamp)::bigint + 64800, 'return'
FROM _bk WHERE g % 3 = 0 AND status = 7;

INSERT INTO "tbl_DepositLog" (booking_id, delta, ts, reason)
SELECT g, -(total * 0.25), extract(epoch FROM d_to::timestamp)::bigint + 64800, 'keep'
FROM _bk WHERE g % 3 = 0 AND status = 7;

DROP TABLE _bk;
ANALYZE;

-- Контрольные числа для сверки после генерации (заполнить при прогоне, пока — ожидание):
--   tbl_Branches 12, tbl_Items 4000, tbl_Customers 60000, tbl_Bookings 300000,
--   tbl_Payments ≈ 570 000, tbl_DepositLog ≈ 200 000.
