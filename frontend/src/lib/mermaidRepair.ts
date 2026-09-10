const RISKY = /[():]/

function readBalanced(
  line: string,
  from: number,
  open: string,
  close: string
): { text: string; end: number } | null {
  const closeTwo = close.length === 2
  let depth = 1
  let i = from
  while (i < line.length) {
    if (closeTwo && line.startsWith(close, i) && depth === 1) {
      return { text: line.slice(from, i), end: i + 2 }
    }
    const ch = line[i]
    if (ch === open) {
      depth += 1
    } else if (ch === close[0]) {
      depth -= 1
      if (depth === 0) {
        return { text: line.slice(from, i), end: i + 1 }
      }
    }
    i += 1
  }
  return null
}

function maybeQuote(text: string): string {
  const trimmed = text.trim()
  if (trimmed.startsWith('"') && trimmed.endsWith('"')) {
    return trimmed
  }
  if (!RISKY.test(trimmed)) {
    return text
  }
  return `"${trimmed}"`
}

function repairLine(line: string): string {
  let out = ''
  let i = 0
  while (i < line.length) {
    const two = line.slice(i, i + 2)
    if (two === '((' || two === '[[') {
      const close = two === '((' ? '))' : ']]'
      const content = readBalanced(line, i + 2, two[0], close)
      if (content === null) {
        out += two
        i += 2
        continue
      }
      out += two + maybeQuote(content.text) + close
      i = content.end
      continue
    }
    const ch = line[i]
    if (ch === '[') {
      const content = readBalanced(line, i + 1, '[', ']')
      if (content === null) {
        out += ch
        i += 1
        continue
      }
      out += `[${maybeQuote(content.text)}]`
      i = content.end
      continue
    }
    if (ch === '"') {
      const closeQuote = line.indexOf('"', i + 1)
      if (closeQuote === -1) {
        out += line.slice(i)
        break
      }
      out += line.slice(i, closeQuote + 1)
      i = closeQuote + 1
      continue
    }
    out += ch
    i += 1
  }
  return out
}

export function repairMermaidSource(code: string): string | null {
  const repaired = code
    .split('\n')
    .map((line) => repairLine(line))
    .join('\n')
  return repaired === code ? null : repaired
}
