const SEPARATORS = new Set(['-', '_', '.', '/', ' ', ':', '@'])

const BOUNDARY_START = 8
const BOUNDARY_SEPARATOR = 6
const CONSECUTIVE_STEP = 4
const EXACT_MATCH = 10

export function fuzzyScore(query: string, target: string): number | null {
  if (query === '') {
    return 0
  }
  const q = query.toLowerCase()
  const t = target.toLowerCase()
  if (q === t) {
    return EXACT_MATCH + BOUNDARY_START + q.length * (1 + CONSECUTIVE_STEP)
  }
  let score = 0
  let qi = 0
  let consecutive = 0
  let prevIndex = -2
  for (let ti = 0; ti < t.length && qi < q.length; ti += 1) {
    if (t[ti] !== q[qi]) {
      continue
    }
    let bonus = 0
    if (ti === 0) {
      bonus += BOUNDARY_START
    } else if (SEPARATORS.has(t[ti - 1])) {
      bonus += BOUNDARY_SEPARATOR
    }
    if (ti === prevIndex + 1) {
      consecutive += 1
      bonus += CONSECUTIVE_STEP * consecutive
    } else {
      consecutive = 0
    }
    score += 1 + bonus
    prevIndex = ti
    qi += 1
  }
  if (qi < q.length) {
    return null
  }
  return score
}

export function fuzzyFilter<T>(
  items: T[],
  query: string,
  getText: (item: T) => string
): T[] {
  const needle = query.trim()
  if (!needle) {
    return items
  }
  const scored = items.flatMap((item) => {
    const text = getText(item)
    const score = fuzzyScore(needle, text)
    if (score === null) {
      return []
    }
    return [{ item, score, text }]
  })
  scored.sort(
    (a, b) =>
      b.score - a.score || a.text.length - b.text.length || a.text.localeCompare(b.text)
  )
  return scored.map((entry) => entry.item)
}
