import { useCallback, useEffect, useState, type RefObject } from 'react'

export interface SelectionCapture {
  text: string
  top: number
  left: number
}

export function useTextSelection(
  containerRef: RefObject<HTMLElement | null>
): { capture: SelectionCapture | null; clear: () => void } {
  const [capture, setCapture] = useState<SelectionCapture | null>(null)

  useEffect(() => {
    const onUp = () => {
      const container = containerRef.current
      if (container === null) {
        setCapture(null)
        return
      }
      const selection = window.getSelection()
      const text = selection?.toString().trim() ?? ''
      if (
        selection === null ||
        selection.isCollapsed ||
        text.length === 0 ||
        selection.rangeCount === 0
      ) {
        setCapture(null)
        return
      }
      const range = selection.getRangeAt(0)
      const node = range.commonAncestorContainer
      const element = node.nodeType === Node.TEXT_NODE ? node.parentElement : (node as Element)
      if (element === null || !container.contains(element)) {
        setCapture(null)
        return
      }
      let top: number
      let left: number
      if (typeof range.getBoundingClientRect === 'function') {
        const rect = range.getBoundingClientRect()
        top = rect.bottom + 6
        left = rect.left
      } else {
        const hostRect = container.getBoundingClientRect()
        top = hostRect.top + 40
        left = hostRect.left + 40
      }
      setCapture({ text, top, left })
    }
    document.addEventListener('mouseup', onUp)
    return () => document.removeEventListener('mouseup', onUp)
  }, [containerRef])

  const clear = useCallback(() => {
    window.getSelection()?.removeAllRanges()
    setCapture(null)
  }, [])

  return { capture, clear }
}
