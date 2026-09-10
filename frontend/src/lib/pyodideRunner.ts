import { loadPyodide, type PyodideInterface } from 'pyodide'
import pyodideWasmUrl from 'pyodide/pyodide.asm.wasm?url'

export interface CodeTestCase {
  call: string
  expected: unknown
  expected_stdout?: string | null
}

export interface CodeCaseResult {
  call: string
  passed: boolean
  output?: string
  stdout?: string
}

export interface CodeRunPayload {
  code: string
  results: CodeCaseResult[]
}

let pyodidePromise: Promise<PyodideInterface> | null = null

function indexURL(): string {
  return pyodideWasmUrl.slice(0, pyodideWasmUrl.lastIndexOf('/') + 1)
}

export async function getPyodide(): Promise<PyodideInterface> {
  pyodidePromise ??= loadPyodide({ indexURL: indexURL() })
  return pyodidePromise
}

export function resetPyodide(): void {
  pyodidePromise = null
}

export function normalizeOutputText(value: string): string {
  return value
    .trim()
    .split('\n')
    .map((line) => line.trimEnd())
    .join('\n')
}

export function valuesMatch(expected: unknown, actual: unknown): boolean {
  if (typeof expected === 'number' && typeof actual === 'number') {
    return Math.abs(actual - expected) <= 1e-6 * Math.max(1, Math.abs(expected))
  }
  if (typeof expected === 'string' && typeof actual === 'string') {
    return normalizeOutputText(expected) === normalizeOutputText(actual)
  }
  if (Array.isArray(expected) && Array.isArray(actual)) {
    return (
      expected.length === actual.length &&
      expected.every((entry, index) => valuesMatch(entry, actual[index]))
    )
  }
  return expected === actual
}

function safeJsonParse(text: string): unknown {
  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}

export async function runCodeTests(
  code: string,
  tests: CodeTestCase[],
): Promise<CodeRunPayload> {
  const pyodide = await getPyodide()
  pyodide.runPython(code)
  const results: CodeCaseResult[] = []
  for (const test of tests) {
    const stdoutChunks: string[] = []
    pyodide.setStdout({ batched: (chunk: string) => void stdoutChunks.push(chunk) })
    let output: string | undefined
    let failed = false
    try {
      output = pyodide.runPython(
        `__import__('json').dumps(${test.call})`,
      ) as string
    } catch {
      failed = true
    }
    pyodide.setStdout({})
    const stdout = stdoutChunks.join('\n')
    const passed =
      !failed &&
      output !== undefined &&
      valuesMatch(test.expected, safeJsonParse(output)) &&
      (test.expected_stdout == null ||
        normalizeOutputText(test.expected_stdout) === normalizeOutputText(stdout))
    results.push({ call: test.call, passed, output, stdout })
  }
  return { code, results }
}
