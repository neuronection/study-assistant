import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { NameEditor, normalizeName } from './NameEditor'

describe('NameEditor', () => {
  test('Enter submits the form; Shift+Enter inserts a newline', () => {
    const onSubmit = vi.fn()
    const onChange = vi.fn()
    render(
      <form onSubmit={onSubmit}>
        <NameEditor value="Lectures" onChange={onChange} onCancel={() => {}} ariaLabel="Rename" />
      </form>
    )
    const editor = screen.getByLabelText('Rename')
    expect(editor.tagName).toBe('TEXTAREA')

    fireEvent.keyDown(editor, { key: 'Enter', shiftKey: true })
    expect(onSubmit).not.toHaveBeenCalled()

    fireEvent.keyDown(editor, { key: 'Enter' })
    expect(onSubmit).toHaveBeenCalledTimes(1)
  })

  test('Escape cancels without submitting', () => {
    const onCancel = vi.fn()
    const onSubmit = vi.fn()
    render(
      <form onSubmit={onSubmit}>
        <NameEditor value="Lectures" onChange={() => {}} onCancel={onCancel} ariaLabel="Rename" />
      </form>
    )
    fireEvent.keyDown(screen.getByLabelText('Rename'), { key: 'Escape' })
    expect(onCancel).toHaveBeenCalledTimes(1)
    expect(onSubmit).not.toHaveBeenCalled()
  })

  test('grows to fit multiline drafts', () => {
    const { rerender } = render(
      <NameEditor value="start" onChange={() => {}} onCancel={() => {}} ariaLabel="Rename" />
    )
    const editor = screen.getByLabelText('Rename') as HTMLTextAreaElement
    Object.defineProperty(editor, 'scrollHeight', {
      configurable: true,
      get: () => editor.value.split('\n').length * 20,
    })

    rerender(
      <NameEditor value="one" onChange={() => {}} onCancel={() => {}} ariaLabel="Rename" />
    )
    expect(editor.style.height).toBe('20px')

    rerender(
      <NameEditor
        value={'one\ntwo\nthree'}
        onChange={() => {}}
        onCancel={() => {}}
        ariaLabel="Rename"
      />
    )
    expect(editor.style.height).toBe('60px')
  })
})

describe('normalizeName', () => {
  test('collapses newlines into single spaces and trims', () => {
    expect(normalizeName('Lecture\n  Notes\n\n Week 1 ')).toBe('Lecture Notes Week 1')
  })

  test('keeps interior spacing on one line intact', () => {
    expect(normalizeName('Lecture  Notes')).toBe('Lecture  Notes')
  })

  test('newline-only drafts normalize to empty', () => {
    expect(normalizeName('\n \n')).toBe('')
  })
})
