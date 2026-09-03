import { useState } from 'react'
import { Loader2, Play } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import {
  runCodeTests,
  type CodeRunPayload,
  type CodeTestCase,
} from '@/lib/pyodideRunner'

export type { CodeRunPayload } from '@/lib/pyodideRunner'
import { cn } from '@/lib/utils'

export interface CodeQuestionInput {
  starter_code: string
  tests: CodeTestCase[]
  timeout_ms?: number
}

export function isCodeInput(
  input: { widget: string; tests?: unknown } | null | undefined,
): input is CodeQuestionInput & { widget: string } {
  return input?.widget === 'code' && Array.isArray(input.tests)
}

export function codeResponseComplete(
  response: CodeRunPayload | null,
  input: CodeQuestionInput,
): boolean {
  return !!response?.results && response.results.length === input.tests.length
}

export function CodeAnswer({
  input,
  response,
  onChange,
  disabled,
  onRun,
}: {
  input: CodeQuestionInput
  response: CodeRunPayload | null
  onChange?: (next: CodeRunPayload) => void
  disabled?: boolean
  onRun?: () => Promise<CodeRunPayload>
}) {
  const { t } = useTranslation()
  const [pending, setPending] = useState(false)
  const interactive = onChange !== undefined && disabled !== true
  const code = response?.code ?? input.starter_code ?? ''
  const runner = onRun ?? (() => runCodeTests(code, input.tests))
  const hasRun = codeResponseComplete(response, input)

  return (
    <div className="space-y-2">
      <textarea
        className="border-border bg-surface min-h-40 w-full rounded-md border px-3 py-2 font-mono text-sm"
        aria-label={t('quiz.codeEditorLabel')}
        spellCheck={false}
        disabled={!interactive}
        value={code}
        onChange={(event) =>
          onChange?.({ code: event.target.value, results: [] })
        }
      />
      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={!interactive || pending}
          onClick={() => {
            setPending(true)
            void runner()
              .then((payload) => onChange?.(payload))
              .catch(() => undefined)
              .finally(() => setPending(false))
          }}
        >
          {pending ? <Loader2 className="animate-spin" aria-hidden /> : <Play aria-hidden />}
          {t('quiz.codeRun')}
        </Button>
        {hasRun ? (
          <span
            className={cn(
              'rounded-full px-2 py-0.5 text-[11px]',
              response!.results.every((entry) => entry.passed)
                ? 'bg-success/15 text-success'
                : 'bg-warning/15 text-warning',
            )}
          >
            {t('quiz.codePassed', {
              passed: response!.results.filter((entry) => entry.passed).length,
              total: input.tests.length,
            })}
          </span>
        ) : (
          <span className="text-muted-foreground text-xs">
            {t('quiz.codeRunHint')}
          </span>
        )}
      </div>
      {hasRun ? (
        <ol className="space-y-1">
          {input.tests.map((test, index) => {
            const result = response!.results[index]
            return (
              <li
                key={index}
                className={cn(
                  'border-border rounded-md border px-3 py-2 text-xs',
                  result?.passed
                    ? 'border-success/40 bg-success/10'
                    : 'border-danger/40 bg-danger/10',
                )}
              >
                <code className="font-mono">{test.call}</code>
                <span className="text-muted-foreground ml-2">
                  → {result?.passed ? t('quiz.codePass') : t('quiz.codeFail')}
                </span>
                {!result?.passed && result?.output !== undefined ? (
                  <p className="text-muted-foreground mt-1 font-mono">
                    {t('quiz.codeGot')}: {result.output}
                  </p>
                ) : null}
              </li>
            )
          })}
        </ol>
      ) : null}
    </div>
  )
}
