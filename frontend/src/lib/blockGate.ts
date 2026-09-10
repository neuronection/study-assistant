import katex from 'katex'

export type BlockGateKind = 'mermaid' | 'math'

export interface BlockFixGateResult {
  ok: boolean
  error?: string
}

export interface ExtractedBlock {
  source: string
  display: boolean
}

export async function validateMermaidSource(
  text: string
): Promise<BlockFixGateResult> {
  try {
    const mod = await import('mermaid')
    await mod.default.parse(text)
    return { ok: true }
  } catch (error) {
    return {
      ok: false,
      error: error instanceof Error ? error.message : String(error),
    }
  }
}

export function validateMathSource(
  text: string,
  display = false
): BlockFixGateResult {
  try {
    katex.renderToString(text, {
      throwOnError: true,
      displayMode: display,
      output: 'html',
    })
    return { ok: true }
  } catch (error) {
    return {
      ok: false,
      error: error instanceof Error ? error.message : String(error),
    }
  }
}

export async function validateBlockSource(
  kind: BlockGateKind,
  text: string,
  display = false
): Promise<BlockFixGateResult> {
  return kind === 'mermaid'
    ? validateMermaidSource(text)
    : validateMathSource(text, display)
}

function findMathSpan(md: string, start: number, stop: number): ExtractedBlock | null {
  if (md[start + 1] === '$') {
    const close = md.indexOf('$$', start + 2)
    if (close === -1 || close === start + 2) {
      return null
    }
    const boundary = md.indexOf('\n\n', start + 2)
    if (boundary !== -1 && close > boundary) {
      return null
    }
    return { source: md.slice(start + 2, close), display: true }
  }
  const close = md.indexOf('$', start + 1)
  if (close === -1 || close >= stop || close === start + 1) {
    return null
  }
  const content = md.slice(start + 1, close)
  if (/^\s|\s$/.test(content) || md[close + 1] === '$') {
    return null
  }
  return { source: content, display: false }
}

export function extractBlock(
  kind: BlockGateKind,
  markdown: string
): ExtractedBlock | null {
  const lines = markdown.split('\n')
  let index = 0
  let offset = 0
  let fenceMarker: string | null = null
  while (index < lines.length) {
    const line = lines[index]
    if (fenceMarker !== null) {
      if (line.trimStart().startsWith(fenceMarker)) {
        fenceMarker = null
      }
      offset += line.length + 1
      index += 1
      continue
    }
    const fence = line.match(/^\s{0,3}(```+|~~~+)\s*(.*)$/)
    if (fence !== null) {
      const marker = fence[1].slice(0, 3)
      const info = fence[2].trim()
      if (kind === 'mermaid' && info === 'mermaid') {
        const body: string[] = []
        index += 1
        while (
          index < lines.length &&
          !lines[index].trimStart().startsWith(marker)
        ) {
          body.push(lines[index])
          index += 1
        }
        return { source: body.join('\n'), display: false }
      }
      fenceMarker = marker
      offset += line.length + 1
      index += 1
      continue
    }
    if (kind === 'math') {
      let cursor = 0
      while (cursor < line.length) {
        if (line[cursor] === '$') {
          const span = findMathSpan(
            markdown,
            offset + cursor,
            offset + line.length
          )
          if (span !== null) {
            return span
          }
        }
        cursor += 1
      }
    }
    offset += line.length + 1
    index += 1
  }
  return null
}

export async function gateResult(
  kind: BlockGateKind,
  markdown: string
): Promise<BlockFixGateResult> {
  const extracted = extractBlock(kind, markdown)
  if (extracted === null) {
    return { ok: false, error: 'block-not-found' }
  }
  return validateBlockSource(kind, extracted.source, extracted.display)
}
