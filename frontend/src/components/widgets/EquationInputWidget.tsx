import { useWidgetState } from './useWidgetState'
import type { WidgetComponentProps } from './types'

type EquationInputProps = {
  prompt: string
  placeholder?: string
}

type EquationInputState = {
  value: string
}

export function EquationInputWidget({ props, state, onStateChange }: WidgetComponentProps) {
  const config = props as EquationInputProps
  const seed = state as Partial<EquationInputState>
  const [value, update] = useWidgetState<EquationInputState>(
    { value: typeof seed.value === 'string' ? seed.value : '' },
    onStateChange,
  )
  return (
    <div className="border-border bg-subtle rounded-md border p-3 text-sm">
      {config?.prompt ? <p className="mb-2 font-medium">{config.prompt}</p> : null}
      <input
        type="text"
        value={value.value}
        placeholder={config?.placeholder}
        onChange={(event) => update({ value: event.target.value })}
        className="border-border bg-surface focus:ring-ring w-full rounded-md border px-3 py-1.5 font-mono text-sm"
      />
    </div>
  )
}
