import { Check, Highlighter, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import type { Anchor } from '@/lib/api'

const COLORS = ['yellow', 'green', 'blue', 'pink'] as const

export function HighlightsPanel({
  anchors,
  busy,
  onPatch,
  onDelete,
  onJump,
}: {
  anchors: Anchor[]
  busy: boolean
  onPatch: (anchorId: string, body: { note_md?: string | null; color?: string }) => Promise<void>
  onDelete: (anchorId: string) => Promise<void>
  onJump: (anchorId: string) => void
}) {
  const { t } = useTranslation()
  const [editingId, setEditingId] = useState<string | null>(null)
  const [draft, setDraft] = useState('')

  if (anchors.length === 0) {
    return (
      <p className="text-muted-foreground border-border rounded-md border border-dashed p-3 text-xs">
        {t('library.highlightsEmpty')}
      </p>
    )
  }

  return (
    <ul className="border-border divide-border divide-y overflow-hidden rounded-md border">
      {anchors.map((anchor) => (
        <li key={anchor.id} className="flex flex-col gap-1 p-3">
          <div className="flex items-start gap-2">
            <Highlighter
              className="text-muted-foreground mt-0.5 size-3.5 shrink-0"
              aria-hidden
            />
            <button
              type="button"
              className="min-w-0 flex-1 text-left text-sm"
              onClick={() => onJump(anchor.id)}
              title={t('library.highlightJump')}
            >
              <span className="line-clamp-3">“{anchor.quote ?? ''}”</span>
            </button>
            <div className="flex shrink-0 items-center gap-1">
              {COLORS.map((color) => (
                <button
                  key={color}
                  type="button"
                  aria-label={t(`library.highlightColor.${color}`)}
                  aria-pressed={anchor.color === color}
                  disabled={busy}
                  onClick={() => void onPatch(anchor.id, { color })}
                  className={`size-3 rounded-full border ${
                    anchor.color === color
                      ? 'ring-foreground/50 ring-2 ring-offset-1'
                      : ''
                  }`}
                  style={{ backgroundColor: `var(--hl-${color})` }}
                />
              ))}
              <Button
                variant="ghost"
                size="icon"
                aria-label={t('library.highlightDelete')}
                disabled={busy}
                onClick={() => void onDelete(anchor.id)}
              >
                <Trash2 className="size-3.5" aria-hidden />
              </Button>
            </div>
          </div>
          {anchor.orphaned ? (
            <p className="text-warning text-xs" role="status">
              {t('library.highlightOrphaned')}
            </p>
          ) : null}
          {editingId === anchor.id ? (
            <div className="flex flex-col gap-1 pl-5">
              <textarea
                aria-label={t('library.highlightNote')}
                value={draft}
                rows={2}
                onChange={(event) => setDraft(event.target.value)}
                className="bg-surface border-border w-full rounded-md border p-2 text-xs"
              />
              <div className="flex justify-end gap-1">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setEditingId(null)}
                >
                  {t('library.cancelEdit')}
                </Button>
                <Button
                  size="sm"
                  disabled={busy}
                  onClick={async () => {
                    await onPatch(anchor.id, { note_md: draft })
                    setEditingId(null)
                  }}
                >
                  <Check className="size-3.5" aria-hidden />
                  {t('library.highlightSaveNote')}
                </Button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              className="text-muted-foreground hover:text-foreground pl-5 text-left text-xs"
              onClick={() => {
                setEditingId(anchor.id)
                setDraft(anchor.note_md ?? '')
              }}
            >
              {anchor.note_md ? anchor.note_md : t('library.highlightAddNote')}
            </button>
          )}
        </li>
      ))}
    </ul>
  )
}
