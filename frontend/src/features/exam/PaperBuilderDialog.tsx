import { useMutation, useQueryClient } from '@tanstack/react-query'
import { FilePlus2, Plus, Trash2, X } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { createPaper } from '@/lib/api'
import { useCloseFloatings } from '@/lib/ui-overlays'

interface SectionDraft {
  key: number
  title: string
  count: number
  marks: number
  difficulty: number | null
}

let nextKey = 2

function sectionDraft(key: number, title: string): SectionDraft {
  return { key, title, count: 5, marks: 20, difficulty: null }
}

export function PaperBuilderDialog({
  courseId,
  nodeId,
  onClose,
  onCreated,
}: {
  courseId: string
  nodeId: string | null
  onClose: () => void
  onCreated: () => void
}) {
  useCloseFloatings()
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [title, setTitle] = useState(t('exams.defaultTitle'))
  const [duration, setDuration] = useState(90)
  const [instructions, setInstructions] = useState('')
  const [sections, setSections] = useState<SectionDraft[]>([sectionDraft(1, t('exams.sectionA'))])
  const [bands, setBands] = useState([
    { label: 'A', min: 90 },
    { label: 'B', min: 80 },
    { label: 'C', min: 70 },
    { label: 'D', min: 60 },
  ])
  const totalMarks = sections.reduce((sum, section) => sum + section.marks, 0)

  const create = useMutation({
    mutationFn: () =>
      createPaper(courseId, {
        title: title.trim(),
        duration_min: duration,
        node_id: nodeId,
        instructions_md: instructions.trim() || null,
        sections: sections.map((section) => ({
          title: section.title.trim(),
          count: section.count,
          marks: section.marks,
          difficulty: section.difficulty,
        })),
        grade_bands: bands.map((band) => ({
          label: band.label.trim(),
          min: band.min,
        })),
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['papers', courseId] })
      onCreated()
      onClose()
    },
  })

  const invalid =
    duration < 5 ||
    duration > 360 ||
    bands.some(
      (band) =>
        !band.label.trim() ||
        band.min < 0 ||
        band.min > 100 ||
        bands.filter((entry) => entry.label.trim() === band.label.trim()).length > 1,
    ) ||
    sections.some(
      (section) =>
        !section.title.trim() ||
        section.count < 1 ||
        section.marks < 1 ||
        section.marks < section.count,
    )

  const update = (key: number, patch: Partial<SectionDraft>) =>
    setSections((previous) =>
      previous.map((section) => (section.key === key ? { ...section, ...patch } : section))
    )

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={t('exams.builderTitle')}
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose()
        }
      }}
    >
      <div className="bg-surface border-border flex max-h-[88vh] w-full max-w-2xl flex-col rounded-lg border shadow-[var(--as-shadow-3)]">
        <header className="border-border flex items-center justify-between border-b px-4 py-2">
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <FilePlus2 className="text-primary size-4" aria-hidden />
            {t('exams.builderTitle')}
          </h2>
          <button
            type="button"
            aria-label={t('chat.close')}
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground rounded p-1"
          >
            <X className="size-4" aria-hidden />
          </button>
        </header>
        <div className="flex-1 space-y-4 overflow-y-auto p-4">
          <div className="grid gap-3 sm:grid-cols-[1fr_8rem]">
            <label className="space-y-1 text-xs">
              <span className="text-muted-foreground">{t('exams.titleLabel')}</span>
              <input
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                className="bg-surface border-border w-full rounded-md border px-2 py-1.5 text-sm"
              />
            </label>
            <label className="space-y-1 text-xs">
              <span className="text-muted-foreground">{t('exams.duration')}</span>
              <input
                type="number"
                min={5}
                max={360}
                value={duration}
                onChange={(event) => setDuration(Number(event.target.value))}
                className="bg-surface border-border w-full rounded-md border px-2 py-1.5 text-sm"
              />
            </label>
          </div>
          <label className="block space-y-1 text-xs">
            <span className="text-muted-foreground">{t('exams.instructions')}</span>
            <textarea
              value={instructions}
              onChange={(event) => setInstructions(event.target.value)}
              rows={2}
              className="bg-surface border-border w-full rounded-md border px-2 py-1.5 text-sm"
            />
          </label>

          <div className="space-y-2">
            {sections.map((section, index) => (
              <div key={section.key} className="border-border rounded-md border p-3">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <span className="text-xs font-medium">
                    {t('exams.sectionN', { n: index + 1 })}
                  </span>
                  {sections.length > 1 ? (
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={t('exams.removeSection', { n: index + 1 })}
                      onClick={() =>
                        setSections((previous) =>
                          previous.filter((entry) => entry.key !== section.key)
                        )
                      }
                    >
                      <Trash2 className="size-3.5" aria-hidden />
                    </Button>
                  ) : null}
                </div>
                <div className="grid gap-2 sm:grid-cols-[1fr_5rem_5rem_7rem]">
                  <input
                    value={section.title}
                    onChange={(event) => update(section.key, { title: event.target.value })}
                    aria-label={t('exams.sectionTitle', { n: index + 1 })}
                    className="bg-surface border-border rounded-md border px-2 py-1 text-xs"
                  />
                  <input
                    type="number"
                    min={1}
                    max={50}
                    value={section.count}
                    onChange={(event) =>
                      update(section.key, { count: Number(event.target.value) })
                    }
                    aria-label={t('exams.sectionCount', { n: index + 1 })}
                    className="bg-surface border-border rounded-md border px-2 py-1 text-xs"
                  />
                  <input
                    type="number"
                    min={1}
                    max={1000}
                    value={section.marks}
                    onChange={(event) =>
                      update(section.key, { marks: Number(event.target.value) })
                    }
                    aria-label={t('exams.sectionMarks', { n: index + 1 })}
                    className="bg-surface border-border rounded-md border px-2 py-1 text-xs"
                  />
                  <select
                    value={section.difficulty ?? ''}
                    onChange={(event) =>
                      update(section.key, {
                        difficulty:
                          event.target.value === '' ? null : Number(event.target.value),
                      })
                    }
                    aria-label={t('exams.sectionDifficulty', { n: index + 1 })}
                    className="bg-surface border-border rounded-md border px-2 py-1 text-xs"
                  >
                    <option value="">{t('exams.anyDifficulty')}</option>
                    {[1, 2, 3, 4, 5].map((level) => (
                      <option key={level} value={level}>
                        {t('exams.difficultyN', { n: level })}
                      </option>
                    ))}
                  </select>
                </div>
                {section.marks < section.count ? (
                  <p className="text-danger mt-1 text-[11px]" role="alert">
                    {t('exams.marksPerQuestion')}
                  </p>
                ) : null}
              </div>
            ))}
            <div className="flex items-center justify-between">
              <Button
                variant="ghost"
                size="sm"
                onClick={() =>
                  setSections((previous) => [
                    ...previous,
                    sectionDraft(nextKey++, t('exams.sectionN', { n: previous.length + 1 })),
                  ])
                }
              >
                <Plus className="size-3.5" aria-hidden />
                {t('exams.addSection')}
              </Button>
              <span className="text-muted-foreground text-xs">
                {t('exams.totalMarks', { marks: totalMarks })}
              </span>
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-semibold">{t('exams.gradeScale')}</h3>
              <span className="text-muted-foreground text-[11px]">
                {t('exams.gradeScaleHint')}
              </span>
            </div>
            {bands.map((band, index) => (
              <div key={index} className="flex items-center gap-2">
                <input
                  value={band.label}
                  onChange={(event) =>
                    setBands((previous) =>
                      previous.map((entry, position) =>
                        position === index ? { ...entry, label: event.target.value } : entry
                      )
                    )
                  }
                  aria-label={t('exams.bandLabel', { n: index + 1 })}
                  className="bg-surface border-border w-16 rounded-md border px-2 py-1 text-xs"
                />
                <span className="text-muted-foreground text-xs">≥</span>
                <input
                  type="number"
                  min={0}
                  max={100}
                  value={band.min}
                  onChange={(event) =>
                    setBands((previous) =>
                      previous.map((entry, position) =>
                        position === index
                          ? { ...entry, min: Number(event.target.value) }
                          : entry
                      )
                    )
                  }
                  aria-label={t('exams.bandMin', { n: index + 1 })}
                  className="bg-surface border-border w-20 rounded-md border px-2 py-1 text-xs"
                />
                <span className="text-muted-foreground text-xs">%</span>
                {bands.length > 1 ? (
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={t('exams.removeBand', { n: index + 1 })}
                    onClick={() =>
                      setBands((previous) =>
                        previous.filter((_, position) => position !== index)
                      )
                    }
                  >
                    <Trash2 className="size-3.5" aria-hidden />
                  </Button>
                ) : null}
              </div>
            ))}
            <Button
              variant="ghost"
              size="sm"
              onClick={() =>
                setBands((previous) => [
                  ...previous,
                  { label: t('exams.bandN', { n: previous.length + 1 }), min: 50 },
                ])
              }
            >
              <Plus className="size-3.5" aria-hidden />
              {t('exams.addBand')}
            </Button>
          </div>
          {create.isError ? (
            <p className="text-danger text-xs" role="alert">
              {(create.error as Error).message}
            </p>
          ) : null}
        </div>
        <footer className="border-border flex items-center justify-end gap-2 border-t px-4 py-2">
          <span className="text-muted-foreground mr-auto text-[11px]">{t('exams.seeded')}</span>
          <Button size="sm" disabled={invalid || create.isPending || !title.trim()} onClick={() => create.mutate()}>
            {create.isPending ? <Spinner /> : null}
            {t('exams.assemble')}
          </Button>
        </footer>
      </div>
    </div>
  )
}
