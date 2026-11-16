import { useCallback, useEffect, useRef, type RefObject } from 'react'

import type { Anchor } from '@/lib/api'

const HIGHLIGHT_COLORS = ['yellow', 'green', 'blue', 'pink'] as const

interface CharOrigin {
  node: Text
  offset: number
}

interface TextMap {
  text: string
  origin: CharOrigin[]
}

interface HighlightRegistry {
  set(name: string, highlight: unknown): void
  delete(name: string): void
}

type HighlightConstructor = new (...ranges: Range[]) => { add(range: Range): void }

function buildTextMap(root: HTMLElement): TextMap {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const parent = node.parentElement
      if (parent === null) {
        return NodeFilter.FILTER_REJECT
      }
      const tag = parent.tagName.toLowerCase()
      if (tag === 'script' || tag === 'style') {
        return NodeFilter.FILTER_REJECT
      }
      return NodeFilter.FILTER_ACCEPT
    },
  })
  const origin: CharOrigin[] = []
  const characters: string[] = []
  let pendingSpace = false
  let current = walker.nextNode()
  while (current !== null) {
    const text = current as Text
    for (let offset = 0; offset < text.data.length; offset += 1) {
      const character = text.data[offset]
      if (/\s/.test(character)) {
        pendingSpace = characters.length > 0
        continue
      }
      if (pendingSpace) {
        characters.push(' ')
        origin.push({ node: text, offset })
        pendingSpace = false
      }
      characters.push(character)
      origin.push({ node: text, offset })
    }
    current = walker.nextNode()
  }
  return { text: characters.join(''), origin }
}

function normalizeQuote(value: string): string {
  return value.split(/\s+/).filter(Boolean).join(' ')
}

function findOccurrence(text: string, quote: string, occurrence: number): number {
  const needle = normalizeQuote(quote)
  if (needle.length === 0) {
    return -1
  }
  let start = -1
  for (let index = 0; index <= occurrence; index += 1) {
    start = text.indexOf(needle, start + 1)
    if (start < 0) {
      return -1
    }
  }
  return start
}

export function useDocumentHighlights(
  containerRef: RefObject<HTMLElement | null>,
  anchors: Anchor[],
  revision: string | number | null
): { jumpTo: (anchorId: string) => void } {
  const ranges = useRef(new Map<string, Range>())

  useEffect(() => {
    const container = containerRef.current
    const registry = (CSS as unknown as { highlights?: HighlightRegistry }).highlights
    const HighlightCtor = (globalThis as unknown as { Highlight?: HighlightConstructor })
      .Highlight
    if (container === null || registry === undefined || HighlightCtor === undefined) {
      return undefined
    }
    for (const color of HIGHLIGHT_COLORS) {
      registry.delete(`sa-hl-${color}`)
    }
    const rangeMap = ranges.current
    rangeMap.clear()
    const frame = requestAnimationFrame(() => {
      const map = buildTextMap(container)
      const byColor = new Map<string, Range[]>()
      for (const anchor of anchors) {
        if (anchor.orphaned || !anchor.quote) {
          continue
        }
        const occurrence =
          typeof anchor.payload.occurrence === 'number' ? anchor.payload.occurrence : 0
        const start = findOccurrence(map.text, anchor.quote, occurrence)
        if (start < 0) {
          continue
        }
        const end = start + normalizeQuote(anchor.quote).length
        const first = map.origin[start]
        const last = map.origin[end - 1]
        if (first === undefined || last === undefined) {
          continue
        }
        const range = document.createRange()
        range.setStart(first.node, first.offset)
        range.setEnd(last.node, last.offset + 1)
        rangeMap.set(anchor.id, range)
        const color = HIGHLIGHT_COLORS.includes(
          anchor.color as (typeof HIGHLIGHT_COLORS)[number]
        )
          ? anchor.color
          : 'yellow'
        const bucket = byColor.get(color) ?? []
        bucket.push(range)
        byColor.set(color, bucket)
      }
      for (const [color, colorRanges] of byColor) {
        registry.set(`sa-hl-${color}`, new HighlightCtor(...colorRanges))
      }
    })
    return () => {
      cancelAnimationFrame(frame)
      for (const color of HIGHLIGHT_COLORS) {
        registry.delete(`sa-hl-${color}`)
      }
      rangeMap.clear()
    }
  }, [anchors, containerRef, revision])

  const jumpTo = useCallback((anchorId: string) => {
    const range = ranges.current.get(anchorId)
    const element =
      range?.startContainer.nodeType === Node.TEXT_NODE
        ? range.startContainer.parentElement
        : (range?.startContainer as Element | undefined)
    element?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [])

  return { jumpTo }
}
