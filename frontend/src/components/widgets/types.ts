import type { ComponentType } from 'react'

export interface WidgetComponentProps {
  id: string
  props: Record<string, unknown>
  state: Record<string, unknown>
  onStateChange?: (state: Record<string, unknown>) => void
}

export type WidgetComponent = ComponentType<WidgetComponentProps>
