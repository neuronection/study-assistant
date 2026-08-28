import Paragraph from '@tiptap/extension-paragraph'
import type { Node as ProseMirrorNode } from '@tiptap/pm/model'
import type { Editor } from '@tiptap/react'

const NBSP_MD = '&nbsp;'
const NBSP = '\u00A0'

export const MATH_NEWLINE = '\u2063'

interface SerializerState {
  write(payload: string): void
  renderInline(node: { childCount: number }): void
  closeBlock(node: { childCount: number }): void
}

export const BlankLineParagraph = Paragraph.extend({
  addStorage() {
    return {
      markdown: {
        serialize: (state: SerializerState, node: { childCount: number }) => {
          if (node.childCount === 0) {
            state.write(NBSP)
          } else {
            state.renderInline(node)
          }
          state.closeBlock(node)
        },
      },
    }
  },
})

export function encodeMarkdownForParse(md: string): string {
  const core = protectMathSpans(md.replace(/^\n+/, '').replace(/\n+$/, ''))
  return stuffBlankLinesOutsideFences(core)
}

function stuffBlankLinesOutsideFences(md: string): string {
  let out = ''
  let plain = ''
  let inFence = false
  let fenceMarker = ''
  let index = 0
  while (index < md.length) {
    if (md[index] === '\n') {
      if (inFence) {
        out += '\n'
      } else {
        plain += '\n'
      }
      index += 1
      continue
    }
    const lineEnd = md.indexOf('\n', index)
    const stop = lineEnd === -1 ? md.length : lineEnd
    const rest = md.slice(index, stop)
    const fenceMatch = rest.match(/^\s{0,3}(```+|~~~+)/)
    if (fenceMatch) {
      const marker = fenceMatch[1].slice(0, 3)
      if (!inFence) {
        out += plain.replace(
          /\n{3,}/g,
          (run) => `\n\n${`${NBSP_MD}\n\n`.repeat(run.length - 2)}`
        )
        plain = ''
        inFence = true
        fenceMarker = marker
      } else if (marker === fenceMarker) {
        inFence = false
      }
      out += rest
      index = stop
      continue
    }
    if (inFence) {
      out += rest
    } else {
      plain += rest
    }
    index = stop
  }
  out += plain.replace(
    /\n{3,}/g,
    (run) => `\n\n${`${NBSP_MD}\n\n`.repeat(run.length - 2)}`
  )
  return out
}

export function decodeMarkdownFromSerialize(md: string): string {
  return md
    .replace(/^(?:\u00A0\n\n)+/, '')
    .replace(/(?:\n\n)?(?:\u00A0\n\n)*\u00A0?$/, '')
    .replace(/\u00A0\n\n/g, '\n')
}

function transformMathSpans(md: string, onSpan: (span: string) => string): string {
  let out = ''
  let index = 0
  let inFence = false
  let fenceMarker = ''
  while (index < md.length) {
    if (md[index] === '\n') {
      out += '\n'
      index += 1
      continue
    }
    const lineEnd = md.indexOf('\n', index)
    const stop = lineEnd === -1 ? md.length : lineEnd
    const rest = md.slice(index, stop)
    const fenceMatch = rest.match(/^\s{0,3}(```+|~~~+)/)
    if (fenceMatch) {
      const marker = fenceMatch[1].slice(0, 3)
      if (!inFence) {
        inFence = true
        fenceMarker = marker
      } else if (marker === fenceMarker) {
        inFence = false
      }
      out += rest
      index = stop
      continue
    }
    if (inFence) {
      out += rest
      index = stop
      continue
    }
    let cursor = index
    let plain = ''
    while (cursor < stop) {
      const char = md[cursor]
      if (char === '\\' && cursor + 1 < stop) {
        plain += md.slice(cursor, cursor + 2)
        cursor += 2
        continue
      }
      if (char === '`') {
        const run = /^`+/.exec(md.slice(cursor, stop))?.[0] ?? '`'
        const close = md.indexOf(run, cursor + run.length)
        if (close !== -1 && close < stop) {
          plain += md.slice(cursor, close + run.length)
          cursor = close + run.length
        } else {
          plain += md.slice(cursor, stop)
          cursor = stop
        }
        continue
      }
      if (char === '$') {
        const spanEnd = findMathEnd(md, cursor, stop)
        if (spanEnd !== null) {
          out += plain
          plain = ''
          out += onSpan(md.slice(cursor, spanEnd))
          cursor = spanEnd
          continue
        }
      }
      plain += char
      cursor += 1
    }
    out += plain
    index = Math.max(cursor, stop)
  }
  return out
}

function findMathEnd(md: string, start: number, stop: number): number | null {
  if (md[start + 1] === '$') {
    const close = md.indexOf('$$', start + 2)
    if (close === -1 || close === start + 2) {
      return null
    }
    const boundary = md.indexOf('\n\n', start + 2)
    if (boundary !== -1 && close > boundary) {
      return null
    }
    return close + 2
  }
  const close = md.indexOf('$', start + 1)
  if (close === -1 || close >= stop || close === start + 1) {
    return null
  }
  const content = md.slice(start + 1, close)
  if (/^\s|\s$/.test(content) || md[close + 1] === '$') {
    return null
  }
  return close + 1
}

function protectMathSpans(md: string): string {
  return transformMathSpans(md, (span) => {
    const display = span.startsWith('$$')
    const delimiter = display ? '$$' : '$'
    const content = span
      .slice(delimiter.length, span.length - delimiter.length)
      .replace(/\\(?!\|)/g, '\\\\')
    if (display) {
      return `$$${content.replace(/\n/g, MATH_NEWLINE)}$$`
    }
    return `$${content}$`
  })
}

function collectMarkerRanges(
  node: ProseMirrorNode,
  pos: number,
  ranges: { from: number; to: number }[]
): void {
  node.forEach((child, offset) => {
    const childPos = pos + offset
    if (
      child.type.name === 'paragraph' &&
      child.childCount === 1 &&
      child.firstChild?.isText === true &&
      child.firstChild.text === NBSP
    ) {
      ranges.push({ from: childPos + 1, to: childPos + child.nodeSize - 1 })
      return
    }
    collectMarkerRanges(child, childPos, ranges)
  })
}

export function stripBlankMarkers(editor: Editor): void {
  const { tr, doc } = editor.state
  const ranges: { from: number; to: number }[] = []
  collectMarkerRanges(doc, 0, ranges)
  if (ranges.length === 0) {
    return
  }
  tr.setMeta('preventUpdate', true)
  tr.setMeta('addToHistory', false)
  for (const { from, to } of ranges) {
    tr.delete(tr.mapping.map(from), tr.mapping.map(to))
  }
  editor.view.dispatch(tr)
}
