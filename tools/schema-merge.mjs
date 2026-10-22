// Служебный скрипт сборки методички (tools/build-manual.py): вносит в prisma/schema.prisma блоки из методички.
// Использование: node schema-merge.mjs prisma/schema.prisma < блоки.prisma
// Блок с тем же именем (или с тем же именем таблицы в @@map) заменяет прежний на его месте; блок с пометкой
// «…поля как раньше…» дописывается в конец существующей модели; новые блоки добавляются в конец файла.
import fs from 'node:fs'

const file = process.argv[2]
let src = fs.existsSync(file) ? fs.readFileSync(file, 'utf8') : ''
const incoming = fs.readFileSync(0, 'utf8')
const RE = '^(model|enum|view|type|datasource|generator)[ \\t]+(\\w+)[ \\t]*\\{[\\s\\S]*?^\\}[ \\t]*$'

function blocks(text) {
  const out = []
  const re = new RegExp(RE, 'gm')
  let m
  while ((m = re.exec(text))) {
    const map = /@@map\("([^"]+)"\)/.exec(m[0])
    out.push({ kind: m[1], name: m[2], table: map ? map[1] : m[2], text: m[0], at: m.index, end: m.index + m[0].length })
  }
  return out
}

const FRAG = /…(?:старые )?поля как (?:раньше|есть)…/
const norm = (x) => x.replace(/\s+/g, ' ').trim()

for (const n of blocks(incoming)) {
  const cur = blocks(src)
  const o = cur.find((b) => b.kind === n.kind && (b.name === n.name || (n.kind === 'model' && b.table === n.table)))
  const fragment = FRAG.test(n.text)
  let repl
  if (o && fragment) {
    const add = n.text.split('\n').slice(1, -1).filter((l) => !FRAG.test(l) && !norm(o.text).includes(norm(l)))
    repl = o.text.replace(/\n\}[ \t]*$/, '\n\n' + add.join('\n') + '\n}')
  } else repl = n.text
  if (o) {
    // doc-комментарии `///` прямо над старой моделью (например, «таблица без ключа») относились к ней, а не к новой
    let from = o.at
    for (;;) {
      const prev = src.slice(0, from).replace(/\n$/, '')
      const m = /(^|\n)(\/\/\/[^\n]*)$/.exec(prev)
      if (!m) break
      from = prev.length - m[2].length
    }
    src = src.slice(0, from) + repl + src.slice(o.end)
  }
  else src = src.trimEnd() + '\n\n' + repl + '\n'
}
fs.writeFileSync(file, src.endsWith('\n') ? src : src + '\n')
