import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, test, vi, beforeEach, afterEach } from 'vitest'

import { chunkForSpeech, mathToSpeech, stripMathForSpeech } from '@/lib/readAloud'
import { ReadAloudButton } from './ReadAloudButton'

const { mockDefaults } = vi.hoisted(() => ({ mockDefaults: vi.fn() }))
vi.mock('@/lib/api/settings', () => ({
  listTaskDefaults: mockDefaults,
}))

describe('stripMathForSpeech', () => {
  test('strips inline and display math to readable words', () => {
    const text = stripMathForSpeech(
      'The limit $\\lim_{x \\to 0} \\frac{\\sin x}{x} = 1$ matters.'
    )
    expect(text).toContain('limit')
    expect(text).toContain('sine x over x')
    expect(text).not.toContain('\\frac')
    expect(text).not.toContain('$')
  })

  test('converts frac and sqrt inside display math', () => {
    expect(mathToSpeech('\\frac{a}{b}')).toBe('a over b')
    expect(mathToSpeech('\\sqrt{x+1}')).toBe('square root of x+1')
    expect(mathToSpeech('\\int_0^1 x^2 \\, dx')).toContain('integral')
  })

  test('replaces links and images with their labels', () => {
    const text = stripMathForSpeech('![diagram](ca-drawing://1) see [docs](http://x)')
    expect(text).toContain('diagram')
    expect(text).toContain('docs')
    expect(text).not.toContain('http://x')
  })

  test('strips markdown headings and list markers', () => {
    const text = stripMathForSpeech('# Title\n- one\n- two\n1. three')
    expect(text).not.toContain('#')
    expect(text).not.toMatch(/^-/m)
    expect(text).toContain('one')
  })
})

describe('chunkForSpeech', () => {
  test('keeps short text as one chunk', () => {
    expect(chunkForSpeech('short')).toEqual(['short'])
  })

  test('splits long text on sentence boundaries under the cap', () => {
    const sentence = 'This is a sentence. '
    const text = sentence.repeat(600)
    const chunks = chunkForSpeech(text, 1000)
    expect(chunks.length).toBeGreaterThan(1)
    for (const chunk of chunks) {
      expect(chunk.length).toBeLessThanOrEqual(1000)
    }
    expect(chunks.join(' ')).toContain('This is a sentence.')
  })
})

describe('ReadAloudButton', () => {
  let speechSynthesis: {
    getVoices: ReturnType<typeof vi.fn>
    cancel: ReturnType<typeof vi.fn>
    speak: ReturnType<typeof vi.fn>
    addEventListener: ReturnType<typeof vi.fn>
    removeEventListener: ReturnType<typeof vi.fn>
  }

  beforeEach(() => {
    mockDefaults.mockReset()
    mockDefaults.mockResolvedValue([{ requires: 'text', model_id: 1 }])
    speechSynthesis = {
      getVoices: vi.fn(() => [{ name: 'Voice' }]),
      cancel: vi.fn(),
      speak: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }
    vi.stubGlobal(
      'speechSynthesis',
      speechSynthesis as unknown as SpeechSynthesis
    )
    vi.stubGlobal(
      'SpeechSynthesisUtterance',
      class {
        text: string
        rate = 1
        onend: (() => void) | null = null
        onerror: (() => void) | null = null
        constructor(text: string) {
          this.text = text
        }
      }
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  test('renders play button when browser voices exist and speaks the stripped text', async () => {
    const user = userEvent.setup()
    render(<ReadAloudButton markdown="Value: $\\frac{1}{2}$" />)
    const play = await screen.findByRole('button', { name: /read aloud/i })
    await user.click(play)
    await waitFor(() => {
      expect(speechSynthesis.speak).toHaveBeenCalled()
    })
    const utterance = speechSynthesis.speak.mock.calls[0][0] as {
      text: string
    }
    expect(utterance.text).toContain('1 over 2')
    expect(utterance.text).not.toContain('\\frac')
  })

  test('hides entirely when no speech engine is available', async () => {
    speechSynthesis.getVoices.mockReturnValue([])
    mockDefaults.mockResolvedValue([])
    render(<ReadAloudButton markdown="hello" />)
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /read aloud/i })).toBeNull()
    })
  })
})
