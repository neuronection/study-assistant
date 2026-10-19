import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { audienceOfFile, docsNodes, landingDocFile, type DocsTree } from './extensionDocsViews'
import { ExtensionDocsButton } from './ExtensionDocsButton'

const getExtensionDocumentation = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    getExtensionDocumentation: (id: string, file?: string) =>
      getExtensionDocumentation(id, file),
  }
})

const TREE: DocsTree = {
  version: 1,
  categories: [
    {
      category: 'overview',
      title: 'What is this',
      items: [
        {
          id: 'overview',
          file: 'overview.md',
          title: 'Overview',
          audience: 'user',
        },
      ],
    },
    {
      category: 'usage',
      items: [
        {
          id: 'usage',
          file: 'usage.md',
          title: 'Usage',
          index: true,
          audience: 'dev',
        },
      ],
    },
  ],
}

describe('extensionDocsViews', () => {
  test('docsNodes renders categories with i18n-resolved labels', () => {
    const nodes = docsNodes(TREE, 'en')
    expect(nodes).toHaveLength(2)
    expect(nodes[0]).toMatchObject({ id: 'category:overview', title: 'What is this' })
    expect(nodes[0].children).toEqual([{ id: 'overview.md', title: 'Overview' }])
  })

  test('docsNodes title-cases bare category slugs', () => {
    const nodes = docsNodes(
      { version: 1, categories: [{ category: 'troubleshooting', items: [] }] },
      null,
    )
    expect(nodes[0].title).toBe('Troubleshooting')
  })

  test('landingDocFile applies the landing rule (index flag first)', () => {
    expect(landingDocFile(TREE)).toBe('usage.md')
    expect(
      landingDocFile({ version: 1, categories: TREE.categories.slice(0, 1) }),
    ).toBe('overview.md')
    expect(landingDocFile(null)).toBeNull()
  })

  test('audienceOfFile returns the owning item audience', () => {
    expect(audienceOfFile(TREE, 'overview.md')).toBe('user')
    expect(audienceOfFile(TREE, 'usage.md')).toBe('dev')
    expect(audienceOfFile(TREE, 'missing.md')).toBeNull()
  })
})

function renderButton(extensionId = 'mcp') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ExtensionDocsButton extensionId={extensionId} />
    </QueryClientProvider>,
  )
}

describe('ExtensionDocsButton + dialog', () => {
  beforeEach(() => {
    getExtensionDocumentation.mockReset()
    getExtensionDocumentation.mockImplementation((_id: string, file?: string) => {
      if (file && file !== 'overview.md') {
        return Promise.resolve({ markdown: `# ${file}\n\nBody text.`, tree: null })
      }
      return Promise.resolve({ markdown: '# Overview\n\nBody text.', tree: TREE })
    })
  })

  test('opens the dialog on the landing page', async () => {
    renderButton('mcp')
    fireEvent.click(screen.getByTestId('extension-docs-mcp'))
    await waitFor(() => {
      expect(getExtensionDocumentation.mock.calls[0]?.[0]).toBe('mcp')
    })
    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeTruthy()
    })
    expect(screen.getByText('Overview')).toBeTruthy()
  })

  test('switching pages fetches the requested file', async () => {
    renderButton('discovery')
    fireEvent.click(screen.getByTestId('extension-docs-discovery'))
    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeTruthy()
    })
    const usageEntry = screen.getAllByText('Usage')[0]
    fireEvent.click(usageEntry)
    await waitFor(() => {
      expect(getExtensionDocumentation.mock.calls.at(-1)?.[1]).toBe('usage.md')
    })
    await waitFor(() => {
      expect(screen.getAllByText('Body text.').length).toBeGreaterThan(0)
    })
  })

  test('render errors surface in the error pane', async () => {
    getExtensionDocumentation.mockRejectedValue(new Error('backend down'))
    renderButton('external-sources')
    fireEvent.click(screen.getByTestId('extension-docs-external-sources'))
    await waitFor(() => {
      expect(screen.getAllByText('backend down').length).toBeGreaterThan(0)
    })
  })
})
