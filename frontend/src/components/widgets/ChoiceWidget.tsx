import { useWidgetState } from './useWidgetState'
import type { WidgetComponentProps } from './types'

type ChoiceProps = {
  prompt: string
  options: string[]
}

type ChoiceState = {
  selected: number | null
}

export function ChoiceWidget({ id, props, state, onStateChange }: WidgetComponentProps) {
  const config = props as ChoiceProps
  const seed = state as Partial<ChoiceState>
  const [value, update] = useWidgetState<ChoiceState>(
    { selected: typeof seed.selected === 'number' ? seed.selected : null },
    onStateChange,
  )
  const options = Array.isArray(config?.options) ? config.options : []
  const selected = value.selected
  return (
    <div className="border-border bg-subtle rounded-md border p-3 text-sm">
      {config?.prompt ? <p className="mb-2 font-medium">{config.prompt}</p> : null}
      <ul className="space-y-1.5">
        {options.map((option, index) => (
          <li key={option}>
            <label className="flex items-center gap-2">
              <input
                type="radio"
                name={id}
                checked={selected === index}
                onChange={() => update({ selected: index })}
                className="accent-primary"
              />
              <span>{option}</span>
            </label>
          </li>
        ))}
      </ul>
    </div>
  )
}
