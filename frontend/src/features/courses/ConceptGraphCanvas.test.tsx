import { describe, expect, test } from 'vitest'

import { layoutGraph, mulberry32, type GraphLayout } from './ConceptGraphCanvas'
import type { ConceptGraph } from '@/lib/api'

function graph(count: number, links: ConceptGraph['links'] = []): ConceptGraph {
  return {
    concepts: Array.from({ length: count }, (_, index) => ({
      id: index + 1,
      name: `concept-${index + 1}`,
      description: null,
      aliases: [],
      nodes:
        index % 3 === 0
          ? [{ node_id: 1, node_title: 'Ch' }]
          : [],
      mastery: (['strong', 'shaky', 'weak', null] as const)[index % 4],
    })),
    links,
  }
}

describe('mulberry32', () => {
  test('is deterministic for a seed', () => {
    const a = mulberry32(42)
    const b = mulberry32(42)
    const seqA = [a(), a(), a()]
    const seqB = [b(), b(), b()]
    expect(seqA).toEqual(seqB)
    expect(new Set(seqA).size).toBe(3)
  })
})

describe('layoutGraph', () => {
  test('produces identical layouts for identical input and seed', () => {
    const data = graph(6, [
      { from: 'concept-1', to: 'concept-2', relation: 'prereq-of' },
      { from: 'concept-2', to: 'concept-3', relation: 'related-to' },
    ])
    const first: GraphLayout = layoutGraph(data, 7)
    const second: GraphLayout = layoutGraph(data, 7)
    expect(first.nodes.map((node) => [node.id, node.x, node.y])).toEqual(
      second.nodes.map((node) => [node.id, node.x, node.y]),
    )
    expect(first.edges).toEqual([
      { from: 1, to: 2, relation: 'prereq-of' },
      { from: 2, to: 3, relation: 'related-to' },
    ])
  })

  test('keeps nodes inside the canvas bounds', () => {
    const layout = layoutGraph(graph(30), 3)
    for (const node of layout.nodes) {
      expect(node.x).toBeGreaterThanOrEqual(0)
      expect(node.x).toBeLessThanOrEqual(900)
      expect(node.y).toBeGreaterThanOrEqual(0)
      expect(node.y).toBeLessThanOrEqual(560)
    }
  })

  test('drops mastery-free nodes into the unknown bucket without breaking layout', () => {
    const layout = layoutGraph(graph(5), 1)
    const unknown = layout.nodes.filter((node) => node.mastery === null)
    expect(unknown.length).toBeGreaterThan(0)
    for (const node of unknown) {
      expect(node.radius).toBeGreaterThan(0)
    }
  })

  test('declutters beyond 150 concepts to the top-K by degree', () => {
    const links: ConceptGraph['links'] = []
    for (let i = 2; i <= 60; i += 1) {
      links.push({ from: 'concept-1', to: `concept-${i}`, relation: 'related-to' })
    }
    const data = graph(200, links)
    const layout = layoutGraph(data, 5)
    expect(layout.nodes.length).toBe(150)
    expect(layout.nodes.some((node) => node.id === 1)).toBe(true)
    expect(layout.edges.every((edge) => edge.from === 1)).toBe(true)
  })
})
