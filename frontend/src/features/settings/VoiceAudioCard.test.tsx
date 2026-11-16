import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { VoiceAudioCard } from './VoiceAudioCard'

const listTasks = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return { ...actual, listTasks: () => listTasks() }
})

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children }: { children: React.ReactNode }) => <a>{children}</a>,
}))

const TASKS = [
  {
    task: 'transcribe',
    description: 'Speech to text',
    requires: 'stt',
    model_id: '1',
    model_label: 'whisper-1',
    fallback_model_id: null,
    fallback_model_label: null,
    default_model_label: null,
    inherits_default: false,
  },
  {
    task: 'tts',
    description: 'Text to speech',
    requires: 'tts',
    model_id: null,
    model_label: null,
    fallback_model_id: null,
    fallback_model_label: null,
    default_model_label: null,
    inherits_default: false,
  },
]

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <VoiceAudioCard />
    </QueryClientProvider>,
  )
}

describe('VoiceAudioCard', () => {
  beforeEach(() => {
    listTasks.mockReset().mockResolvedValue(TASKS)
    vi.stubGlobal('speechSynthesis', {
      getVoices: () => [
        { name: 'English Voice', lang: 'en-US', voiceURI: 'voice-en' },
        { name: 'German Voice', lang: 'de-DE', voiceURI: 'voice-de' },
      ],
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      cancel: vi.fn(),
      speak: vi.fn(),
    })
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        getUserMedia: vi.fn(),
        enumerateDevices: vi.fn().mockResolvedValue([
          { kind: 'audioinput', label: 'Mic' },
          { kind: 'videoinput', label: 'Cam' },
        ]),
      },
    })
  })

  test('shows assigned and fallback speech capabilities', async () => {
    renderCard()
    expect(await screen.findByText('whisper-1')).toBeInTheDocument()
    expect(screen.getByText('Device voice fallback')).toBeInTheDocument()
    expect(screen.getAllByText('Available').length).toBeGreaterThanOrEqual(2)
    fireEvent.change(screen.getByRole('combobox', { name: 'Browser voice' }), {
      target: { value: 'voice-de' },
    })
    expect(window.localStorage.getItem('sa-browser-voice')).toBe('voice-de')
    expect(screen.getByText(/Audio inputs detected: 1/)).toBeInTheDocument()
    fireEvent.change(screen.getByRole('combobox', { name: 'Speaking speed' }), {
      target: { value: '1.5' },
    })
    expect(window.localStorage.getItem('sa-speech-rate')).toBe('1.5')
  })
})
