import { EditorContent, useEditor } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Image from '@tiptap/extension-image'
import { TableCell, TableHeader, TableRow } from '@tiptap/extension-table'
import { Markdown } from 'tiptap-markdown'
import { Fragment } from '@tiptap/pm/model'
import { NodeSelection, TextSelection } from '@tiptap/pm/state'
import { act, render } from '@testing-library/react'
import { describe, expect, test } from 'vitest'
import type { Editor as TiptapEditor } from '@tiptap/react'

import { CaMath } from './CaMath'
import { CaMermaid } from './CaMermaid'
import { MarkdownTable } from './MarkdownTable'
import {
  BlankLineParagraph,
  decodeMarkdownFromSerialize,
} from './markdownFidelity'
import {
  captureSelection,
  selectionToMarkdown,
  summarizeFragment,
  summaryTotalBlocks,
} from './selectionCapture'

type HeldEditor = NonNullable<ReturnType<typeof useEditor>>

const MERMAID_SOURCE = 'flowchart TD\n  A --> B'

interface DocLike {
  type: string
  content?: DocLike[]
  attrs?: Record<string, unknown>
  text?: string
  marks?: { type: string }[]
}

function setup(): Promise<HeldEditor> {
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
        CaMath,
        CaMermaid,
        MarkdownTable,
        TableRow,
        TableCell,
        TableHeader,
        Image,
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
  return ready.then(() => held as HeldEditor)
}

async function setDoc(held: HeldEditor, doc: DocLike): Promise<void> {
  await act(async () => {
    held.commands.setContent(doc as never, { emitUpdate: false })
  })
}

function editorMarkdown(held: TiptapEditor): string {
  const storage = held.storage as unknown as {
    markdown: { serializer: { serialize: (content: unknown) => string } }
  }
  return decodeMarkdownFromSerialize(
    storage.markdown.serializer.serialize(held.state.doc)
  )
}

function selectText(held: TiptapEditor, from: number, to: number): void {
  held.view.dispatch(
    held.state.tr.setSelection(TextSelection.create(held.state.doc, from, to))
  )
}

function selectNodeAt(held: TiptapEditor, name: string): number {
  let found = -1
  held.state.doc.forEach((child, offset) => {
    if (found === -1 && child.type.name === name) {
      found = offset
    }
  })
  expect(found).toBeGreaterThanOrEqual(0)
  held.view.dispatch(
    held.state.tr.setSelection(NodeSelection.create(held.state.doc, found))
  )
  return found
}

describe('selectionCapture', () => {
  test('a single mermaid node selection serializes byte-identically to the editor output', async () => {
    const held = await setup()
    await setDoc(held, {
      type: 'doc',
      content: [
        { type: 'paragraph', content: [{ type: 'text', text: 'before' }] },
        { type: 'caMermaid', attrs: { source: MERMAID_SOURCE } },
      ],
    })
    selectNodeAt(held, 'caMermaid')
    const capture = captureSelection(held)
    expect(capture).not.toBeNull()
    expect(capture?.markdown).toBe('```mermaid\n' + MERMAID_SOURCE + '\n```')
    expect(capture?.markdown).toBe(editorMarkdown(held).split('\n\n')[1])
    expect(capture?.summary.diagrams).toBe(1)
    expect(capture?.summary.textBlocks).toBe(0)
    expect(summaryTotalBlocks(capture!.summary)).toBe(1)
  })

  test('inline and display math selections serialize to delimiters', async () => {
    const held = await setup()
    await setDoc(held, {
      type: 'doc',
      content: [
        {
          type: 'paragraph',
          content: [
            { type: 'text', text: 'value ' },
            { type: 'caMath', attrs: { latex: '\\frac{1}{2}', display: false } },
            { type: 'caMath', attrs: { latex: '\\int_0^1', display: true } },
          ],
        },
      ],
    })
    selectText(held, 1, held.state.doc.content.size - 1)
    const capture = captureSelection(held)
    expect(capture?.markdown).toBe(
      'value $\\frac{1}{2}$$$\\int_0^1$$'
    )
    expect(capture?.markdown).toBe(editorMarkdown(held))
    expect(capture?.summary.formulas).toBe(2)
    expect(capture?.summary.textBlocks).toBe(1)
  })

  test('a text selection spanning a table serializes it to pipes with the delimiter row', async () => {
    const held = await setup()
    await setDoc(held, {
      type: 'doc',
      content: [
        { type: 'paragraph', content: [{ type: 'text', text: 'before' }] },
        {
          type: 'table',
          content: [
            {
              type: 'tableRow',
              content: [
                {
                  type: 'tableHeader',
                  content: [{ type: 'paragraph', content: [{ type: 'text', text: 'a' }] }],
                },
                {
                  type: 'tableHeader',
                  content: [{ type: 'paragraph', content: [{ type: 'text', text: 'b' }] }],
                },
              ],
            },
            {
              type: 'tableRow',
              content: [
                {
                  type: 'tableCell',
                  content: [{ type: 'paragraph', content: [{ type: 'text', text: '1' }] }],
                },
                {
                  type: 'tableCell',
                  content: [{ type: 'paragraph', content: [{ type: 'text', text: '2' }] }],
                },
              ],
            },
          ],
        },
        { type: 'paragraph', content: [{ type: 'text', text: 'after' }] },
      ],
    })
    selectText(held, 1, held.state.doc.content.size - 1)
    const capture = captureSelection(held)
    expect(capture?.markdown).toBe(
      'before\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n\nafter'
    )
    expect(capture?.summary.tables).toBe(1)
    expect(capture?.summary.textBlocks).toBe(2)
  })

  test('a mixed text+block range captures every kind and a correct summary', async () => {
    const held = await setup()
    await setDoc(held, {
      type: 'doc',
      content: [
        { type: 'paragraph', content: [{ type: 'text', text: 'first' }] },
        { type: 'heading', attrs: { level: 2 }, content: [{ type: 'text', text: 'head' }] },
        { type: 'caMermaid', attrs: { source: MERMAID_SOURCE } },
        {
          type: 'bulletList',
          content: [
            { type: 'listItem', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'item' }] }] },
          ],
        },
        { type: 'paragraph', content: [{ type: 'text', text: 'last' }] },
      ],
    })
    selectText(held, 1, held.state.doc.content.size - 1)
    const capture = captureSelection(held)
    expect(capture).not.toBeNull()
    expect(capture?.markdown).toContain('first')
    expect(capture?.markdown).toContain('## head')
    expect(capture?.markdown).toContain('```mermaid')
    expect(capture?.markdown).toContain('- item')
    expect(capture?.markdown).toContain('last')
    const summary = capture?.summary
    expect(summary?.textBlocks).toBe(4)
    expect(summary?.diagrams).toBe(1)
    expect(summaryTotalBlocks(summary!)).toBe(5)
    expect(summary?.lines).toBe(capture?.markdown.split('\n').length)
    expect(summary?.preview).toBe(capture?.markdown)
  })

  test('a collapsed selection refuses capture so the helper falls back to the whole note', async () => {
    const held = await setup()
    await setDoc(held, {
      type: 'doc',
      content: [{ type: 'paragraph', content: [{ type: 'text', text: 'only' }] }],
    })
    selectText(held, 1, 1)
    expect(captureSelection(held)).toBeNull()
  })

  test('selectionToMarkdown never mutates the document and trims trailing newlines', async () => {
    const held = await setup()
    await setDoc(held, {
      type: 'doc',
      content: [
        { type: 'paragraph', content: [{ type: 'text', text: 'one' }] },
        { type: 'paragraph', content: [{ type: 'text', text: 'two' }] },
      ],
    })
    const before = held.state.doc.toJSON()
    const markdown = selectionToMarkdown(held, 0, held.state.doc.content.size)
    expect(markdown).toBe('one\n\ntwo')
    expect(held.state.doc.toJSON()).toEqual(before)
  })

  test('summarizeFragment counts nested containers and atoms', async () => {
    const held = await setup()
    const { schema } = held.state
    const paragraph = schema.nodes.paragraph.create(null, schema.text('hi'))
    const listItem = schema.nodes.listItem.create(null, paragraph)
    const bulletList = schema.nodes.bulletList.create(null, listItem)
    const quote = schema.nodes.blockquote.create(null, paragraph)
    const fragment = Fragment.fromArray([
      schema.nodes.caMermaid.create({ source: MERMAID_SOURCE }),
      schema.nodes.caMath.create({ latex: 'x', display: false }),
      schema.nodes.codeBlock.create(null, schema.text('code')),
      schema.nodes.image.create({ src: 'ca-drawing://1', alt: '' }),
      paragraph,
      bulletList,
      quote,
    ])
    const summary = summarizeFragment(fragment, 'a\nb\nc')
    expect(summary.diagrams).toBe(1)
    expect(summary.formulas).toBe(1)
    expect(summary.codeBlocks).toBe(1)
    expect(summary.imagesDrawings).toBe(1)
    expect(summary.textBlocks).toBe(3)
    expect(summary.lines).toBe(3)
    expect(summary.preview).toBe('a\nb\nc')
  })

  test('the preview is capped at 280 characters', async () => {
    const held = await setup()
    const { schema } = held.state
    const paragraph = schema.nodes.paragraph.create(null, schema.text('x'))
    const summary = summarizeFragment(
      Fragment.fromArray([paragraph, paragraph]),
      'y'.repeat(400)
    )
    expect(summary.preview).toHaveLength(280)
    expect(summary.lines).toBe(1)
  })

  test('a heading+list+blockquote mix captures faithful markdown and counts', async () => {
    const held = await setup()
    await setDoc(held, {
      type: 'doc',
      content: [
        { type: 'heading', attrs: { level: 3 }, content: [{ type: 'text', text: 'Title' }] },
        {
          type: 'orderedList',
          content: [
            { type: 'listItem', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'step one' }] }] },
            { type: 'listItem', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'step two' }] }] },
          ],
        },
        {
          type: 'blockquote',
          content: [{ type: 'paragraph', content: [{ type: 'text', text: 'quoted note' }] }],
        },
      ],
    })
    selectText(held, 1, held.state.doc.content.size - 1)
    const capture = captureSelection(held)
    expect(capture?.markdown).toBe(
      '### Title\n\n1. step one\n2. step two\n\n> quoted note'
    )
    expect(capture?.summary.textBlocks).toBe(4)
    expect(capture?.summary.diagrams).toBe(0)
  })

  test('a drawing reference inside the selection is counted and serialized as an image', async () => {
    const held = await setup()
    await setDoc(held, {
      type: 'doc',
      content: [
        { type: 'paragraph', content: [{ type: 'text', text: 'look' }] },
        {
          type: 'paragraph',
          content: [
            {
              type: 'image',
              attrs: { src: 'ca-drawing://7', alt: 'handwritten drawing' },
            },
          ],
        },
      ],
    })
    selectText(held, 1, held.state.doc.content.size - 1)
    const capture = captureSelection(held)
    expect(capture?.markdown).toContain('![handwritten drawing](ca-drawing://7)')
    expect(capture?.summary.imagesDrawings).toBe(1)
    expect(capture?.summary.textBlocks).toBe(2)
  })

  test('inline math wrapped in code spans stays literal in the capture', async () => {
    const held = await setup()
    await setDoc(held, {
      type: 'doc',
      content: [
        {
          type: 'paragraph',
          content: [
            { type: 'text', text: 'run ' },
            {
              type: 'text',
              marks: [{ type: 'code' }],
              text: '$\\alpha$ stays raw',
            },
            { type: 'text', text: ' now' },
          ],
        },
      ],
    })
    selectText(held, 1, held.state.doc.content.size - 1)
    const capture = captureSelection(held)
    expect(capture?.markdown).toBe('run `$\\alpha$ stays raw` now')
    expect(capture?.summary.formulas).toBe(0)
    expect(capture?.summary.textBlocks).toBe(1)
  })

  test('a whole-document selection matches the editor serialize output byte-for-byte', async () => {
    const held = await setup()
    await setDoc(held, {
      type: 'doc',
      content: [
        { type: 'paragraph', content: [{ type: 'text', text: 'intro' }] },
        { type: 'caMermaid', attrs: { source: MERMAID_SOURCE } },
        {
          type: 'paragraph',
          content: [
            { type: 'text', text: 'math ' },
            { type: 'caMath', attrs: { latex: '\\alpha', display: false } },
          ],
        },
      ],
    })
    selectText(held, 1, held.state.doc.content.size - 1)
    const capture = captureSelection(held)
    expect(capture?.markdown).toBe(editorMarkdown(held))
  })
})
