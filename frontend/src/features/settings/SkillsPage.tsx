import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ChevronLeft,
  Download,
  FlaskConical,
  Loader2,
  RotateCcw,
  Save,
  Upload,
} from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  activateSkillVersion,
  contextVars,
  restoreSkillDefault,
  saveSkillVersion,
  skillResolution,
  skillTestRun,
  skillVersions,
} from '@/lib/api'

import { cn } from '@/lib/utils'

interface EditorProps {
  skillKey: string
  name: string
  courseId: number | null
  onBack: () => void
}

const SCOPES = ['system', 'course_type', 'course'] as const

export function SkillsEditor({ skillKey, name, courseId, onBack }: EditorProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const versions = useQuery({ queryKey: ['skill-versions', skillKey], queryFn: () => skillVersions(skillKey) })
  const resolution = useQuery({
    queryKey: ['skill-resolution', skillKey, courseId],
    queryFn: () => skillResolution(skillKey, courseId),
  })
  const vars = useQuery({ queryKey: ['context-vars'], queryFn: contextVars })

  const active = resolution.data?.active
  const [scope, setScope] = useState<'system' | 'course_type' | 'course'>('system')
  const [systemTemplate, setSystemTemplate] = useState('')
  const [userTemplate, setUserTemplate] = useState('')
  const [maxWords, setMaxWords] = useState<number | ''>('')
  const [noReveal, setNoReveal] = useState(true)
  const [message, setMessage] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<{
    system: string
    user: string
    constraints: { kind: string; params: Record<string, unknown> }[]
  } | null>(null)

  const save = useMutation({
    mutationFn: () =>
      saveSkillVersion(skillKey, {
        scope_type: scope,
        scope_ref: scope === 'course' ? courseId : scope === 'course_type' ? undefined : null,
        system_template: systemTemplate,
        user_template: userTemplate,
        contract: { max_words: maxWords === '' ? null : maxWords, no_answer_reveal: noReveal },
      }),
    onSuccess: async () => {
      setMessage(t('skills.saved'))
      await queryClient.invalidateQueries({ queryKey: ['skill-versions', skillKey] })
      await queryClient.invalidateQueries({ queryKey: ['skill-resolution', skillKey, courseId] })
    },
    onError: (err: Error) => setMessage(err.message),
  })

  const testRun = useMutation({
    mutationFn: () =>
      skillTestRun(skillKey, {
        hint_level: '2',
        user_question: 'Test question',
        step_prompt: 'Compute $\\frac{d}{dx} x^2$.',
      }),
    onSuccess: (result) => {
      setMessage(null)
      setTestResult(result)
    },
    onError: (err: Error) => setMessage(err.message),
  })

  const activate = useMutation({
    mutationFn: (versionId: number) => activateSkillVersion(skillKey, versionId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['skill-versions', skillKey] })
      await queryClient.invalidateQueries({ queryKey: ['skill-resolution', skillKey, courseId] })
    },
  })

  const restore = useMutation({
    mutationFn: () => restoreSkillDefault(skillKey),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['skill-versions', skillKey] })
      await queryClient.invalidateQueries({ queryKey: ['skill-resolution', skillKey, courseId] })
    },
  })

  const insertVar = (key: string) => {
    setSystemTemplate((current) => `${current}{{${key}}}`)
  }

  const allVersions = versions.data ?? []

  return (
    <div className="mx-auto max-w-4xl space-y-4 p-8">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={onBack}>
            <ChevronLeft aria-hidden />
            {t('skills.back')}
          </Button>
          <h1 className="text-xl font-semibold">{name}</h1>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" disabled={restore.isPending} onClick={() => restore.mutate()}>
            <RotateCcw aria-hidden />
            {t('skills.restore')}
          </Button>
          <Button size="sm" disabled={save.isPending || !systemTemplate.trim()} onClick={() => save.mutate()}>
            {save.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <Save aria-hidden />}
            {t('skills.saveVersion')}
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t('skills.scopeTitle')}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-2 text-xs">
          {SCOPES.map((entry) => (
            <button
              key={entry}
              type="button"
              onClick={() => setScope(entry)}
              className={cn(
                'rounded-md border px-3 py-1.5',
                scope === entry ? 'border-primary bg-primary/10 text-primary' : 'border-border'
              )}
            >
              {t(`skills.scope.${entry}`)}
              {resolution.data?.chain[entry] ? (
                <span className="text-muted-foreground ml-1">({resolution.data.chain[entry]})</span>
              ) : null}
            </button>
          ))}
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{t('skills.templateSystem')}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="flex flex-wrap gap-1">
              {(Object.entries(vars.data ?? {}).slice(0, 8)).map(([key, info]) => (
                <button
                  key={key}
                  type="button"
                  title={`${info.type} — ${info.docs}`}
                  onClick={() => insertVar(key)}
                  className="bg-subtle text-muted-foreground hover:text-foreground rounded-full px-2 py-0.5 text-[11px]"
                >
                  {'{{'}{key}{'}}'}
                </button>
              ))}
            </div>
            <textarea
              className="bg-surface border-border h-64 w-full resize-y rounded-md border p-3 font-mono text-xs"
              value={systemTemplate}
              onChange={(event) => setSystemTemplate(event.target.value)}
              placeholder={active?.system_template ?? ''}
              aria-label={t('skills.templateSystem')}
            />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{t('skills.templateUser')}</CardTitle>
          </CardHeader>
          <CardContent>
            <textarea
              className="bg-surface border-border h-64 w-full resize-y rounded-md border p-3 font-mono text-xs"
              value={userTemplate}
              onChange={(event) => setUserTemplate(event.target.value)}
              placeholder={t('skills.userHint')}
              aria-label={t('skills.templateUser')}
            />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t('skills.contractTitle')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap items-center gap-4 text-xs">
            <label className="flex items-center gap-1">
              {t('skills.maxWords')}
              <input
                type="number"
                min={1}
                className="bg-surface border-border w-20 rounded-md border px-2 py-1"
                value={maxWords}
                placeholder={t('skills.unlimited')}
                onChange={(event) =>
                  setMaxWords(event.target.value === '' ? '' : Number(event.target.value))
                }
              />
            </label>
            <label className="flex items-center gap-1">
              <input
                type="checkbox"
                checked={noReveal}
                onChange={(event) => setNoReveal(event.target.checked)}
              />
              {t('skills.noAnswerReveal')}
            </label>
          </div>
          <p className="text-muted-foreground text-[11px]">{t('skills.contractNote')}</p>
        </CardContent>
      </Card>

      <div className="flex gap-2">
        <Button variant="outline" size="sm" disabled={testRun.isPending} onClick={() => testRun.mutate()}>
          {testRun.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <FlaskConical aria-hidden />}
          {t('skills.testRun')}
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={!active}
          onClick={() => {
            const blob = new Blob(
              [
                JSON.stringify(
                  {
                    system_template: systemTemplate || active?.system_template,
                    user_template: userTemplate || active?.user_template || '',
                    contract: active?.contract ?? {},
                  },
                  null,
                  2
                ),
              ],
              { type: 'application/json' }
            )
            const url = URL.createObjectURL(blob)
            const anchor = document.createElement('a')
            anchor.href = url
            anchor.download = `${skillKey}.skill.json`
            anchor.click()
            URL.revokeObjectURL(url)
          }}
        >
          <Download aria-hidden />
          {t('skills.exportPack')}
        </Button>
        <input
          id="skill-import"
          type="file"
          accept="application/json,.json"
          className="hidden"
          onChange={(event) => {
            const file = event.target.files?.[0]
            if (!file) {
              return
            }
            void file
              .text()
              .then((text) => {
                const parsed = JSON.parse(text) as { system_template?: string; user_template?: string }
                if (!parsed.system_template) {
                  throw new Error('missing system_template')
                }
                setSystemTemplate(parsed.system_template)
                setUserTemplate(parsed.user_template ?? '')
                setMessage(t('skills.imported'))
              })
              .catch((error: Error) => setMessage(error.message))
            event.target.value = ''
          }}
        />
        <Button variant="outline" size="sm" onClick={() => document.getElementById('skill-import')?.click()}>
          <Upload aria-hidden />
          {t('skills.importPack')}
        </Button>
      </div>

      {testResult ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{t('skills.testResult')}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <pre className="bg-subtle max-h-48 overflow-auto rounded-md p-3 text-xs">{testResult.system}</pre>
            <div className="flex flex-wrap gap-1">
              {testResult.constraints.map((constraint) => (
                <span key={constraint.kind} className="bg-primary/10 text-primary rounded-full px-2 py-0.5 text-[11px]">
                  {constraint.kind}
                  {constraint.params.n !== undefined ? ` (n=${String(constraint.params.n)})` : ''}
                </span>
              ))}
            </div>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t('skills.versionsTitle')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1">
          {allVersions.length === 0 ? (
            <p className="text-muted-foreground text-xs">{t('skills.noVersions')}</p>
          ) : (
            allVersions.map((version) => (
              <div
                key={version.id}
                className="border-border flex items-center gap-3 rounded-md border px-3 py-2 text-xs"
              >
                <span className="text-muted-foreground w-24 shrink-0">
                  {t(`skills.scope.${version.scope_type}`)} {t('skills.versionLabel', { version: version.version })}
                </span>
                <span className="min-w-0 flex-1 truncate text-[11px]">
                  {version.system_template.slice(0, 80)}
                </span>
                {version.is_active ? (
                  <span className="bg-success/15 text-success shrink-0 rounded-full px-2 py-0.5 text-[10px]">
                    {t('skills.active')}
                  </span>
                ) : (
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={activate.isPending}
                    onClick={() => activate.mutate(version.id)}
                  >
                    {t('skills.activate')}
                  </Button>
                )}
              </div>
            ))
          )}
        </CardContent>
      </Card>

      {message ? <p className="text-muted-foreground text-xs">{message}</p> : null}
    </div>
  )
}
