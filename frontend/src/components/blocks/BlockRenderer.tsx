import katex from 'katex'
import { defaultUrlTransform, type Components } from 'react-markdown'
import { isValidElement, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import ReactMarkdown from 'react-markdown'
import rehypeKatex from 'rehype-katex'
import remarkMath from 'remark-math'

import { Copy as CopyIcon } from 'lucide-react'

import { cn } from '@/lib/utils'
import { EntityMention } from '@/features/ai/EntityMention'
import type { MentionRef } from '@/lib/api'
import { MermaidDiagram } from './MermaidDiagram'
import { PlotlyChart } from './PlotlyChart'
import { JsxGraphBoard } from './JsxGraphBoard'
import { getWidgetComponent } from '../widgets/registry'

import type {
  Block,
  ChartBlock,
  CodeBlock,
  DiagramBlock,
  DrawingBlock,
  GeoBlock,
  ImageBlock,
  MathBlock,
  MentionBlock,
  TableBlock,
  TextBlock,
  WidgetBlock,
} from './types'

export interface DrawingMeta {
  id: number
  png_sha: string | null
  ocr_markdown: string | null
}

export type DrawingResolver = (id: number) => DrawingMeta | undefined



const MENTION_TOKEN_RE = /\[(M|N|C|T|Q|E)(\d+)\]/g

function mentionsToMarkdownLinks(md: string, mentions: MentionRef[]): string {
  const known = new Map(mentions.map((mention) => [mention.ref, mention]))
  return md.replace(MENTION_TOKEN_RE, (token, letter: string, id: string) => {
    const mention = known.get(`${letter}${id}`)
    return mention ? `[@${mention.ref}](mention:${mention.ref} "${mention.title}")` : token
  })
}

function MentionLink({
  href,
  children,
  mentions,
}: {
  href?: string
  children?: ReactNode
  mentions: MentionRef[]
}) {
  if (href?.startsWith('mention:')) {
    const mention = mentions.find((entry) => entry.ref === href.slice('mention:'.length))
    if (mention) {
      return <EntityMention mention={mention} />
    }
  }
  return <a href={href}>{children}</a>
}

function mentionUrlTransform(url: string) {
  if (url.startsWith('mention:')) {
    return url
  }
  return defaultUrlTransform(url)
}

function FenceAwarePre({ children }: { children?: ReactNode }) {
  const child = Array.isArray(children) ? children[0] : children
  if (isValidElement<{ className?: string; children?: ReactNode }>(child)) {
    const className = child.props.className ?? ''
    if (className.includes('language-mermaid')) {
      const inner = child.props.children
      const code = (Array.isArray(inner) ? inner.join('') : String(inner ?? '')).replace(
        /\n$/,
        ''
      )
      return <MermaidDiagram code={code} />
    }
  }
  const inner = isValidElement<{ children?: ReactNode }>(child)
    ? child.props.children
    : undefined
  const code = Array.isArray(inner) ? inner.join('') : String(inner ?? '')
  return (
    <CodeSurface code={code.replace(/\n$/, '')}>
      <pre>{children}</pre>
    </CodeSurface>
  )
}

function TextBlockView({ block }: { block: TextBlock }) {
  const mentions = block.mentions ?? []
  const markdown = mentions.length
    ? mentionsToMarkdownLinks(block.md, mentions)
    : block.md
  const components: Components = {
    pre: ({ children }) => <FenceAwarePre>{children}</FenceAwarePre>,
  }
  if (mentions.length) {
    components.a = ({ href, children }) => (
      <MentionLink href={href} mentions={mentions}>
        {children}
      </MentionLink>
    )
  }
  return (
    <div className="text-sm leading-relaxed">
      <ReactMarkdown
        remarkPlugins={[remarkMath]}
        rehypePlugins={[rehypeKatex]}
        urlTransform={mentionUrlTransform}
        components={components}
      >
        {markdown}
      </ReactMarkdown>
    </div>
  )
}

function MentionBlockView({ block }: { block: MentionBlock }) {
  return (
    <span className="inline">
      <EntityMention
        mention={{
          ref: block.ref,
          kind: block.kind,
          id: block.id,
          title: block.title,
          course_id: block.course_id ?? null,
        }}
      />
    </span>
  )
}

function MathBlockView({ block }: { block: MathBlock }) {
  const html = katex.renderToString(block.latex, {
    displayMode: block.display ?? false,
    throwOnError: false,
    strict: false,
  })
  return (
    <div
      className={cn('py-1', block.display && 'my-3 overflow-x-auto text-center')}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}

function DiagramBlockView({ block }: { block: DiagramBlock }) {
  return <MermaidDiagram code={block.mermaid} />
}

function ChartBlockView({ block }: { block: ChartBlock }) {
  return <PlotlyChart figure={block.plotly ?? {}} />
}

function ImageBlockView({ block }: { block: ImageBlock }) {
  const { t } = useTranslation()
  return (
    <div className="border-border text-muted-foreground flex h-32 items-center justify-center rounded-md border border-dashed text-xs">
      {t('blocks.imagePlaceholder')}
      {block.alt ? ` · ${block.alt}` : null}
    </div>
  )
}

function TableBlockView({ block }: { block: TableBlock }) {
  const [header, ...rows] = block.rows
  return (
    <figure className="my-3">
      <div className="overflow-x-auto">
        <table className="border-border w-full border-collapse text-sm">
          {header ? (
            <thead>
              <tr>
                {header.map((cell, i) => (
                  <th key={i} className="border-border bg-subtle border px-3 py-1.5 text-left font-medium">
                    {cell}
                  </th>
                ))}
              </tr>
            </thead>
          ) : null}
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}>
                {row.map((cell, j) => (
                  <td key={j} className="border-border border px-3 py-1.5">
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {block.caption ? (
        <figcaption className="text-muted-foreground mt-1 text-center text-xs">{block.caption}</figcaption>
      ) : null}
    </figure>
  )
}

function CopyButton({ text }: { text: string }) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)
  return (
    <button
      type="button"
      title={copied ? t('blocks.copied') : t('blocks.copyCode')}
      aria-label={copied ? t('blocks.copied') : t('blocks.copyCode')}
      className="bg-surface border-border text-muted-foreground hover:text-foreground absolute right-1.5 top-1.5 rounded border p-1 opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100"
      onClick={() => {
        void navigator.clipboard?.writeText(text).then(() => {
          setCopied(true)
          window.setTimeout(() => setCopied(false), 1500)
        })
      }}
    >
      <CopyIcon className="size-3" aria-hidden />
    </button>
  )
}

function CodeSurface({ code, children }: { code: string; children: ReactNode }) {
  return (
    <div className="group relative">
      <CopyButton text={code} />
      <pre className="bg-subtle my-3 overflow-x-auto rounded-md p-3 font-mono text-xs">
        {children}
      </pre>
    </div>
  )
}

function CodeBlockView({ block }: { block: CodeBlock }) {
  return (
    <CodeSurface code={block.code}>
      <code>{block.code}</code>
    </CodeSurface>
  )
}

function GeoBlockView({ block }: { block: GeoBlock }) {
  const { t } = useTranslation()
  const script = block.jsxgraph ?? ''
  if (!script.trim()) {
    return (
      <div className="border-border bg-subtle text-muted-foreground flex h-32 items-center justify-center rounded-md border border-dashed text-xs">
        {t('blocks.geoPlaceholder')}
      </div>
    )
  }
  return <JsxGraphBoard script={script} />
}

function DrawingBlockView({
  block,
  resolve,
}: {
  block: DrawingBlock
  resolve?: DrawingResolver
}) {
  const { t } = useTranslation()
  const meta = resolve?.(block.drawing_id)
  if (meta?.png_sha) {
    return (
      <figure className="my-3 space-y-1">
        <img
          src={`/api/v1/blobs/${meta.png_sha}`}
          alt={t('notes.drawingAlt')}
          className="border-border bg-white w-full rounded-md border"
        />
        {meta.ocr_markdown ? (
          <details className="text-xs">
            <summary className="text-muted-foreground cursor-pointer">
              {t('notes.transcript')}
            </summary>
            <pre className="bg-subtle mt-1 rounded-md p-2 font-mono text-[11px] whitespace-pre-wrap">
              {meta.ocr_markdown}
            </pre>
          </details>
        ) : null}
      </figure>
    )
  }
  return (
    <div className="border-border bg-subtle text-muted-foreground my-3 rounded-md border border-dashed p-3 text-xs">
      {t('notes.drawingInlinePlaceholder', { id: block.drawing_id })}
    </div>
  )
}

function WidgetBlockView({
  block,
  onStateChange,
}: {
  block: WidgetBlock
  onStateChange?: (widgetId: string, state: Record<string, unknown>) => void
}) {
  const { t } = useTranslation()
  const Component = getWidgetComponent(block.widget)
  if (!Component) {
    return (
      <div className="border-border bg-subtle text-muted-foreground rounded-md border border-dashed p-3 text-xs">
        {t('blocks.unsupported')}: {block.widget}
      </div>
    )
  }
  return (
    <Component
      id={block.id}
      props={block.props ?? {}}
      state={block.state ?? {}}
      onStateChange={
        onStateChange ? (next) => onStateChange(block.id, next) : undefined
      }
    />
  )
}

function UnknownBlockView({ block }: { block: Block }) {
  const { t } = useTranslation()
  return (
    <div className="border-border bg-subtle text-muted-foreground rounded-md border border-dashed p-3 text-xs">
      {t('blocks.unsupported')}: {block.type}
    </div>
  )
}

export function BlockRenderer({
  blocks,
  className,
  resolveDrawing,
  onWidgetStateChange,
}: {
  blocks: Block[]
  className?: string
  resolveDrawing?: DrawingResolver
  onWidgetStateChange?: (widgetId: string, state: Record<string, unknown>) => void
}) {
  return (
    <div className={cn('space-y-2', className)}>
      {blocks.map((block, i) => {
        switch (block.type) {
          case 'text':
            return <TextBlockView key={i} block={block as TextBlock} />
          case 'mention':
            return <MentionBlockView key={i} block={block as MentionBlock} />
          case 'math':
            return <MathBlockView key={i} block={block as MathBlock} />
          case 'diagram':
            return <DiagramBlockView key={i} block={block as DiagramBlock} />
          case 'chart':
            return <ChartBlockView key={i} block={block as ChartBlock} />
          case 'image':
            return <ImageBlockView key={i} block={block as ImageBlock} />
          case 'table':
            return <TableBlockView key={i} block={block as TableBlock} />
          case 'code':
            return <CodeBlockView key={i} block={block as CodeBlock} />
          case 'geo':
            return <GeoBlockView key={i} block={block as GeoBlock} />
          case 'drawing':
            return (
              <DrawingBlockView
                key={i}
                block={block as DrawingBlock}
                resolve={resolveDrawing}
              />
            )
          case 'widget':
            return (
              <WidgetBlockView
                key={i}
                block={block as WidgetBlock}
                onStateChange={onWidgetStateChange}
              />
            )
          default:
            return <UnknownBlockView key={i} block={block} />
        }
      })}
    </div>
  )
}
