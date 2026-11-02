import { BellRing, CheckCircle2, Save } from 'lucide-react'
import { useEffect, useState } from 'react'
import api from '../api'
import { PageTitle } from './Dashboard'

const when = (value) => new Date(value).toLocaleString('en-IN', {
  dateStyle: 'medium',
  timeStyle: 'short',
})

export default function Settings() {
  const [form, setForm] = useState(null)
  const [days, setDays] = useState('1, 3')
  const [deliveries, setDeliveries] = useState([])
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')

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

  const set = (key) => (event) => setForm((value) => ({
    ...value,
    [key]: event.target.type === 'checkbox' ? event.target.checked : event.target.value,
  }))

  async function save(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    setNotice('')
    const followupDays = days.split(',').map((value) => Number(value.trim())).filter(Boolean)
    try {
      const { data } = await api.put('/api/settings/notifications', {
        ...form,
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

  if (!form) return <div className="screen-center">Loading settings…</div>

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
        </section>
        <section className="panel settings-panel">
          <div className="settings-heading"><CheckCircle2 /><div><h2>Meeting follow-ups</h2><p>Send after confirmed, scheduled, or completed calls.</p></div></div>
          <label className="toggle-row"><span><strong>Enable follow-ups</strong><small>Each configured delay sends once.</small></span><input type="checkbox" checked={form.followup_enabled} onChange={set('followup_enabled')} /></label>
          <label>Days after meeting<input value={days} onChange={(event) => setDays(event.target.value)} placeholder="1, 3" required /><small>Comma-separated days, from 1 to 90.</small></label>
          <label>Follow-up message<textarea rows="7" value={form.followup_template} onChange={set('followup_template')} required /></label>
        </section>
        <div className="settings-actions span-2">
          <div>{error && <div className="alert error">{error}</div>}{notice && <div className="alert success">{notice}</div>}</div>
          <button className="primary-button" disabled={busy}><Save size={17} />{busy ? 'Saving…' : 'Save settings'}</button>
        </div>
      </form>
      <section className="panel">
        <div className="panel-title"><h2>Recent notification deliveries</h2></div>
        <div className="table-wrap"><table><thead><tr><th>Contact</th><th>Type</th><th>Meeting</th><th>Sent</th></tr></thead><tbody>{deliveries.map((item) => <tr key={item.id}><td><strong>{item.name}</strong><small>{item.recipient}</small></td><td>{item.notification_key.replaceAll('_', ' ')}</td><td>{when(item.start_at)}</td><td>{when(item.sent_at)}</td></tr>)}</tbody></table>{!deliveries.length && <div className="empty">No automated messages sent yet.</div>}</div>
      </section>
      <div className="notice"><strong>Available placeholders</strong><p>{'{name}, {date}, {time}, {minutes}, {days}'}</p></div>
    </>
  )
}
