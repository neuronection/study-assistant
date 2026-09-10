import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, ClipboardList, Package } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { CourseSelectField } from '@/components/workspace/CoursePicker'
import {
  importInboxFile,
  importQpkg,
  importQuiz,
  inboxPath,
  scanInbox,
  type ImportResult,
} from '@/lib/api'

import { cn } from '@/lib/utils'
import { useCloseFloatings } from '@/lib/ui-overlays'

export function ImportDialog({
  courseId,
  onClose,
}: {
  courseId: number | null
  onClose: () => void
}) {
  useCloseFloatings()
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [tab, setTab] = useState<'paste' | 'file' | 'inbox' | 'author'>('paste')
  const [caqText, setCaqText] = useState('')
  const [preview, setPreview] = useState<ImportResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pkgResult, setPkgResult] = useState<string | null>(null)
  const [pkgFile, setPkgFile] = useState<File | null>(null)
  const [pickedCourse, setPickedCourse] = useState<number | null>(null)
  const pkgInput = useRef<HTMLInputElement>(null)
  const courseIdForRequest = courseId ?? pickedCourse

  const run = useMutation({
    mutationFn: ({ dryRun, courseIdForBody }: { dryRun: boolean; courseIdForBody: number }) =>
      importQuiz(JSON.parse(caqText), dryRun, courseIdForBody),
    onSuccess: async (result) => {
      setError(null)
      if (result.dry_run) {
        setPreview(result)
      } else {
        await queryClient.invalidateQueries({ queryKey: ['quizzes'] })
        onClose()
      }
    },
    onError: (err: Error) => setError(err.message),
  })

  const runPkg = useMutation({
    mutationFn: ({
      file,
      dryRun,
      courseIdForBody,
    }: {
      file: File
      dryRun: boolean
      courseIdForBody: number
    }) => importQpkg(file, dryRun, courseIdForBody),
    onSuccess: async (result, variables) => {
      setError(null)
      if (variables.dryRun) {
        setPreview(result)
      } else {
        await queryClient.invalidateQueries({ queryKey: ['quizzes'] })
        onClose()
      }
    },
    onError: (err: Error) => setError(err.message),
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <Card className="max-h-[90vh] w-full max-w-lg overflow-y-auto">
        <CardHeader>
          <CardTitle className="text-base">{t('quiz.importTitle')}</CardTitle>
          <p className="text-muted-foreground text-xs">{t('quiz.importHint')}</p>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex gap-1">
            {(['paste', 'file', 'inbox', 'author'] as const).map((entry) => (
              <button
                key={entry}
                type="button"
                onClick={() => setTab(entry)}
                className={cn(
                  'rounded-md px-2.5 py-1 text-xs transition-colors',
                  tab === entry
                    ? 'bg-subtle font-medium'
                    : 'text-muted-foreground hover:text-foreground'
                )}
              >
                {t(`quiz.importTab.${entry}`)}
              </button>
            ))}
          </div>
          {tab === 'paste' ? (
            <textarea
              className="bg-surface border-border h-48 w-full resize-none rounded-md border p-3 font-mono text-xs"
              placeholder={t('quiz.importPlaceholder')}
              value={caqText}
              onChange={(event) => setCaqText(event.target.value)}
            />
          ) : null}
          {courseId === null && tab !== 'author' ? (
            <CourseSelectField value={pickedCourse} onChange={setPickedCourse} />
          ) : null}
          {tab === 'file' ? (
            <PackageTab
              pkgInput={pkgInput}
              onPkg={(file) => {
                setPkgResult(file.name)
                setPkgFile(file)
                if (courseIdForRequest !== null) {
                  runPkg.mutate({ file, dryRun: true, courseIdForBody: courseIdForRequest })
                }
              }}
              pkgResult={pkgResult}
              pkgFile={pkgFile}
              runPkg={runPkg}
              courseIdForRequest={courseIdForRequest}
            />
          ) : null}
          {tab === 'inbox' ? (
            <InboxTab
              courseId={courseIdForRequest}
              onImported={async () => {
                await queryClient.invalidateQueries({ queryKey: ['quizzes'] })
                onClose()
              }}
            />
          ) : null}
          {tab === 'author' ? <AuthorTab /> : null}
          {tab === 'paste' ? (
            <>
              {error ? <p className="text-danger text-xs">{error}</p> : null}
              {preview && run.data ? (
                <div className="space-y-1">
                  <p className="text-xs">
                    {t('quiz.importResults', { valid: preview.valid, total: preview.total })}
                  </p>
                  {preview.results.map((result) => (
                    <p
                      key={result.index}
                      className={cn('text-xs', result.ok ? 'text-success' : 'text-danger')}
                    >
                      {result.ok ? '✓' : '✗'}{' '}
                      {t('quiz.questionN', { n: result.index + 1 })}
                      {result.problems.length > 0 ? `: ${result.problems.join(', ')}` : ''}
                    </p>
                  ))}
                </div>
              ) : null}
              <div className="flex justify-end gap-2">
                <Button variant="ghost" size="sm" onClick={onClose}>
                  {t('settings.cancel')}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!caqText.trim() || run.isPending || courseIdForRequest === null}
                  onClick={() => {
                    if (courseIdForRequest !== null) {
                      run.mutate({ dryRun: true, courseIdForBody: courseIdForRequest })
                    }
                  }}
                >
                  {t('quiz.validate')}
                </Button>
                <Button
                  size="sm"
                  disabled={!caqText.trim() || run.isPending || courseIdForRequest === null}
                  onClick={() => {
                    if (courseIdForRequest !== null) {
                      run.mutate({ dryRun: false, courseIdForBody: courseIdForRequest })
                    }
                  }}
                >
                  {t('quiz.importCommit')}
                </Button>
              </div>
            </>
          ) : null}
          {tab !== 'paste' && tab !== 'author' ? (
            <div className="flex justify-end">
              <Button variant="ghost" size="sm" onClick={onClose}>
                {t('settings.cancel')}
              </Button>
            </div>
          ) : null}
          {tab === 'author' ? (
            <div className="flex justify-end">
              <Button variant="ghost" size="sm" onClick={onClose}>
                {t('settings.cancel')}
              </Button>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  )
}

function PackageTab({
  pkgInput,
  onPkg,
  pkgResult,
  pkgFile,
  runPkg,
  courseIdForRequest,
}: {
  pkgInput: React.RefObject<HTMLInputElement | null>
  onPkg: (file: File) => void
  pkgResult: string | null
  pkgFile: File | null
  courseIdForRequest: number | null
  runPkg: {
    isPending: boolean
    mutate: (variables: { file: File; dryRun: boolean; courseIdForBody: number }) => void
    data?: ImportResult
  }
}) {
  const { t } = useTranslation()
  const [preview, setPreview] = useState<ImportResult | null>(null)
  useEffect(() => {
    if (runPkg.data && runPkg.data.dry_run) {
      setPreview(runPkg.data)
    }
  }, [runPkg.data])
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <input
          ref={pkgInput}
          type="file"
          accept=".qpkg"
          className="hidden"
          onChange={(event) => {
            const file = event.target.files?.[0]
            if (file) {
              onPkg(file)
            }
            event.target.value = ''
          }}
        />
        <Button
          variant="ghost"
          size="sm"
          disabled={runPkg.isPending}
          onClick={() => pkgInput.current?.click()}
        >
          <Package aria-hidden />
          {t('quiz.pickQpkg')}
        </Button>
        {pkgResult ? (
          <span className="text-muted-foreground truncate text-xs">{pkgResult}</span>
        ) : null}
      </div>
      {preview ? (
        <div className="space-y-1">
          <p className="text-xs">
            {t('quiz.importResults', { valid: preview.valid, total: preview.total })}
          </p>
          {preview.results.map((result) => (
            <p
              key={result.index}
              className={cn('text-xs', result.ok ? 'text-success' : 'text-danger')}
            >
              {result.ok ? '✓' : '✗'} {t('quiz.questionN', { n: result.index + 1 })}
              {result.problems.length > 0 ? `: ${result.problems.join(', ')}` : ''}
            </p>
          ))}
          <div className="flex justify-end">
            <Button
              size="sm"
              disabled={runPkg.isPending || pkgFile === null || courseIdForRequest === null}
              onClick={() => {
                if (pkgFile && courseIdForRequest !== null) {
                  runPkg.mutate({ file: pkgFile, dryRun: false, courseIdForBody: courseIdForRequest })
                }
              }}
            >
              {t('quiz.importCommit')}
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  )
}

function InboxTab({
  courseId,
  onImported,
}: {
  courseId: number | null
  onImported: () => Promise<void>
}) {
  const { t } = useTranslation()
  const entries = useQuery({ queryKey: ['inbox'], queryFn: scanInbox })
  const pathInfo = useQuery({ queryKey: ['inbox-path'], queryFn: inboxPath })
  const [message, setMessage] = useState<string | null>(null)

  const importFile = useMutation({
    mutationFn: ({ filename, courseIdForBody }: { filename: string; courseIdForBody: number }) =>
      importInboxFile(filename, courseIdForBody),
    onSuccess: async (result) => {
      setMessage(t('quiz.inboxImported', { valid: result.valid }))
      await onImported()
    },
    onError: (err: Error) => setMessage(err.message),
  })

  const list = entries.data ?? []
  return (
    <div className="space-y-2">
      <p className="text-muted-foreground text-xs">
        {t('quiz.inboxHint')}
      </p>
      <code className="bg-subtle block truncate rounded-md p-2 text-[11px]">
        {pathInfo.data ?? '…'}
      </code>
      {list.length === 0 ? (
        <p className="text-muted-foreground py-4 text-center text-xs">
          {t('quiz.inboxEmpty')}
        </p>
      ) : (
        list.map((entry) => (
          <div
            key={entry.filename}
            className="border-border flex items-center gap-2 rounded-md border px-2 py-1.5"
          >
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-medium">
                {entry.filename}
                {entry.title ? (
                  <span className="text-muted-foreground"> — {entry.title}</span>
                ) : null}
              </p>
              {entry.ok ? (
                <p className="text-success text-[11px]">
                  {t('quiz.inboxValid', { count: entry.question_count })}
                </p>
              ) : (
                <p className="text-danger truncate text-[11px]">
                  {entry.problems.slice(0, 2).join('; ')}
                </p>
              )}
            </div>
            <Button
              size="sm"
              variant={entry.ok ? 'default' : 'outline'}
              disabled={importFile.isPending || courseId === null}
              onClick={() => {
                if (courseId !== null) {
                  importFile.mutate({ filename: entry.filename, courseIdForBody: courseId })
                }
              }}
            >
              {t('quiz.importCommit')}
            </Button>
          </div>
        ))
      )}
      {message ? <p className="text-muted-foreground text-[11px]">{message}</p> : null}
    </div>
  )
}

function AuthorTab() {
  const { t } = useTranslation()
  const [topic, setTopic] = useState('')
  const [count, setCount] = useState(8)
  const [difficulty, setDifficulty] = useState(3)
  const [types, setTypes] = useState<string[]>(['single', 'equation'])
  const [copied, setCopied] = useState(false)

  const toggleType = (qtype: string) => {
    setTypes((current) =>
      current.includes(qtype) ? current.filter((entry) => entry !== qtype) : [...current, qtype]
    )
  }

  const prompt = t('quiz.authorPrompt', {
    topic: topic.trim() || t('quiz.authorAnyTopic'),
    count,
    difficulty,
    types: types.join(', ') || 'single',
  })

  return (
    <div className="space-y-3">
      <p className="text-muted-foreground text-xs">{t('quiz.authorHint')}</p>
      <input
        className="bg-surface border-border w-full rounded-md border px-3 py-2 text-sm"
        placeholder={t('quiz.authorTopicPlaceholder')}
        value={topic}
        onChange={(event) => setTopic(event.target.value)}
      />
      <div className="flex items-center gap-3 text-xs">
        <label className="flex items-center gap-1">
          {t('quiz.authorCount')}
          <input
            type="number"
            min={1}
            max={30}
            className="bg-surface border-border w-16 rounded-md border px-2 py-1"
            value={count}
            onChange={(event) => setCount(Number(event.target.value))}
          />
        </label>
        <label className="flex items-center gap-1">
          {t('quiz.authorDifficulty')}
          <input
            type="number"
            min={1}
            max={5}
            className="bg-surface border-border w-16 rounded-md border px-2 py-1"
            value={difficulty}
            onChange={(event) => setDifficulty(Number(event.target.value))}
          />
        </label>
      </div>
      <div className="flex flex-wrap gap-1">
        {['single', 'multi', 'truefalse', 'text', 'numeric', 'equation'].map((qtype) => (
          <button
            key={qtype}
            type="button"
            onClick={() => toggleType(qtype)}
            className={cn(
              'rounded-full border px-2.5 py-0.5 text-[11px]',
              types.includes(qtype)
                ? 'border-primary bg-primary/10 text-primary'
                : 'border-border text-muted-foreground'
            )}
          >
            {qtype}
          </button>
        ))}
      </div>
      <textarea
        readOnly
        className="bg-subtle h-44 w-full resize-none rounded-md border p-3 font-mono text-[11px]"
        value={prompt}
        aria-label={t('quiz.authorPromptLabel')}
      />
      <div className="flex justify-end gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={async () => {
            await navigator.clipboard?.writeText(prompt)
            setCopied(true)
          }}
        >
          {copied ? <Check className="text-success" aria-hidden /> : <ClipboardList aria-hidden />}
          {copied ? t('quiz.authorCopied') : t('quiz.authorCopy')}
        </Button>
      </div>
    </div>
  )
}
