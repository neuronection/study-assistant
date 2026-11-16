import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import {
  Camera,
  Check,
  Clipboard,
  FileText,
  History,
  Loader2,
  Sigma,
  Sparkles,
  Trash2,
  TriangleAlert,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { BlockRenderer } from '@/components/blocks/BlockRenderer'
import type { Block } from '@/components/blocks/types'
import { MathInput } from '@/components/math/MathInput'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorBanner } from '@/components/ErrorBanner'
import {
  checkSolveVariant,
  deleteSolve,
  recognizeSolve,
  saveSolveNote,
  recordActivation,
  solveHistory,
  solveProblem,
  solveVariants,
  type SolveCheck,
  type SolveEntry,
  type SolveVariant,
} from '@/lib/api'
import { cn } from '@/lib/utils'

type Mode = 'typed' | 'paste' | 'photo'

function mathBlock(latex: string): Block[] {
  return [{ type: 'text', md: `$$ ${latex} $$` }] as Block[]
}

function StepRow({ step }: { step: NonNullable<SolveEntry['result']['steps']>[number] }) {
  const { t } = useTranslation()
  return (
    <li className="border-border rounded-md border p-3">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">{step.title ?? step.op}</span>
        {step.verified ? (
          <span className="bg-success/10 text-success inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px]">
            <Check className="size-3" aria-hidden />
            {t('solve.verified')}
          </span>
        ) : (
          <span className="bg-danger/10 text-danger inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px]">
            <TriangleAlert className="size-3" aria-hidden />
            {t('solve.unverified')}
          </span>
        )}
        {step.check ? (
          <span className="text-muted-foreground text-[10px]">{step.check}</span>
        ) : null}
      </div>
      <div className="grid gap-2 sm:grid-cols-[1fr_auto_1fr] sm:items-center">
        <div className="bg-subtle rounded p-2 text-sm">
          {step.before ? <BlockRenderer blocks={mathBlock(step.before)} /> : null}
        </div>
        <span className="text-muted-foreground text-center" aria-hidden>
          →
        </span>
        <div className="bg-subtle rounded p-2 text-sm">
          {step.after ? <BlockRenderer blocks={mathBlock(step.after)} /> : null}
        </div>
      </div>
      {step.detail ? <p className="text-muted-foreground mt-2 text-xs">{step.detail}</p> : null}
    </li>
  )
}

function VariantPractice({ entry }: { entry: SolveEntry }) {
  const { t } = useTranslation()
  const [variants, setVariants] = useState<SolveVariant[]>([])
  const [responses, setResponses] = useState<Record<number, string>>({})
  const [checks, setChecks] = useState<Record<number, SolveCheck>>({})
  const [loaded, setLoaded] = useState(false)
  useEffect(() => {
    setVariants([])
    setResponses({})
    setChecks({})
    setLoaded(false)
  }, [entry.id])
  const load = useMutation({
    mutationFn: () => solveVariants(entry.id),
    onSuccess: (rows) => {
      setVariants(rows)
      setLoaded(true)
    },
  })
  const check = useMutation({
    mutationFn: ({ index, response }: { index: number; response: string }) =>
      checkSolveVariant(entry.id, index, response),
    onSuccess: (result, variables) =>
      setChecks((current) => ({ ...current, [variables.index]: result })),
  })

  if (variants.length === 0) {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={load.isPending || !entry.verified}
          onClick={() => load.mutate()}
        >
          {load.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <Sparkles aria-hidden />}
          {t('solve.generateVariants')}
        </Button>
        {loaded ? (
          <span className="text-muted-foreground text-[11px]">{t('solve.variantsEmpty')}</span>
        ) : null}
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">{t('solve.variants')}</h3>
        <span className="text-muted-foreground text-[11px]">{t('solve.variantsHint')}</span>
      </div>
      {variants.map((variant) => {
        const result = checks[variant.index]
        return (
          <div key={variant.index} className="border-border rounded-md border p-3">
            <p className="mb-2 text-sm">
              <BlockRenderer blocks={[{ type: 'text', md: variant.prompt }] as Block[]} />
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <input
                value={responses[variant.index] ?? ''}
                onChange={(event) =>
                  setResponses((current) => ({ ...current, [variant.index]: event.target.value }))
                }
                aria-label={t('solve.variantAnswer', { n: variant.index + 1 })}
                className="bg-surface border-border min-w-0 flex-1 rounded-md border px-2 py-1 text-sm"
                placeholder={t('solve.variantPlaceholder')}
              />
              <Button
                size="sm"
                disabled={check.isPending || !(responses[variant.index] ?? '').trim()}
                onClick={() =>
                  check.mutate({
                    index: variant.index,
                    response: responses[variant.index] ?? '',
                  })
                }
              >
                {t('solve.check')}
              </Button>
            </div>
            {result ? (
              <p
                className={cn(
                  'mt-2 text-xs',
                  result.correct ? 'text-success' : 'text-danger',
                )}
                role="status"
              >
                {result.correct
                  ? t('solve.variantCorrect')
                  : t('solve.variantIncorrect', { answer: result.expected ?? '' })}
              </p>
            ) : null}
          </div>
        )
      })}
    </div>
  )
}

function ResultCard({
  entry,
  onSaved,
}: {
  entry: SolveEntry
  onSaved: (noteId: string) => void
}) {
  const { t } = useTranslation()
  const result = entry.result
  const save = useMutation({
    mutationFn: () => saveSolveNote(entry.id),
    onSuccess: (saved) => onSaved(saved.note_id),
  })
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    if (!result.answer_latex) {
      return
    }
    await navigator.clipboard.writeText(result.answer_latex)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1500)
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <Sigma className="text-primary size-4" aria-hidden />
            {result.title ?? t('solve.resultTitle')}
          </CardTitle>
          <span
            className={cn(
              'rounded-full px-2 py-0.5 text-[11px]',
              result.verified
                ? 'bg-success/10 text-success'
                : 'bg-warning/10 text-warning',
            )}
          >
            {result.verified ? t('solve.verifiedAnswer') : t('solve.unverifiedAnswer')}
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {result.answer_latex ? (
          <div className="bg-subtle rounded-lg p-4 text-lg">
            <BlockRenderer blocks={mathBlock(result.answer_latex)} />
          </div>
        ) : null}
        {result.message ? (
          <div className="border-warning/40 bg-warning/10 text-warning rounded-lg border p-3 text-sm">
            {result.message}
          </div>
        ) : null}
        {result.steps && result.steps.length > 0 ? (
          <div className="space-y-2">
            <h3 className="text-sm font-semibold">{t('solve.steps')}</h3>
            <ol className="space-y-2">
              {result.steps.map((step, index) => (
                <StepRow key={`${step.op}-${index}`} step={step} />
              ))}
            </ol>
          </div>
        ) : null}
        {result.assumptions && result.assumptions.length > 0 ? (
          <div>
            <h3 className="text-sm font-semibold">{t('solve.assumptions')}</h3>
            <ul className="text-muted-foreground mt-1 list-disc space-y-1 pl-5 text-xs">
              {result.assumptions.map((assumption) => (
                <li key={assumption}>{assumption}</li>
              ))}
            </ul>
          </div>
        ) : null}
        <div className="flex flex-wrap gap-2">
          {result.answer_latex ? (
            <Button variant="ghost" size="sm" onClick={() => void copy()}>
              <Clipboard className="size-3.5" aria-hidden />
              {copied ? t('solve.copied') : t('solve.copyLatex')}
            </Button>
          ) : null}
          <Button
            variant="outline"
            size="sm"
            disabled={!entry.verified || save.isPending || entry.note_id !== null}
            onClick={() => save.mutate()}
          >
            {save.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <FileText aria-hidden />}
            {entry.note_id ? t('solve.savedNote') : t('solve.saveNote')}
          </Button>
          <VariantPractice entry={entry} />
        </div>
        <ErrorBanner message={save.isError ? (save.error as Error).message : null} />
      </CardContent>
    </Card>
  )
}

export function SolvePage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [mode, setMode] = useState<Mode>('typed')
  const [input, setInput] = useState('')
  const [entry, setEntry] = useState<SolveEntry | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [savedNoteId, setSavedNoteId] = useState<string | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  const history = useQuery({
    queryKey: ['solve-history'],
    queryFn: () => solveHistory(20),
  })
  const solve = useMutation({
    mutationFn: () => solveProblem({ input_text: input, input_kind: inputKind(mode) }),
    onSuccess: (created) => {
      if (created.verified) {
        void recordActivation('solve_completed', { surface: 'problem_desk' })
      }
      setEntry(created)
      setError(null)
      setSavedNoteId(null)
      void queryClient.invalidateQueries({ queryKey: ['solve-history'] })
    },
    onError: (err: Error) => setError(err.message),
  })
  const recognize = useMutation({
    mutationFn: (file: File) => recognizeSolve(file),
    onSuccess: (result) => {
      const candidate = result.latex_candidates.at(-1) ?? result.text
      setInput(candidate)
      setMode('typed')
      setError(null)
    },
    onError: (err: Error) => setError(err.message),
  })
  const remove = useMutation({
    mutationFn: (id: string) => deleteSolve(id),
    onSuccess: async () => {
      setEntry(null)
      await queryClient.invalidateQueries({ queryKey: ['solve-history'] })
    },
  })

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
        event.preventDefault()
        if (input.trim() && !solve.isPending) {
          solve.mutate()
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [input, solve])

  return (
    <div className="mx-auto w-full max-w-6xl space-y-6 p-4 md:p-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold">
            <Sigma className="text-primary size-5" aria-hidden />
            {t('solve.title')}
          </h1>
          <p className="text-muted-foreground mt-1 max-w-2xl text-sm">{t('solve.subtitle')}</p>
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="space-y-4">
          <Card>
            <CardContent className="space-y-3 p-4">
              <div className="flex flex-wrap gap-1">
                {(['typed', 'paste', 'photo'] as const).map((item) => (
                  <button
                    key={item}
                    type="button"
                    aria-pressed={mode === item}
                    onClick={() => setMode(item)}
                    className={cn(
                      'rounded-full border px-3 py-1 text-xs transition-colors',
                      mode === item
                        ? 'border-primary bg-primary text-primary-foreground'
                        : 'border-border hover:bg-subtle',
                    )}
                  >
                    {t(`solve.mode.${item}`)}
                  </button>
                ))}
              </div>

              {mode === 'typed' ? (
                <div className="border-border rounded-md border p-3">
                  <MathInput value={input} onChange={setInput} />
                  <p className="text-muted-foreground mt-2 text-[11px]">{t('solve.mathHint')}</p>
                </div>
              ) : null}
              {mode === 'paste' ? (
                <textarea
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  rows={3}
                  aria-label={t('solve.pasteLabel')}
                  placeholder={t('solve.placeholder')}
                  className="bg-surface border-border w-full rounded-md border px-3 py-2 font-mono text-sm"
                />
              ) : null}
              {mode === 'photo' ? (
                <div className="space-y-2">
                  <input
                    ref={fileInput}
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={(event) => {
                      const file = event.target.files?.[0]
                      if (file) {
                        recognize.mutate(file)
                      }
                      event.target.value = ''
                    }}
                  />
                  <Button
                    variant="outline"
                    onClick={() => fileInput.current?.click()}
                    disabled={recognize.isPending}
                  >
                    {recognize.isPending ? (
                      <Loader2 className="animate-spin" aria-hidden />
                    ) : (
                      <Camera aria-hidden />
                    )}
                    {t('solve.choosePhoto')}
                  </Button>
                  <p className="text-muted-foreground text-[11px]">{t('solve.photoHint')}</p>
                </div>
              ) : null}

              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-muted-foreground text-[11px]">{t('solve.shortcut')}</p>
                <Button
                  disabled={!input.trim() || solve.isPending}
                  onClick={() => solve.mutate()}
                >
                  {solve.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <Sigma aria-hidden />}
                  {t('solve.solve')}
                </Button>
              </div>
              <ErrorBanner message={error} />
            </CardContent>
          </Card>

          {entry ? (
            <ResultCard
              entry={entry}
              onSaved={(noteId) => {
                setSavedNoteId(noteId)
                setEntry((current) => (current ? { ...current, note_id: noteId } : current))
              }}
            />
          ) : (
            <Card>
              <CardContent className="p-6">
                <EmptyState title={t('solve.empty')} />
              </CardContent>
            </Card>
          )}
          {savedNoteId ? (
            <p className="text-success text-xs">
              {t('solve.noteSaved')}{' '}
              <button
                type="button"
                className="underline"
                onClick={() => void navigate({ to: '/note/$noteId', params: { noteId: savedNoteId } })}
              >
                {t('solve.openNote')}
              </button>
            </p>
          ) : null}
        </div>

        <aside className="space-y-3">
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <History className="size-4" aria-hidden />
            {t('solve.history')}
          </h2>
          {history.data && history.data.length === 0 ? (
            <p className="text-muted-foreground text-xs">{t('solve.historyEmpty')}</p>
          ) : null}
          <ul className="space-y-1.5">
            {(history.data ?? []).map((row) => (
              <li key={row.id}>
                <button
                  type="button"
                  onClick={() => {
                    setEntry(row)
                    setSavedNoteId(row.note_id)
                    setError(null)
                  }}
                  className={cn(
                    'border-border hover:bg-subtle w-full rounded-md border px-2 py-1.5 text-left text-xs',
                    entry?.id === row.id && 'border-primary/60 bg-primary/5',
                  )}
                >
                  <span className="line-clamp-2 block">{row.input_text}</span>
                  <span className="text-muted-foreground mt-1 flex items-center justify-between gap-2 text-[10px]">
                    <span>{row.intent}</span>
                    <span>{row.verified ? t('solve.verified') : t('solve.unverified')}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
          {entry ? (
            <Button
              variant="ghost"
              size="sm"
              className="text-danger"
              disabled={remove.isPending}
              onClick={() => remove.mutate(entry.id)}
            >
              <Trash2 className="size-3.5" aria-hidden />
              {t('solve.deleteEntry')}
            </Button>
          ) : null}
        </aside>
      </div>
    </div>
  )
}

function inputKind(mode: Mode): string {
  if (mode === 'paste') {
    return 'pasted'
  }
  if (mode === 'photo') {
    return 'photo'
  }
  return 'typed'
}
