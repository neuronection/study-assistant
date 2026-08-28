import { useEffect, useId, useState } from 'react'

let mermaidInit: Promise<void> | null = null

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

function sweepStrayErrorDiagrams(): void {
  document
    .querySelectorAll<HTMLElement>('body > [id^="dmermaid-"]')
    .forEach((node) => node.remove())
}

export function MermaidDiagram({ code }: { code: string }) {
  const reactId = useId()
  const [svg, setSvg] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    setSvg(null)
    setFailed(false)
    ensureMermaid()
      .then(() => import('mermaid'))
      .then((mod) =>
        mod.default.render(`mermaid-${reactId.replace(/[^a-zA-Z0-9-]/g, '')}`, code)
      )
      .then((result) => {
        if (!cancelled) {
          setSvg(result.svg)
        }
      })
      .catch(() => {
        sweepStrayErrorDiagrams()
        if (!cancelled) {
          setFailed(true)
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
