import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, test } from 'vitest'
import {
  addNode,
  composeMaterialAsync,
  generateQuiz,
  getMaterial,
  getNodeArtifacts,
  nodeWorkspace,
  outlineCommit,
  outlineDraft,
  ROOT_WS,
  NODE_WS,
  DRAFT,
  primeDefaults,
  renderWorkspace,
  navigateMock,
  routerHolder,
} from './harness'

describe('OverviewTab', () => {
  test('root workspace renders tabs, outline editor and child cards', async () => {
    primeDefaults()
    renderWorkspace('/courses/3')
    expect(await screen.findByRole('heading', { name: 'Calculus I' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Overview' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Practice' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /ai outline/i })).toBeInTheDocument()
    expect(screen.getAllByText('Derivatives').length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: /^practice$/i })).toBeInTheDocument()
  })

  test('child cards show the subsection description when set', async () => {
    primeDefaults()
    nodeWorkspace.mockImplementation((id: string) =>
      Promise.resolve(
        id === '1'
          ? {
              ...ROOT_WS,
              children: [
                { id: '5', title: 'Derivatives', depth: 1, order_idx: 0, objectives: [], summary: 'Rates of change' },
                { id: '6', title: 'Integrals', depth: 1, order_idx: 1, objectives: [], summary: null },
              ],
              child_materials: { 5: [], 6: [] },
            }
          : NODE_WS
      )
    )
    renderWorkspace('/courses/3')
    expect(await screen.findByText('Rates of change')).toBeInTheDocument()
  })

  test('quick practice on a child card quizzes that child node', async () => {
    primeDefaults()
    generateQuiz.mockResolvedValue({ id: '43', title: 'Chain rule · quiz', question_count: 8 })
    renderWorkspace('/courses/3/n/5')
    fireEvent.click(await screen.findByRole('button', { name: /^practice$/i }))
    await waitFor(() =>
      expect(generateQuiz).toHaveBeenCalledWith({ course_id: '3', node_id: '11', count: 8 })
    )
  })

  test('practice pending state marks only the clicked child card', async () => {
    primeDefaults()
    nodeWorkspace.mockImplementation((id: string) =>
      Promise.resolve(
        id === '1'
          ? ROOT_WS
          : {
              ...NODE_WS,
              children: [
                { id: '11', title: 'Chain rule', depth: 2, order_idx: 0, objectives: [], summary: null },
                { id: '12', title: 'Integration by parts', depth: 2, order_idx: 1, objectives: [], summary: null },
              ],
              child_materials: { 11: [], 12: [] },
            }
      )
    )
    generateQuiz.mockImplementation(() => new Promise(() => undefined))
    renderWorkspace('/courses/3/n/5')
    const practiceButtons = await screen.findAllByRole('button', { name: /^practice$/i })
    expect(practiceButtons).toHaveLength(2)
    fireEvent.click(practiceButtons[0])
    await waitFor(() =>
      expect(generateQuiz).toHaveBeenCalledWith({ course_id: '3', node_id: '11', count: 8 })
    )
    const pending = screen.getAllByRole('button', { name: /^practice$/i })
    expect(pending[0]).toBeDisabled()
    expect(pending[0].querySelector('.animate-spin')).not.toBeNull()
    expect(pending[1].querySelector('.animate-spin')).toBeNull()
  })

  test('overview cheat-sheet menu offers open existing and regenerate when a sheet exists', async () => {
    primeDefaults()
    getNodeArtifacts.mockResolvedValue({
      cheat_sheet: { material_id: '42', title: 'Derivatives — cheat sheet' },
      reviews: [
        { material_id: '50', title: 'Derivatives — Review 2026-08-21' },
        { material_id: '45', title: 'Derivatives — Review 2026-08-14' },
      ],
    })
    renderWorkspace('/courses/3/n/5')
    expect(await screen.findByRole('button', { name: /review 2026-08-21/i })).toBeInTheDocument()
    fireEvent.pointerDown(screen.getByRole('button', { name: /cheat sheet/i }))
    expect(screen.getByRole('menuitem', { name: /open existing/i })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: /regenerate cheat sheet/i })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('menuitem', { name: /open existing/i }))
    await waitFor(() =>
      expect(routerHolder.current!.state.location.search).toMatchObject({ material: '42' })
    )
  })

  test('overview cheat-sheet menu offers generate and opens the cheat-sheet builder', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/n/5')
    fireEvent.pointerDown(await screen.findByRole('button', { name: /cheat sheet/i }))
    expect(screen.getByRole('menuitem', { name: /generate cheat sheet/i })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: /open existing/i })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('menuitem', { name: /generate cheat sheet/i }))
    expect(await screen.findByLabelText('Document kind')).toHaveValue('cheat_sheet')
  })

  test('overview cheat-sheet builder composes with the cheat_sheet kind and previews the result', async () => {
    primeDefaults()
    getMaterial.mockResolvedValue({
      material: {
        id: '99',
        title: 'Derivatives — cheat sheet',
        kind: 'markdown',
        status: 'ready',
        filename: 'Cheat sheet.md',
        mime: 'text/markdown',
        pages: null,
        course_id: '3',
        folder_id: null,
        blob_sha: null,
        created_at: '2026-08-23T00:00:00Z',
      },
      extraction: {
        id: '1',
        material_id: '99',
        version: 1,
        extractor: 'text',
        markdown: '# Derivatives cheat sheet\n\n- Power rule: $f\'(x) = nx^{n-1}$',
        blocks: [],
      },
      index_card: null,
      drawings: [],
    })
    renderWorkspace('/courses/3/n/5')
    fireEvent.pointerDown(await screen.findByRole('button', { name: /cheat sheet/i }))
    fireEvent.click(screen.getByRole('menuitem', { name: /generate cheat sheet/i }))
    const submit = await screen.findByRole('button', { name: /^compose$/i })
    fireEvent.click(submit)
    await waitFor(() =>
      expect(composeMaterialAsync).toHaveBeenCalledWith(
        expect.objectContaining({ node_id: '5', kind: 'cheat_sheet' })
      )
    )
    fireEvent.click(await screen.findByRole('button', { name: /close/i }))
    await waitFor(() => expect(getMaterial).toHaveBeenCalledWith('99'))
    expect(await screen.findByText(/Power rule/)).toBeInTheDocument()
  })

  test('overview adds a child node under the current node', async () => {
    primeDefaults()
    addNode.mockResolvedValue({ id: '12', title: 'Integrals', order_idx: 1000, depth: 2 })
    renderWorkspace('/courses/3/n/5')
    fireEvent.click(await screen.findByRole('button', { name: 'Add child' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Node title' }), {
      target: { value: 'Integrals' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    await waitFor(() => expect(addNode).toHaveBeenCalledWith('3', '5', 'Integrals'))
  })

  test('overview empty state offers to add the first child', async () => {
    primeDefaults()
    nodeWorkspace.mockImplementation((id: string) =>
      Promise.resolve(id === '1' ? ROOT_WS : { ...NODE_WS, children: [], child_materials: {} })
    )
    renderWorkspace('/courses/3/n/5')
    expect(await screen.findByText(/No subsections yet/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add child' })).toBeInTheDocument()
  })

  test('fresh course root shows the guided onboarding card instead of the action bar', async () => {
    primeDefaults()
    nodeWorkspace.mockImplementation((id: string) =>
      Promise.resolve(id === '1' ? { ...ROOT_WS, children: [], child_materials: {} } : NODE_WS)
    )
    renderWorkspace('/courses/3')
    expect(await screen.findByTestId('course-onboarding')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /add materials/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /generate ai outline/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /add node/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /study this course/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /ask the tutor/i })).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /compose study material/i })
    ).not.toBeInTheDocument()
  })

  test('onboarding add materials navigates to the materials tab', async () => {
    primeDefaults()
    nodeWorkspace.mockImplementation((id: string) =>
      Promise.resolve(id === '1' ? { ...ROOT_WS, children: [], child_materials: {} } : NODE_WS)
    )
    renderWorkspace('/courses/3')
    fireEvent.click(await screen.findByRole('button', { name: /add materials/i }))
    expect(navigateMock).toHaveBeenCalledWith({
      to: '/courses/$courseId',
      params: { courseId: '3' },
      search: { tab: 'materials' },
    })
  })

  test('onboarding generate outline drafts the course outline', async () => {
    primeDefaults()
    outlineDraft.mockResolvedValue(DRAFT)
    nodeWorkspace.mockImplementation((id: string) =>
      Promise.resolve(id === '1' ? { ...ROOT_WS, children: [], child_materials: {} } : NODE_WS)
    )
    renderWorkspace('/courses/3')
    fireEvent.click(await screen.findByRole('button', { name: /generate ai outline/i }))
    await waitFor(() => expect(outlineDraft).toHaveBeenCalledWith('3'))
    expect(await screen.findByText('Limits')).toBeInTheDocument()
  })

  test('root overview hosts outline actions in the action bar', async () => {
    primeDefaults()
    renderWorkspace('/courses/3')
    expect(await screen.findByRole('heading', { name: 'Calculus I' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /ai outline/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /add node/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add child' })).not.toBeInTheDocument()
  })

  test('root overview add node posts against the root', async () => {
    primeDefaults()
    addNode.mockResolvedValue({ id: '9', title: 'Integrals', order_idx: 1000, depth: 1 })
    renderWorkspace('/courses/3')
    fireEvent.click(await screen.findByRole('button', { name: /add node/i }))
    const input = screen.getByPlaceholderText('Node title')
    fireEvent.change(input, { target: { value: 'Integrals' } })
    fireEvent.submit(input.closest('form') as HTMLFormElement)
    await waitFor(() => expect(addNode).toHaveBeenCalledWith('3', '1', 'Integrals'))
  })

  test('root AI outline drafts, prunes and commits', async () => {
    primeDefaults()
    outlineDraft.mockResolvedValue(DRAFT)
    outlineCommit.mockResolvedValue({ chapters: 1, sections: 1, allocations: 1 })
    renderWorkspace('/courses/3')
    fireEvent.click(await screen.findByRole('button', { name: /ai outline/i }))
    expect(await screen.findByText('Limits')).toBeInTheDocument()
    expect(screen.getByText('Continuity')).toBeInTheDocument()

    const draftCard = screen
      .getByRole('button', { name: /commit outline/i })
      .closest('[data-as="card"]') as HTMLElement
    const derivativesRow = within(draftCard)
      .getByText('Derivatives')
      .closest('div') as HTMLElement
    fireEvent.click(within(derivativesRow).getByRole('button', { name: /remove/i }))
    await waitFor(() => expect(within(draftCard).queryByText('Derivatives')).not.toBeInTheDocument())
    expect(within(draftCard).getByText('Continuity')).toBeInTheDocument()

    fireEvent.click(within(draftCard).getByRole('button', { name: /commit outline/i }))
    await waitFor(() => expect(outlineCommit).toHaveBeenCalledWith('3', [DRAFT.chapters['0']]))
    await waitFor(() => expect(screen.queryByText('Limits')).not.toBeInTheDocument())
  })

  test('root AI outline cancel discards the draft', async () => {
    primeDefaults()
    outlineDraft.mockResolvedValue(DRAFT)
    renderWorkspace('/courses/3')
    fireEvent.click(await screen.findByRole('button', { name: /ai outline/i }))
    expect(await screen.findByText('Limits')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }))
    await waitFor(() => expect(screen.queryByText('Limits')).not.toBeInTheDocument())
  })

  test('materials tab lists only the node materials, not child sections', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/n/5?tab=materials')
    expect(await screen.findByRole('button', { name: /chain-rule\.pdf/i })).toBeInTheDocument()
    expect(screen.queryByText('worked problems')).not.toBeInTheDocument()
    expect(screen.queryByText('Chain rule')).not.toBeInTheDocument()
  })

  test('overview no longer renders the AI instructions card', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/n/5')
    await screen.findByRole('heading', { name: 'Derivatives' })
    expect(screen.queryByText('AI instructions for this node')).not.toBeInTheDocument()
  })

})
