import type { Fragment } from '@tiptap/pm/model'
import type { Editor } from '@tiptap/react'

import { selectedRange } from './insertMarkdown'
import { decodeMarkdownFromSerialize } from './markdownFidelity'

const PREVIEW_CAP = 280

export interface SelectionSummary {
  diagrams: number
  formulas: number
  codeBlocks: number
  tables: number
  imagesDrawings: number
  textBlocks: number
  lines: number
  preview: string
}

export interface CapturedSelection {
  from: number
  to: number
  markdown: string
  summary: SelectionSummary
}

interface MarkdownSerializerStorage {
  markdown: { serializer: { serialize: (content: unknown) => string } }
}

const ATOM_KINDS: Record<string, keyof Omit<SelectionSummary, 'lines' | 'preview'>> = {
  caMermaid: 'diagrams',
  caMath: 'formulas',
  codeBlock: 'codeBlocks',
  table: 'tables',
  image: 'imagesDrawings',
}

const CONTAINER_NAMES = new Set(['blockquote', 'bulletList', 'orderedList', 'listItem'])

export function summarizeFragment(
  fragment: Fragment,
  markdown = ''
): SelectionSummary {
  const summary: SelectionSummary = {
    diagrams: 0,
    formulas: 0,
    codeBlocks: 0,
    tables: 0,
    imagesDrawings: 0,
    textBlocks: 0,
    lines: 0,
    preview: '',
  }
  fragment.forEach((node) => {
    if (node.type.name === 'paragraph' || node.type.name === 'heading') {
      if (node.childCount === 0) {
        return
      }
      summary.textBlocks += 1
      node.content.forEach((child) => {
        if (child.type.name === 'caMath') {
          summary.formulas += 1
        } else if (child.type.name === 'image') {
          summary.imagesDrawings += 1
        }
      })
      return
    }
    const kind = ATOM_KINDS[node.type.name]
    if (kind !== undefined) {
      summary[kind] += 1
      return
    }
    if (CONTAINER_NAMES.has(node.type.name)) {
      const nested = summarizeFragment(node.content)
      summary.diagrams += nested.diagrams
      summary.formulas += nested.formulas
      summary.codeBlocks += nested.codeBlocks
      summary.tables += nested.tables
      summary.imagesDrawings += nested.imagesDrawings
      summary.textBlocks += nested.textBlocks
    }
  })
  if (markdown !== '') {
    summary.lines = markdown.split('\n').length
    summary.preview =
      markdown.length > PREVIEW_CAP ? markdown.slice(0, PREVIEW_CAP) : markdown
  }
  return summary
}

export function selectionToMarkdown(
  editor: Editor,
  from: number,
  to: number
): string {
  const { doc, schema } = editor.state
  const start = Math.max(0, Math.min(from, to))
  const end = Math.min(doc.content.size, Math.max(from, to))
  const cut = doc.cut(start, end)
  const standalone = schema.topNodeType.create(null, cut.content)
  const storage = editor.storage as unknown as MarkdownSerializerStorage
  return decodeMarkdownFromSerialize(
    storage.markdown.serializer.serialize(standalone)
  ).replace(/\n+$/, '')
}

export function captureSelection(editor: Editor): CapturedSelection | null {
  const { from, to } = selectedRange(editor)
  if (from >= to) {
    return null
  }
  const markdown = selectionToMarkdown(editor, from, to)
  if (!markdown.trim()) {
    return null
  }
  const { doc } = editor.state
  const summary = summarizeFragment(
    doc.cut(from, Math.min(to, doc.content.size)).content,
    markdown
  )
  return { from, to, markdown, summary }
}

export function summaryTotalBlocks(summary: SelectionSummary): number {
  return (
    summary.diagrams +
    summary.formulas +
    summary.codeBlocks +
    summary.tables +
    summary.imagesDrawings +
    summary.textBlocks
  )
}
