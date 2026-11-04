import { Filter, Search, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import api from '../api'
import useDebouncedValue from '../hooks/useDebouncedValue'
import { PageTitle, Status } from './Dashboard'
import SelectField from '../components/SelectField'

const statuses = ['requested', 'confirmed', 'scheduled', 'completed', 'cancelled', 'no_show']
const stages = ['new', 'qualified', 'proposal', 'won', 'lost']
const when = (value) => value ? new Date(value).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Kolkata' }) : '—'
const localInput = (value) => value ? new Date(value).toLocaleString('sv-SE', { timeZone: 'Asia/Kolkata' }).slice(0, 16).replace(' ', 'T') : ''
const detailMessage = (error) => {
  const detail = error.response?.data?.detail
  return Array.isArray(detail) ? detail[0]?.msg : detail || 'Could not save the meeting. Please try again.'
}

export default function Meetings() {
  const [rows, setRows] = useState([])
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('')
  const [selected, setSelected] = useState(null)
  const [draft, setDraft] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [newMeeting, setNewMeeting] = useState(null)
  const debouncedQ = useDebouncedValue(q)

  async function load() {
    setLoading(true); setError('')
    try { const { data } = await api.get('/api/meetings', { params: { q: debouncedQ, status } }); setRows(data) }
    catch { setError('Could not load meetings. Please try again.') }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [debouncedQ, status])
  async function open(id) {
    setError(''); setNotice('')
    try {
      const { data } = await api.get(`/api/meetings/${id}`)
      setSelected(data)
      setDraft({ ...data, start_input: localInput(data.start_at), end_input: localInput(data.end_at) })
    } catch { setError('Could not open this meeting. Please try again.') }
  }
  async function save(changes) {
    setBusy(true); setError(''); setNotice('')
    try {
      const { data } = await api.patch(`/api/meetings/${selected.id}`, changes)
      setSelected(data)
      setDraft({ ...data, start_input: localInput(data.start_at), end_input: localInput(data.end_at) })
      setNotice('Meeting saved.')
      await load()
    } catch (err) { setError(detailMessage(err)) }
    finally { setBusy(false) }
  }
  function submit(event, statusOverride) {
    event.preventDefault()
    if (!draft.start_input || !draft.end_input || draft.end_input <= draft.start_input) {
      setError('End time must be after the start time.'); return
    }
    save({ status: statusOverride || draft.status, lead_stage: draft.lead_stage, meeting_mode: draft.meeting_mode || '',
      assigned_to: draft.assigned_to || '', notes: draft.notes || '',
      start_at: `${draft.start_input}:00+05:30`, end_at: `${draft.end_input}:00+05:30` })
  }
  const set = (key) => (event) => setDraft((current) => ({ ...current, [key]: event.target.value }))
  async function createMeeting(event) {
    event.preventDefault(); setBusy(true); setError('')
    try {
      if (newMeeting.end_input <= newMeeting.start_input) throw new Error('End time must be after start time.')
      const { start_input, end_input, ...values } = newMeeting
      await api.post('/api/meetings', { ...values, start_at: `${start_input}:00+05:30`, end_at: `${end_input}:00+05:30` })
      setNewMeeting(null); setNotice('Meeting added.'); await load()
    } catch (err) { setError(err.response ? detailMessage(err) : err.message) }
    finally { setBusy(false) }
  }

  return <>
    <PageTitle kicker="SCHEDULE & HISTORY" title="Meetings" subtitle="Review requests, update their outcome, and schedule the next conversation." action={<div className="page-actions"><button className="primary-button compact" onClick={() => { setError(''); setNewMeeting({ name: '', phone: '', email: '', company: '', interest: '', purpose: '', meeting_mode: 'Phone call', start_input: '', end_input: '', status: 'scheduled', lead_stage: 'new' }) }}>Add meeting</button><a className="secondary-button compact" href="/book" target="_blank" rel="noreferrer">Open booking form</a></div>} />
    {error && !selected && !newMeeting && <div className="alert error" role="alert">{error}</div>}{notice && !selected && !newMeeting && <div className="alert success">{notice}</div>}
    <div className="filter-row"><label className="search"><Search size={17} /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name, phone, company, requirement…" aria-label="Search meetings" /></label><div className="filter-select"><Filter size={16} /><SelectField value={status} onChange={setStatus} aria-label="Filter by status" options={[{ value: '', label: 'All statuses' }, ...statuses.map((item) => ({ value: item, label: item.replaceAll('_', ' ') }))]} /></div></div>
    <section className="panel no-pad"><div className="table-wrap"><table><thead><tr><th>Contact</th><th>Requirement</th><th>Date & time</th><th>Mode</th><th>Stage</th><th>Status</th></tr></thead><tbody>{rows.map((item) => <tr key={item.id} className="clickable" onClick={() => open(item.id)}><td><strong>{item.name}</strong><small>{item.phone} · {item.company || '—'}</small></td><td><strong>{item.interest || 'General enquiry'}</strong><small className="truncate">{item.purpose}</small></td><td>{when(item.start_at)}</td><td>{item.meeting_mode}</td><td><span className="stage">{item.lead_stage}</span></td><td><Status value={item.status} /></td></tr>)}</tbody></table>{loading ? <div className="empty">Loading meetings…</div> : !rows.length && <div className="empty">No meeting requests match these filters.</div>}</div></section>
    {selected && draft && <div className="drawer-backdrop" onClick={() => { setSelected(null); setDraft(null) }}><aside className="drawer" onClick={(e) => e.stopPropagation()}><button className="drawer-close" aria-label="Close meeting details" onClick={() => { setSelected(null); setDraft(null) }}><X /></button><span className="eyebrow">REQUEST #{selected.id}</span><h2>{selected.name}</h2><p className="muted">{selected.company} · {selected.phone}</p><p className="muted">Meeting status tracks the call. CRM stage tracks the sales opportunity.</p>
      {error && <div className="alert error" role="alert">{error}</div>}{notice && <div className="alert success">{notice}</div>}
      <form onSubmit={submit}><div className="detail-grid"><label>Status<SelectField value={draft.status} onChange={(value) => setDraft((current) => ({ ...current, status: value }))} aria-label="Meeting status" options={statuses.map((item) => ({ value: item, label: item.replaceAll('_', ' ') }))} /></label><label>CRM stage<SelectField value={draft.lead_stage} onChange={(value) => setDraft((current) => ({ ...current, lead_stage: value }))} aria-label="CRM stage" options={stages} /></label><label>Start (IST)<input type="datetime-local" required value={draft.start_input} onChange={set('start_input')} /></label><label>End (IST)<input type="datetime-local" required value={draft.end_input} onChange={set('end_input')} /></label><label className="span-2">Meeting mode<input value={draft.meeting_mode || ''} onChange={set('meeting_mode')} /></label><div><span>Interest</span><strong>{selected.interest || 'General enquiry'}</strong></div><div className="span-2"><span>Requirement</span><p>{selected.purpose}</p></div><label className="span-2">Assigned to<input value={draft.assigned_to || ''} onChange={set('assigned_to')} placeholder="Enter a team member's name" /></label><label className="span-2">Internal notes<textarea rows="4" value={draft.notes || ''} onChange={set('notes')} /></label></div><div className="page-actions"><button className="primary-button" disabled={busy}>{busy ? 'Saving…' : 'Save changes'}</button>{selected.status !== 'completed' && <button type="button" className="secondary-button" disabled={busy} onClick={(event) => submit(event, 'completed')}>Mark complete</button>}</div></form>
      <h3 className="history-title">Activity history</h3><div className="timeline">{(selected.history || []).map((event) => <div key={event.id}><i /><p><strong>{event.action.replaceAll('_', ' ')}</strong><span>{event.old_value ? `${event.old_value} → ` : ''}{event.new_value}</span><small>{event.changed_by} · {when(event.created_at)}</small></p></div>)}</div></aside></div>}
    {newMeeting && <div className="drawer-backdrop" onClick={() => setNewMeeting(null)}><aside className="drawer" onClick={(event) => event.stopPropagation()}><button className="drawer-close" aria-label="Close new meeting" onClick={() => setNewMeeting(null)}><X /></button><h2>Add a meeting</h2><p>Record an existing appointment or a completed call. Times are in India time.</p>{error && <div className="alert error" role="alert">{error}</div>}<form className="template-form" onSubmit={createMeeting}>{[['name', 'Contact name'], ['phone', 'Phone number'], ['email', 'Email'], ['company', 'Company'], ['interest', 'Interest'], ['purpose', 'Requirement'], ['meeting_mode', 'Meeting mode']].map(([key, label]) => <label key={key}>{label}<input required={['name', 'phone'].includes(key)} type={key === 'email' ? 'email' : 'text'} value={newMeeting[key]} onChange={(event) => setNewMeeting({ ...newMeeting, [key]: event.target.value })} /></label>)}<label>Start (IST)<input required type="datetime-local" value={newMeeting.start_input} onChange={(event) => setNewMeeting({ ...newMeeting, start_input: event.target.value })} /></label><label>End (IST)<input required type="datetime-local" value={newMeeting.end_input} onChange={(event) => setNewMeeting({ ...newMeeting, end_input: event.target.value })} /></label><label>Status<select value={newMeeting.status} onChange={(event) => setNewMeeting({ ...newMeeting, status: event.target.value })}>{statuses.map((item) => <option key={item}>{item}</option>)}</select></label><label>CRM stage<select value={newMeeting.lead_stage} onChange={(event) => setNewMeeting({ ...newMeeting, lead_stage: event.target.value })}>{stages.map((item) => <option key={item}>{item}</option>)}</select></label><button className="primary-button" disabled={busy}>{busy ? 'Saving…' : 'Add meeting'}</button></form></aside></div>}
  </>
}
