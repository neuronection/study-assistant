import { Node } from '@tiptap/core'
import { NodeViewWrapper, ReactNodeViewRenderer, type ReactNodeViewProps } from '@tiptap/react'
import katex from 'katex'
import { X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'

import { MathInput } from '@/components/math/MathInput'
import { MATH_NEWLINE } from '@/components/editor/markdownFidelity'
import { cn } from '@/lib/utils'

interface MathHit {
  start: number
  end: number
  latex: string
  display: boolean
}

function firstMathSpan(text: string, from: number): MathHit | null {
  const dollar = text.indexOf('$', from)
  if (dollar === -1) {
    return null
  }
  if (text[dollar + 1] === '$') {
    const close = text.indexOf('$$', dollar + 2)
    if (close === -1 || close === dollar + 2) {
      return firstMathSpan(text, dollar + 2)
    }
    const latex = text.slice(dollar + 2, close)
    if (latex.includes('\n\n')) {
      return firstMathSpan(text, dollar + 2)
    }
    return { start: dollar, end: close + 2, latex, display: true }
  }
  const lineEnd = text.indexOf('\n', dollar)
  const stop = lineEnd === -1 ? text.length : lineEnd
  const close = text.indexOf('$', dollar + 1)
  if (close === -1 || close >= stop || close === dollar + 1) {
    return firstMathSpan(text, dollar + 1)
  }
  const latex = text.slice(dollar + 1, close)
  if (/^\s|\s$/.test(latex) || text[close + 1] === '$') {
    return firstMathSpan(text, dollar + 1)
  }
  return { start: dollar, end: close + 1, latex, display: false }
}

function insertMathElement(node: Text, hit: MathHit): Text {
  const parent = node.parentElement
  if (parent === null) {
    return node
  }
  const span = document.createElement('span')
  span.setAttribute('data-ca-math', '')
  span.setAttribute('data-display', hit.display ? 'true' : 'false')
  span.setAttribute(
    'data-latex',
    hit.latex.split(MATH_NEWLINE).join('\n').replace(/\\\|/g, '|')
  )
  const mathText = node.splitText(hit.start)
  const tail = mathText.splitText(hit.end - hit.start)
  parent.insertBefore(span, tail)
  mathText.remove()
  return tail
}

function transformMathDom(root: HTMLElement): void {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  const textNodes: Text[] = []
  while (walker.nextNode()) {
    textNodes.push(walker.currentNode as Text)
  }
  for (const node of textNodes) {
    const parent = node.parentElement
    if (parent === null || parent.closest('code, pre') !== null) {
      continue
    }
    let current: Text = node
    while (current.data.includes('$')) {
      const hit = firstMathSpan(current.data, 0)
      if (hit === null) {
        break
      }
      const next = insertMathElement(current, hit)
      if (next === current) {
        break
      }
      current = next
    }
  }
}

export const CaMath = Node.create({
  name: 'caMath',
  inline: true,
  atom: true,
  group: 'inline',

  addAttributes() {
    return {
      latex: { default: '' },
      display: { default: false },
      autofocus: { default: false },
    }
  },

  addStorage() {
    return {
      markdown: {
        serialize(state: { write: (payload: string) => void }, node: { attrs: { latex: string; display: boolean } }) {
          const { latex, display } = node.attrs
          state.write(display ? `$$${latex}$$` : `$${latex}$`)
        },
        parse: {
          updateDOM(element: HTMLElement) {
            transformMathDom(element)
          },
        },
      },
    }
  },

  parseHTML() {
    return [
      {
        tag: 'span[data-ca-math]',
        getAttrs: (element) => ({
          latex: element.getAttribute('data-latex') ?? '',
          display: element.getAttribute('data-display') === 'true',
        }),
      },
    ]
  },

  renderHTML({ node }) {
    return [
      'span',
      {
        'data-ca-math': '',
        'data-latex': node.attrs.latex,
        'data-display': node.attrs.display ? 'true' : 'false',
      },
    ]
  },

  addNodeView() {
    return ReactNodeViewRenderer(MathView)
  },
})

function renderLatex(latex: string, display: boolean): string | null {
  try {
    return katex.renderToString(latex, {
      throwOnError: false,
      displayMode: display,
      output: 'html',
    })
  } catch {
    return null
  }
}

function MathView({ node, updateAttributes, selected, editor }: ReactNodeViewProps<HTMLElement>) {
  const { t } = useTranslation()
  const [editing, setEditing] = useState(false)
  const [position, setPosition] = useState<{ top: number; left: number } | null>(null)
  const anchorRef = useRef<HTMLSpanElement>(null)
  const latex = typeof node.attrs.latex === 'string' ? node.attrs.latex : ''
  const display = node.attrs.display === true

  const html = useMemo(() => renderLatex(latex, display), [latex, display])

  const openEditor = () => {
    const rect = anchorRef.current?.getBoundingClientRect()
    setPosition(
      rect ? { top: rect.bottom + 8, left: rect.left } : { top: 100, left: 100 }
    )
    setEditing(true)
  }

  useEffect(() => {
    if (node.attrs.autofocus !== true) {
      return
    }
    openEditor()
    updateAttributes({ autofocus: false })
     
  }, [node.attrs.autofocus, updateAttributes])

  return (
    <NodeViewWrapper as="span">
      <span
        ref={anchorRef}
        data-ca-math-view
        title={latex}
        onDoubleClick={editor.isEditable ? openEditor : undefined}
        className={cn(
          'ca-math inline-block cursor-pointer rounded px-0.5 align-baseline',
          selected && 'ring-primary ring-2'
        )}
      >
        {html !== null ? (
          <span dangerouslySetInnerHTML={{ __html: html }} />
        ) : (
          <code className="bg-subtle rounded px-1 font-mono text-xs">{latex}</code>
        )}
      </span>
      {editing && position !== null
        ? createPortal(
            <>
              <div
                className="fixed inset-0 z-40"
                onClick={() => setEditing(false)}
                aria-hidden
              />
              <div
                role="dialog"
                aria-label={t('editor.mathEdit')}
                className="bg-surface border-border animate-in fixed z-50 w-[min(28rem,90vw)] rounded-lg border p-3 shadow-lg"
                style={{ top: position.top, left: position.left }}
                onKeyDown={(event) => {
                  if (event.key === 'Escape') {
                    setEditing(false)
                  }
                }}
              >
                <div className="mb-2 flex items-center justify-between gap-2">
                  <p className="text-muted-foreground text-xs">{t('editor.mathEdit')}</p>
                  <button
                    type="button"
                    aria-label={t('editor.close')}
                    className="text-muted-foreground hover:text-foreground rounded p-1"
                    onClick={() => setEditing(false)}
                  >
                    <X className="size-4" aria-hidden />
                  </button>
                </div>
                <div className="bg-subtle rounded-md p-2">
                  <MathInput
                    value={latex}
                    onChange={(value) => updateAttributes({ latex: value })}
                  />
                </div>
                <div className="mt-2 flex justify-end">
                  <button
                    type="button"
                    className="text-muted-foreground hover:text-foreground text-xs"
                    onClick={() => setEditing(false)}
                  >
                    {t('editor.mathDone')}
                  </button>
                </div>
              </div>
            </>,
            document.body
          )
        : null}
    </NodeViewWrapper>
  )
}
