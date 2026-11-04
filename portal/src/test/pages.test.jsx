import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { addDays, format } from 'date-fns'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import BookingForm from '../pages/BookingForm'
import Campaigns from '../pages/Campaigns'
import Conversations from '../pages/Conversations'
import Layout from '../components/Layout'
import Sidebar from '../components/Sidebar'
import CRM from '../pages/CRM'
import Dashboard from '../pages/Dashboard'
import Login from '../pages/Login'
import Meetings from '../pages/Meetings'
import Settings from '../pages/Settings'
import Templates from '../pages/Templates'
import Waba from '../pages/Waba'

const api = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
}))
const publicApi = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
const auth = vi.hoisted(() => ({
  login: vi.fn(),
  logout: vi.fn(),
  loading: false,
  user: { full_name: 'Mechman Admin', role: 'admin' },
}))

vi.mock('../api', () => ({ default: api, publicApi, API_BASE_URL: '' }))
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => auth }))

const renderRoute = (component, route = '/') => render(
  <MemoryRouter initialEntries={[route]}>{component}</MemoryRouter>,
)

beforeEach(() => {
  api.get.mockReset()
  api.post.mockReset()
  api.patch.mockReset()
  api.put.mockReset()
  api.delete.mockReset()
  publicApi.get.mockReset()
  publicApi.post.mockReset()
  auth.login.mockReset()
  auth.logout.mockReset()
  auth.loading = false
  auth.user = { full_name: 'Mechman Admin', role: 'admin' }
})

afterEach(cleanup)

describe('dashboard controls', () => {
  test('login submits credentials and reports an invalid login', async () => {
    const user = userEvent.setup()
    auth.user = null
    auth.login.mockRejectedValueOnce({ response: { data: { detail: 'Invalid username or password' } } })
    renderRoute(<Login />, '/login')

    await user.type(screen.getByLabelText('Username'), 'admin')
    await user.type(screen.getByLabelText('Password'), 'wrong-password')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    expect(auth.login).toHaveBeenCalledWith('admin', 'wrong-password')
    expect(await screen.findByText('Invalid username or password')).toBeVisible()
  })

  test('booking form loads slots, selects a time, and submits', async () => {
    const user = userEvent.setup()
    publicApi.get.mockImplementation((url) => {
      if (url === '/api/public/config') return Promise.resolve({ data: { business_hours: 'Monday-Saturday' } })
      return Promise.resolve({ data: [{ start_time: '09:00', label: '9:00 AM' }] })
    })
    publicApi.post.mockResolvedValue({
      data: { meeting_id: 7, start_at: '2027-01-04T09:00:00+05:30' },
    })
    renderRoute(<BookingForm />, '/book?name=Asha&phone=9876543210&interest=PowerMill&purpose=Five-axis+demo')

    await user.type(screen.getByLabelText('Email address *'), 'asha@example.com')
    const bookingDate = format(addDays(new Date(), 2), 'yyyy-MM-dd')
    fireEvent.change(screen.getByLabelText('Meeting date *'), { target: { value: bookingDate } })
    await user.click(await screen.findByRole('button', { name: /9:00 AM/i }))
    await user.click(screen.getByRole('button', { name: 'Book meeting' }))

    expect(publicApi.post).toHaveBeenCalledWith('/api/public/meetings', expect.objectContaining({
      name: 'Asha', phone: '9876543210', email: 'asha@example.com', start_time: '09:00', interest: 'PowerMill', purpose: 'Five-axis demo',
    }))
    expect(await screen.findByText('Your meeting is requested.')).toBeVisible()
  })

  test('meetings search, filters, opens a record, and updates fields', async () => {
    const user = userEvent.setup()
    const meeting = {
      id: 1, name: 'Asha Shah', phone: '919876543210', company: 'Acme',
      interest: 'Fusion 360', purpose: 'CAM workflow', start_at: '2027-01-04T09:00:00+05:30', end_at: '2027-01-04T10:00:00+05:30',
      meeting_mode: 'Video', lead_stage: 'new', status: 'requested', history: [],
    }
    api.get.mockImplementation((url) => Promise.resolve({ data: url === '/api/meetings/1' ? meeting : [meeting] }))
    api.patch.mockImplementation((_url, change) => Promise.resolve({ data: { ...meeting, ...change, history: undefined } }))
    renderRoute(<Meetings />)

    expect(await screen.findByText('Asha Shah')).toBeVisible()
    await user.type(screen.getByPlaceholderText(/Search name/), 'Asha')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Filter by status' }), 'requested')
    await user.click(screen.getByText('Asha Shah'))
    expect(await screen.findByText('REQUEST #1')).toBeVisible()

    await user.selectOptions(screen.getByRole('combobox', { name: 'Status' }), 'confirmed')
    const assigned = screen.getByLabelText('Assigned to')
    await user.type(assigned, 'Kiran')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(api.patch).toHaveBeenCalledWith('/api/meetings/1', expect.objectContaining({ status: 'confirmed', assigned_to: 'Kiran' }))
    await user.click(screen.getByRole('button', { name: 'Close meeting details' }))
    expect(screen.queryByText('REQUEST #1')).not.toBeInTheDocument()
  })

  test('CRM search opens and closes a contact drawer', async () => {
    const user = userEvent.setup()
    const row = { id: 2, name: 'Dev Mehta', phone: '919999999999', email: 'dev@example.com', company: 'Delta', lead_stage: 'qualified', meeting_count: 1 }
    api.get.mockImplementation((url) => Promise.resolve({ data: url === '/api/crm/contacts/2' ? { ...row, meetings: [] } : [row] }))
    renderRoute(<CRM />)

    await user.type(screen.getByRole('textbox', { name: 'Search CRM contacts' }), 'Dev')
    expect(await screen.findByText('Dev Mehta')).toBeVisible()
    await user.click(screen.getByText('Dev Mehta'))
    expect(await screen.findByText('CRM CONTACT #2')).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Close contact details' }))
    expect(screen.queryByText('CRM CONTACT #2')).not.toBeInTheDocument()
  })

  test('notification settings toggle and save', async () => {
    const user = userEvent.setup()
    const settings = {
      reminder_enabled: true,
      reminder_minutes_before: 60,
      followup_enabled: true,
      followup_days: [1, 3],
      reminder_template: 'Reminder message long enough for validation',
      followup_template: 'Follow-up message long enough for validation',
    }
    api.get.mockImplementation((url) => Promise.resolve({ data: url.endsWith('/deliveries') ? [] : settings }))
    api.put.mockResolvedValue({ data: { ...settings, reminder_enabled: false } })
    renderRoute(<Settings />)

    const reminderToggle = await screen.findByRole('checkbox', { name: /Enable reminders/i })
    await user.click(reminderToggle)
    await user.click(screen.getByRole('button', { name: /Save settings/i }))

    expect(api.put).toHaveBeenCalledWith('/api/settings/notifications', expect.objectContaining({
      reminder_enabled: false, reminder_minutes_before: 60, followup_days: [1, 3],
    }))
    expect(await screen.findByText('Notification settings saved.')).toBeVisible()
  })

  test('settings verifies and changes the account password', async () => {
    const user = userEvent.setup()
    const settings = {
      reminder_enabled: true, reminder_minutes_before: 60, followup_enabled: true,
      followup_days: [1], reminder_template: 'Reminder', followup_template: 'Follow up',
    }
    api.get.mockImplementation((url) => Promise.resolve({ data: url.endsWith('/deliveries') ? [] : settings }))
    api.post.mockResolvedValue({ data: { message: 'Password changed successfully' } })
    renderRoute(<Settings />)

    await user.type(await screen.findByLabelText('Current password'), 'old-password')
    await user.type(screen.getByLabelText('New password'), 'new-password-123')
    await user.type(screen.getByLabelText('Confirm new password'), 'new-password-123')
    await user.click(screen.getByRole('button', { name: /Change password/i }))

    expect(api.post).toHaveBeenCalledWith('/api/auth/change-password', {
      current_password: 'old-password', new_password: 'new-password-123', confirm_password: 'new-password-123',
    })
    expect(await screen.findByText('Password changed successfully')).toBeVisible()
  })

  test('conversation inbox opens a thread, takes control, and sends a reply', async () => {
    const user = userEvent.setup()
    const row = { id: 8, contact_name: 'Asha Shah', phone: '919876543210', last_message: 'Need a CAM quote', mode: 'bot' }
    let takenOver = false
    api.get.mockImplementation((url) => Promise.resolve({ data: url === '/api/conversations/8' ? { ...row, is_taken_over: takenOver, messages: [{ id: 1, direction: 'inbound', text: 'Need a CAM quote' }] } : [{ ...row, is_taken_over: takenOver }] }))
    api.post.mockImplementation((url) => {
      if (url.endsWith('/take-over')) takenOver = true
      return Promise.resolve({ data: { is_taken_over: takenOver } })
    })
    renderRoute(<Conversations />)

    await user.click(await screen.findByText('Asha Shah'))
    expect((await screen.findAllByText('Need a CAM quote')).length).toBe(2)
    await user.click(screen.getByRole('button', { name: /Take over/i }))
    expect(api.post).toHaveBeenCalledWith('/api/conversations/8/take-over')
    await user.type(screen.getByLabelText('Reply message'), 'We can help with that.')
    await user.click(screen.getByRole('button', { name: /Send/i }))
    expect(api.post).toHaveBeenCalledWith('/api/conversations/8/messages', { text: 'We can help with that.', template_id: null, parameters: [] })
  })

  test('campaign workspace exposes CSV, pasted-number, and CRM audience sources', async () => {
    const user = userEvent.setup()
    api.get.mockImplementation((url) => {
      if (url === '/api/templates') return Promise.resolve({ data: [{ id: 1, name: 'approved_offer', status: 'APPROVED', body: 'Hello', header_format: 'NONE' }] })
      return Promise.resolve({ data: [] })
    })
    renderRoute(<Campaigns />)

    await user.click(await screen.findByRole('button', { name: /New campaign/i }))
    expect(screen.getByRole('button', { name: /CSV \/ Excel/i })).toBeVisible()
    expect(screen.getByRole('button', { name: /Paste numbers/i })).toBeVisible()
    expect(screen.getByRole('button', { name: /CRM audience/i })).toBeVisible()
  })

  test('WABA status renders Cloud API and webhook health', async () => {
    api.get.mockResolvedValue({ data: { status: 'connected', display_phone_number: '+91 99999 99999', app_secret_configured: true, verify_token_configured: true, quality_rating: 'GREEN' } })
    renderRoute(<Waba />)

    expect(await screen.findByText('WhatsApp credentials are configured.')).toBeVisible()
    expect(screen.getByText('Meta webhook')).toBeVisible()
    expect(api.get).toHaveBeenCalledWith('/api/waba/status')
  })

  test('templates sync, create a draft, and submit for approval', async () => {
    const user = userEvent.setup()
    const row = { id: 4, name: 'meeting_confirmed', language: 'en_US', category: 'UTILITY', body: 'Your meeting is confirmed.', status: 'draft' }
    api.get.mockResolvedValue({ data: [row] })
    api.post.mockResolvedValue({ data: { updated: 1 } })
    renderRoute(<Templates />)

    expect(await screen.findByText('meeting_confirmed')).toBeVisible()
    await user.click(screen.getByRole('button', { name: /Sync Meta/i }))
    expect(api.post).toHaveBeenCalledWith('/api/templates/sync')
    await user.click(screen.getByRole('button', { name: /Submit/i }))
    expect(api.post).toHaveBeenCalledWith('/api/templates/4/submit')
    await user.click(screen.getByRole('button', { name: /New template/i }))
    expect(screen.getByText('Create message template')).toBeVisible()
  })

  test('analytics renders all summary cards and recent meetings', async () => {
    api.get.mockResolvedValue({ data: {
      total_contacts: 5, total_meetings: 5, upcoming_meetings: 4, today_meetings: 1,
      by_status: [{ status: 'requested', count: 5 }], monthly_trend: [{ month: '2027-01', count: 5 }],
      recent_meetings: [{ id: 1, name: 'Asha Shah', phone: '919876543210', status: 'requested' }],
    } })
    renderRoute(<Dashboard />)

    expect(await screen.findByText('Asha Shah')).toBeVisible()
    expect(screen.getByText('CRM contacts')).toBeVisible()
    expect(screen.getByText('Meeting requests')).toBeVisible()
  })

  test('sidebar navigation, sign out, and mobile menu controls respond', async () => {
    const user = userEvent.setup()
    const onNavigate = vi.fn()
    const { unmount } = renderRoute(<Sidebar onNavigate={onNavigate} />)

    await user.click(screen.getByRole('link', { name: /Meetings/i }))
    expect(onNavigate).toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: /Sign out/i }))
    expect(auth.logout).toHaveBeenCalled()
    unmount()

    renderRoute(<Layout />)
    await user.click(screen.getByRole('button', { name: 'Open menu' }))
    expect(screen.getByRole('button', { name: 'Close menu' })).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Close menu' }))
    expect(screen.getByRole('button', { name: 'Open menu' })).toBeVisible()
  })
})
