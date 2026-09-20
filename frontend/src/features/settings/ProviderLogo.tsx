import {
  siAnthropic,
  siDeepseek,
  siGooglegemini,
  siMistralai,
  siOllama,
  siOpenrouter,
} from 'simple-icons'

const ICON_PATHS: Record<string, string> = {
  gemini: siGooglegemini.path,
  openrouter: siOpenrouter.path,
  anthropic: siAnthropic.path,
  mistral: siMistralai.path,
  deepseek: siDeepseek.path,
  ollama: siOllama.path,
}

export function ProviderLogo({ presetKey, label }: { presetKey: string | null; label: string }) {
  const path = presetKey ? ICON_PATHS[presetKey] : undefined
  if (path) {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true" className="size-5 shrink-0" fill="currentColor">
        <path d={path} />
      </svg>
    )
  }
  return (
    <span
      aria-hidden="true"
      className="border-border text-muted-foreground flex size-5 shrink-0 items-center justify-center rounded-full border text-[10px] font-semibold"
    >
      {label.charAt(0)}
    </span>
  )
}
