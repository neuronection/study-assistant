import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import {
  Modal,
  ModalContent,
  ModalDescription,
  ModalHeader,
  ModalTitle,
} from '@neuronection/assistant-ui'
import { getMaterial, reingestMaterial } from '@/lib/api'
import type { Material } from '@/lib/api/materials'
import { cn } from '@/lib/utils'

export const REEXTRACT_BUSY_STATUSES = new Set(['pending', 'processing'])

export const REEXTRACT_MODES = ['auto', 'text', 'ocr'] as const
export type ReExtractMode = (typeof REEXTRACT_MODES)[number]

const MODE_META: Record<ReExtractMode, { label: string; desc: string }> = {
  auto: { label: 'reextract.modeAuto', desc: 'reextract.modeAutoDesc' },
  text: { label: 'reextract.modeText', desc: 'reextract.modeTextDesc' },
  ocr: { label: 'reextract.modeOcr', desc: 'reextract.modeOcrDesc' },
}

export function ReExtractDialog({
  materialId,
  open,
  onClose,
  onSuccess,
}: {
  materialId: number | null
  open: boolean
  onClose: () => void
  onSuccess?: () => void | Promise<void>
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [selected, setSelected] = useState<ReExtractMode>('auto')
  const effective = materialId !== null && open

  const detail = useQuery({
    queryKey: ['material', materialId],
    queryFn: () => getMaterial(materialId ?? 0),
    enabled: effective,
  })
  const material: Material | undefined = effective ? detail.data?.material : undefined

  const run = useMutation({
    mutationFn: async () => {
      if (!material) {
        throw new Error(t('reextract.hint'))
      }
      return reingestMaterial(material.id, { mode: selected })
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['material', materialId] })
      await queryClient.invalidateQueries({ queryKey: ['materials'] })
      onClose()
      if (onSuccess) {
        await onSuccess()
      }
    },
  })

  const busy = material !== undefined && REEXTRACT_BUSY_STATUSES.has(material.status)
  const modes = REEXTRACT_MODES.filter((mode) =>
    (material?.reextract_modes ?? ['auto']).includes(mode),
  )

  return (
    <Modal open={effective} onOpenChange={(next) => !next && onClose()}>
      <ModalContent size="md" closeLabel={t('common.close')} aria-describedby="re-extract-hint">
        <ModalHeader>
          <ModalTitle className="text-base">{t('reextract.title')}</ModalTitle>
          <ModalDescription id="re-extract-hint">
            {material
              ? t('reextract.hint', { title: material.title })
              : t('reextract.loading')}
          </ModalDescription>
        </ModalHeader>
        <form
          data-testid="reextract-dialog"
          className="space-y-3 px-6 pb-6"
          onSubmit={(event) => {
            event.preventDefault()
            if (material && !busy) {
              run.mutate()
            }
          }}
        >
          <fieldset disabled={!material || busy} className="space-y-2">
            {modes.map((mode) => (
              <ModeCard
                key={mode}
                mode={mode}
                material={material}
                selected={selected === mode}
                onSelect={() => setSelected(mode)}
              />
            ))}
          </fieldset>
          {busy ? <p className="text-warning text-xs">{t('reextract.busyHint')}</p> : null}
          {run.isError ? (
            <p className="text-danger text-xs">{String(run.error)}</p>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" size="sm" onClick={onClose}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" size="sm" disabled={!material || busy || run.isPending}>
              {run.isPending ? (
                <Loader2 className="animate-spin" aria-hidden />
              ) : (
                <RefreshCw aria-hidden />
              )}
              {t('reextract.confirm')}
            </Button>
          </div>
        </form>
      </ModalContent>
    </Modal>
  )
}

function ModeCard({
  mode,
  material,
  selected,
  onSelect,
}: {
  mode: ReExtractMode
  material: Material | undefined
  selected: boolean
  onSelect: () => void
}) {
  const { t } = useTranslation()
  const isOcr = mode === 'ocr'
  return (
    <label
      className={cn(
        'border-border bg-surface hover:border-primary/60 flex cursor-pointer items-start gap-3 rounded-lg border px-3 py-2.5 transition-colors',
        selected && 'border-primary ring-primary/20 ring-2',
      )}
      data-testid={`reextract-mode-${mode}`}
    >
      <input
        type="radio"
        name="reextract-mode"
        className="sr-only"
        checked={selected}
        onChange={onSelect}
      />
      <span className="flex-1 space-y-0.5">
        <span className="block text-sm font-medium">
          {t(MODE_META[mode].label)}
          {isOcr && material?.pages !== null && material?.pages !== undefined ? (
            <span className="text-muted-foreground font-normal">
              {' '}
              · {t('reextract.ocrCost', { count: material.pages })}
            </span>
          ) : null}
        </span>
        <span className="text-muted-foreground block text-xs">{t(MODE_META[mode].desc)}</span>
      </span>
    </label>
  )
}
