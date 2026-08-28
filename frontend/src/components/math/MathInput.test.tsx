import { render, waitFor } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { MathInput } from './MathInput'

describe('MathInput', () => {
  test('dispatched input events call onChange', async () => {
    const onChange = vi.fn()
    const { container } = render(<MathInput value="" onChange={onChange} />)
    const field = (await waitFor(() => {
      const element = container.querySelector('math-field')
      expect(element).not.toBeNull()
      return element!
    })) as HTMLElement & { value: string }
    field.value = '2x'
    field.dispatchEvent(new Event('input', { bubbles: true }))
    expect(onChange).toHaveBeenCalledWith('2x')
  })
})
