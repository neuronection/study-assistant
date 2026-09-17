import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import type { ConceptGraph } from '@/lib/api'
import { useMediaQuery } from '@/lib/use-media-query'

export interface LayoutNode {
  id: number
  name: string
  x: number
  y: number
  radius: number
  mastery: 'strong' | 'shaky' | 'weak' | null
}

export interface LayoutEdge {
  from: number
  to: number
  relation: string
}

export interface GraphLayout {
  nodes: LayoutNode[]
  edges: LayoutEdge[]
}

const WIDTH = 900
const HEIGHT = 560
const ITERATIONS = 300
const MAX_VISIBLE = 150
const SPRING_LENGTH = 120

export function mulberry32(seed: number): () => number {
  let state = seed >>> 0
  return () => {
    state = (state + 0x6d2b79f5) >>> 0
    let t = state
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

export function layoutGraph(graph: ConceptGraph, seed = 42): GraphLayout {
  const degree = new Map<number, number>()
  const idByName = new Map(graph.concepts.map((concept) => [concept.name, concept.id]))
  const edges: LayoutEdge[] = []
  for (const link of graph.links) {
    const from = idByName.get(link.from)
    const to = idByName.get(link.to)
    if (from === undefined || to === undefined) {
      continue
    }
    degree.set(from, (degree.get(from) ?? 0) + 1)
    degree.set(to, (degree.get(to) ?? 0) + 1)
    edges.push({ from, to, relation: link.relation })
  }

  let visible = graph.concepts
  if (visible.length > MAX_VISIBLE) {
    visible = [...visible]
      .sort(
        (a, b) => (degree.get(b.id) ?? 0) - (degree.get(a.id) ?? 0) || a.id - b.id,
      )
      .slice(0, MAX_VISIBLE)
    const keep = new Set(visible.map((concept) => concept.id))
    return {
      nodes: layoutNodes(visible, edges, seed),
      edges: edges.filter((edge) => keep.has(edge.from) && keep.has(edge.to)),
    }
  }
  return { nodes: layoutNodes(visible, edges, seed), edges }
}

function layoutNodes(
  concepts: ConceptGraph['concepts'],
  edges: LayoutEdge[],
  seed: number,
): LayoutNode[] {
  const rand = mulberry32(seed)
  const count = Math.max(concepts.length, 1)
  const nodes: LayoutNode[] = concepts.map((concept, index) => {
    const angle = (2 * Math.PI * index) / count
    return {
      id: concept.id,
      name: concept.name,
      x: WIDTH / 2 + Math.cos(angle) * (HEIGHT / 3) * (0.8 + rand() * 0.4),
      y: HEIGHT / 2 + Math.sin(angle) * (HEIGHT / 3) * (0.8 + rand() * 0.4),
      radius: 8 + Math.min(concept.nodes.length, 12) * 1.5,
      mastery: concept.mastery ?? null,
    }
  })
  const byId = new Map(nodes.map((node) => [node.id, node]))
  const springs: { a: LayoutNode; b: LayoutNode }[] = []
  for (const edge of edges) {
    const a = byId.get(edge.from)
    const b = byId.get(edge.to)
    if (a !== undefined && b !== undefined) {
      springs.push({ a, b })
    }
  }

  for (let step = 0; step < ITERATIONS; step += 1) {
    const cooling = 1 - step / ITERATIONS
    for (const node of nodes) {
      node.x += (rand() - 0.5) * 6 * cooling
      node.y += (rand() - 0.5) * 6 * cooling
    }
    for (let i = 0; i < nodes.length; i += 1) {
      for (let j = i + 1; j < nodes.length; j += 1) {
        const a = nodes[i]
        const b = nodes[j]
        const dx = b.x - a.x
        const dy = b.y - a.y
        const dist2 = Math.max(dx * dx + dy * dy, 64)
        const dist = Math.sqrt(dist2)
        const force = (2400 * cooling) / dist2
        a.x -= (dx / dist) * force
        a.y -= (dy / dist) * force
        b.x += (dx / dist) * force
        b.y += (dy / dist) * force
      }
    }
    for (const spring of springs) {
      const dx = spring.b.x - spring.a.x
      const dy = spring.b.y - spring.a.y
      const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1)
      const force = (dist - SPRING_LENGTH) * 0.02 * cooling
      spring.a.x += (dx / dist) * force
      spring.a.y += (dy / dist) * force
      spring.b.x -= (dx / dist) * force
      spring.b.y -= (dy / dist) * force
    }
    for (const node of nodes) {
      node.x = Math.min(Math.max(node.x, node.radius + 8), WIDTH - node.radius - 8)
      node.y = Math.min(Math.max(node.y, node.radius + 8), HEIGHT - node.radius - 8)
    }
  }
  return nodes
}

const MASTERY_COLORS: Record<string, string> = {
  strong: 'var(--as-success, #2e9e6b)',
  shaky: 'var(--as-warning, #d9a13c)',
  weak: 'var(--as-danger, #d25454)',
  unknown: 'var(--color-muted-foreground, #8a8a8a)',
}

export function ConceptGraphCanvas({
  graph,
  onSelect,
}: {
  graph: ConceptGraph
  onSelect: (conceptId: number) => void
}) {
  const { t } = useTranslation()
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const [hovered, setHovered] = useState<LayoutNode | null>(null)
  const layout = useMemo(() => layoutGraph(graph), [graph])
  const belowLg = useMediaQuery('(max-width: 1023px)')
  const ariaLabel = t('concepts.canvasAria', { count: layout.nodes.length })

  useEffect(() => {
    const canvas = canvasRef.current
    if (canvas === null) {
      return
    }
    const ctx = canvas.getContext('2d')
    if (ctx === null) {
      return
    }
    const dpr = window.devicePixelRatio || 1
    canvas.width = WIDTH * dpr
    canvas.height = HEIGHT * dpr
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, WIDTH, HEIGHT)

    ctx.strokeStyle = 'rgba(128, 128, 128, 0.35)'
    for (const edge of layout.edges) {
      const a = layout.nodes.find((node) => node.id === edge.from)
      const b = layout.nodes.find((node) => node.id === edge.to)
      if (a === undefined || b === undefined) {
        continue
      }
      ctx.beginPath()
      ctx.moveTo(a.x, a.y)
      ctx.lineTo(b.x, b.y)
      ctx.stroke()
    }
    for (const node of layout.nodes) {
      ctx.beginPath()
      ctx.fillStyle =
        node.id === hovered?.id
          ? MASTERY_COLORS.strong
          : (MASTERY_COLORS[node.mastery ?? 'unknown'] ?? MASTERY_COLORS.unknown)
      ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2)
      ctx.fill()
      ctx.fillStyle = 'rgba(0, 0, 0, 0.85)'
      ctx.font = '11px sans-serif'
      ctx.textAlign = 'center'
      ctx.fillText(node.name, node.x, node.y + node.radius + 12)
    }
  }, [layout, hovered])

  const pick = (clientX: number, clientY: number): LayoutNode | null => {
    const canvas = canvasRef.current
    if (canvas === null) {
      return null
    }
    const rect = canvas.getBoundingClientRect()
    const x = ((clientX - rect.left) / rect.width) * WIDTH
    const y = ((clientY - rect.top) / rect.height) * HEIGHT
    return (
      layout.nodes.find(
        (node) => (node.x - x) ** 2 + (node.y - y) ** 2 <= (node.radius + 4) ** 2,
      ) ?? null
    )
  }

  if (belowLg) {
    return null
  }

  const hoveredCoverage =
    hovered !== null
      ? (graph.concepts.find((entry) => entry.id === hovered.id)?.nodes.length ?? 0)
      : 0

  return (
    <div className="relative">
      <canvas
        ref={canvasRef}
        data-as="concept-graph"
        role="img"
        aria-label={ariaLabel}
        style={{ width: '100%', height: 'auto', aspectRatio: `${WIDTH} / ${HEIGHT}` }}
        className="bg-surface border-border rounded-lg border"
        onClick={(event) => {
          const node = pick(event.clientX, event.clientY)
          if (node !== null) {
            onSelect(node.id)
          }
        }}
        onPointerMove={(event) => {
          setHovered(pick(event.clientX, event.clientY))
        }}
        onPointerLeave={() => setHovered(null)}
      />
      {hovered !== null ? (
        <div className="border-border bg-surface-raised text-foreground pointer-events-none absolute left-3 top-3 rounded-md border px-2 py-1 text-xs shadow-sm">
          {t('concepts.canvasNode', { name: hovered.name, count: hoveredCoverage })}
        </div>
      ) : null}
    </div>
  )
}
