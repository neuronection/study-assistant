import '@testing-library/jest-dom/vitest'

import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

import { initI18n } from '@/lib/i18n'

class ResizeObserverStub implements ResizeObserver {
  private readonly callback: ResizeObserverCallback

  constructor(callback: ResizeObserverCallback) {
    this.callback = callback
  }

  observe(target: Element): void {
    const box = { inlineSize: 800, blockSize: 600 } as ResizeObserverSize
    const entry = {
      target,
      borderBoxSize: [box],
    } as unknown as ResizeObserverEntry
    this.callback([entry], this as unknown as ResizeObserver)
  }

  unobserve(): void {}

  disconnect(): void {}
}

if (typeof globalThis.ResizeObserver === 'undefined') {
  globalThis.ResizeObserver = ResizeObserverStub
}

if (typeof Element.prototype.scrollIntoView !== 'function') {
  Element.prototype.scrollIntoView = () => {}
}

const clientRects = () => [new DOMRect(0, 0, 100, 20)] as unknown as DOMRectList
Element.prototype.getClientRects = clientRects
Element.prototype.getBoundingClientRect = () => new DOMRect(0, 0, 100, 20)
;(Text.prototype as unknown as { getClientRects: () => DOMRectList }).getClientRects =
  clientRects
;(Range.prototype as unknown as { getClientRects: () => DOMRectList }).getClientRects =
  clientRects
;(Range.prototype as unknown as { getBoundingClientRect: () => DOMRect }).getBoundingClientRect =
  () => new DOMRect(0, 0, 100, 20)

if (typeof document.elementFromPoint !== 'function') {
  Object.defineProperty(document, 'elementFromPoint', {
    configurable: true,
    value: () => document.querySelector('.ProseMirror') ?? document.body,
  })
}

void initI18n()

afterEach(() => {
  cleanup()
})
