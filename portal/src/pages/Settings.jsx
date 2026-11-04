import { BellRing, CheckCircle2, KeyRound, Save, ShieldCheck } from 'lucide-react'
import { useEffect, useState } from 'react'
import api from '../api'
import { PageTitle } from './Dashboard'
import Waba from './Waba'
import WebhookStatus from './WebhookStatus'

const when = (value) => new Date(value).toLocaleString('en-IN', {
  dateStyle: 'medium',
  timeStyle: 'short',
})

export default function Settings() {
  const [form, setForm] = useState(null)
  const [days, setDays] = useState('1, 3')
  const [deliveries, setDeliveries] = useState([])
  const [templates, setTemplates] = useState([])
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [password, setPassword] = useState({ current_password: '', new_password: '', confirm_password: '' })
  const [passwordBusy, setPasswordBusy] = useState(false)
  const [passwordError, setPasswordError] = useState('')
  const [passwordNotice, setPasswordNotice] = useState('')

  useEffect(() => {
    Promise.all([
      api.get('/api/settings/notifications'),
      api.get('/api/settings/notifications/deliveries'),
    ]).then(([settingsResponse, deliveriesResponse]) => {
      setForm(settingsResponse.data)
      setDays(settingsResponse.data.followup_days.join(', '))
      setDeliveries(deliveriesResponse.data)
    }).catch(() => setError('Could not load notification settings.'))
  }, [])
  useEffect(() => { api.get('/api/templates').then(({ data }) => setTemplates(Array.isArray(data) ? data.filter((item) => item.status === 'APPROVED' && !['IMAGE', 'VIDEO', 'DOCUMENT'].includes(item.header_format)) : [])).catch(() => {}) }, [])

  const set = (key) => (event) => setForm((value) => ({
    ...value,
    [key]: event.target.type === 'checkbox' ? event.target.checked : event.target.value,
  }))
  const templateSelector = (prefix) => {
    const nameKey = `${prefix}_meta_template`; const languageKey = `${prefix}_meta_language`; const mappingKey = `${prefix}_meta_parameters`
    const chosen = templates.find((item) => item.name === form[nameKey] && item.language === (form[languageKey] || 'en_US'))
    const count = Math.max(0, ...[...(chosen?.body?.matchAll(/\{\{(\d+)\}\}/g) || [])].map((item) => Number(item[1])))
    const mapping = form[mappingKey] || ['name']
    return <><label>Approved WhatsApp template<select value={chosen?.id || ''} onChange={(event) => {
      const template = templates.find((item) => String(item.id) === event.target.value)
      const variableCount = Math.max(0, ...[...(template?.body?.matchAll(/\{\{(\d+)\}\}/g) || [])].map((item) => Number(item[1])))
      setForm((value) => ({ ...value, [nameKey]: template?.name || '', [languageKey]: template?.language || 'en_US', [mappingKey]: Array(variableCount).fill('name') }))
    }}><option value="">None — free text only within the 24-hour reply window</option>{templates.map((item) => <option key={item.id} value={item.id}>{item.name} ({item.language})</option>)}</select><small>{chosen ? 'This approved message is sent instead of the free text above.' : form[nameKey] ? `Saved template ${form[nameKey]} is unavailable or not approved; select another.` : 'Select an approved template to send outside the 24-hour reply window.'}</small></label>{chosen && <p className="muted">{chosen.body}</p>}{chosen && Array.from({ length: count }, (_, index) => <label key={index}>Value for {`{{${index + 1}}}`}<select value={mapping[index] || ''} onChange={(event) => setForm((value) => ({ ...value, [mappingKey]: Array.from({ length: count }, (_, position) => position === index ? event.target.value : mapping[position] || 'name') }))}><option value="">Choose value</option>{(prefix === 'reminder' ? ['name', 'date', 'time', 'minutes'] : ['name', 'date', 'time', 'days']).map((value) => <option key={value}>{value}</option>)}</select></label>)}</>
  }

  async function save(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    setNotice('')
    const followupDays = days.split(',').map((value) => Number(value.trim())).filter(Boolean)
    try {
      const normalized = { ...form }
      for (const prefix of ['reminder', 'followup']) {
        const mappingKey = `${prefix}_meta_parameters`
        const template = templates.find((item) => item.name === form[`${prefix}_meta_template`] && item.language === (form[`${prefix}_meta_language`] || 'en_US'))
        if (!normalized[mappingKey] && template) {
          const count = Math.max(0, ...[...(template.body?.matchAll(/\{\{(\d+)\}\}/g) || [])].map((item) => Number(item[1])))
          normalized[mappingKey] = Array(count).fill('name')
        }
      }
      const { data } = await api.put('/api/settings/notifications', {
        ...normalized,
        reminder_minutes_before: Number(form.reminder_minutes_before),
        followup_days: followupDays,
      })
      setForm(data)
      setDays(data.followup_days.join(', '))
      setNotice('Notification settings saved.')
    } catch (requestError) {
      const detail = requestError.response?.data?.detail
      setError(Array.isArray(detail) ? detail[0]?.msg : detail || 'Could not save settings.')
    } finally {
      setBusy(false)
    }
  }

  async function changePassword(event) {
    event.preventDefault()
    setPasswordBusy(true); setPasswordError(''); setPasswordNotice('')
    if (password.new_password !== password.confirm_password) {
      setPasswordError('New passwords do not match.'); setPasswordBusy(false); return
    }
    try {
      const { data } = await api.post('/api/auth/change-password', password)
      setPassword({ current_password: '', new_password: '', confirm_password: '' })
      setPasswordNotice(data.message || 'Password changed successfully.')
    } catch (requestError) {
      const detail = requestError.response?.data?.detail
      setPasswordError(Array.isArray(detail) ? detail[0]?.msg : detail || 'Password could not be changed.')
    } finally { setPasswordBusy(false) }
  }

  if (!form) return <div className="screen-center">{error || 'Loading settings…'}</div>

  return (
    <>
      <PageTitle
        kicker="AUTOMATED OUTREACH"
        title="Reminder & follow-up settings"
        subtitle="Messages are sent through the official WABA transport and recorded once."
      />
      <form className="settings-grid" onSubmit={save}>
        <section className="panel settings-panel">
          <div className="settings-heading"><BellRing /><div><h2>Meeting reminder</h2><p>Send before confirmed or scheduled calls.</p></div></div>
          <label className="toggle-row"><span><strong>Enable reminders</strong><small>Pause without deleting your template.</small></span><input type="checkbox" checked={form.reminder_enabled} onChange={set('reminder_enabled')} /></label>
          <label>Minutes before the meeting<input type="number" min="15" max="1440" value={form.reminder_minutes_before} onChange={set('reminder_minutes_before')} required /></label>
          <label>Reminder message<textarea rows="7" value={form.reminder_template} onChange={set('reminder_template')} required /></label>
          {templateSelector('reminder')}
        </section>
        <section className="panel settings-panel">
          <div className="settings-heading"><CheckCircle2 /><div><h2>Meeting follow-ups</h2><p>Send after confirmed, scheduled, or completed calls.</p></div></div>
          <label className="toggle-row"><span><strong>Enable follow-ups</strong><small>Each configured delay sends once.</small></span><input type="checkbox" checked={form.followup_enabled} onChange={set('followup_enabled')} /></label>
          <label>Days after meeting<input value={days} onChange={(event) => setDays(event.target.value)} placeholder="1, 3" required /><small>Comma-separated days, from 1 to 90.</small></label>
          <label>Follow-up message<textarea rows="7" value={form.followup_template} onChange={set('followup_template')} required /></label>
          {templateSelector('followup')}
        </section>
        <div className="settings-actions span-2">
          <div>{error && <div className="alert error">{error}</div>}{notice && <div className="alert success">{notice}</div>}</div>
          <button className="primary-button" disabled={busy}><Save size={17} />{busy ? 'Saving…' : 'Save settings'}</button>
        </div>
      </form>
      <section className="panel">
        <div className="panel-title"><h2>Recent notification deliveries</h2></div>
        <div className="table-wrap"><table><thead><tr><th>Contact</th><th>Type</th><th>Meeting</th><th>Last attempt</th><th>Status</th></tr></thead><tbody>{deliveries.map((item) => <tr key={item.id}><td><strong>{item.name}</strong><small>{item.recipient}</small></td><td>{item.notification_key.replaceAll('_', ' ')}</td><td>{when(item.start_at)}</td><td>{when(item.sent_at)}</td><td>{item.status}<small>{item.error || ''}</small></td></tr>)}</tbody></table>{!deliveries.length && <div className="empty">No automated messages attempted yet.</div>}</div>
      </section>
      <section className="panel account-settings">
        <div className="settings-heading"><ShieldCheck /><div><h2>Account security</h2><p>Change the password used to access this CRM.</p></div></div>
        <form className="password-form" onSubmit={changePassword}>
          <label>Current password<input aria-label="Current password" required type="password" autoComplete="current-password" value={password.current_password} onChange={(event) => setPassword({ ...password, current_password: event.target.value })} /></label>
          <label>New password<input aria-label="New password" required minLength="10" type="password" autoComplete="new-password" value={password.new_password} onChange={(event) => setPassword({ ...password, new_password: event.target.value })} /><small>Use at least 10 characters.</small></label>
          <label>Confirm new password<input aria-label="Confirm new password" required minLength="10" type="password" autoComplete="new-password" value={password.confirm_password} onChange={(event) => setPassword({ ...password, confirm_password: event.target.value })} /></label>
          <div className="password-actions"><div>{passwordError && <div className="alert error">{passwordError}</div>}{passwordNotice && <div className="alert success">{passwordNotice}</div>}</div><button className="primary-button" disabled={passwordBusy}><KeyRound size={17} />{passwordBusy ? 'Changing…' : 'Change password'}</button></div>
        </form>
      </section>
      <div className="notice"><strong>Available placeholders</strong><p>{'{name}, {date}, {time}, {minutes}, {days}'}</p></div>
      <details className="panel"><summary>Advanced WhatsApp connection and webhook settings</summary><p>These details are normally maintained by your administrator.</p><Waba embedded /><WebhookStatus embedded /></details>
    </>
  )
}
