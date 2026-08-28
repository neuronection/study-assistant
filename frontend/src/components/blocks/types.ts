import type { MentionRef } from '@/lib/api'

export interface TextBlock {
  type: 'text'
  md: string
  mentions?: MentionRef[]
}

export interface MentionBlock {
  type: 'mention'
  ref: string
  kind: MentionRef['kind']
  id: number
  title: string
  course_id?: number | null
}

export interface MathBlock {
  type: 'math'
  latex: string
  display?: boolean
}

export interface DiagramBlock {
  type: 'diagram'
  mermaid: string
}

export interface ChartBlock {
  type: 'chart'
  plotly: Record<string, unknown>
}

export interface ImageBlock {
  type: 'image'
  blob?: string
  alt?: string
}

export interface TableBlock {
  type: 'table'
  rows: string[][]
  caption?: string
}

export interface CodeBlock {
  type: 'code'
  lang?: string
  code: string
}

export interface GeoBlock {
  type: 'geo'
  jsxgraph: string
}

export interface DrawingBlock {
  type: 'drawing'
  drawing_id: number
}

export interface WidgetBlock {
  type: 'widget'
  widget: string
  id: string
  props: Record<string, unknown>
  state?: Record<string, unknown>
}

export interface UnknownBlock {
  type: string
  [key: string]: unknown
}

export type Block =
  | TextBlock
  | MentionBlock
  | MathBlock
  | DiagramBlock
  | ChartBlock
  | ImageBlock
  | TableBlock
  | CodeBlock
  | GeoBlock
  | DrawingBlock
  | WidgetBlock
  | UnknownBlock
