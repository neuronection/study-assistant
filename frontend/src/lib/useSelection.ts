import { useCallback, useMemo, useRef, useState } from 'react'

export interface SelectionModifierEvent {
  ctrlKey: boolean
  metaKey: boolean
  shiftKey: boolean
  button?: number
}

export function isModifierEvent(event: SelectionModifierEvent): boolean {
  return event.ctrlKey || event.metaKey || event.shiftKey
}

export function isKeyboardClick(event: { detail: number }): boolean {
  return event.detail === 0
}

export function nextSelection(
  current: ReadonlySet<string>,
  order: readonly string[],
  anchor: string | null,
  id: string,
  event: SelectionModifierEvent
): { selected: Set<string>; anchor: string | null } {
  if (event.ctrlKey || event.metaKey) {
    const selected = new Set(current)
    if (selected.has(id)) {
      selected.delete(id)
    } else {
      selected.add(id)
    }
    return { selected, anchor: id }
  }
  if (event.shiftKey && anchor !== null) {
    const anchorIndex = order.indexOf(anchor)
    const idIndex = order.indexOf(id)
    if (anchorIndex === -1 || idIndex === -1) {
      return { selected: new Set([id]), anchor: id }
    }
    const [from, to] =
      anchorIndex <= idIndex ? [anchorIndex, idIndex] : [idIndex, anchorIndex]
    const selected = new Set(order.slice(from, to + 1))
    return { selected, anchor }
  }
  if (current.has(id)) {
    return { selected: new Set(current), anchor: id }
  }
  return { selected: new Set([id]), anchor: id }
}

export function useSelection(order: readonly string[]) {
  const [selected, setSelected] = useState<Set<string>>(() => new Set())
  const anchorRef = useRef<string | null>(null)
  const orderRef = useRef(order)
  orderRef.current = order

  const pointerDown = useCallback(
    (id: string, event: SelectionModifierEvent) => {
      if (event.button !== undefined && event.button !== 0) {
        return
      }
      setSelected((current) => {
        const result = nextSelection(
          current,
          orderRef.current,
          anchorRef.current,
          id,
          event
        )
        anchorRef.current = result.anchor
        return result.selected
      })
    },
    []
  )

  const clear = useCallback(() => {
    anchorRef.current = null
    setSelected(new Set())
  }, [])

  const set = useCallback((ids: Iterable<string>) => {
    setSelected(new Set(ids))
  }, [])

  const union = useCallback((ids: Iterable<string>) => {
    setSelected((current) => {
      const merged = new Set(current)
      for (const id of ids) {
        merged.add(id)
      }
      return merged
    })
  }, [])

  const value = useMemo(() => ({ selected }), [selected])

  return { selected: value.selected, pointerDown, clear, set, union }
}
