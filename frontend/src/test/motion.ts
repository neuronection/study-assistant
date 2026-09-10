import { cleanup, render } from '@testing-library/react'
import type { RenderResult } from '@testing-library/react'
import type { ReactNode } from 'react'
import { expect } from 'vitest'

export const motionState = { reduced: false }

function stripDynamicAttributes(html: string): string {
  return html.replace(/ style="[^"]*"/g, '').replace(/ data-projection-id="[^"]*"/g, '')
}

export async function rendersIdenticallyUnderReducedMotion(
  renderUi: () => ReactNode,
  settle?: (result: RenderResult) => Promise<unknown>,
): Promise<void> {
  motionState.reduced = false
  const full = render(renderUi())
  await settle?.(full)
  const fullHtml = stripDynamicAttributes(full.container.innerHTML)
  cleanup()
  motionState.reduced = true
  const reduced = render(renderUi())
  await settle?.(reduced)
  const reducedHtml = stripDynamicAttributes(reduced.container.innerHTML)
  cleanup()
  motionState.reduced = false
  expect(reducedHtml).toBe(fullHtml)
}
