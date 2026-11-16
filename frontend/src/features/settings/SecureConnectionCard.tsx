import { Check, Download, Monitor, ShieldAlert, ShieldCheck, X } from 'lucide-react'
import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { detectSecureContext } from '@/lib/secure-context'
import { useInstallPrompt } from '@/lib/use-install-prompt'
import { Button } from '@/components/ui/button'

function Capability({
  label,
  available,
}: {
  label: string
  available: boolean
}) {
  const { t } = useTranslation()
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] ${
        available
          ? 'border-success/40 text-success'
          : 'border-border text-muted-foreground'
      }`}
      aria-label={`${label}: ${available ? t('settings.secureAvailable') : t('settings.secureUnavailable')}`}
    >
      {available ? (
        <Check className="size-3" aria-hidden />
      ) : (
        <X className="size-3" aria-hidden />
      )}
      {label}
    </span>
  )
}

export function SecureConnectionCard() {
  const { t } = useTranslation()
  const report = useMemo(() => detectSecureContext(), [])
  const installPrompt = useInstallPrompt()

  const status = report.desktop
    ? {
        icon: Monitor,
        title: t('settings.secureDesktopTitle'),
        body: t('settings.secureDesktopBody'),
        tone: 'text-primary',
      }
    : report.secure
      ? {
          icon: ShieldCheck,
          title: t('settings.secureHttpsTitle'),
          body: t('settings.secureHttpsBody'),
          tone: 'text-success',
        }
      : {
          icon: ShieldAlert,
          title: t('settings.secureHttpTitle'),
          body: t('settings.secureHttpBody'),
          tone: 'text-warning',
        }
  const Icon = status.icon

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm">
          <Icon className={`size-4 ${status.tone}`} aria-hidden />
          {t('settings.secureTitle')}
        </CardTitle>
        <CardDescription>{status.title}</CardDescription>
      </CardHeader>
      <CardContent className="max-w-xl space-y-3">
        <p className="text-muted-foreground text-xs">{status.body}</p>
        {!report.desktop ? (
          <div className="flex flex-wrap gap-1.5">
            <Capability label={t('settings.secureCapInstall')} available={report.install} />
            <Capability
              label={t('settings.secureCapShare')}
              available={report.shareTarget}
            />
            <Capability
              label={t('settings.secureCapMic')}
              available={report.mediaCapture && report.mediaRecorder}
            />
            <Capability
              label={t('settings.secureCapNotifications')}
              available={report.notifications}
            />
          </div>
        ) : null}
        {!report.desktop && (report.install || installPrompt.available) ? (
          <Button
            size="sm"
            variant="outline"
            onClick={() => void installPrompt.install()}
          >
            <Download className="size-3.5" aria-hidden />
            {t('settings.secureInstallAction')}
          </Button>
        ) : null}
        {!report.secure && !report.desktop ? (
          <details className="text-muted-foreground text-xs">
            <summary className="cursor-pointer select-none">
              {t('settings.secureDetailsTitle')}
            </summary>
            <p className="pt-2">{t('settings.secureDetailsBody')}</p>
          </details>
        ) : null}
      </CardContent>
    </Card>
  )
}
