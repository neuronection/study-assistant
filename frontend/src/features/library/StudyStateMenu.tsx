import { ChevronDown } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import {
  Menu,
  MenuCheckboxItem,
  MenuContent,
  MenuTrigger,
} from '@/components/ui/popover-menu'
import { cn } from '@/lib/utils'

export type StudyStatus = 'unread' | 'reading' | 'studied'

const STUDY_STATUSES: StudyStatus[] = ['unread', 'reading', 'studied']

const STATUS_DOT: Record<StudyStatus, string> = {
  unread: 'bg-muted-foreground/40',
  reading: 'bg-warning',
  studied: 'bg-success',
}

export function StudyStateMenu({
  status,
  pending,
  onChange,
}: {
  status: StudyStatus
  pending?: boolean
  onChange: (next: StudyStatus) => void
}) {
  const { t } = useTranslation()
  return (
    <Menu modal={false}>
      <MenuTrigger asChild disabled={pending}>
        <Button
          variant="outline"
          size="sm"
          aria-label={t('library.studyState')}
          className="gap-1.5"
        >
          <span className={cn('size-2 rounded-full', STATUS_DOT[status])} aria-hidden />
          {t(`library.studyState_${status}`)}
          <ChevronDown className="text-muted-foreground size-3.5" aria-hidden />
        </Button>
      </MenuTrigger>
      <MenuContent align="end">
        {STUDY_STATUSES.map((option) => (
          <MenuCheckboxItem
            key={option}
            checked={status === option}
            disabled={pending}
            onSelect={() => {
              if (option !== status) {
                onChange(option)
              }
            }}
          >
            {t(`library.studyState_${option}`)}
          </MenuCheckboxItem>
        ))}
      </MenuContent>
    </Menu>
  )
}
