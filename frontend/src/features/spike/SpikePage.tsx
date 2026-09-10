import { useEffect, useRef, useState } from 'react'
import type { MathfieldElement } from 'mathlive'
import { useTranslation } from 'react-i18next'

import { BlockRenderer } from '@/components/blocks/BlockRenderer'
import type { Block } from '@/components/blocks/types'
import { DrawCanvas, type Stroke } from '@/components/canvas/DrawCanvas'
import { ensureMathlive } from '@/components/math/MathInput'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

const MERMAID_SAMPLE = 'graph LR\n  A[Upload] --> B[OCR]\n  B --> C[Extraction]\n  C --> D[Search index]'

const KATEX_BLOCKS: Block[] = [
  { type: 'math', latex: '\\int_0^1 x^2\\,dx = \\tfrac{1}{3}', display: true },
  {
    type: 'text',
    md: 'Inline math: the chain rule $\\frac{dy}{dx} = f\'(g(x))\\,g\'(x)$ inside markdown.',
  },
]

function MathField({
  initial,
  onChange,
}: {
  initial: string
  onChange: (value: string) => void
}) {
  const ref = useRef<MathfieldElement>(null)
  const [ready, setReady] = useState(
    () => typeof window !== 'undefined' && window.customElements.get('math-field') != null
  )

  useEffect(() => {
    if (ready) {
      return undefined
    }
    let cancelled = false
    void ensureMathlive().then(() => {
      if (!cancelled) {
        setReady(true)
      }
    })
    return () => {
      cancelled = true
    }
  }, [ready])

  useEffect(() => {
    const element = ref.current
    if (!element) {
      return
    }
    element.value = initial
    const handler = () => onChange(element.value)
    element.addEventListener('input', handler)
    return () => element.removeEventListener('input', handler)
  }, [initial, onChange, ready])

  if (!ready) {
    return <div className="bg-subtle h-9 animate-pulse rounded-md" aria-hidden />
  }
  return <math-field ref={ref} style={{ display: 'block' }} />
}

export function CanvasCard() {
  const { t } = useTranslation()
  const [strokes, setStrokes] = useState<Stroke[]>([])
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">{t('spike.canvas')}</CardTitle>
        <CardDescription>{t('spike.canvasHint')}</CardDescription>
      </CardHeader>
      <CardContent>
        <DrawCanvas strokes={strokes} onChange={setStrokes} />
      </CardContent>
    </Card>
  )
}

export function SpikeContent() {
  const { t } = useTranslation()
  const [latex, setLatex] = useState('\\frac{x^2+1}{x-2}')

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t('spike.katex')}</CardTitle>
          <CardDescription>{t('spike.katexHint')}</CardDescription>
        </CardHeader>
        <CardContent>
          <BlockRenderer blocks={KATEX_BLOCKS} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t('spike.mermaid')}</CardTitle>
          <CardDescription>{t('spike.mermaidHint')}</CardDescription>
        </CardHeader>
        <CardContent>
          <BlockRenderer blocks={[{ type: 'diagram', mermaid: MERMAID_SAMPLE }]} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t('spike.mathlive')}</CardTitle>
          <CardDescription>{t('spike.mathliveHint')}</CardDescription>
        </CardHeader>
        <CardContent>
          <MathField initial={latex} onChange={setLatex} />
          <p className="text-muted-foreground mt-3 font-mono text-xs">
            {t('spike.mathliveValue')}: {latex}
          </p>
        </CardContent>
      </Card>

      <CanvasCard />
    </div>
  )
}

export function SpikePage() {
  const { t } = useTranslation()

  return (
    <div className="mx-auto max-w-4xl space-y-4 p-8">
      <header>
        <h1 className="text-2xl font-semibold">{t('spike.title')}</h1>
        <p className="text-muted-foreground mt-1 text-sm">{t('spike.subtitle')}</p>
      </header>

      <SpikeContent />
    </div>
  )
}
