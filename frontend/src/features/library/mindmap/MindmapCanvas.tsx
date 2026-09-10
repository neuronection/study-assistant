import { useEffect, useRef } from 'react'

import type { INode } from 'markmap-common'
import type { Markmap } from 'markmap-view'

export interface MindmapCanvasHandle {
  fit: () => void
}

export function MindmapCanvas({
  markdown,
  ariaLabel,
  className,
  apiRef,
  onNodeClick,
}: {
  markdown: string
  ariaLabel?: string
  className?: string
  apiRef?: { current: MindmapCanvasHandle | null }
  onNodeClick?: (startLine: number) => void
}) {
  const svgRef = useRef<SVGSVGElement>(null)
  const mmRef = useRef<Markmap | null>(null)
  const clickRef = useRef(onNodeClick)
  clickRef.current = onNodeClick

  useEffect(() => {
    const svg = svgRef.current
    if (!svg) return
    let cancelled = false
    let mm: Markmap | null = null
    Promise.all([import('markmap-lib'), import('markmap-view')])
      .then(([lib, view]) => {
        if (cancelled) return
        const transformer = new lib.Transformer()
        const { root } = transformer.transform(markdown)
        mm = view.Markmap.create(
          svg,
          { fitRatio: 0.95, maxInitialScale: 2, initialExpandLevel: -1 },
          root
        )
        mmRef.current = mm
        if (apiRef) {
          apiRef.current = {
            fit: () => {
              void mm?.fit()
            },
          }
        }
      })
      .catch(() => {
        mmRef.current = null
      })
    return () => {
      cancelled = true
      mmRef.current = null
      if (apiRef) {
        apiRef.current = null
      }
      mm?.destroy()
    }
  }, [markdown, apiRef])

  const resolveNode = (target: Element): INode | null => {
    const mm = mmRef.current
    if (!mm) return null
    const data = mm.state.data
    if (!data) return null
    const stack: INode[] = [data]
    while (stack.length > 0) {
      const node = stack.pop()
      if (!node) continue
      const found = mm.findElement(node)
      if (found && (found.g === target || found.g.contains(target))) return node
      stack.push(...(node.children ?? []))
    }
    return null
  }

  const onClick = (event: React.MouseEvent<SVGSVGElement>) => {
    if (!clickRef.current) return
    const target = event.target as Element
    if (target.closest('circle')) return
    const node = resolveNode(target)
    if (!node) return
    const lines = node.payload?.lines
    const start = typeof lines === 'string' ? Number(lines.split(',')[0]) : Number.NaN
    clickRef.current(start)
  }

  return (
    <svg
      ref={svgRef}
      className={className}
      role="img"
      aria-label={ariaLabel}
      onClick={onClick}
    />
  )
}
