import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { TimeLimitDialog } from './TimeLimitDialog'

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string, values?: Record<string, unknown>) =>
        values ? `${key}:${JSON.stringify(values)}` : key,
      i18n: actual.setDefaults,
    }),
  }
})

vi.mock('@/lib/ui-overlays', () => ({
  useCloseFloatings: () => {},
}))

describe('TimeLimitDialog', () => {
  test('picking a preset submits minutes as seconds', () => {
    const onConfirm = vi.fn()
    render(
      <TimeLimitDialog
        title="Time limit"
        currentSec={null}
        onConfirm={onConfirm}
        onClose={() => {}}
      />
    )
    fireEvent.click(screen.getByRole('radio', { name: /120/ }))
    fireEvent.click(screen.getByRole('button', { name: /common\.apply/ }))
    expect(onConfirm).toHaveBeenCalledWith(7200)
  })

  test('no limit submits null', () => {
    const onConfirm = vi.fn()
    render(
      <TimeLimitDialog
        title="Time limit"
        currentSec={3600}
        onConfirm={onConfirm}
        onClose={() => {}}
      />
    )
    fireEvent.click(screen.getByRole('radio', { name: /timeLimitNone/ }))
    fireEvent.click(screen.getByRole('button', { name: /common\.apply/ }))
    expect(onConfirm).toHaveBeenCalledWith(null)
  })

  test('custom minutes are accepted and converted', () => {
    const onConfirm = vi.fn()
    render(
      <TimeLimitDialog
        title="Time limit"
        currentSec={null}
        onConfirm={onConfirm}
        onClose={() => {}}
      />
    )
    fireEvent.click(screen.getByRole('radio', { name: /timeLimitCustom/ }))
    const input = screen.getByRole('spinbutton', { name: /timeLimitCustom/ })
    fireEvent.change(input, { target: { value: '25' } })
    fireEvent.click(screen.getByRole('button', { name: /common\.apply/ }))
    expect(onConfirm).toHaveBeenCalledWith(1500)
  })
})
