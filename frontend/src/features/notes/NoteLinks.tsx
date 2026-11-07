import { useQuery } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { Link2, Unlink } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { listNoteLinks } from '@/lib/api'
import { cn } from '@/lib/utils'

export function NoteLinks({ noteId }: { noteId: string }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const links = useQuery({
    queryKey: ['note-links', noteId],
    queryFn: () => listNoteLinks(noteId),
  })
  const outbound = links.data?.outbound ?? []
  const backlinks = links.data?.backlinks ?? []
  if (outbound.length === 0 && backlinks.length === 0) {
    return null
  }
  const open = (targetId: string) => {
    void navigate({ to: '/note/$noteId', params: { noteId: String(targetId) } })
  }
  const chip = (
    key: string,
    label: string,
    targetId: string | null,
    broken: boolean,
    direction: 'out' | 'in'
  ) => (
    <button
      key={key}
      type="button"
      disabled={targetId === null}
      title={broken ? t('notes.linkBroken') : label}
      data-testid={`note-link-${direction}`}
      className={cn(
        'border-border inline-flex max-w-48 items-center gap-1 rounded-full border px-2 py-0.5 text-[11px]',
        targetId === null
          ? 'text-muted-foreground border-dashed opacity-70'
          : 'bg-subtle hover:border-primary'
      )}
      onClick={() => targetId !== null && open(targetId)}
    >
      {targetId === null ? <Unlink className="size-3" aria-hidden /> : <Link2 className="size-3" aria-hidden />}
      <span className="truncate">{label}</span>
    </button>
  )
  return (
    <div className="flex flex-wrap items-center gap-1" data-testid="note-links">
      {outbound.map((link) =>
        chip(link.id, link.title ?? link.target, link.note_id, link.broken, 'out')
      )}
      {backlinks.map((link) => chip(`in-${link.id}`, link.title ?? link.target, link.note_id, false, 'in'))}
    </div>
  )
}
