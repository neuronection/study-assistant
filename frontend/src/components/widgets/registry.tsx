import { ChecklistWidget } from './ChecklistWidget'
import { ChoiceWidget } from './ChoiceWidget'
import { EquationInputWidget } from './EquationInputWidget'
import { NumberlineWidget } from './NumberlineWidget'
import { SliderWidget } from './SliderWidget'
import { JsxGraphBoard } from '../blocks/JsxGraphBoard'
import { PlotlyChart } from '../blocks/PlotlyChart'
import type { WidgetComponent, WidgetComponentProps } from './types'

function ChartWidget({ props }: WidgetComponentProps) {
  const figure = (props?.plotly ?? {}) as Record<string, unknown>
  return <PlotlyChart figure={figure} />
}

function GeoWidget({ props }: WidgetComponentProps) {
  const script = typeof props?.jsxgraph === 'string' ? props.jsxgraph : ''
  return <JsxGraphBoard script={script} />
}

const WIDGET_COMPONENTS: Record<string, WidgetComponent> = {
  chart: ChartWidget,
  geo: GeoWidget,
  checklist: ChecklistWidget,
  choice: ChoiceWidget,
  slider: SliderWidget,
  equation_input: EquationInputWidget,
  numberline: NumberlineWidget,
}

export function getWidgetComponent(name: string): WidgetComponent | undefined {
  return WIDGET_COMPONENTS[name]
}
