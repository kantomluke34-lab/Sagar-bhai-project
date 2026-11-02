import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import { AuthProvider, useAuth } from '../contexts/AuthContext'

const api = vi.hoisted(() => ({ get: vi.fn() }))
const clearToken = vi.hoisted(() => vi.fn())

vi.mock('../api', () => ({
  default: api,
  clearToken,
  getToken: vi.fn(),
  setToken: vi.fn(),
}))

function Status() {
  const { loading, user } = useAuth()
  return <span>{loading ? 'loading' : user ? 'signed-in' : 'public'}</span>
}

beforeEach(() => {
  window.history.pushState({}, '', '/book')
  api.get.mockReset()
  clearToken.mockReset()
})

afterEach(() => {
  window.history.pushState({}, '', '/')
})

test('does not check dashboard authentication on the public booking route', async () => {
  render(<AuthProvider><Status /></AuthProvider>)

  expect(await screen.findByText('public')).toBeVisible()
  expect(api.get).not.toHaveBeenCalled()
  expect(clearToken).not.toHaveBeenCalled()
})
