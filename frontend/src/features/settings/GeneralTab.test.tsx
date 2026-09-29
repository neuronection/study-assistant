import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import i18next from 'i18next'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { storageKeys } from '@/lib/constants'
import { availableLocales } from '@/lib/locales'
import { useInterfacePrefsStore } from '@/lib/interface-prefs'

import { GeneralTab } from './GeneralTab'

const listMySessions = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    listMySessions: () => listMySessions(),
  }
})

function renderGeneral() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <GeneralTab />
    </QueryClientProvider>,
  )
}

function openPicker() {
  fireEvent.click(screen.getByRole('combobox', { name: 'Language' }))
}

describe('GeneralTab', () => {
  beforeEach(() => {
    listMySessions.mockReset()
    listMySessions.mockResolvedValue([])
  })

  afterEach(async () => {
    localStorage.removeItem(storageKeys.locale)
    await i18next.changeLanguage('en')
  })

  test('offers the picker-eligible locales for search', async () => {
    renderGeneral()
    openPicker()
    for (const locale of availableLocales()) {
      expect(await screen.findByRole('option', { name: locale.name })).toBeInTheDocument()
    }
  })

  test('search filters the language list', async () => {
    renderGeneral()
    openPicker()
    const search = screen.getByPlaceholderText('Search languages…')
    fireEvent.change(search, { target: { value: 'Ελλ' } })
    await waitFor(() => {
      expect(screen.queryByRole('option', { name: 'Deutsch' })).not.toBeInTheDocument()
    })
    expect(screen.getByRole('option', { name: 'Ελληνικά' })).toBeInTheDocument()
  })

  test('picking a language applies instantly, persists and updates html lang', async () => {
    renderGeneral()
    openPicker()
    fireEvent.click(await screen.findByRole('option', { name: 'Deutsch' }))

    await waitFor(() => {
      expect(document.documentElement.lang).toBe('de')
    })
    expect(localStorage.getItem(storageKeys.locale)).toBe('de')
    expect(i18next.resolvedLanguage).toBe('de')
    expect(screen.getByRole('combobox', { name: 'Sprache' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('combobox', { name: 'Sprache' }))
    fireEvent.click(await screen.findByRole('option', { name: 'English' }))
    await waitFor(() => {
      expect(document.documentElement.lang).toBe('en')
    })
    expect(localStorage.getItem(storageKeys.locale)).toBe('en')
  })

  test('interface toggles persist per surface and apply instantly', () => {
    localStorage.removeItem(storageKeys.interfacePrefs)
    renderGeneral()

    const paletteToggle = screen.getByRole('checkbox', {
      name: 'Recent sections in the command palette',
    })
    expect(paletteToggle).toBeChecked()
    fireEvent.click(paletteToggle)
    expect(paletteToggle).not.toBeChecked()
    expect(useInterfacePrefsStore.getState().prefs.paletteRecent).toBe(false)
    expect(localStorage.getItem(storageKeys.interfacePrefs)).toBe(
      JSON.stringify({
        homeContinue: true,
        paletteRecent: false,
        courseJumpBackIn: true,
        courseCardMeta: true,
      })
    )

    const homeToggle = screen.getByRole('checkbox', { name: 'Continue card on Home' })
    expect(homeToggle).toBeChecked()
    localStorage.removeItem(storageKeys.interfacePrefs)
  })
})
