import { act, fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { Popover } from './popover'
import { useCloseFloatings } from '@/lib/ui-overlays'

function Overlay() {
  useCloseFloatings()
  return <div>overlay-body</div>
}

describe('Popover', () => {
  test('a mounted overlay closes all open popovers', () => {
    render(
      <>
        <Popover trigger={<span>gear</span>} label="Cheat sheet">
          <p>panel-body</p>
        </Popover>
      </>
    )
    fireEvent.click(screen.getByRole('button', { name: 'Cheat sheet' }))
    expect(screen.getByRole('dialog', { name: 'Cheat sheet' })).toBeInTheDocument()

    render(<Overlay />)
    expect(screen.queryByRole('dialog', { name: 'Cheat sheet' })).not.toBeInTheDocument()
  })

  test('a popover opened after the overlay keeps working', () => {
    render(
      <>
        <Overlay />
        <Popover trigger={<span>gear</span>} label="Node settings">
          <p>panel-body</p>
        </Popover>
      </>
    )
    fireEvent.click(screen.getByRole('button', { name: 'Node settings' }))
    expect(screen.getByRole('dialog', { name: 'Node settings' })).toBeInTheDocument()
  })

  test('opens on trigger click and closes on a second click', () => {
    render(
      <Popover trigger={<span>gear</span>} label="Node settings">
        <p>panel-body</p>
      </Popover>
    )
    const trigger = screen.getByRole('button', { name: 'Node settings' })
    expect(screen.queryByText('panel-body')).not.toBeInTheDocument()
    fireEvent.click(trigger)
    expect(screen.getByRole('dialog', { name: 'Node settings' })).toBeInTheDocument()
    expect(trigger).toHaveAttribute('aria-expanded', 'true')
    fireEvent.click(trigger)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  test('closes on outside pointerdown and Escape', () => {
    render(
      <Popover trigger={<span>gear</span>} label="Node settings">
        <input aria-label="Field" />
      </Popover>
    )
    fireEvent.click(screen.getByRole('button', { name: 'Node settings' }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()

    fireEvent.pointerDown(document.body)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Node settings' }))
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  test('inside clicks keep it open and the panel takes focus', () => {
    render(
      <Popover trigger={<span>gear</span>} label="Node settings">
        <input aria-label="Field" />
      </Popover>
    )
    fireEvent.click(screen.getByRole('button', { name: 'Node settings' }))
    const panel = screen.getByRole('dialog')
    expect(document.activeElement).toBe(panel)
    fireEvent.pointerDown(screen.getByRole('textbox', { name: 'Field' }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  test('align positions the panel relative to the trigger', () => {
    const rectSpy = vi
      .spyOn(HTMLElement.prototype, 'getBoundingClientRect')
      .mockReturnValue({
        top: 100,
        bottom: 140,
        left: 200,
        right: 300,
        width: 100,
        height: 40,
        x: 200,
        y: 100,
        toJSON: () => ({}),
      })
    try {
      const endView = render(
        <Popover trigger={<span>gear</span>} label="Node settings">
          <p>panel-body</p>
        </Popover>
      )
      fireEvent.click(screen.getByRole('button', { name: 'Node settings' }))
      const endPanel = screen.getByRole('dialog')
      expect(endPanel.style.left).toBe('300px')
      endView.unmount()

      const startView = render(
        <Popover trigger={<span>gear</span>} label="Node settings" align="start">
          <p>panel-body</p>
        </Popover>
      )
      fireEvent.click(screen.getByRole('button', { name: 'Node settings' }))
      expect(screen.getByRole('dialog').style.left).toBe('200px')
      startView.unmount()
    } finally {
      rectSpy.mockRestore()
    }
  })

  test('panel renders in a portal outside clipping ancestors and above overlays', () => {
    const clipping = document.createElement('div')
    clipping.style.overflow = 'hidden'
    clipping.style.width = '10px'
    document.body.append(clipping)
    const view = render(
      <Popover trigger={<span>gear</span>} label="Node settings">
        <p>panel-body</p>
      </Popover>,
      { container: clipping }
    )
    fireEvent.click(screen.getByRole('button', { name: 'Node settings' }))
    const panel = screen.getByRole('dialog')
    expect(panel.parentElement).toBe(document.body)
    expect(clipping.contains(panel)).toBe(false)
    expect(panel.className).toContain('z-[60]')
    view.unmount()
    clipping.remove()
  })

  test('panelClassName overrides the default width', () => {
    render(
      <Popover trigger={<span>gear</span>} label="Node settings" panelClassName="w-64">
        <p>panel-body</p>
      </Popover>
    )
    fireEvent.click(screen.getByRole('button', { name: 'Node settings' }))
    const className = screen.getByRole('dialog').className
    expect(className).toContain('w-64')
    expect(className).not.toContain('w-80')
  })

  test('closes when focus leaves the panel', () => {
    const outsideButton = document.createElement('button')
    outsideButton.textContent = 'elsewhere'
    document.body.append(outsideButton)
    render(
      <Popover trigger={<span>gear</span>} label="Node settings">
        <input aria-label="Field" />
      </Popover>
    )
    fireEvent.click(screen.getByRole('button', { name: 'Node settings' }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()

    const field = screen.getByRole('textbox', { name: 'Field' })
    field.focus()
    fireEvent.focusOut(field, { relatedTarget: outsideButton })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    outsideButton.remove()
  })

  test('trigger wrapper ignores clicks bubbling through content', () => {
    const onClick = vi.fn()
    render(
      <Popover trigger={<span>gear</span>} label="Node settings">
        <button type="button" onClick={onClick}>
          inner
        </button>
      </Popover>
    )
    fireEvent.click(screen.getByRole('button', { name: 'Node settings' }))
    fireEvent.click(screen.getByRole('button', { name: 'inner' }))
    expect(onClick).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  test('openOnHover opens on trigger mouse enter and closes on leave', () => {
    render(
      <Popover trigger={<span>gear</span>} label="Node settings" openOnHover>
        <p>panel-body</p>
      </Popover>
    )
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    fireEvent.mouseEnter(screen.getByRole('button', { name: 'Node settings' }))
    expect(screen.getByRole('dialog', { name: 'Node settings' })).toBeInTheDocument()
    fireEvent.mouseLeave(screen.getByRole('button', { name: 'Node settings' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  test('click still toggles when openOnHover is set', () => {
    render(
      <Popover trigger={<span>gear</span>} label="Node settings" openOnHover>
        <p>panel-body</p>
      </Popover>
    )
    const trigger = screen.getByRole('button', { name: 'Node settings' })
    fireEvent.click(trigger)
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    fireEvent.click(trigger)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  test('movable renders a drag handle and dragging moves the panel within the window', () => {
    const rectSpy = vi
      .spyOn(HTMLElement.prototype, 'getBoundingClientRect')
      .mockReturnValue({
        top: 100,
        bottom: 140,
        left: 200,
        right: 300,
        width: 100,
        height: 40,
        x: 200,
        y: 100,
        toJSON: () => ({}),
      })
    try {
      render(
        <Popover
          trigger={<span>gear</span>}
          label="Node settings"
          movable
          panelClassName="w-80"
        >
          <p>panel-body</p>
        </Popover>
      )
      fireEvent.click(screen.getByRole('button', { name: 'Node settings' }))
      const panel = screen.getByRole('dialog')
      const handle = panel.querySelector('[data-popover-drag-handle]') as HTMLElement
      expect(handle).not.toBeNull()
      fireEvent.pointerDown(handle, {
        pointerId: 1,
        clientX: 0,
        clientY: 0,
        button: 0,
      })
      fireEvent.pointerMove(handle, {
        pointerId: 1,
        clientX: 50,
        clientY: 40,
        button: 0,
      })
      fireEvent.pointerUp(handle, { pointerId: 1 })
      expect(panel.style.left).toBe('250px')
      expect(panel.style.top).toBe('140px')
    } finally {
      rectSpy.mockRestore()
    }
  })

  test('dragging the movable handle clamps the panel inside the window', () => {
    const rectSpy = vi
      .spyOn(HTMLElement.prototype, 'getBoundingClientRect')
      .mockReturnValue({
        top: 100,
        bottom: 140,
        left: 200,
        right: 300,
        width: 100,
        height: 40,
        x: 200,
        y: 100,
        toJSON: () => ({}),
      })
    try {
      render(
        <Popover
          trigger={<span>gear</span>}
          label="Node settings"
          movable
          panelClassName="w-80"
        >
          <p>panel-body</p>
        </Popover>
      )
      fireEvent.click(screen.getByRole('button', { name: 'Node settings' }))
      const panel = screen.getByRole('dialog')
      const handle = panel.querySelector('[data-popover-drag-handle]') as HTMLElement
      const maxLeft = window.innerWidth - 100 - 8
      const maxTop = window.innerHeight - 40 - 8
      fireEvent.pointerDown(handle, {
        pointerId: 1,
        clientX: 0,
        clientY: 0,
        button: 0,
      })
      fireEvent.pointerMove(handle, {
        pointerId: 1,
        clientX: 99999,
        clientY: 99999,
        button: 0,
      })
      fireEvent.pointerUp(handle, { pointerId: 1 })
      expect(panel.style.left).toBe(`${maxLeft}px`)
      expect(panel.style.top).toBe(`${maxTop}px`)
    } finally {
      rectSpy.mockRestore()
    }
  })

  test('resizable renders resize handles that change the panel size', () => {
    const rectSpy = vi
      .spyOn(HTMLElement.prototype, 'getBoundingClientRect')
      .mockReturnValue({
        top: 100,
        bottom: 140,
        left: 200,
        right: 300,
        width: 100,
        height: 40,
        x: 200,
        y: 100,
        toJSON: () => ({}),
      })
    try {
      render(
        <Popover
          trigger={<span>gear</span>}
          label="Node settings"
          resizable
          minWidth={80}
          minHeight={60}
          panelClassName="w-80"
        >
          <p>panel-body</p>
        </Popover>
      )
      fireEvent.click(screen.getByRole('button', { name: 'Node settings' }))
      const panel = screen.getByRole('dialog')
      const handles = panel.querySelectorAll('[data-resize-dir]')
      expect(handles.length).toBe(8)
      const se = panel.querySelector('[data-resize-dir="se"]') as HTMLElement
      fireEvent.pointerDown(se, {
        pointerId: 1,
        clientX: 0,
        clientY: 0,
        button: 0,
      })
      fireEvent.pointerMove(se, {
        pointerId: 1,
        clientX: 50,
        clientY: 60,
        button: 0,
      })
      fireEvent.pointerUp(se, { pointerId: 1 })
      expect(panel.style.width).toBe('150px')
      expect(panel.style.height).toBe('100px')
    } finally {
      rectSpy.mockRestore()
    }
  })

  test('resizing clamps the panel to the window bounds', () => {
    const rectSpy = vi
      .spyOn(HTMLElement.prototype, 'getBoundingClientRect')
      .mockReturnValue({
        top: 100,
        bottom: 140,
        left: 200,
        right: 300,
        width: 100,
        height: 40,
        x: 200,
        y: 100,
        toJSON: () => ({}),
      })
    try {
      render(
        <Popover
          trigger={<span>gear</span>}
          label="Node settings"
          resizable
          minWidth={80}
          minHeight={60}
          panelClassName="w-80"
        >
          <p>panel-body</p>
        </Popover>
      )
      fireEvent.click(screen.getByRole('button', { name: 'Node settings' }))
      const panel = screen.getByRole('dialog')
      const se = panel.querySelector('[data-resize-dir="se"]') as HTMLElement
      const maxWidth = window.innerWidth - 16
      const maxHeight = window.innerHeight - 16
      fireEvent.pointerDown(se, {
        pointerId: 1,
        clientX: 0,
        clientY: 0,
        button: 0,
      })
      fireEvent.pointerMove(se, {
        pointerId: 1,
        clientX: 99999,
        clientY: 99999,
        button: 0,
      })
      fireEvent.pointerUp(se, { pointerId: 1 })
      expect(panel.style.width).toBe(`${maxWidth}px`)
      expect(panel.style.height).toBe(`${maxHeight}px`)
    } finally {
      rectSpy.mockRestore()
    }
  })

  test('resizing honors minWidth and minHeight', () => {
    const rectSpy = vi
      .spyOn(HTMLElement.prototype, 'getBoundingClientRect')
      .mockReturnValue({
        top: 100,
        bottom: 140,
        left: 200,
        right: 300,
        width: 100,
        height: 40,
        x: 200,
        y: 100,
        toJSON: () => ({}),
      })
    try {
      render(
        <Popover
          trigger={<span>gear</span>}
          label="Node settings"
          resizable
          minWidth={80}
          minHeight={60}
          panelClassName="w-80"
        >
          <p>panel-body</p>
        </Popover>
      )
      fireEvent.click(screen.getByRole('button', { name: 'Node settings' }))
      const panel = screen.getByRole('dialog')
      const nw = panel.querySelector('[data-resize-dir="nw"]') as HTMLElement
      fireEvent.pointerDown(nw, {
        pointerId: 1,
        clientX: 0,
        clientY: 0,
        button: 0,
      })
      fireEvent.pointerMove(nw, {
        pointerId: 1,
        clientX: 99999,
        clientY: 99999,
        button: 0,
      })
      fireEvent.pointerUp(nw, { pointerId: 1 })
      expect(panel.style.width).toBe('80px')
      expect(panel.style.height).toBe('60px')
    } finally {
      rectSpy.mockRestore()
    }
  })

  test('a non-floatable popover renders no drag or resize handles', () => {
    render(
      <Popover trigger={<span>gear</span>} label="Node settings">
        <p>panel-body</p>
      </Popover>
    )
    fireEvent.click(screen.getByRole('button', { name: 'Node settings' }))
    const panel = screen.getByRole('dialog')
    expect(panel.querySelector('[data-popover-drag-handle]')).toBeNull()
    expect(panel.querySelector('[data-resize-dir]')).toBeNull()
  })

  test('a floatable popover clips its content wrapper instead of scrolling the panel', () => {
    render(
      <Popover
        trigger={<span>gear</span>}
        label="Node settings"
        resizable
        panelClassName="w-80"
      >
        <p>panel-body</p>
      </Popover>
    )
    fireEvent.click(screen.getByRole('button', { name: 'Node settings' }))
    const panel = screen.getByRole('dialog')
    expect(panel.className).not.toContain('overflow-y-auto')
    const wrapper = panel.querySelector('.overflow-hidden')
    expect(wrapper).not.toBeNull()
  })

  test('re-clamps the position when the panel grows so the bottom stays in the window', () => {
    const rectSpy = vi
      .spyOn(HTMLElement.prototype, 'getBoundingClientRect')
      .mockReturnValue({
        top: 100,
        bottom: 140,
        left: 200,
        right: 300,
        width: 100,
        height: 40,
        x: 200,
        y: 100,
        toJSON: () => ({}),
      })
    let resizeCallback: ResizeObserverCallback | null = null
    class MockResizeObserver {
      constructor(callback: ResizeObserverCallback) {
        resizeCallback = callback
      }
      observe(): void {}
      unobserve(): void {}
      disconnect(): void {}
    }
    vi.stubGlobal('ResizeObserver', MockResizeObserver)
    try {
      render(
        <Popover
          trigger={<span>gear</span>}
          label="Node settings"
          resizable
          panelClassName="w-80"
        >
          <p>panel-body</p>
        </Popover>
      )
      fireEvent.click(screen.getByRole('button', { name: 'Node settings' }))
      const panel = screen.getByRole('dialog')
      Object.defineProperty(panel, 'offsetHeight', {
        configurable: true,
        get: () => 700,
      })
      Object.defineProperty(panel, 'offsetWidth', {
        configurable: true,
        get: () => 100,
      })
      act(() => {
        resizeCallback?.(
          [{ target: panel, borderBoxSize: [] } as unknown as ResizeObserverEntry],
          {} as ResizeObserver
        )
      })
      const top = Number.parseFloat(panel.style.top)
      expect(top + 700).toBeLessThanOrEqual(window.innerHeight - 8)
    } finally {
      rectSpy.mockRestore()
      vi.unstubAllGlobals()
    }
  })
})
