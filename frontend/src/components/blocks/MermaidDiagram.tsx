import { useEffect, useId, useRef, useState } from 'react'

let mermaidInit: Promise<void> | null = null
let renderChain: Promise<unknown> = Promise.resolve()

function ensureMermaid() {
  if (!mermaidInit) {
    mermaidInit = import('mermaid').then((mod) => {
      mod.default.initialize({
        startOnLoad: false,
        theme: 'neutral',
        securityLevel: 'strict',
        suppressErrorRendering: true,
      })
    })
  }
  return mermaidInit
}

function runExclusive<T>(task: () => Promise<T>): Promise<T> {
  const run = renderChain.then(task, task)
  renderChain = run.then(
    () => undefined,
    () => undefined
  )
  return run
}

export function MermaidDiagram({
  code,
  onError,
  onSuccess,
}: {
  code: string
  onError?: (message: string) => void
  onSuccess?: () => void
}) {
  const reactId = useId()
  const [svg, setSvg] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  const onErrorRef = useRef(onError)
  const onSuccessRef = useRef(onSuccess)
  useEffect(() => {
    onErrorRef.current = onError
    onSuccessRef.current = onSuccess
  })

  useEffect(() => {
    let cancelled = false
    setSvg(null)
    setFailed(false)
    const renderId = `mermaid-${reactId.replace(/[^a-zA-Z0-9-]/g, '')}`
    ensureMermaid()
      .then(() => import('mermaid'))
      .then((mod) => runExclusive(() => mod.default.render(renderId, code)))
      .then((result) => {
        if (!cancelled) {
          setSvg(result.svg)
          onSuccessRef.current?.()
        }
      })
      .catch((error) => {
        document.getElementById(`d${renderId}`)?.remove()
        if (!cancelled) {
          setFailed(true)
          onErrorRef.current?.(error instanceof Error ? error.message : String(error))
        }
      })
    return () => {
      cancelled = true
    }
  }, [reactId, code])

  if (failed) {
    return <pre className="bg-subtle rounded-md p-3 font-mono text-xs">{code}</pre>
  }
  if (svg === null) {
    return <div className="bg-subtle h-16 animate-pulse rounded-md" />
  }
  return (
    <div
      className="my-0 w-full overflow-x-auto [&_svg]:max-w-full"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  )
}
