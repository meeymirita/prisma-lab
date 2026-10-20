# -*- coding: utf-8 -*-
"""Схемы Prisma Lab: python3 prisma/src/schemes.py [имя] -> prisma/src/schemes/<имя>.html (вставляются в методичку блоком ```svg @имя)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../fixes/common/_tools'))
from svgkit import Svg  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'schemes')
S = {}


def scheme(f):
    S[f.__name__.replace('_', '-')] = f
    return f


@scheme
def prisma_parts():
    s = Svg(700, 250, 'Три части Prisma: схема и конфиг, CLI с миграциями, сгенерированный клиент с адаптером и база', pid='pp')
    s.box(10, 30, 150, 70, ['schema.prisma', 'prisma.config.ts', '«чертёж»'], fill=.14, bold=True, size=11)
    s.box(10, 140, 150, 60, ['база', 'PostgreSQL 18'], fill=.22, bold=True, size=12)
    s.box(230, 80, 140, 80, ['Prisma CLI', 'generate · migrate', 'db pull', '«фабрика»'], fill=.1, bold=True, size=11)
    s.box(440, 30, 120, 70, ['Клиент', 'src/generated', 'типы из схемы'], fill=.14, size=11)
    s.box(440, 140, 120, 60, ['адаптер pg', 'пул соединений'], fill=.08, size=11)
    s.box(590, 80, 100, 70, ['твой код', 'на TypeScript'], fill=.06, bold=True, size=11)
    s.arrow(160, 62, 228, 108)
    s.arrow(370, 108, 438, 66, 'generate', lx=400, ly=76)
    s.arrow(370, 132, 160, 165, 'migrate', lx=268, ly=164, dash=True)
    s.arrow(160, 172, 228, 144, 'db pull', lx=196, ly=164, dash=True)
    s.arrow(590, 105, 562, 70)
    s.arrow(500, 100, 500, 138)
    s.arrow(440, 170, 162, 170, dash=True)
    s.text(350, 20, 'переводчик между тобой (TypeScript) и базой (SQL)', size=12, weight='700')
    s.text(350, 236, 'в Prisma 7 generate и сид сами не запускаются; адрес базы — в prisma.config.ts', size=11, op=.85)
    return s.html()


@scheme
def introspection():
    s = Svg(700, 230, 'Интроспекция: db pull читает таблицы, ключи и типы чужой базы и пишет схему; смысл данных остаётся за человеком', pid='in')
    s.box(10, 40, 170, 130, ['чужая база', '', 'tbl_Bookings', 'd_from  text', 'price  text', 'status  smallint'], fill=.12, size=11)
    s.box(250, 70, 130, 70, ['prisma db pull', 'читает каталог'], fill=.2, bold=True, size=12)
    s.box(450, 40, 240, 130, ['schema.prisma', '', 'model tbl_Bookings {', '  d_from String?', '  price String?', '  status Int? @db.SmallInt', '}'], fill=.08, size=11)
    s.arrow(180, 105, 248, 105)
    s.arrow(380, 105, 448, 105)
    s.text(350, 24, 'описание квартиры по осмотру: видно стены, не видно планов', size=12, weight='700')
    s.text(350, 196, 'видит: таблицы, колонки, типы, ключи.  Не видит: что price — деньги, а status — состояние брони', size=11, op=.9)
    s.text(350, 214, 'таблица без первичного ключа получает @@ignore и в клиенте отсутствует', size=11, op=.9)
    return s.html()


@scheme
def types_map():
    s = Svg(700, 250, 'Три языка: PostgreSQL, Prisma и TypeScript и перевод основных типов', pid='tm')
    cols = [('PostgreSQL', 40), ('Prisma', 270), ('TypeScript', 500)]
    for name, x in cols:
        s.box(x, 14, 160, 30, [name], fill=.2, bold=True, size=12)
    rows = [('numeric(12,2)', 'Decimal', 'Prisma.Decimal'), ('bigint', 'BigInt', 'bigint'), ('integer', 'Int', 'number'),
            ('timestamptz', 'DateTime', 'Date'), ('jsonb', 'Json', 'JsonValue'), ('text', 'String', 'string')]
    for i, (a, b, c) in enumerate(rows):
        y = 56 + i * 30
        s.box(40, y, 160, 24, [a], fill=.06, size=11)
        s.box(270, y, 160, 24, [b], fill=.1, size=11)
        s.box(500, y, 160, 24, [c], fill=.06, size=11)
        s.arrow(200, y + 12, 268, y + 12)
        s.arrow(430, y + 12, 498, y + 12)
    s.text(350, 242, 'деньги — Decimal, счётчики — bigint: оба не превращаются в number молча', size=11, op=.85)
    return s.html()


@scheme
def n_plus_one():
    s = Svg(700, 260, 'N+1: цикл с запросом внутри даёт сотни запросов; include собирает те же данные за три', pid='np1')
    s.text(170, 20, 'в цикле: 1 + N + N', size=13, weight='700')
    s.box(10, 40, 90, 36, ['код'], fill=.1, bold=True)
    for i in range(6):
        y = 38 + i * 30
        s.box(190, y, 150, 24, ['запрос ' + str(i + 1)], fill=.06 + (i % 2) * .03, size=11)
        s.arrow(100, 58, 188, y + 12)
    s.text(265, 224, '… и так 400 раз', size=11, op=.85)
    s.text(530, 20, 'include: 3 запроса', size=13, weight='700')
    s.box(420, 40, 90, 36, ['код'], fill=.1, bold=True)
    for i, t in enumerate(['брони (200)', 'клиенты IN (…)', 'предметы IN (…)']):
        y = 56 + i * 44
        s.box(560, y, 130, 32, [t], fill=.2, bold=True, size=11)
        s.arrow(510, 58, 558, y + 16)
    s.text(350, 250, 'курьер за каждой посылкой отдельно против одной поездки со всем грузом', size=11, op=.85)
    return s.html()


@scheme
def offset_vs_cursor():
    s = Svg(700, 230, 'OFFSET читает и выбрасывает все пропущенные строки, cursor идёт сразу к закладке', pid='oc')
    s.text(170, 20, 'skip: 249 950, take: 50', size=13, weight='700')
    for i in range(12):
        s.box(10 + i * 27, 36, 24, 36, [], fill=.05 if i < 10 else .3)
    s.text(150, 92, '… прочитано и выброшено 249 950 строк …', size=11, op=.85)
    s.arrow(14, 110, 330, 110)
    s.text(170, 128, 'время растёт с номером страницы', size=11)
    s.text(530, 20, 'cursor: id > 249 950', size=13, weight='700')
    for i in range(12):
        s.box(380 + i * 27, 36, 24, 36, [], fill=.05 if i < 10 else .3, dash=(i < 10))
    s.arrow(558, 140, 558, 76)
    s.text(558, 158, 'закладка: сразу сюда', size=11, weight='700')
    s.text(530, 128, 'время почти не зависит от глубины', size=11)
    s.text(350, 206, 'страница 1 000 000 в книге: листать с начала против открыть по закладке', size=11, op=.85)
    return s.html()


@scheme
def migrate_flow():
    s = Svg(700, 250, 'migrate dev: shadow-база проигрывает историю, сравнивает со схемой, пишет и применяет миграцию; deploy только применяет', pid='mf')
    s.text(260, 20, 'migrate dev (у тебя на ноутбуке)', size=13, weight='700')
    s.box(10, 40, 100, 50, ['история', 'prisma/migrations'], fill=.1, size=11)
    s.box(150, 40, 100, 50, ['shadow-база', 'временная'], fill=.14, size=11)
    s.box(290, 40, 100, 50, ['сравнить', 'со схемой'], fill=.1, size=11)
    s.box(430, 40, 110, 50, ['новый', 'migration.sql'], fill=.22, bold=True, size=11)
    s.box(580, 40, 110, 50, ['реальная база', '+ _prisma_migrations'], fill=.14, size=10)
    for x in (110, 250, 390, 540):
        s.arrow(x, 65, x + 38, 65)
    s.text(350, 130, 'migrate deploy (CI, прод)', size=13, weight='700')
    s.box(120, 150, 150, 50, ['все папки миграций'], fill=.1, size=11)
    s.box(330, 150, 110, 50, ['ещё не', 'применённые'], fill=.14, size=11)
    s.box(500, 150, 120, 50, ['реальная база'], fill=.22, bold=True, size=11)
    s.arrow(270, 175, 328, 175)
    s.arrow(440, 175, 498, 175)
    s.text(350, 226, 'примерка на макете против боевого монтажа: никаких вопросов и сравнений', size=11, op=.85)
    return s.html()


@scheme
def expand_contract():
    s = Svg(700, 250, 'Expand, backfill, switch, contract: безопасная смена типа колонки на живой базе', pid='ec')
    steps = [('1  expand', 'добавить новую\nколонку'), ('2  backfill', 'заполнить порциями'), ('3  switch', 'код читает и пишет\nновую'), ('4  contract', 'убрать старую\nпосле проверки')]
    for i, (a, b) in enumerate(steps):
        x = 8 + i * 172
        s.box(x, 40, 150, 70, [a] + b.split('\n'), fill=.08 + i * .05, bold=True, size=11)
        if i < 3:
            s.arrow(x + 150, 75, x + 172, 75)
    s.box(8, 140, 150, 40, ['старая колонка', 'жива и цела'], fill=.06, size=11)
    s.box(180, 140, 150, 40, ['две колонки', 'сверка сумм'], fill=.06, size=11)
    s.box(352, 140, 150, 40, ['старая — в запасе', 'откат возможен'], fill=.06, size=11)
    s.box(524, 140, 150, 40, ['дамп до contract', 'защитная проверка'], fill=.18, size=11, bold=True)
    for x in (83, 255, 427, 599):
        s.line(x, 110, x, 140, dash=True, op=.6)
    s.text(350, 20, 'ремонт дороги по полосам: движение не останавливается', size=12, weight='700')
    s.text(350, 214, 'откат возможен на любом шаге, кроме последнего; поэтому перед ним — копия и проверка', size=11, op=.85)
    return s.html()


@scheme
def lost_update():
    s = Svg(700, 250, 'Потерянное обновление: два кассира читают 100, оба пишут 110, итог 110 вместо 120', pid='lu')
    s.text(100, 22, 'кассир A', size=12, weight='700')
    s.text(350, 22, 'база: bonus_points', size=12, weight='700')
    s.text(600, 22, 'кассир B', size=12, weight='700')
    s.box(300, 34, 100, 36, ['100'], fill=.14, bold=True, size=14)
    s.arrow(150, 56, 298, 56, 'читаю: 100', lx=225, ly=48)
    s.arrow(550, 78, 402, 62, 'читаю: 100', lx=480, ly=60)
    s.box(300, 110, 100, 36, ['110'], fill=.2, bold=True, size=14)
    s.arrow(150, 128, 298, 128, 'пишу 100+10', lx=225, ly=120)
    s.box(300, 170, 100, 36, ['110'], fill=.28, bold=True, size=14)
    s.arrow(550, 190, 402, 190, 'пишу 100+10', lx=480, ly=182)
    s.text(350, 232, 'между «прочитал» и «записал» есть щель; атомарный increment её закрывает', size=11, op=.9)
    return s.html()


@scheme
def exclude_constraint():
    s = Svg(700, 250, 'EXCLUDE: два диапазона одного предмета не могут пересекаться; база отвергает вторую бронь', pid='ex')
    s.line(60, 60, 640, 60, op=.5)
    for i, d in enumerate(['1', '2', '3', '4', '5', '6', '7', '8']):
        s.line(60 + i * 83, 56, 60 + i * 83, 64, op=.7)
        s.text(60 + i * 83, 80, d + ' янв', size=10, op=.8)
    s.bar(60, 96, 245, 32, 'бронь A  1–3 янв', fill=.26, size=11)
    s.bar(226, 140, 245, 32, 'бронь B  3–5 янв  ✕ пересекается', fill=.1, dash=True, size=11)
    s.bar(473, 96, 165, 32, 'бронь C  6–7 янв  ✓', fill=.18, size=11)
    s.box(10, 190, 680, 44, ['EXCLUDE USING gist (item_id WITH =, period WITH &&) WHERE (статус «живой»)'], fill=.08, bold=True, size=12)
    s.text(350, 20, 'расписание переговорной: два события в одно время не помещаются', size=12, weight='700')
    return s.html()


@scheme
def fk_two_step():
    s = Svg(700, 230, 'Внешний ключ в два шага: NOT VALID действует для новых строк сразу, VALIDATE проверяет старые без остановки записи', pid='fk')
    s.box(10, 50, 190, 70, ['ADD CONSTRAINT', '… NOT VALID', 'мгновенно'], fill=.14, bold=True, size=11)
    s.box(255, 50, 190, 70, ['новые строки', 'проверяются сразу', 'старые пока — нет'], fill=.08, size=11)
    s.box(500, 50, 190, 70, ['VALIDATE CONSTRAINT', 'долго, но запись', 'продолжается'], fill=.22, bold=True, size=11)
    s.arrow(200, 85, 253, 85)
    s.arrow(445, 85, 498, 85)
    s.text(350, 24, 'проверка каждой строки в один приём остановила бы таблицу', size=12, weight='700')
    s.box(10, 150, 680, 54, ['перед этим: найти и разобрать сирот (LEFT JOIN … IS NULL), записать решения в журнал'], fill=.06, size=11)
    return s.html()


@scheme
def ledger_double_entry():
    s = Svg(700, 260, 'Двойная запись: платёж 1000 даёт две проводки с суммой ноль; остаток счёта — сумма проводок', pid='le')
    s.box(10, 40, 150, 60, ['операция', 'tx_id = …', 'платёж 1 000'], fill=.1, bold=True, size=11)
    s.box(250, 30, 180, 40, ['CASH   +1 000'], fill=.22, bold=True, size=12)
    s.box(250, 90, 180, 40, ['REVENUE   −1 000'], fill=.14, bold=True, size=12)
    s.arrow(160, 60, 248, 50)
    s.arrow(160, 80, 248, 110)
    s.box(480, 30, 210, 40, ['сумма операции = 0', 'проверяет отложенный триггер'], fill=.06, size=11)
    s.arrow(430, 50, 478, 50, dash=True)
    s.box(10, 160, 680, 60, ['остаток CASH = сумма всех проводок по счёту: нигде не хранится, поэтому его нельзя «подогнать»', 'ошибка исправляется новой компенсирующей проводкой, а не правкой старой'], fill=.05, size=11)
    s.text(350, 20, 'бухгалтерская книга: каждая копейка откуда-то и куда-то', size=12, weight='700')
    s.text(350, 246, 'залог — на отдельном счёте DEPOSITS: это обязательство, а не выручка', size=11, op=.85)
    return s.html()


@scheme
def extension_layers():
    s = Svg(700, 250, 'Слои расширений вокруг клиента: каждый запрос проходит через soft delete, замер и область видимости', pid='xl')
    s.box(10, 90, 100, 50, ['твой код'], fill=.1, bold=True)
    layers = [('softDelete', 130), ('timing', 250), ('branchScope', 370)]
    for name, x in layers:
        s.box(x, 70, 110, 90, [name, 'query()'], fill=.12, bold=True, size=11)
    s.box(500, 80, 80, 70, ['Prisma', 'Client'], fill=.2, bold=True, size=11)
    s.box(610, 80, 80, 70, ['база'], fill=.22, bold=True, size=12)
    s.arrow(110, 115, 128, 115)
    for x in (240, 360):
        s.arrow(x, 115, x + 10, 115)
    s.arrow(480, 115, 498, 115)
    s.arrow(580, 115, 608, 115)
    s.text(350, 20, 'турникет перед всеми дверями, а не охранник у каждой', size=12, weight='700')
    s.text(350, 190, 'у каждого слоя: до query(args) — вход, после — выход; result и model — свои добавки', size=11, op=.9)
    s.text(350, 212, 'raw-запросы идут мимо слоёв query: правила для них — в базе (RLS) или тестом', size=11, op=.9)
    return s.html()


@scheme
def tenant_models():
    s = Svg(700, 250, 'Три модели изоляции тенантов: общие таблицы с RLS, схема на тенанта, база на тенанта', pid='tn')
    cols = [('Колонка + RLS', ['одни таблицы', 'branch_id в строке', 'политика в базе'], .22, 'наш выбор'),
            ('Схема на тенанта', ['branch_3.bookings', 'branch_7.bookings', 'миграции ×N'], .1, 'жёстче, дороже'),
            ('База на тенанта', ['rental_3', 'rental_7', 'пулы ×N'], .06, 'максимум изоляции')]
    for i, (t, lines, f, note) in enumerate(cols):
        x = 10 + i * 232
        s.box(x, 40, 210, 120, [t] + lines, fill=f, bold=True, size=11)
        s.text(x + 105, 184, note, size=11, op=.9)
    s.text(350, 20, 'общая комната с запертыми шкафчиками, коридор или целое здание', size=12, weight='700')
    s.text(350, 226, 'внутренние подразделения одной компании: колонка + RLS; внешние клиенты — чаще схема или база', size=11, op=.85)
    return s.html()


@scheme
def connection_pool():
    s = Svg(700, 250, 'Пул соединений: приложения берут по несколько линий, сумма не должна превысить max_connections базы', pid='cp')
    for i, n in enumerate(['приложение 1', 'приложение 2', 'воркер']):
        y = 30 + i * 62
        s.box(10, y, 130, 44, [n, 'пул max = 10'], fill=.1, size=11)
        s.arrow(140, y + 22, 300, 120)
    s.box(300, 80, 130, 80, ['(PgBouncer)', 'если нужен'], fill=.06, dash=True, size=11)
    s.arrow(430, 120, 520, 120)
    s.box(520, 50, 170, 140, ['PostgreSQL', '', 'max_connections = 100', '', '3 × 10 = 30 + запас'], fill=.2, bold=True, size=11)
    s.text(350, 18, 'телефонные линии: больше линий, чем у АТС, не бывает', size=12, weight='700')
    s.text(350, 226, 'процессы × max ≤ max_connections − запас;  connectionTimeoutMillis: быстрая ошибка вместо вечной очереди', size=11, op=.9)
    return s.html()


@scheme
def test_template_db():
    s = Svg(700, 250, 'Шаблонная база: эталон со всем устройством, на каждый файл тестов копия за миллисекунды', pid='tt')
    s.box(10, 90, 150, 70, ['rental_template', 'схема + ограничения', 'триггеры, права'], fill=.22, bold=True, size=11)
    for i, n in enumerate(['rental_test_101', 'rental_test_102', 'rental_test_103']):
        y = 30 + i * 70
        s.box(300, y, 150, 44, [n, 'свои данные'], fill=.1, size=11)
        s.arrow(160, 125, 298, y + 22, 'TEMPLATE' if i == 0 else None, lx=230, ly=60)
        s.box(520, y, 170, 44, ['файл тестов ' + str(i + 1), 'DROP после'], fill=.06, size=11)
        s.arrow(450, y + 22, 518, y + 22)
    s.text(350, 18, 'параллельные тесты не мешают друг другу и рабочей базе', size=12, weight='700')
    s.text(350, 240, 'мок не проверит EXCLUDE, триггеры и RLS: они существуют только в настоящем PostgreSQL', size=11, op=.85)
    return s.html()


@scheme
def final_task():
    s = Svg(700, 260, 'Итоговое задание: наследство → чистка → инварианты → безопасность → производительность → поставка', pid='ft')
    layers = [('Наследство', 'восстановить, осмотреть, baseline'), ('Чистка', 'expand/contract, ключи, дубли'), ('Инварианты', 'EXCLUDE, ledger, идемпотентность'),
              ('Безопасность', 'роль, RLS, расширения'), ('Скорость', 'индексы, EXPLAIN, пул, нагрузка'), ('Поставка', 'тесты, CI, образ, метрики, ADR')]
    for i, (a, b) in enumerate(layers):
        y = 12 + i * 40
        s.box(10, y, 150, 32, [a], fill=.16, bold=True, size=12)
        s.box(180, y, 340, 32, [b], fill=.06, size=11)
    s.box(550, 60, 140, 110, ['самопроверка', 'таблица приёмки', 'в ТЗ'], fill=.22, bold=True, size=12)
    s.arrow(520, 115, 548, 115)
    s.text(620, 196, 'схему данных', size=11, op=.85)
    s.text(620, 212, 'нарисуешь ты сама —', size=11, op=.85)
    s.text(620, 228, 'это часть проверки', size=11, op=.85)
    return s.html()


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    for name, f in S.items():
        if len(sys.argv) > 1 and name != sys.argv[1]:
            continue
        open(os.path.join(OUT, name + '.html'), 'w', encoding='utf-8').write(f())
        print('схема:', name)
