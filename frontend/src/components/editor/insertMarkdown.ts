import { createNodeFromContent } from '@tiptap/core'
import type { Editor } from '@tiptap/react'

export type InsertMarkdownMode = 'replace-selection' | 'at-cursor' | 'after-block'

export interface SelectionRange {
  from: number
  to: number
}

interface MarkdownStorageLike {
  parser: {
    parse: (markdown: string, options?: { inline?: boolean }) => string
  }
}

function selectionFromDOM(editor: Editor): SelectionRange | null {
  const selection = editor.view.dom.ownerDocument.getSelection()
  if (selection === null || selection.isCollapsed) {
    return null
  }
  const anchorNode = selection.anchorNode
  const focusNode = selection.focusNode
  if (
    anchorNode === null ||
    focusNode === null ||
    !editor.view.dom.contains(anchorNode) ||
    !editor.view.dom.contains(focusNode)
  ) {
    return null
  }
  try {
    const anchor = editor.view.posAtDOM(anchorNode, selection.anchorOffset)
    const focus = editor.view.posAtDOM(focusNode, selection.focusOffset)
    if (anchor < 0 || focus < 0) {
      return null
    }
    return { from: Math.min(anchor, focus), to: Math.max(anchor, focus) }
  } catch {
    return null
  }
}

export function textBetween(
  editor: Editor,
  from: number,
  to: number,
  separator = '\n'
): string {
  const start = Math.max(1, Math.min(from, to))
  const end = Math.min(editor.state.doc.content.size, Math.max(from, to))
  return start >= end ? '' : editor.state.doc.textBetween(start, end, separator)
}

export function selectedRange(editor: Editor): SelectionRange {
  const { from, to } = editor.state.selection
  if (from !== to) {
    return { from, to }
  }
  return selectionFromDOM(editor) ?? { from, to }
}

export function hasSelection(editor: Editor): boolean {
  const { from, to } = selectedRange(editor)
  return from !== to
}

export function selectedText(editor: Editor): string {
  const { from, to } = selectedRange(editor)
  return textBetween(editor, from, to)
}

export function surroundingText(editor: Editor, around = 2000, cap = 6000): string {
  const { from, to } = selectedRange(editor)
  return textBetween(editor, Math.max(1, from - around), to + around).slice(0, cap)
}

export function insertMarkdown(
  editor: Editor,
  markdown: string,
  mode: InsertMarkdownMode,
  range?: SelectionRange | null
): void {
  const storage = editor.storage as unknown as { markdown: MarkdownStorageLike }
  const html = storage.markdown.parser.parse(markdown, { inline: false })
  const node = createNodeFromContent(html, editor.schema, {
    errorOnInvalidContent: false,
  })
  const { from, to } = editor.state.selection
  let targetFrom = from
  let targetTo = to
  if (mode === 'replace-selection') {
    if (range !== undefined && range !== null && range.from !== range.to) {
      targetFrom = range.from
      targetTo = range.to
    } else if (targetFrom === targetTo) {
      const domRange = selectionFromDOM(editor)
      if (domRange !== null) {
        targetFrom = domRange.from
        targetTo = domRange.to
      }
    }
  }
  if (mode === 'after-block') {
    const blockEnd = editor.state.selection.$from.end()
    targetFrom = blockEnd
    targetTo = blockEnd
  }
  const transaction = editor.state.tr.replaceWith(targetFrom, targetTo, node.content)
  editor.view.dispatch(transaction)
  editor.commands.focus()
}