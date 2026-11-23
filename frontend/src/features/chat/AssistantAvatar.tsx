import { Sparkles } from 'lucide-react'

export function AssistantAvatar() {
  return (
    <span
      aria-hidden
      className="flex size-7 shrink-0 items-center justify-center rounded-full bg-[linear-gradient(135deg,var(--as-primary),var(--as-ai))] text-[var(--as-ai-fg)] shadow-[var(--as-shadow-1)]"
    >
      <Sparkles className="size-3.5" />
    </span>
  )
}
