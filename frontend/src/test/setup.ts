import '@testing-library/jest-dom/vitest'

import { cleanup, configure } from '@testing-library/react'
import i18next from 'i18next'
import { afterEach } from 'vitest'

import de from '@/locales/de.json'
import el from '@/locales/el.json'
import { initI18n } from '@/lib/i18n'

configure({ asyncUtilTimeout: 20_000 })

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

await initI18n()
i18next.addResourceBundle('de', 'translation', de, true, true)
i18next.addResourceBundle('el', 'translation', el, true, true)

afterEach(() => {
  cleanup()
})
