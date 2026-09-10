import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import {
  createGenesisCourse,
  draftGenesis,
  getSearchProvider,
  type GenesisDraft,
} from '@/lib/api'
import { useCloseFloatings } from '@/lib/ui-overlays'

const LEVELS: Array<{ value: string; key: string }> = [
  { value: 'school', key: 'levelSchool' },
  { value: 'university-intro', key: 'levelUniversityIntro' },
  { value: 'university-advanced', key: 'levelUniversityAdvanced' },
]

export function GenesisDialog({ onClose }: { onClose: () => void }) {
  useCloseFloatings()
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [step, setStep] = useState<'topic' | 'review' | 'options'>('topic')
  const [topic, setTopic] = useState('')
  const [level, setLevel] = useState('')
  const [draft, setDraft] = useState<GenesisDraft | null>(null)
  const [lessons, setLessons] = useState(true)
  const [quizzes, setQuizzes] = useState(false)
  const [flashcards, setFlashcards] = useState(false)
  const [ground, setGround] = useState(false)
  const provider = useQuery({
    queryKey: ['search-provider'],
    queryFn: getSearchProvider,
  })
  const providerAssigned = provider.data?.assigned ?? false

  const draftMutation = useMutation({
    mutationFn: () =>
      draftGenesis({ topic: topic.trim(), level: level || null, ground }),
    onSuccess: (result) => {
      setDraft(result)
      setStep('review')
    },
  })

  const commitMutation = useMutation({
    mutationFn: () => {
      if (draft === null) {
        throw new Error('no draft')
      }
      return createGenesisCourse({
        draft,
        lessons,
        quizzes,
        flashcards,
        sources: draft.sources ?? [],
      })
    },
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: ['courses'] })
      await queryClient.invalidateQueries({ queryKey: ['jobs-summary'] })
      onClose()
      void navigate({
        to: '/courses/$courseId',
        params: { courseId: String(result.course.id) },
      })
    },
  })

  const optionsOn = [lessons, quizzes, flashcards].filter(Boolean).length
  const estimate = draft === null ? 0 : draft.chapters.length * optionsOn
  const busy = draftMutation.isPending || commitMutation.isPending
  const activeError: unknown = draftMutation.error ?? commitMutation.error
  const error =
    draftMutation.isError || commitMutation.isError
      ? activeError instanceof Error
        ? activeError.message
        : t('genesis.failed')
      : null

  const updateChapter = (index: number, title: string) => {
    if (draft === null) {
      return
    }
    const chapters = draft.chapters.map((chapter, i) =>
      i === index ? { ...chapter, title } : chapter
    )
    setDraft({ ...draft, chapters })
  }

  const updateSection = (chapterIndex: number, sectionIndex: number, title: string) => {
    if (draft === null) {
      return
    }
    const chapters = draft.chapters.map((chapter, i) =>
      i === chapterIndex
        ? {
            ...chapter,
            sections: chapter.sections.map((section, j) =>
              j === sectionIndex ? { ...section, title } : section
            ),
          }
        : chapter
    )
    setDraft({ ...draft, chapters })
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={t('genesis.title')}
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose()
        }
      }}
    >
      <div className="bg-surface border-border flex max-h-[80vh] w-full max-w-xl flex-col rounded-lg border shadow-xl">
        <header className="border-border flex items-center justify-between border-b px-4 py-2">
          <h2 className="text-sm font-semibold">{t('genesis.title')}</h2>
          <span className="text-muted-foreground text-[11px]">
            {t('genesis.step', { step: step === 'topic' ? 1 : step === 'review' ? 2 : 3 })}
          </span>
        </header>
        <div className="flex flex-1 flex-col gap-3 overflow-y-auto p-4">
          {step === 'topic' ? (
            <>
              <p className="text-muted-foreground text-xs">{t('genesis.hint')}</p>
              <input
                autoFocus
                className="bg-surface border-border rounded-md border px-2 py-1.5 text-sm"
                placeholder={t('genesis.topicPlaceholder')}
                value={topic}
                onChange={(event) => setTopic(event.target.value)}
              />
              <select
                className="bg-surface border-border rounded-md border px-2 py-1.5 text-sm"
                value={level}
                onChange={(event) => setLevel(event.target.value)}
                aria-label={t('genesis.levelLabel')}
              >
                <option value="">{t('genesis.levelNone')}</option>
                {LEVELS.map((entry) => (
                  <option key={entry.value} value={entry.value}>
                    {t(`genesis.${entry.key}`)}
                  </option>
                ))}
              </select>
              {providerAssigned ? (
                <label className="flex cursor-pointer items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={ground}
                    onChange={(event) => setGround(event.target.checked)}
                  />
                  {t('genesis.groundOption')}
                </label>
              ) : null}
            </>
          ) : null}
          {step === 'review' && draft !== null ? (
            <>
              <p className="text-muted-foreground text-xs">{t('genesis.reviewHint')}</p>
              <input
                className="bg-surface border-border rounded-md border px-2 py-1.5 text-sm font-medium"
                value={draft.title}
                aria-label={t('genesis.titleLabel')}
                onChange={(event) => setDraft({ ...draft, title: event.target.value })}
              />
              {draft.chapters.map((chapter, chapterIndex) => (
                <div
                  key={chapterIndex}
                  className="border-border space-y-2 rounded-md border p-2"
                >
                  <input
                    className="bg-surface border-border w-full rounded-md border px-2 py-1 text-sm font-medium"
                    value={chapter.title}
                    aria-label={t('genesis.chapterLabel', { number: chapterIndex + 1 })}
                    onChange={(event) => updateChapter(chapterIndex, event.target.value)}
                  />
                  {chapter.sections.map((section, sectionIndex) => (
                    <div key={sectionIndex} className="ml-3 space-y-1">
                      <input
                        className="bg-surface border-border w-full rounded-md border px-2 py-1 text-sm"
                        value={section.title}
                        aria-label={t('genesis.sectionLabel', {
                          chapter: chapterIndex + 1,
                          number: sectionIndex + 1,
                        })}
                        onChange={(event) =>
                          updateSection(chapterIndex, sectionIndex, event.target.value)
                        }
                      />
                      {section.objectives.length > 0 ? (
                        <p className="text-muted-foreground text-[11px]">
                          {section.objectives.join(' · ')}
                        </p>
                      ) : null}
                    </div>
                  ))}
                </div>
              ))}
            </>
          ) : null}
          {step === 'options' && draft !== null ? (
            <>
              <p className="text-muted-foreground text-xs">{t('genesis.optionsHint')}</p>
              {(
                [
                  ['lessons', lessons, setLessons],
                  ['quizzes', quizzes, setQuizzes],
                  ['flashcards', flashcards, setFlashcards],
                ] as const
              ).map(([key, value, setValue]) => (
                <label
                  key={key}
                  className="flex cursor-pointer items-center gap-2 text-sm"
                >
                  <input
                    type="checkbox"
                    checked={value}
                    onChange={(event) => setValue(event.target.checked)}
                  />
                  {t(`genesis.${key}Option`)}
                </label>
              ))}
              <p className="bg-subtle text-muted-foreground rounded-md p-2 text-xs">
                {t('genesis.estimate', { count: estimate })}
              </p>
            </>
          ) : null}
          {error !== null ? (
            <p className="text-destructive text-xs" role="alert">
              {error}
            </p>
          ) : null}
        </div>
        <footer className="border-border flex items-center justify-between gap-2 border-t px-4 py-2">
          <Button variant="ghost" size="sm" onClick={onClose} disabled={busy}>
            {t('library.cancelEdit')}
          </Button>
          <div className="flex gap-2">
            {step === 'topic' ? (
              <Button
                size="sm"
                disabled={!topic.trim() || busy}
                onClick={() => draftMutation.mutate()}
              >
                {draftMutation.isPending ? <Spinner /> : null}
                {t('genesis.draftButton')}
              </Button>
            ) : null}
            {step === 'review' ? (
              <>
                <Button variant="outline" size="sm" onClick={() => setStep('topic')}>
                  {t('genesis.back')}
                </Button>
                <Button size="sm" onClick={() => setStep('options')}>
                  {t('genesis.next')}
                </Button>
              </>
            ) : null}
            {step === 'options' ? (
              <>
                <Button variant="outline" size="sm" onClick={() => setStep('review')}>
                  {t('genesis.back')}
                </Button>
                <Button
                  size="sm"
                  disabled={busy || optionsOn === 0}
                  onClick={() => commitMutation.mutate()}
                >
                  {commitMutation.isPending ? <Spinner /> : null}
                  {t('genesis.createButton')}
                </Button>
              </>
            ) : null}
          </div>
        </footer>
      </div>
    </div>
  )
}
