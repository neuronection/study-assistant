import { useEffect, useId, useState } from 'react'

type Board = ReturnType<typeof import('jsxgraph')['JSXGraph']['initBoard']>

export function JsxGraphBoard({ script }: { script: string }) {
  const reactId = useId()
  const boardId = `jxg-${reactId.replace(/[^a-zA-Z0-9-]/g, '')}`
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    let board: Board | undefined
    import('jsxgraph')
      .then(({ JSXGraph }) => {
        if (cancelled) return
        board = JSXGraph.initBoard(boardId, {
          boundingbox: [-8, 6, 8, -6],
          axis: true,
          showCopyright: false,
          showNavigation: false,
        })
        board.jc.parse(script)
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })
    return () => {
      cancelled = true
      const current = board
      if (current) {
        import('jsxgraph')
          .then(({ JSXGraph }) => JSXGraph.freeBoard(current))
          .catch(() => {})
      }
    }
  }, [boardId, script])

  if (failed) {
    return <pre className="bg-subtle rounded-md p-3 font-mono text-xs">{script}</pre>
  }
  return (
    <div className="min-w-0 overflow-hidden">
      <div id={boardId} className="h-72 w-full" />
    </div>
  )
}
