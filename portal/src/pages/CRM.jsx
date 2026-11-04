import { Download, Plus, Save, Search, Upload, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import api from '../api'
import useDebouncedValue from '../hooks/useDebouncedValue'
import { PageTitle } from './Dashboard'

const when = (value) => value ? new Date(value).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Kolkata' }) : '—'
const blank = { name: '', phone: '', email: '', company: '', designation: '', city: '', source: 'manual', lead_stage: 'new', lead_status: 'open' }
const stages = ['new', 'qualified', 'proposal', 'won', 'lost']
const errorMessage = (error, fallback) => {
  const detail = error.response?.data?.detail
  return Array.isArray(detail) ? detail.map((item) => item.msg).join('; ') : detail || fallback
}
const payloadFor = (item) => Object.fromEntries(Object.keys(blank).map((key) => [key, item[key] || blank[key]]))

export default function CRM() {
  const [rows, setRows] = useState([]); const [q, setQ] = useState(''); const [page, setPage] = useState(1); const [total, setTotal] = useState(0)
  const [selected, setSelected] = useState(null); const [draft, setDraft] = useState(null)
  const [busy, setBusy] = useState(false); const [loading, setLoading] = useState(true); const [error, setError] = useState(''); const [notice, setNotice] = useState('')
  const [importData, setImportData] = useState(null); const [importing, setImporting] = useState(false); const [columns, setColumns] = useState({})
  const debouncedQ = useDebouncedValue(q); const pageSize = 25
  async function load() {
    setLoading(true); setError('')
    try {
      const { data } = await api.get('/api/crm/contacts', { params: { q: debouncedQ, page, page_size: pageSize } })
      setRows(Array.isArray(data) ? data : data.items); setTotal(Array.isArray(data) ? data.length : data.total)
    } catch (err) { setError(errorMessage(err, 'Could not load contacts.')) }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [debouncedQ, page])
  async function open(id) {
    setError(''); setNotice('')
    try { const { data } = await api.get(`/api/crm/contacts/${id}`); setSelected(data) }
    catch (err) { setError(errorMessage(err, 'Could not open contact.')) }
  }
  async function saveContact(event) {
    event.preventDefault(); setBusy(true); setError('')
    try {
      if (selected) await api.put(`/api/crm/contacts/${selected.id}`, payloadFor(draft))
      else await api.post('/api/crm/contacts', payloadFor(draft))
      const id = selected?.id; setDraft(null); setNotice('Contact saved.')
      if (id) await open(id)
      await load()
    } catch (err) { setError(errorMessage(err, 'Contact could not be saved.')) }
    finally { setBusy(false) }
  }
  async function saveConsent(event) {
    event.preventDefault(); setBusy(true); setError(''); setNotice('')
    try {
      const { data } = await api.put(`/api/crm/contact-consent/${selected.id}`, { status: selected.consent_status,
        source: selected.consent_source || null, captured_at: selected.consent_captured_at ? new Date(`${String(selected.consent_captured_at).slice(0, 10)}T12:00:00+05:30`).toISOString() : null })
      setSelected(data); setNotice('Consent saved.'); await load()
    } catch (err) { setError(errorMessage(err, 'Consent could not be saved.')) }
    finally { setBusy(false) }
  }
  async function updateLeadStatus(status) {
    setBusy(true); setError(''); setNotice('')
    try {
      await api.put(`/api/crm/contacts/${selected.id}`, { ...payloadFor(selected), lead_status: status })
      await open(selected.id); setNotice(status === 'completed' ? 'Lead marked complete.' : 'Lead reopened.'); await load()
    } catch (err) { setError(errorMessage(err, 'Could not update the lead.')) }
    finally { setBusy(false) }
  }
  async function exportContacts() {
    setBusy(true); setError('')
    try {
      const { data } = await api.get('/api/crm/contacts', { params: { q: debouncedQ } })
      const quote = (value) => `"${String(value ?? '').replaceAll('"', '""')}"`
      const csv = ['Name,Phone,Email,Company,City,Lead Stage,Consent', ...data.map((item) => [item.name, item.phone, item.email, item.company, item.city, item.lead_stage, item.consent_status].map(quote).join(','))].join('\n')
      const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
      const link = document.createElement('a'); link.href = url; link.download = 'mechman-crm-contacts.csv'; link.click(); URL.revokeObjectURL(url)
    } catch (err) { setError(errorMessage(err, 'Could not export contacts.')) }
    finally { setBusy(false) }
  }
  async function previewImport(event) {
    const file = event.target.files?.[0]; if (!file) return
    setBusy(true); setError('')
    try {
      const form = new FormData(); form.append('upload', file)
      const { data } = await api.post('/api/campaigns/import/preview', form)
      const find = (pattern) => data.columns.find((column) => pattern.test(column)) || ''
      setColumns({ name: find(/^(name|full.?name|contact.?name)$/i), phone: data.phone_column || '', email: find(/^e-?mail$/i), company: find(/^(company|organisation|organization)$/i), city: find(/^city$/i), designation: find(/^(designation|job.?title)$/i) })
      setImportData(data)
    } catch (err) { setError(errorMessage(err, 'Could not read the file.')) }
    finally { setBusy(false) }
  }
  const mappedRows = importData && columns.name && columns.phone ? importData.rows.map((row, index) => {
    const name = String(row[columns.name] || '').trim(); const digits = String(row[columns.phone] || '').replace(/\D/g, '')
    return { index: index + 2, valid: name.length >= 2 && name.length <= 160 && digits.length >= 8 && digits.length <= 15 && String(row[columns.email] || '').length <= 255 && String(row[columns.company] || '').length <= 200 && String(row[columns.city] || '').length <= 120 && String(row[columns.designation] || '').length <= 160,
      value: { name, phone: digits, email: row[columns.email] || '', company: row[columns.company] || '', city: row[columns.city] || '', designation: row[columns.designation] || '', lead_stage: 'new' } }
  }) : []
  async function importContacts() {
    const valid = mappedRows.filter((row) => row.valid).map((row) => row.value)
    if (!valid.length) { setError('Choose name and phone columns with at least one valid contact.'); return }
    setBusy(true); setError('')
    try {
      const { data } = await api.post('/api/crm/contacts/import', { rows: valid })
      setNotice(`Import complete: ${data.added} added, ${data.duplicates} duplicates skipped, ${mappedRows.length - valid.length} invalid rows skipped. Consent remains unknown.`)
      setImporting(false); setImportData(null); setPage(1); await load()
    } catch (err) { setError(errorMessage(err, 'Import failed.')) }
    finally { setBusy(false) }
  }
  const setField = (key) => (event) => setDraft((current) => ({ ...current, [key]: event.target.value }))
  const modalError = (selected || draft || importing) && error
  return <>
    <PageTitle kicker="RELATIONSHIP PIPELINE" title="CRM contacts" subtitle="Manage contacts, meeting history, and WhatsApp consent." action={<div className="page-actions"><button className="secondary-button" onClick={() => { setImporting(true); setError(''); setNotice('') }}><Upload size={16} />Import</button><button className="secondary-button" onClick={exportContacts} disabled={busy}><Download size={16} />Export CSV</button><button className="primary-button" onClick={() => { setSelected(null); setDraft({ ...blank }); setError(''); setNotice('') }}><Plus size={16} />Add contact</button></div>} />
    {error && !modalError && <div className="alert error" role="alert">{error}</div>}{notice && !selected && <div className="alert success">{notice}</div>}
    <label className="search wide-search"><Search size={17} /><input value={q} onChange={(e) => { setQ(e.target.value); setPage(1) }} placeholder="Search name, phone, email or company…" aria-label="Search CRM contacts" /></label>
    <section className="panel no-pad crm-table"><div className="table-wrap"><table><thead><tr><th>Contact</th><th>Company</th><th>Lead stage</th><th>Lead status</th><th>Meetings</th><th>Next meeting</th><th>Last activity</th></tr></thead><tbody>{rows.map((item) => <tr key={item.id} className="clickable" onClick={() => open(item.id)}><td><strong>{item.name}</strong><small>{item.phone}{item.email ? ` · ${item.email}` : ''}</small></td><td>{item.company || '—'}<small>{item.designation || item.city || ''}</small></td><td><span className="stage">{item.lead_stage}</span></td><td>{item.lead_status || 'open'}</td><td>{item.meeting_count}</td><td>{when(item.next_meeting)}</td><td>{when(item.last_activity)}</td></tr>)}</tbody></table>{loading ? <div className="empty">Loading contacts…</div> : !rows.length && <div className="empty">No contacts match this search.</div>}</div><div className="pagination"><span>{total ? `${(page - 1) * pageSize + 1}–${Math.min(page * pageSize, total)} of ${total}` : '0 contacts'}</span><button className="secondary-button compact" disabled={page <= 1 || loading} onClick={() => setPage((value) => value - 1)}>Previous</button><button className="secondary-button compact" disabled={page * pageSize >= total || loading} onClick={() => setPage((value) => value + 1)}>Next</button></div></section>
    {(selected || draft) && <div className="drawer-backdrop" onClick={() => { setSelected(null); setDraft(null); setError('') }}><aside className="drawer" onClick={(event) => event.stopPropagation()}><button className="drawer-close" aria-label="Close contact details" onClick={() => { setSelected(null); setDraft(null); setError('') }}><X /></button><span className="eyebrow">{selected ? `CRM CONTACT #${selected.id}` : 'NEW CONTACT'}</span><h2>{selected?.name || 'Add contact'}</h2>{modalError && <div className="alert error" role="alert">{error}</div>}{notice && <div className="alert success">{notice}</div>}
      {draft ? <form className="template-form" onSubmit={saveContact}><label>Name<input required minLength="2" value={draft.name} onChange={setField('name')} /></label><label>Phone<input required value={draft.phone} onChange={setField('phone')} placeholder="Country code + number" /></label><label>Email<input type="email" value={draft.email || ''} onChange={setField('email')} /></label><label>Company<input value={draft.company || ''} onChange={setField('company')} /></label><label>Designation<input value={draft.designation || ''} onChange={setField('designation')} /></label><label>City<input value={draft.city || ''} onChange={setField('city')} /></label><label>Source<input value={draft.source || ''} onChange={setField('source')} placeholder="How this contact found you" /></label><label>Lead stage<select value={draft.lead_stage} onChange={setField('lead_stage')}>{stages.map((stage) => <option key={stage}>{stage}</option>)}</select></label><div className="page-actions"><button className="primary-button" disabled={busy}>Save contact</button>{selected && <button type="button" className="secondary-button" onClick={() => { setDraft(null) }}>Cancel</button>}</div></form> : <><p className="muted">{selected.phone} · {selected.email || 'No email'}</p><div className="page-actions"><button className="secondary-button" onClick={() => { setDraft(payloadFor(selected)) }}>Edit contact</button><button className="primary-button" disabled={busy} onClick={() => updateLeadStatus(selected.lead_status === 'completed' ? 'open' : 'completed')}>{selected.lead_status === 'completed' ? 'Reopen lead' : 'Mark lead complete'}</button></div><p className="muted">Lead completion is separate from meeting status and sales stage.</p><div className="contact-card"><div><span>Company</span><strong>{selected.company || '—'}</strong></div><div><span>Designation</span><strong>{selected.designation || '—'}</strong></div><div><span>City</span><strong>{selected.city || '—'}</strong></div><div><span>Stage</span><strong>{selected.lead_stage}</strong></div><div><span>Lead status</span><strong>{selected.lead_status || 'open'}</strong></div><div><span>Source</span><strong>{selected.source || '—'}</strong></div></div><form className="consent-editor" onSubmit={saveConsent}><div><h3>WhatsApp consent</h3><p>Only contacts who opted in can receive campaign messages.</p></div><div className="detail-grid"><label>Status<select value={selected.consent_status || 'unknown'} onChange={(event) => setSelected({ ...selected, consent_status: event.target.value })}><option value="unknown">Unknown</option><option value="opted_in">Opted in</option><option value="opted_out">Opted out</option></select></label><label>Source<input required={selected.consent_status === 'opted_in'} value={selected.consent_source || ''} onChange={(event) => setSelected({ ...selected, consent_source: event.target.value })} placeholder="Website form" /></label><label>Captured on<input required={selected.consent_status === 'opted_in'} type="date" value={selected.consent_captured_at ? String(selected.consent_captured_at).slice(0, 10) : ''} onChange={(event) => setSelected({ ...selected, consent_captured_at: event.target.value })} /></label></div><button className="secondary-button" disabled={busy}><Save size={15} />Save consent</button></form><h3 className="history-title">Meeting history</h3><div className="meeting-list">{(selected.meetings || []).map((meeting) => <article key={meeting.id}><div><strong>{meeting.interest || 'General enquiry'}</strong><span>{when(meeting.start_at)}</span></div><p>{meeting.purpose}</p><small>{meeting.status} · {meeting.source}</small></article>)}</div></>}
    </aside></div>}
    {importing && <div className="drawer-backdrop" onClick={() => { setImporting(false); setError('') }}><aside className="drawer" onClick={(event) => event.stopPropagation()}><button className="drawer-close" aria-label="Close import" onClick={() => { setImporting(false); setError('') }}><X /></button><h2>Import contacts</h2><p>Upload a CSV or Excel file with headings. Existing phone numbers are skipped. Import does not grant WhatsApp consent.</p>{modalError && <div className="alert error" role="alert">{error}</div>}<label>Choose file<input type="file" accept=".csv,.xls,.xlsx,.xlsm" onChange={previewImport} /></label>{importData && <><p>{importData.row_count} rows found. Choose the matching columns.</p><div className="detail-grid">{['name', 'phone', 'email', 'company', 'city', 'designation'].map((key) => <label key={key}>{key}{['name', 'phone'].includes(key) ? ' *' : ''}<select value={columns[key] || ''} onChange={(event) => setColumns({ ...columns, [key]: event.target.value })}><option value="">{['name', 'phone'].includes(key) ? 'Choose column' : 'Skip'}</option>{importData.columns.map((column) => <option key={column}>{column}</option>)}</select></label>)}</div><p>{mappedRows.filter((row) => row.valid).length} valid rows; {mappedRows.filter((row) => !row.valid).length} invalid rows will be skipped.</p>{mappedRows.some((row) => !row.valid) && <p className="muted">Check rows: {mappedRows.filter((row) => !row.valid).slice(0, 20).map((row) => row.index).join(', ')}</p>}<button className="primary-button" disabled={busy || !columns.name || !columns.phone} onClick={importContacts}>Import valid contacts</button></>}</aside></div>}
  </>
}
