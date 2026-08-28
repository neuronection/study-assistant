import { useTranslation } from 'react-i18next'

import { WorkingDirEditor } from '@/features/settings/WorkingDirEditor'

export function WorkingDirStep() {
  const { t } = useTranslation()
  return (
    <div className="space-y-3">
      <p className="text-muted-foreground text-sm">{t('onboarding.workingDirHint')}</p>
      <WorkingDirEditor />
      <p className="text-muted-foreground text-[11px]">{t('onboarding.workingDirNote')}</p>
    </div>
  )
}
