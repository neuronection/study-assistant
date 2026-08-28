import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from '@tanstack/react-router'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { SettingsPage } from './SettingsPage'

const listSkills = vi.fn()
const listCourseTypes = vi.fn()
const listCourses = vi.fn()
const skillVersions = vi.fn()
const skillResolution = vi.fn()
const contextVars = vi.fn()
const saveSkillVersion = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    listSkills: () => listSkills(),
    listCourseTypes: () => listCourseTypes(),
    listCourses: () => listCourses(),
    skillVersions: (key: string) => skillVersions(key),
    skillResolution: (key: string, courseId?: number | null) => skillResolution(key, courseId),
    contextVars: () => contextVars(),
    saveSkillVersion: (key: string, body: unknown) => saveSkillVersion(key, body),
    listProviders: () => Promise.resolve([]),
    listModels: () => Promise.resolve([]),
    listTasks: () => Promise.resolve([]),
    listPresets: () => Promise.resolve({}),
  }
})

async function renderSettings(initial = '/settings?tab=skills') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const rootRoute = createRootRoute({ component: () => <Outlet /> })
  const settingsRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/settings',
    validateSearch: (search: Record<string, unknown>) => ({
      tab: typeof search.tab === 'string' ? search.tab : undefined,
    }),
    component: () => <SettingsPage />,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([settingsRoute]),
    history: createMemoryHistory({ initialEntries: [initial] }),
  })
  const result = render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
  await screen.findByRole('heading', { name: /settings/i })
  return result
}

describe('Settings Skills tab', () => {
  beforeEach(() => {
    listSkills.mockReset()
    listCourseTypes.mockReset()
    listCourses.mockReset()
    skillVersions.mockReset()
    skillResolution.mockReset()
    contextVars.mockReset()
    saveSkillVersion.mockReset()
    listSkills.mockResolvedValue([
      {
        key: 'tutor.hint',
        task: 'tutor',
        name: 'Tutor hint',
        description: 'Guided hint ladder',
        is_system: true,
      },
    ])
    listCourseTypes.mockResolvedValue([{ id: 1, key: 'math', name: 'Math', description: null }])
    listCourses.mockResolvedValue([])
    skillVersions.mockResolvedValue([
      {
        id: 1,
        scope_type: 'system',
        scope_ref: null,
        version: 1,
        system_template: 'You are a patient tutor.',
        user_template: '',
        contract: { max_words: 100, no_answer_reveal: true },
        is_active: true,
        created_at: '2026-08-19',
      },
    ])
    skillResolution.mockResolvedValue({
      chain: { system: 'v1' },
      active: {
        id: 1,
        scope_type: 'system',
        scope_ref: null,
        version: 1,
        system_template: 'You are a patient tutor.',
        user_template: '',
        contract: { max_words: 100, no_answer_reveal: true },
        is_active: true,
        created_at: '2026-08-19',
      },
    })
    contextVars.mockResolvedValue({ hint_level: { type: 'int', docs: 'level' } })
  })

  test('lists skills and opens the editor', async () => {
    await renderSettings()
    expect(await screen.findByText('Tutor hint')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /edit/i }))
    expect(await screen.findByText(/System template/)).toBeInTheDocument()
    const systemArea = screen.getByLabelText(/System template/) as HTMLTextAreaElement
    await waitFor(() => expect(systemArea.placeholder).toContain('patient tutor'))
  })

  test('saving creates a new version with the edited template', async () => {
    saveSkillVersion.mockResolvedValue({ id: 2, version: 2 })
    await renderSettings()
    fireEvent.click(await screen.findByRole('button', { name: /edit/i }))
    const systemArea = (await screen.findByLabelText(/System template/)) as HTMLTextAreaElement
    fireEvent.change(systemArea, { target: { value: 'You are a very Socratic tutor.' } })
    fireEvent.click(screen.getByRole('button', { name: /save new version/i }))
    await waitFor(() =>
      expect(saveSkillVersion).toHaveBeenCalledWith(
        'tutor.hint',
        expect.objectContaining({
          scope_type: 'system',
          system_template: 'You are a very Socratic tutor.',
        })
      )
    )
  })
})
