import { useWidgetState } from './useWidgetState'
import type { WidgetComponentProps } from './types'

type ChecklistProps = {
  prompt: string
  items: string[]
  multiple?: boolean
}

type ChecklistState = {
  checked: string[]
}

export function ChecklistWidget({ id, props, state, onStateChange }: WidgetComponentProps) {
  const config = props as ChecklistProps
  const seed = state as Partial<ChecklistState>
  const [value, update] = useWidgetState<ChecklistState>(
    { checked: Array.isArray(seed.checked) ? seed.checked : [] },
    onStateChange,
  )
  const items = Array.isArray(config?.items) ? config.items : []
  const checked = Array.isArray(value.checked) ? value.checked : []
  const single = config?.multiple === false
  const toggle = (item: string) => {
    const selected = checked.includes(item)
    if (single) {
      update({ checked: selected ? [] : [item] })
      return
    }
    update({
      checked: selected ? checked.filter((entry) => entry !== item) : [...checked, item],
    })
  }
  return (
    <div className="border-border bg-subtle rounded-md border p-3 text-sm">
      {config?.prompt ? <p className="mb-2 font-medium">{config.prompt}</p> : null}
      <ul className="space-y-1.5">
        {items.map((item) => (
          <li key={item}>
            <label className="flex items-center gap-2">
              <input
                type={single ? 'radio' : 'checkbox'}
                name={id}
                checked={checked.includes(item)}
                onChange={() => toggle(item)}
                className="accent-primary"
              />
              <span>{item}</span>
            </label>
          </li>
        ))}
      </ul>
    </div>
  )
}
