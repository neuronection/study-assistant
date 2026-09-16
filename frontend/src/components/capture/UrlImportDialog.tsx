import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { Download, Link2, Loader2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import {
  Modal,
  ModalContent,
  ModalDescription,
  ModalHeader,
  ModalTitle,
} from '@neuronection/assistant-ui'
import { createLinkMaterial, importUrlMaterial, listCourses } from '@/lib/api'
import { useImportUrlStore } from '@/lib/import-url-store'
import { useWorkspaceStore } from '@/lib/workspace-store'
import { cn } from '@/lib/utils'

type ImportMode = 'attach' | 'import'

export function UrlImportDialog() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const open = useImportUrlStore((state) => state.open)
  const prefilledUrl = useImportUrlStore((state) => state.url)
  const prefilledNodeId = useImportUrlStore((state) => state.nodeId)
  const closeImport = useImportUrlStore((state) => state.closeImport)
  const courseId = useWorkspaceStore((state) => state.courseId)
  const [mode, setMode] = useState<ImportMode>('attach')
  const [url, setUrl] = useState('')
  const [selectedCourse, setSelectedCourse] = useState<number | null>(null)

  useEffect(() => {
    if (open) {
      setUrl(prefilledUrl)
    }
  }, [open, prefilledUrl])

  const courses = useQuery({
    queryKey: ['courses'],
    queryFn: listCourses,
    enabled: open,
  })
  const effectiveCourseId =
    selectedCourse ?? courseId ?? courses.data?.[0]?.id ?? null

  const run = useMutation({
    mutationFn: async () => {
      if (effectiveCourseId === null) {
        throw new Error(t('workspace.openCourseFirst'))
      }
      if (mode === 'attach') {
        return createLinkMaterial({
          course_id: effectiveCourseId,
          url: url.trim(),
          node_id: prefilledNodeId ?? undefined,
        })
      }
      return importUrlMaterial(effectiveCourseId, url.trim())
    },
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: ['materials'] })
      closeImport()
      setUrl('')
      void navigate({
        to: '/library/$materialId',
        params: { materialId: String(result.material.id) },
      })
    },
  })

  return (
    <Modal open={open} onOpenChange={(next) => !next && closeImport()}>
      <ModalContent size="md" closeLabel={t('common.close')} aria-describedby="import-url-hint">
        <ModalHeader>
          <ModalTitle className="text-base">{t('importUrl.title')}</ModalTitle>
          <ModalDescription id="import-url-hint">
            {t('importUrl.hint')}
          </ModalDescription>
        </ModalHeader>
        <form
          className="space-y-3 px-6 pb-6"
          onSubmit={(event) => {
            event.preventDefault()
            if (url.trim()) {
              run.mutate()
            }
          }}
        >
          <div
            className="bg-subtle grid grid-cols-2 gap-1 rounded-md p-1"
            role="tablist"
            aria-label={t('importUrl.modeLabel')}
          >
            {(
              [
                ['attach', 'modeAttach'],
                ['import', 'modeImport'],
              ] as const
            ).map(([value, labelKey]) => (
              <button
                key={value}
                type="button"
                role="tab"
                aria-selected={mode === value}
                className={cn(
                  'rounded-md px-2 py-1.5 text-xs',
                  mode === value
                    ? 'bg-surface text-foreground shadow-sm'
                    : 'text-muted-foreground hover:text-foreground',
                )}
                onClick={() => setMode(value)}
              >
                {t(`importUrl.${labelKey}`)}
              </button>
            ))}
          </div>
          {mode === 'attach' && prefilledNodeId !== null ? (
            <p className="text-muted-foreground text-xs">
              {t('importUrl.attachPlacement')}
            </p>
          ) : null}
          <label className="block space-y-1">
            <span className="text-muted-foreground text-xs">{t('importUrl.urlLabel')}</span>
            <input
              type="url"
              required
              className="bg-surface border-border focus:border-primary w-full rounded-md border px-3 py-2 text-sm outline-none"
              placeholder="https://en.wikipedia.org/wiki/Integration_by_parts"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
            />
          </label>
          <label className="block space-y-1">
            <span className="text-muted-foreground text-xs">{t('importUrl.courseLabel')}</span>
            <select
              className="bg-surface border-border w-full rounded-md border px-3 py-2 text-sm"
              value={effectiveCourseId ?? ''}
              onChange={(event) => setSelectedCourse(Number(event.target.value))}
            >
              {(courses.data ?? []).map((course) => (
                <option key={course.id} value={course.id}>
                  {course.title}
                </option>
              ))}
            </select>
          </label>
          {run.isError ? (
            <p className="text-danger text-xs">{String(run.error)}</p>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" size="sm" onClick={closeImport}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" size="sm" disabled={run.isPending || !url.trim()}>
              {run.isPending ? (
                <Loader2 className="animate-spin" aria-hidden />
              ) : mode === 'attach' ? (
                <Link2 aria-hidden />
              ) : (
                <Download aria-hidden />
              )}
              {mode === 'attach'
                ? t('importUrl.attachAction')
                : t('importUrl.importAction')}
            </Button>
          </div>
        </form>
      </ModalContent>
    </Modal>
  )
}
