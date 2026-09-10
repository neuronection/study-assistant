import { searchScore } from '@neuronection/assistant-ui/fuzzy'

export { fuzzyScore, searchScore } from '@neuronection/assistant-ui/fuzzy'

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
    const score = searchScore(needle, text)
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
