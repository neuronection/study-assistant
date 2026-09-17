import { Node } from '@tiptap/core'
import { NodeViewWrapper, ReactNodeViewRenderer, type ReactNodeViewProps } from '@tiptap/react'
import { Sparkles, X } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'

import { MermaidDiagram } from '@/components/blocks/MermaidDiagram'
import { BlockFixPanel } from '@/features/ai/BlockFixPanel'
import { validateMermaidSource } from '@/lib/blockGate'
import { repairMermaidSource } from '@/lib/mermaidRepair'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface SerializerState {
  write: (payload: string) => void
  text: (content: string, escape?: boolean) => void
  ensureNewLine: () => void
  closeBlock: (node: unknown) => void
}

function transformMermaidDom(root: HTMLElement): void {
  root.querySelectorAll('pre > code.language-mermaid').forEach((code) => {
    const pre = code.parentElement
    if (pre === null || pre.parentElement === null) {
      return
    }
    const diagram = document.createElement('div')
    diagram.setAttribute('data-ca-mermaid', '')
    diagram.setAttribute('data-source', code.textContent ?? '')
    pre.parentElement.replaceChild(diagram, pre)
  })
}

export const CaMermaid = Node.create({
  name: 'caMermaid',
  group: 'block',
  atom: true,

  addAttributes() {
    return {
      source: { default: '' },
      autofocus: { default: false },
    }
  },

  addStorage() {
    return {
      markdown: {
        serialize(state: SerializerState, node: { attrs: { source: string } }) {
          state.write('```mermaid\n')
          state.text(node.attrs.source, false)
          state.ensureNewLine()
          state.write('```')
          state.closeBlock(node)
        },
        parse: {
          updateDOM(element: HTMLElement) {
            transformMermaidDom(element)
          },
        },
      },
    }
  },

  parseHTML() {
    return [
      {
        tag: 'div[data-ca-mermaid]',
        getAttrs: (element) => ({
          source: element.getAttribute('data-source') ?? '',
        }),
      },
    ]
  },

  renderHTML({ node }) {
    return ['div', { 'data-ca-mermaid': '', 'data-source': node.attrs.source }]
  },

  addNodeView() {
    return ReactNodeViewRenderer(MermaidView)
  },
})

function MermaidView({ node, updateAttributes, selected, editor }: ReactNodeViewProps<HTMLElement>) {
  const { t } = useTranslation()
  const [editing, setEditing] = useState(false)
  const [fixOpen, setFixOpen] = useState(false)
  const [diagnostic, setDiagnostic] = useState<string | null>(null)
  const source = typeof node.attrs.source === 'string' ? node.attrs.source : ''

  const validateMermaid = useCallback(
    async (text: string) => validateMermaidSource(text),
    []
  )

  const tier0Repair = useCallback(
    async (text: string) => repairMermaidSource(text),
    []
  )

  useEffect(() => {
    if (node.attrs.autofocus !== true) {
      return
    }
    setEditing(true)
    updateAttributes({ autofocus: false })

  }, [node.attrs.autofocus, updateAttributes])

  return (
    <NodeViewWrapper>
      <div
        data-ca-mermaid-view
        title={t('editor.mermaidEdit')}
        onDoubleClick={editor.isEditable ? () => setEditing(true) : undefined}
        className={cn(
          'bg-subtle relative my-2 cursor-pointer overflow-x-auto rounded-md p-2 transition-shadow hover:shadow-[var(--as-shadow-1)]',
          selected && 'ring-primary ring-2'
        )}
      >
        <MermaidDiagram
          code={source}
          onError={setDiagnostic}
          onSuccess={() => setDiagnostic(null)}
        />
        {diagnostic !== null && editor.isEditable ? (
          <div className="mt-1 flex items-center justify-between gap-2">
            <span className="text-danger text-[11px]">{t('editor.mermaidBroken')}</span>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => {
                setFixOpen(true)
                setEditing(true)
              }}
            >
              <Sparkles className="size-3.5" aria-hidden />
              {t('editor.ai.fix.button')}
            </Button>
          </div>
        ) : null}
      </div>
      {editing
        ? createPortal(
            <>
              <div
                className="fixed inset-0 z-40 bg-black/30"
                onClick={() => setEditing(false)}
                aria-hidden
              />
              <div
                role="dialog"
                aria-label={t('editor.mermaidEdit')}
                className="bg-surface border-border fixed top-1/2 left-1/2 z-50 flex max-h-[80vh] w-[min(40rem,90vw)] -translate-x-1/2 -translate-y-1/2 flex-col rounded-lg border p-4 shadow-[var(--as-shadow-2)]"
                onKeyDown={(event) => {
                  if (event.key === 'Escape') {
                    setEditing(false)
                  }
                }}
              >
                <div className="mb-2 flex items-center justify-between">
                  <p className="text-muted-foreground text-xs">{t('editor.mermaidEdit')}</p>
                  <button
                    type="button"
                    aria-label={t('editor.close')}
                    className="text-muted-foreground hover:text-foreground rounded p-1"
                    onClick={() => setEditing(false)}
                  >
                    <X className="size-4" aria-hidden />
                  </button>
                </div>
                <textarea
                  autoFocus
                  aria-label={t('editor.mermaidSource')}
                  spellCheck={false}
                  className="bg-surface border-border min-h-40 flex-1 resize-none rounded-md border p-2 font-mono text-xs"
                  value={source}
                  onChange={(event) => updateAttributes({ source: event.target.value })}
                />
                {fixOpen ? (
                  <div className="border-border mt-2 rounded-md border p-2">
                    <BlockFixPanel
                      kind="mermaid"
                      source={source}
                      diagnostic={diagnostic ?? ''}
                      validate={validateMermaid}
                      tier0Repair={tier0Repair}
                      onApply={(fixed) => {
                        updateAttributes({ source: fixed })
                        setFixOpen(false)
                      }}
                      onDiscard={() => setFixOpen(false)}
                    />
                  </div>
                ) : (
                  <div className="mt-2 flex justify-end">
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => setFixOpen(true)}
                    >
                      <Sparkles className="size-3.5" aria-hidden />
                      {t('editor.ai.fix.button')}
                    </Button>
                  </div>
                )}
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
