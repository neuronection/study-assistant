export type JsonPatchOp =
  | { op: 'add' | 'replace'; path: string; value: unknown }
  | { op: 'remove'; path: string }

function escapePointer(segment: string): string {
  return segment.replace(/~/g, '~0').replace(/\//g, '~1')
}

export function diffState(
  prev: Record<string, unknown>,
  next: Record<string, unknown>,
): JsonPatchOp[] {
  const ops: JsonPatchOp[] = []
  const keys = new Set([...Object.keys(prev), ...Object.keys(next)])
  for (const key of keys) {
    const path = `/${escapePointer(key)}`
    const hasPrev = Object.prototype.hasOwnProperty.call(prev, key)
    const hasNext = Object.prototype.hasOwnProperty.call(next, key)
    if (hasNext && !hasPrev) {
      ops.push({ op: 'add', path, value: next[key] })
    } else if (hasPrev && !hasNext) {
      ops.push({ op: 'remove', path })
    } else if (hasPrev && hasNext && !Object.is(prev[key], next[key])) {
      ops.push({ op: 'replace', path, value: next[key] })
    }
  }
  return ops
}
