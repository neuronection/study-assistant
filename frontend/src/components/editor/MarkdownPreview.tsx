import { EditorContent, useEditor } from '@tiptap/react'
import { StarterKit } from '@tiptap/starter-kit'
import { TableCell, TableHeader, TableRow } from '@tiptap/extension-table'
import { useEffect } from 'react'
import { Markdown } from 'tiptap-markdown'

import { CaMath } from './CaMath'
import { CaMermaid } from './CaMermaid'
import { MarkdownTable } from './MarkdownTable'
import {
  BlankLineParagraph,
  encodeMarkdownForParse,
  stripBlankMarkers,
} from './markdownFidelity'

const PROSE_CLASS =
  'prose-notes bg-surface w-full p-1 text-sm outline-none ' +
  '[&_h2]:text-lg [&_h2]:font-semibold [&_h3]:text-base [&_h3]:font-semibold ' +
  '[&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5 ' +
  '[&_pre]:bg-subtle [&_pre]:rounded-md [&_pre]:p-3 [&_pre]:font-mono [&_pre]:text-xs ' +
  '[&_code]:bg-subtle [&_code]:rounded [&_code]:px-1 [&_code]:font-mono [&_code]:text-xs ' +
  '[&_table]:w-full [&_table]:border-collapse [&_th]:border [&_th]:border-border ' +
  '[&_th]:p-1 [&_th]:text-left [&_td]:border [&_td]:border-border [&_td]:p-1'

export function MarkdownPreview({ markdown }: { markdown: string }) {
  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        paragraph: false,
        link: {
          protocols: ['http', 'https', 'mailto', 'ca-material', 'ca-drawing', 'mention'],
        },
      }),
      BlankLineParagraph,
      CaMath,
      CaMermaid,
      MarkdownTable,
      TableRow,
      TableCell,
      TableHeader,
      Markdown.configure({ html: false, breaks: true, linkify: false }),
    ],
    content: encodeMarkdownForParse(markdown),
    editable: false,
  })

  useEffect(() => {
    if (editor === null || editor.isDestroyed) {
      return
    }
    editor.commands.setContent(encodeMarkdownForParse(markdown), { emitUpdate: false })
    stripBlankMarkers(editor)
  }, [editor, markdown])

  if (editor === null) {
    return null
  }
  return <EditorContent editor={editor} className={PROSE_CLASS} />
}