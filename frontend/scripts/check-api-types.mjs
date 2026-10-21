#!/usr/bin/env node
import { readdir, readFile } from 'node:fs/promises'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const apiDir = join(root, 'src', 'lib', 'api')
const SCHEMA_IMPORT = /from '@\/lib\/api-schema'/
const SCHEMA_REF = /(?:Schemas|components)\[/
const ALLOWED_WITHOUT_SCHEMA = new Set(['client.ts', 'index.ts'])

const files = (await readdir(apiDir)).filter((name) => name.endsWith('.ts'))
const registerSource = await readFile(join(apiDir, 'hand-types.ts'), 'utf8')
const registered = new Set(
  [...registerSource.matchAll(/\{ name: '(\w+)'/g)].map((match) => match[1]),
)

function declarations(source) {
  const found = []
  const pattern = /^export (?:interface|type) (\w+)/gm
  let match
  while ((match = pattern.exec(source)) !== null) {
    const start = match.index
    const next = source.slice(match.index + match[0].length).search(/^export /m)
    const end = next === -1 ? source.length : match.index + match[0].length + next
    const body = source.slice(start, end)
    if (!SCHEMA_REF.test(body)) {
      found.push({ name: match[1], body })
    }
  }
  return found
}

const findings = []
const handDecls = new Set()
for (const file of files.sort()) {
  const source = await readFile(join(apiDir, file), 'utf8')
  if (!SCHEMA_IMPORT.test(source) && !ALLOWED_WITHOUT_SCHEMA.has(file)) {
    findings.push(`${file}: does not import the generated api-schema`)
  }
  for (const decl of declarations(source)) {
    handDecls.add(decl.name)
    if (!registered.has(decl.name)) {
      findings.push(`${file}:${decl.name}: hand declaration is not in hand-types.ts HAND_TYPE_REGISTER`)
    }
  }
}

for (const name of [...registered].sort()) {
  if (!handDecls.has(name)) {
    findings.push(`hand-types.ts:${name}: registered exception has no declaration`)
  }
}

if (findings.length > 0) {
  console.error('check-api-types: wire contracts must come from api-schema.d.ts')
  for (const finding of findings) {
    console.error(`  ${finding}`)
  }
  process.exit(1)
}

console.log(
  `check-api-types: clean (${files.length} modules, ${handDecls.size} registered client shapes)`,
)
