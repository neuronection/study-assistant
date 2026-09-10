import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import {
  CodeAnswer,
  codeResponseComplete,
  isCodeInput,
  type CodeQuestionInput,
} from './CodeAnswer'
import type { CodeRunPayload } from '@/lib/pyodideRunner'

vi.mock('@/lib/pyodideRunner', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/pyodideRunner')>()
  return {
    ...actual,
    runCodeTests: vi.fn(),
  }
})

const INPUT: CodeQuestionInput = {
  starter_code: 'def is_palindrome(s):\n    ...',
  tests: [
    { call: "is_palindrome('abba')", expected: true },
    { call: "is_palindrome('abc')", expected: false },
  ],
}

const PAYLOAD: CodeRunPayload = {
  code: 'def is_palindrome(s):\n    return s == s[::-1]',
  results: [
    { call: "is_palindrome('abba')", passed: true, output: 'true' },
    { call: "is_palindrome('abc')", passed: false, output: 'true' },
  ],
}

describe('CodeAnswer', () => {
  test('renders starter code and test cases before running', () => {
    render(<CodeAnswer input={INPUT} response={null} onChange={vi.fn()} />)
    const editor = screen.getByLabelText('Your code') as HTMLTextAreaElement
    expect(editor.value).toBe(INPUT.starter_code)
    expect(screen.getByText(/Run your code against the visible test cases/)).toBeInTheDocument()
  })

  test('run submits the payload and shows per-case verdicts', async () => {
    const onChange = vi.fn()
    render(
      <CodeAnswer
        input={INPUT}
        response={null}
        onChange={onChange}
        onRun={vi.fn().mockResolvedValue(PAYLOAD)}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /run tests/i }))
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(PAYLOAD))
  })

  test('completed run shows the pass counter and per-case badges', () => {
    render(<CodeAnswer input={INPUT} response={PAYLOAD} onChange={vi.fn()} />)
    expect(screen.getByText('1/2 passing')).toBeInTheDocument()
    expect(screen.getAllByText(/pass|fail/).length).toBeGreaterThan(2)
    expect(screen.getByText(/got:/)).toBeInTheDocument()
  })

  test('helpers', () => {
    expect(isCodeInput({ widget: 'code', tests: [] })).toBe(true)
    expect(isCodeInput({ widget: 'math' })).toBe(false)
    expect(codeResponseComplete(null, INPUT)).toBe(false)
    expect(codeResponseComplete({ code: 'x', results: [] }, INPUT)).toBe(false)
    expect(codeResponseComplete(PAYLOAD, INPUT)).toBe(true)
  })
})
