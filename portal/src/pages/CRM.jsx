import { Download, Save, Search, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import api from '../api'
import useDebouncedValue from '../hooks/useDebouncedValue'
import { PageTitle } from './Dashboard'

const when = (value) => value ? new Date(value).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' }) : '—'

export default function CRM() {
  const [rows, setRows] = useState([]); const [q, setQ] = useState(''); const [selected, setSelected] = useState(null); const [busy, setBusy] = useState(false); const [error, setError] = useState('')
  const debouncedQ = useDebouncedValue(q)
  useEffect(() => { api.get('/api/crm/contacts', { params: { q: debouncedQ } }).then(({ data }) => setRows(data)) }, [debouncedQ])
  async function open(id) { const { data } = await api.get(`/api/crm/contacts/${id}`); setSelected(data) }
  async function saveConsent(event) {
    event.preventDefault(); setBusy(true); setError('')
    try {
      const { data } = await api.put(`/api/crm/contact-consent/${selected.id}`, {
        status: selected.consent_status,
        source: selected.consent_source || null,
        captured_at: selected.consent_captured_at ? new Date(selected.consent_captured_at).toISOString() : null,
      })
      setSelected(data)
    } catch (requestError) { setError(requestError.response?.data?.detail || 'Consent could not be saved.') }
    finally { setBusy(false) }
  }
  function exportContacts() {
    const quote = (value) => `"${String(value ?? '').replaceAll('"', '""')}"`
    const csv = ['Name,Phone,Email,Company,City,Lead Stage,Consent', ...rows.map((item) => [item.name, item.phone, item.email, item.company, item.city, item.lead_stage, item.consent_status].map(quote).join(','))].join('\n')
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
    const link = document.createElement('a'); link.href = url; link.download = 'mechman-crm-contacts.csv'; link.click(); URL.revokeObjectURL(url)
  }
  return <>
    <PageTitle kicker="RELATIONSHIP PIPELINE" title="CRM contacts" subtitle="One contact record with meeting history, consent, and next action." action={<button className="secondary-button" onClick={exportContacts}><Download size={16} />Export CSV</button>} />
    {error && <div className="alert error">{error}</div>}
    <label className="search wide-search"><Search size={17} /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search contact, phone, or company…" aria-label="Search CRM contacts" /></label>
    <section className="panel no-pad"><div className="table-wrap"><table><thead><tr><th>Contact</th><th>Company</th><th>Lead stage</th><th>Meetings</th><th>Next meeting</th><th>Last activity</th></tr></thead><tbody>{rows.map((item) => <tr key={item.id} className="clickable" onClick={() => open(item.id)}><td><strong>{item.name}</strong><small>{item.phone}{item.email ? ` · ${item.email}` : ''}</small></td><td>{item.company || '—'}<small>{item.designation || item.city || ''}</small></td><td><span className="stage">{item.lead_stage}</span></td><td>{item.meeting_count}</td><td>{when(item.next_meeting)}</td><td>{when(item.last_activity)}</td></tr>)}</tbody></table>{!rows.length && <div className="empty">No contacts yet. New bookings create CRM contacts automatically.</div>}</div></section>
    {selected && <div className="drawer-backdrop" onClick={() => setSelected(null)}><aside className="drawer" onClick={(e) => e.stopPropagation()}><button className="drawer-close" aria-label="Close contact details" onClick={() => setSelected(null)}><X /></button><span className="eyebrow">CRM CONTACT #{selected.id}</span><h2>{selected.name}</h2><p className="muted">{selected.phone} · {selected.email || 'No email'}</p><div className="contact-card"><div><span>Company</span><strong>{selected.company || '—'}</strong></div><div><span>Designation</span><strong>{selected.designation || '—'}</strong></div><div><span>City</span><strong>{selected.city || '—'}</strong></div><div><span>Stage</span><strong>{selected.lead_stage}</strong></div></div><form className="consent-editor" onSubmit={saveConsent}><div><h3>WhatsApp consent</h3><p>Only opted-in contacts can enter campaign audiences.</p></div><div className="detail-grid"><label>Status<select value={selected.consent_status || 'unknown'} onChange={(event) => setSelected({ ...selected, consent_status: event.target.value })}><option value="unknown">Unknown</option><option value="opted_in">Opted in</option><option value="opted_out">Opted out</option></select></label><label>Source<input required={selected.consent_status === 'opted_in'} value={selected.consent_source || ''} onChange={(event) => setSelected({ ...selected, consent_source: event.target.value })} placeholder="Website form" /></label><label>Captured on<input required={selected.consent_status === 'opted_in'} type="date" value={selected.consent_captured_at ? String(selected.consent_captured_at).slice(0, 10) : ''} onChange={(event) => setSelected({ ...selected, consent_captured_at: event.target.value })} /></label></div><button className="secondary-button" disabled={busy}><Save size={15} />{busy ? 'Saving…' : 'Save consent'}</button></form><h3 className="history-title">Meeting history</h3><div className="meeting-list">{selected.meetings.map((meeting) => <article key={meeting.id}><div><strong>{meeting.interest || 'General enquiry'}</strong><span>{when(meeting.start_at)}</span></div><p>{meeting.purpose}</p><small>{meeting.status} · {meeting.source}</small></article>)}</div></aside></div>}
  </>
}
