import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

const copyText = vi.fn<(value: string) => Promise<boolean>>(async () => true)

vi.mock('@/lib/clipboard', () => ({
  copyText: (value: string) => copyText(value),
}))

import { BlockActions } from './BlockActions'
import type { Block } from './types'

function setup(block: Block) {
  return render(
    <div className="group relative">
      <BlockActions block={block} />
    </div>
  )
}

describe('BlockActions', () => {
  test('renders nothing for non-copyable blocks', () => {
    setup({ type: 'mention', ref: 'N1', kind: 'note', id: 1, title: 'Note' })
    expect(screen.queryByRole('button', { name: 'Copy options' })).toBeNull()
  })

  test('opens the menu from the trigger and copies LaTeX', async () => {
    setup({ type: 'math', latex: 'e^x' })
    fireEvent.pointerDown(screen.getByRole('button', { name: 'Copy options' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Copy LaTeX' }))
    await waitFor(() => expect(copyText).toHaveBeenCalledWith('e^x'))
  })

  test('offers display math as $$-wrapped markdown', async () => {
    setup({ type: 'math', latex: 'e^x', display: true })
    fireEvent.pointerDown(screen.getByRole('button', { name: 'Copy options' }))
    const mdItem = await screen.findByRole('menuitem', { name: 'Copy as Markdown' })
    fireEvent.click(mdItem)
    await waitFor(() => expect(copyText).toHaveBeenCalledWith('$$e^x$$'))
  })

  test('code blocks expose the fenced copy alongside the direct button', async () => {
    setup({ type: 'code', lang: 'python', code: 'print(1)' })
    fireEvent.pointerDown(screen.getByRole('button', { name: 'Copy options' }))
    const fenced = await screen.findByRole('menuitem', { name: 'Copy as fenced block' })
    fireEvent.click(fenced)
    await waitFor(() => expect(copyText).toHaveBeenCalledWith('```python\nprint(1)\n```'))
  })
})
