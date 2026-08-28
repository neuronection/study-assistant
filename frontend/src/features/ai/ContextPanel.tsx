import { useQuery } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import { BookOpen, ChevronDown, Eye, MapPin, StickyNote } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { EntityMention } from '@/features/ai/EntityMention'
import { getChatContext, type ChatRead } from '@/lib/api'

import { cn } from '@/lib/utils'

export function ReadIndicator({ read }: { read: ChatRead }) {
  const { t } = useTranslation()
  return (
    <span
      className="inline-flex items-center gap-1"
      title={t('ai.context.readTooltip', { chars: read.chars })}
    >
      <Eye className="text-muted-foreground size-3 shrink-0" aria-hidden />
      <EntityMention
        mention={{
          ref: read.ref,
          kind: read.kind,
          id: read.id,
          title: read.title,
          course_id: read.course_id ?? null,
        }}
        className="text-muted-foreground"
      />
    </span>
  )
}

export function ContextPanel({ sessionId }: { sessionId: number }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const context = useQuery({
    queryKey: ['chat-context', sessionId],
    queryFn: () => getChatContext(sessionId),
  })

  const node = context.data?.node ?? null
  const notes = context.data?.latest_notes ?? []
  const registry = context.data?.registry ?? []

  return (
    <div className="border-border border-b">
      <button
        type="button"
        className="hover:bg-subtle flex w-full items-center gap-2 px-3 py-2 text-left text-xs font-medium"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
      >
        <BookOpen className="text-muted-foreground size-3.5" aria-hidden />
        {t('ai.context.title')}
        {registry.length > 0 ? (
          <span className="bg-subtle text-muted-foreground rounded-full px-1.5 py-0.5 text-[10px]">
            {registry.length}
          </span>
        ) : null}
        <ChevronDown
          className={cn(
            'text-muted-foreground ml-auto size-3.5 transition-transform',
            open && 'rotate-180',
          )}
          aria-hidden
        />
      </button>
      <AnimatePresence initial={false}>
        {open ? (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="overflow-hidden"
          >
            <div className="space-y-2 px-3 pb-3 text-xs">
              {node ? (
                <p className="flex items-center gap-1.5">
                  <MapPin className="text-muted-foreground size-3" aria-hidden />
                  <span className="text-muted-foreground">{t('ai.context.scope')}</span>
                  <EntityMention
                    mention={{
                      ref: `T${node.id}`,
                      kind: 'node',
                      id: node.id,
                      title: node.title,
                      course_id: context.data?.course_id ?? null,
                    }}
                  />
                </p>
              ) : null}
              {notes.length > 0 ? (
                <p className="flex flex-wrap items-center gap-1.5">
                  <StickyNote className="text-muted-foreground size-3" aria-hidden />
                  <span className="text-muted-foreground">{t('ai.context.autoNotes')}</span>
                  {notes.map((note) => (
                    <span
                      key={note.id}
                      className="bg-subtle text-muted-foreground rounded-full px-2 py-0.5 text-[11px]"
                    >
                      {note.title}
                    </span>
                  ))}
                </p>
              ) : null}
              <div>
                <p className="text-muted-foreground mb-1">{t('ai.context.manifest')}</p>
                {registry.length === 0 ? (
                  <p className="text-muted-foreground italic">{t('ai.context.empty')}</p>
                ) : (
                  <div className="flex flex-wrap gap-1">
                    {registry.slice(0, 24).map((entry) => (
                      <EntityMention key={entry.ref} mention={entry} />
                    ))}
                  </div>
                )}
              </div>
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  )
}
