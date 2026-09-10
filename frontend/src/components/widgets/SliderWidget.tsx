import { useWidgetState } from './useWidgetState'
import type { WidgetComponentProps } from './types'

type SliderProps = {
  prompt: string
  min?: number
  max: number
  step?: number
  unit?: string
}

type SliderState = {
  value: number
}

export function SliderWidget({ props, state, onStateChange }: WidgetComponentProps) {
  const config = props as SliderProps
  const seed = state as Partial<SliderState>
  const min = typeof config?.min === 'number' ? config.min : 0
  const max = typeof config?.max === 'number' ? config.max : 100
  const step = typeof config?.step === 'number' && config.step > 0 ? config.step : 1
  const [value, update] = useWidgetState<SliderState>(
    { value: typeof seed.value === 'number' ? seed.value : min },
    onStateChange,
  )
  const current = typeof value.value === 'number' ? value.value : min
  return (
    <div className="border-border bg-subtle rounded-md border p-3 text-sm">
      {config?.prompt ? <p className="mb-2 font-medium">{config.prompt}</p> : null}
      <div className="flex items-center gap-3">
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={current}
          onChange={(event) => update({ value: Number(event.target.value) })}
          className="w-full accent-primary"
        />
        <span className="text-muted-foreground min-w-[3rem] text-right text-xs">
          {current}
          {config?.unit ? ` ${config.unit}` : ''}
        </span>
      </div>
    </div>
  )
}
