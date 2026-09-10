import { act, fireEvent, render } from '@testing-library/react'
import { useRef } from 'react'
import { describe, expect, test } from 'vitest'

import { useTextSelection } from './useTextSelection'

function Probe({
  onCapture,
}: {
  onCapture: (value: { text: string; top: number; left: number } | null) => void
}) {
  const ref = useRef<HTMLDivElement>(null)
  const { capture, clear } = useTextSelection(ref)
  onCapture(capture)
  return (
    <div>
      <div ref={ref} data-testid="inside">
        <p data-testid="line">selectable line</p>
      </div>
      <p data-testid="outside">outside text</p>
      <button type="button" data-testid="clear-probe" onClick={clear}>
        clear-probe
      </button>
    </div>
  )
}

function selectElement(testId: string) {
  const target = screen_get(testId)
  const range = document.createRange()
  range.selectNodeContents(target)
  const selection = window.getSelection()
  selection?.removeAllRanges()
  selection?.addRange(range)
}

function screen_get(testId: string): HTMLElement {
  const element = document.querySelector(`[data-testid="${testId}"]`)
  if (element === null) {
    throw new Error(`missing ${testId}`)
  }
  return element as HTMLElement
}

describe('useTextSelection (plan 61-D)', () => {
  test('captures a selection inside the container on mouseup', () => {
    let captured: { text: string } | null = null
    render(<Probe onCapture={(value) => (captured = value)} />)
    expect(captured).toBeNull()
    selectElement('line')
    fireEvent.mouseUp(screen_get('inside'))
    expect(captured).not.toBeNull()
    expect(captured!.text).toBe('selectable line')
  })

  test('ignores selections outside the container', () => {
    let captured: { text: string } | null = null
    render(<Probe onCapture={(value) => (captured = value)} />)
    selectElement('outside')
    fireEvent.mouseUp(document.body)
    expect(captured).toBeNull()
  })

  test('collapsed selections capture nothing and clear resets', () => {
    let captured: { text: string } | null = null
    render(<Probe onCapture={(value) => (captured = value)} />)
    window.getSelection()?.removeAllRanges()
    fireEvent.mouseUp(screen_get('inside'))
    expect(captured).toBeNull()

    selectElement('line')
    fireEvent.mouseUp(screen_get('inside'))
    expect(captured).not.toBeNull()
    act(() => {
      fireEvent.click(screen_get('clear-probe'))
    })
    expect(captured).toBeNull()
    expect(window.getSelection()?.rangeCount ?? 0).toBe(0)
  })
})
