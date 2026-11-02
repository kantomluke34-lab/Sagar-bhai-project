import { Filter, Search, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import api from '../api'
import useDebouncedValue from '../hooks/useDebouncedValue'
import { PageTitle, Status } from './Dashboard'

const statuses = ['requested', 'confirmed', 'scheduled', 'completed', 'cancelled', 'no_show']
const stages = ['new', 'qualified', 'proposal', 'won', 'lost']
const when = (value) => value ? new Date(value).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' }) : 'Preferred slot in notes'

export default function Meetings() {
  const [rows, setRows] = useState([]); const [q, setQ] = useState(''); const [status, setStatus] = useState(''); const [selected, setSelected] = useState(null)
  const debouncedQ = useDebouncedValue(q)
  function load() { api.get('/api/meetings', { params: { q: debouncedQ, status } }).then(({ data }) => setRows(data)) }
  useEffect(load, [debouncedQ, status])
  async function open(id) { const { data } = await api.get(`/api/meetings/${id}`); setSelected(data) }
  async function update(key, value) { const { data } = await api.patch(`/api/meetings/${selected.id}`, { [key]: value }); setSelected(data); load() }
  return <>
    <PageTitle kicker="SCHEDULE & HISTORY" title="Meetings" subtitle="Review every request, schedule, status change, and CRM stage." action={<a className="primary-button compact" href="/book" target="_blank">Open booking form</a>} />
    <div className="filter-row"><label className="search"><Search size={17} /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name, phone, company, requirement…" aria-label="Search meetings" /></label><label className="select-filter"><Filter size={16} /><select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filter by status"><option value="">All statuses</option>{statuses.map((item) => <option key={item}>{item}</option>)}</select></label></div>
    <section className="panel no-pad"><div className="table-wrap"><table><thead><tr><th>Contact</th><th>Requirement</th><th>Date & time</th><th>Mode</th><th>Stage</th><th>Status</th></tr></thead><tbody>{rows.map((item) => <tr key={item.id} className="clickable" onClick={() => open(item.id)}><td><strong>{item.name}</strong><small>{item.phone} · {item.company || '—'}</small></td><td><strong>{item.interest || 'General enquiry'}</strong><small className="truncate">{item.purpose}</small></td><td>{when(item.start_at)}</td><td>{item.meeting_mode}</td><td><span className="stage">{item.lead_stage}</span></td><td><Status value={item.status} /></td></tr>)}</tbody></table>{!rows.length && <div className="empty">No meeting requests match these filters.</div>}</div></section>
    {selected && <div className="drawer-backdrop" onClick={() => setSelected(null)}><aside className="drawer" onClick={(e) => e.stopPropagation()}><button className="drawer-close" aria-label="Close meeting details" onClick={() => setSelected(null)}><X /></button><span className="eyebrow">REQUEST #{selected.id}</span><h2>{selected.name}</h2><p className="muted">{selected.company} · {selected.phone}</p><div className="detail-grid"><label>Status<select value={selected.status} onChange={(e) => update('status', e.target.value)}>{statuses.map((item) => <option key={item}>{item}</option>)}</select></label><label>CRM stage<select value={selected.lead_stage} onChange={(e) => update('lead_stage', e.target.value)}>{stages.map((item) => <option key={item}>{item}</option>)}</select></label><div><span>Interest</span><strong>{selected.interest || 'General enquiry'}</strong></div><div><span>Meeting</span><strong>{when(selected.start_at)}</strong></div><div className="span-2"><span>Requirement</span><p>{selected.purpose}</p></div><label className="span-2">Assigned to<input value={selected.assigned_to || ''} onBlur={(e) => update('assigned_to', e.target.value)} onChange={(e) => setSelected((v) => ({ ...v, assigned_to: e.target.value }))} /></label><label className="span-2">Internal notes<textarea rows="4" value={selected.notes || ''} onBlur={(e) => update('notes', e.target.value)} onChange={(e) => setSelected((v) => ({ ...v, notes: e.target.value }))} /></label></div><h3 className="history-title">Activity history</h3><div className="timeline">{selected.history.map((event) => <div key={event.id}><i /><p><strong>{event.action}</strong><span>{event.old_value ? `${event.old_value} → ` : ''}{event.new_value}</span><small>{event.changed_by} · {when(event.created_at)}</small></p></div>)}</div></aside></div>}
  </>
}
