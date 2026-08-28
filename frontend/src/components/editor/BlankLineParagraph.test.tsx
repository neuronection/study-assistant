import { EditorContent, useEditor } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import { Markdown, type MarkdownStorage } from 'tiptap-markdown'
import { act, render } from '@testing-library/react'
import { describe, expect, test } from 'vitest'

import {
  BlankLineParagraph,
  decodeMarkdownFromSerialize,
  encodeMarkdownForParse,
} from './markdownFidelity'

type HeldEditor = NonNullable<ReturnType<typeof useEditor>>

function paragraph(text?: string): Record<string, unknown> {
  return text === undefined
    ? { type: 'paragraph' }
    : { type: 'paragraph', content: [{ type: 'text', text }] }
}

function setup(): Promise<{ held: HeldEditor; markdown: () => string }> {
  let resolveReady: () => void
  const ready = new Promise<void>((resolve) => {
    resolveReady = resolve
  })
  let held: HeldEditor | null = null
  const Probe = () => {
    const editor = useEditor({
      extensions: [
        StarterKit.configure({ paragraph: false }),
        BlankLineParagraph,
        Markdown.configure({ html: false, breaks: true, linkify: false }),
      ],
      content: 'seed',
      onCreate: ({ editor: current }) => {
        held = current
        resolveReady()
      },
    })
    return <EditorContent editor={editor} />
  }
  render(<Probe />)
  return ready.then(() => ({
    held: held as HeldEditor,
    markdown: () =>
      decodeMarkdownFromSerialize(
        (held!.storage as unknown as { markdown: MarkdownStorage }).markdown.getMarkdown()
      ),
  }))
}

describe('BlankLineParagraph', () => {
  test('empty paragraph nodes serialize to blank lines and survive reparse', async () => {
    const { held, markdown } = await setup()

    await act(async () => {
      held.commands.setContent(
        [
          paragraph('a'),
          paragraph(),
          paragraph(),
          paragraph(),
          paragraph(),
          paragraph(),
          paragraph(),
          paragraph('b'),
        ] as never,
        { emitUpdate: false }
      )
    })
    expect(markdown()).toBe('a\n\n\n\n\n\n\n\nb')

    await act(async () => {
      held.commands.setContent(encodeMarkdownForParse(markdown()), {
        emitUpdate: false,
      })
    })
    expect(markdown()).toBe('a\n\n\n\n\n\n\n\nb')
  })

  test('empty paragraphs before the first and after the last text are dropped', async () => {
    const { held, markdown } = await setup()

    await act(async () => {
      held.commands.setContent(
        [paragraph(), paragraph(), paragraph('a'), paragraph(), paragraph()] as never,
        { emitUpdate: false }
      )
    })
    expect(markdown()).toBe('a')
  })

  test('a document of only empty paragraphs emits an empty string', async () => {
    const { held, markdown } = await setup()

    await act(async () => {
      held.commands.setContent([paragraph(), paragraph()] as never, {
        emitUpdate: false,
      })
    })
    expect(markdown()).toBe('')
  })

  test('single blank line between paragraphs stays a single blank line', async () => {
    const { held, markdown } = await setup()

    await act(async () => {
      held.commands.setContent(
        [paragraph('a'), paragraph(), paragraph('b')] as never,
        { emitUpdate: false }
      )
    })
    expect(markdown()).toBe('a\n\n\nb')
  })
})
