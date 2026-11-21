import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

const api = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
}))

vi.mock('../api', () => ({ default: api }))
vi.mock('@xyflow/react', () => ({
  Background: () => null,
  Controls: () => null,
  Handle: () => null,
  MarkerType: { ArrowClosed: 'arrow-closed' },
  MiniMap: () => null,
  Position: { Top: 'top', Bottom: 'bottom' },
  ReactFlow: ({ children }) => <div data-testid="flow-canvas">{children}</div>,
  addEdge: (edge, edges) => [...edges, edge],
  useEdgesState: (initial) => {
    const [edges, setEdges] = useState(initial)
    return [edges, setEdges, vi.fn()]
  },
  useNodesState: (initial) => {
    const [nodes, setNodes] = useState(initial)
    return [nodes, setNodes, vi.fn()]
  },
}))

import DmFlows from '../pages/DmFlows'

beforeEach(() => {
  api.get.mockReset()
  api.post.mockReset()
  api.put.mockReset()
  api.get.mockResolvedValue({ data: [] })
})

afterEach(cleanup)

test('DM flow editor validates the name and protects unsaved changes', async () => {
  const user = userEvent.setup()
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
  render(<DmFlows />)

  await user.click(await screen.findByRole('button', { name: 'New DM Flow' }))
  const name = screen.getByLabelText('Flow name')
  await user.clear(name)
  await user.type(name, 'A')
  await user.click(screen.getByRole('button', { name: /Save draft/i }))

  expect(screen.getByText('Enter a flow name with at least two characters.')).toBeVisible()
  expect(api.post).not.toHaveBeenCalled()
  expect(screen.getByText('Unsaved changes')).toBeVisible()

  await user.click(screen.getByRole('button', { name: 'Close editor' }))
  expect(confirm).toHaveBeenCalledWith('Discard unsaved DM flow changes?')
  expect(screen.getByLabelText('Flow name')).toBeVisible()

  confirm.mockReturnValue(true)
  await user.click(screen.getByRole('button', { name: 'Close editor' }))
  expect(await screen.findByText('No DM flows yet')).toBeVisible()
})

test('publishing clears the unsaved indicator', async () => {
  const user = userEvent.setup()
  let graph
  let published = false
  api.post.mockImplementation((url, payload) => {
    if (url === '/api/dm-flows/validate') return Promise.resolve({ data: { valid: true } })
    if (url === '/api/dm-flows') {
      graph = payload.graph
      return Promise.resolve({ data: { id: 1 } })
    }
    if (url === '/api/dm-flows/1/publish') {
      published = true
      return Promise.resolve({ data: { version: 1 } })
    }
    return Promise.resolve({ data: {} })
  })
  api.get.mockImplementation((url) => {
    if (url === '/api/dm-flows/1') {
      return Promise.resolve({
        data: {
          id: 1,
          name: 'Campaign qualification flow',
          description: '',
          draft_version: 1,
          draft_graph: graph,
          status: published ? 'published' : 'draft',
          published_version: published ? { id: 7, version: 1 } : null,
          executions: [],
        },
      })
    }
    return Promise.resolve({ data: [] })
  })
  render(<DmFlows />)

  await user.click(await screen.findByRole('button', { name: 'New DM Flow' }))
  await user.clear(screen.getByLabelText('Flow name'))
  await user.type(screen.getByLabelText('Flow name'), 'Campaign qualification flow')
  await user.click(screen.getByRole('button', { name: 'Publish' }))

  expect(await screen.findByText('Version 1 published.')).toBeVisible()
  expect(screen.queryByText('Unsaved changes')).not.toBeInTheDocument()
})
