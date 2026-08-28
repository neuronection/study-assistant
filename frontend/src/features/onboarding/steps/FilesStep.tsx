import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { UploadDropzone } from '@/components/materials/UploadDropzone'
import { useMaterialUpload } from '@/components/materials/materialUpload'

import type { WizardCourse } from './CourseStep'

export function FilesStep({ course }: { course: WizardCourse | null }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [uploaded, setUploaded] = useState<string[]>([])

  const upload = useMaterialUpload({
    courseId: course?.id ?? null,
    onUploaded: (result) => {
      setUploaded((current) => [...current, result.material.title])
      void queryClient.invalidateQueries({ queryKey: ['onboarding-state'] })
    },
  })

  if (course === null) {
    return (
      <p className="text-muted-foreground py-4 text-center text-sm">
        {t('onboarding.filesNoCourse')}
      </p>
    )
  }

  return (
    <div className="space-y-3">
      <p className="text-muted-foreground text-sm">{t('onboarding.filesHint')}</p>
      <UploadDropzone
        upload={upload}
        label={t('onboarding.filesDropLabel')}
        hint={course.title}
      />
      {uploaded.length > 0 ? (
        <p className="text-muted-foreground text-xs">
          {t('onboarding.uploadedCount', { count: uploaded.length })}{' '}
          {uploaded
            .slice(0, 3)
            .map((name) => name)
            .join(' · ')}
        </p>
      ) : null}
    </div>
  )
}
