import { fireEvent, screen, waitFor } from '@testing-library/react'
import { describe, expect, test } from 'vitest'
import {
  addNodeConcept,
  commitConcepts,
  conceptGraph,
  extractConcepts,
  removeNodeConcept,
  primeDefaults,
  renderWorkspace,
} from './harness'

describe('CoverageTab', () => {
  test('concepts tab toggles coverage and adds via the picker', async () => {
    primeDefaults()
    addNodeConcept.mockResolvedValue({ node_id: '5', concept_id: '73' })
    removeNodeConcept.mockResolvedValue(undefined)
    conceptGraph.mockResolvedValue({
      concepts: [
        {
          id: '71',
          name: 'chain rule',
          aliases: [],
          nodes: [{ node_id: '5', node_title: 'Derivatives' }],
        },
        { id: '72', name: 'limits', aliases: [], nodes: [{ node_id: '11', node_title: 'Chain rule' }] },
        { id: '73', name: 'continuity', aliases: [], nodes: [] },
      ],
      links: [],
    })
    renderWorkspace('/courses/3/n/5?tab=concepts')
    expect(await screen.findByText('Concept coverage')).toBeInTheDocument()
    expect(screen.getByText('chain rule')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /covers this node/i }))
    await waitFor(() => expect(removeNodeConcept).toHaveBeenCalledWith('5', '71'))

    fireEvent.click(screen.getByRole('button', { name: /cover here/i }))
    await waitFor(() => expect(addNodeConcept).toHaveBeenCalledWith('5', '72'))

    const picker = screen.getByRole('combobox', { name: /add coverage/i })
    fireEvent.change(picker, { target: { value: '73' } })
    await waitFor(() => expect(addNodeConcept).toHaveBeenCalledWith('5', '73'))
  })

  test('concepts tab extracts a draft from the tab bar and commits it', async () => {
    primeDefaults()
    renderWorkspace('/courses/3/n/5?tab=concepts')
    expect(await screen.findByText('Concept coverage')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /extract concepts/i }))
    await waitFor(() => expect(extractConcepts).toHaveBeenCalledWith('3'))
    expect(await screen.findByText('Concept draft')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /commit/i }))
    await waitFor(() =>
      expect(commitConcepts).toHaveBeenCalledWith('3', {
        concepts: [{ name: 'chain rule', description: null, aliases: [] }],
        links: [],
        nodes: [],
      })
    )
  })

})
