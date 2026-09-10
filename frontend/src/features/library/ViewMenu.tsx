import { ChevronDown, Eye } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Menu,
  MenuCheckboxItem,
  MenuContent,
  MenuTrigger,
} from '@/components/ui/popover-menu'

export function ViewMenu({
  label,
  value,
  views,
  onChange,
}: {
  label: string
  value: string
  views: { value: string; label: string }[]
  onChange: (next: string) => void
}) {
  const active = views.find((view) => view.value === value)
  return (
    <Menu modal={false}>
      <MenuTrigger asChild>
        <Button variant="outline" size="sm" aria-label={label} className="gap-1.5">
          <Eye className="size-3.5" aria-hidden />
          {active?.label ?? views[0]?.label}
          <ChevronDown className="text-muted-foreground size-3.5" aria-hidden />
        </Button>
      </MenuTrigger>
      <MenuContent align="start">
        {views.map((view) => (
          <MenuCheckboxItem
            key={view.value}
            checked={view.value === value}
            onSelect={() => {
              if (view.value !== value) {
                onChange(view.value)
              }
            }}
          >
            {view.label}
          </MenuCheckboxItem>
        ))}
      </MenuContent>
    </Menu>
  )
}
