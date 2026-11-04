import { CalendarClock, Copy, Download, FileSpreadsheet, ListFilter, Loader2, Pause, Play, Plus, RotateCcw, Send, Upload, X, XCircle } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import api from '../api'
import useDebouncedValue from '../hooks/useDebouncedValue'
import { PageTitle, Status } from './Dashboard'

const nowLocal = () => {
  const value = new Date(Date.now() + 15 * 60 * 1000)
  return value.toLocaleString('sv-SE', { timeZone: 'Asia/Kolkata' }).slice(0, 16).replace(' ', 'T')
}
const blankCampaign = () => ({ name: '', template_id: '', source_type: 'csv', list_id: '', schedule_type: 'once', scheduled_at: nowLocal(), throttle_seconds: 1, consent_confirmed: false, consent_source: '', consent_captured_at: new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' }), asset_id: null })
const blankAudience = { name: '', description: '', list_type: 'dynamic', filters: { lead_stage: '', city: '', source: '' }, member_ids: [] }
const formatDate = (value) => value ? new Date(value).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Kolkata' }) : '—'
const approved = (template) => String(template.status || '').toUpperCase() === 'APPROVED'
const headerFormat = (template) => String(template?.header_format || (template?.header ? 'TEXT' : 'NONE')).toUpperCase()
const variableCount = (template) => Math.max(0, ...[...(template?.body?.matchAll(/\{\{(\d+)\}\}/g) || [])].map((match) => Number(match[1])))
const normalizePhone = (value) => { const digits = String(value || '').replace(/\D/g, ''); return /^[6-9]\d{9}$/.test(digits) ? `91${digits}` : digits }

export default function Campaigns() {
  const [campaigns, setCampaigns] = useState([])
  const [templates, setTemplates] = useState([])
  const [audiences, setAudiences] = useState([])
  const [contacts, setContacts] = useState([])
  const [contactSearch, setContactSearch] = useState('')
  const [contactPage, setContactPage] = useState(1)
  const [contactTotal, setContactTotal] = useState(0)
  const debouncedContactSearch = useDebouncedValue(contactSearch)
  const [draft, setDraft] = useState(null)
  const [audienceDraft, setAudienceDraft] = useState(null)
  const [detail, setDetail] = useState(null)
  const [importData, setImportData] = useState(null)
  const [phoneColumn, setPhoneColumn] = useState('')
  const [nameColumn, setNameColumn] = useState('')
  const [mapping, setMapping] = useState([])
  const [pastedNumbers, setPastedNumbers] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  async function load() {
    setLoading(true)
    try {
      const [campaignResult, templateResult, audienceResult] = await Promise.all([
        api.get('/api/campaigns'), api.get('/api/templates'), api.get('/api/audiences'),
      ])
      setCampaigns(campaignResult.data || [])
      setTemplates((templateResult.data || []).filter(approved))
      setAudiences(audienceResult.data || [])
    } catch (requestError) { setError(requestError.response?.data?.detail || 'Could not load campaigns.') }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])
  useEffect(() => {
    if (audienceDraft?.list_type !== 'static') return
    api.get('/api/crm/contacts', { params: { q: debouncedContactSearch, page: contactPage, page_size: 25 } })
      .then(({ data }) => { setContacts(data.items || []); setContactTotal(data.total || 0) })
      .catch(() => setError('Could not load contacts for this audience.'))
  }, [audienceDraft?.list_type, debouncedContactSearch, contactPage])
  useEffect(() => {
    const timer = window.setInterval(() => {
      api.get('/api/campaigns').then(({ data }) => setCampaigns(data || [])).catch(() => {})
    }, 5000)
    return () => window.clearInterval(timer)
  }, [])
  useEffect(() => {
    if (!detail?.id) return undefined
    const campaignId = detail.id
    const timer = window.setInterval(() => {
      api.get(`/api/campaigns/${campaignId}`).then(({ data }) => setDetail((current) => current?.id === campaignId ? data : current)).catch(() => {})
    }, 3000)
    return () => window.clearInterval(timer)
  }, [detail?.id])

  const selectedTemplate = useMemo(() => templates.find((item) => item.id === Number(draft?.template_id)), [draft?.template_id, templates])
  const requiredVariables = variableCount(selectedTemplate)
  const mappingOptions = draft?.source_type === 'csv' ? importData?.columns || [] : draft?.source_type === 'paste' ? ['phone'] : ['name', 'phone', 'email', 'company', 'designation', 'city', 'lead_stage', 'source']

  function startDraft() {
    setDraft(blankCampaign()); setImportData(null); setPhoneColumn(''); setNameColumn(''); setMapping([]); setPastedNumbers(''); setError(''); setNotice('')
  }

  async function previewFile(event) {
    const file = event.target.files?.[0]
    if (!file) return
    setBusy(true); setError('')
    try {
      const form = new FormData(); form.append('upload', file)
      const { data } = await api.post('/api/campaigns/import/preview', form)
      setImportData(data); setPhoneColumn(data.phone_column || ''); setNameColumn(data.columns.find((column) => /name/i.test(column)) || '')
      setMapping(Array(requiredVariables).fill(''))
    } catch (requestError) { setError(requestError.response?.data?.detail || 'Could not read recipient file.') }
    finally { setBusy(false) }
  }

  async function uploadMedia(event) {
    const file = event.target.files?.[0]
    if (!file) return
    setBusy(true); setError('')
    try {
      const form = new FormData(); form.append('upload', file)
      const { data } = await api.post('/api/campaigns/media', form)
      setDraft((value) => ({ ...value, asset_id: data.id, asset_name: data.original_name }))
    } catch (requestError) { setError(requestError.response?.data?.detail || 'Media upload failed.') }
    finally { setBusy(false) }
  }

  async function createCampaign(event) {
    event.preventDefault(); setBusy(true); setError(''); setNotice('')
    try {
      let recipients = []
      if (draft.source_type === 'csv') {
        if (!importData || !phoneColumn) throw new Error('Upload a file and select its phone column.')
        recipients = importData.rows.map((row) => ({ phone: normalizePhone(row[phoneColumn]), name: nameColumn ? row[nameColumn] : '', variables: row }))
      } else if (draft.source_type === 'paste') {
        recipients = pastedNumbers.split(/\r?\n|,/).map((value) => value.trim()).filter(Boolean).map(normalizePhone).map((phone) => ({ phone, variables: { phone } }))
      }
      if (recipients.some((row) => row.phone.length < 7 || row.phone.length > 15)) throw new Error('Some phone numbers are invalid. Correct them before scheduling.')
      if (new Set(recipients.map((row) => row.phone)).size !== recipients.length) throw new Error('Duplicate phone numbers found. Remove duplicates before scheduling.')
      if (new Date(`${draft.scheduled_at}:00+05:30`) <= new Date()) throw new Error('Choose a future date and time in India time.')
      const count = draft.source_type === 'list' ? audiences.find((item) => item.id === Number(draft.list_id))?.recipient_count : recipients.length
      if (!count) throw new Error('Choose at least one eligible recipient before scheduling.')
      if (!window.confirm(`Schedule ${draft.schedule_type} campaign “${draft.name}” using ${selectedTemplate.name} for ${count ?? 0} recipient(s) at ${draft.scheduled_at.replace('T', ' ')} IST?`)) return
      const payload = {
        ...draft, template_id: Number(draft.template_id), list_id: draft.list_id ? Number(draft.list_id) : null,
        scheduled_at: new Date(`${draft.scheduled_at}:00+05:30`).toISOString(), parameter_mapping: mapping,
        recipients, consent_captured_at: draft.consent_captured_at ? new Date(`${draft.consent_captured_at}T00:00:00+05:30`).toISOString() : null,
      }
      await api.post('/api/campaigns', payload)
      setDraft(null); setNotice('Campaign scheduled with an immutable recipient snapshot.'); await load()
    } catch (requestError) { setError(requestError.response?.data?.detail || requestError.message || 'Campaign could not be scheduled.') }
    finally { setBusy(false) }
  }

  async function action(id, name) {
    if (name === 'cancel' && !window.confirm('Cancel this campaign? Remaining messages will not be sent.')) return
    if (name === 'retry-failed' && !window.confirm('Review the delivery log first. Retrying can send messages to these recipients again. Continue?')) return
    setBusy(true); setError('')
    try { await api.post(name === 'retry-failed' ? `/api/campaigns/${id}/deliveries/retry-failed` : `/api/campaigns/${id}/${name}`); await load(); if (detail?.id === id) await openDetail(id) }
    catch (requestError) { setError(requestError.response?.data?.detail || `Could not ${name} campaign.`) }
    finally { setBusy(false) }
  }
  async function openDetail(id) {
    try { const { data } = await api.get(`/api/campaigns/${id}`); setDetail(data) }
    catch { setError('Could not load campaign details.') }
  }

  async function saveAudience(event) {
    event.preventDefault(); setBusy(true); setError('')
    try { if (audienceDraft.id) await api.put(`/api/audiences/${audienceDraft.id}`, audienceDraft); else await api.post('/api/audiences', audienceDraft); setAudienceDraft(null); setNotice('CRM audience saved.'); await load() }
    catch (requestError) { setError(requestError.response?.data?.detail || 'Audience could not be saved.') }
    finally { setBusy(false) }
  }
  async function deleteAudience(id) {
    if (!window.confirm('Delete this saved audience? Existing campaigns keep their recipient snapshots.')) return
    setBusy(true); setError('')
    try { await api.delete(`/api/audiences/${id}`); setNotice('Audience deleted.'); await load() }
    catch (requestError) { setError(requestError.response?.data?.detail || 'Audience could not be deleted.') }
    finally { setBusy(false) }
  }

  function deliveryCsv() {
    const quote = (value) => `"${String(value ?? '').replaceAll('"', '""')}"`
    return ['Name,Phone,Status,Error', ...(detail?.deliveries || []).map((item) => [item.name, item.phone, item.status, item.error].map(quote).join(','))].join('\n')
  }
  async function copyLog() {
    try { await navigator.clipboard.writeText((detail?.deliveries || []).map((item) => `${item.phone}\t${item.status}${item.error ? `\t${item.error}` : ''}`).join('\n')); setNotice('Delivery log copied.') }
    catch { setError('Could not copy the delivery log. Use Export CSV instead.') }
  }
  function exportLog() {
    const url = URL.createObjectURL(new Blob([deliveryCsv()], { type: 'text/csv;charset=utf-8' }))
    const link = document.createElement('a'); link.href = url; link.download = `campaign-${detail.id}-deliveries.csv`; link.click(); URL.revokeObjectURL(url)
  }

  return <>
    <PageTitle kicker="WHATSAPP MESSAGING" title="Campaigns" subtitle="An audience is a reusable group of contacts. A campaign sends an approved message to recipients you choose." action={<div className="page-actions"><button className="secondary-button" onClick={() => { setContactSearch(''); setContactPage(1); setAudienceDraft({ ...blankAudience, filters: { ...blankAudience.filters }, member_ids: [] }) }}><ListFilter size={16} />New audience</button><button className="primary-button" onClick={startDraft}><Plus size={16} />New campaign</button></div>} />
    {error && <div className="alert error">{typeof error === 'string' ? error : 'Request failed.'}</div>}
    {notice && <div className="alert success">{notice}</div>}
    <div className="campaign-stats"><article><Send /><span><strong>{campaigns.length}</strong>Total campaigns</span></article><article><CalendarClock /><span><strong>{campaigns.filter((item) => ['scheduled', 'running', 'paused'].includes(item.status)).length}</strong>Active schedules</span></article><article><ListFilter /><span><strong>{audiences.length}</strong>CRM audiences</span></article><article><FileSpreadsheet /><span><strong>{campaigns.reduce((sum, item) => sum + (item.delivered_count || 0), 0)}</strong>Delivered</span></article></div>
    {loading ? <section className="panel empty"><Loader2 className="spin" />Loading campaigns…</section> : <section className="panel no-pad"><div className="table-wrap"><table><thead><tr><th>Campaign</th><th>Template</th><th>Schedule</th><th>Recipients</th><th>Delivery</th><th>Status</th><th>Actions</th></tr></thead><tbody>{campaigns.map((item) => <tr key={item.id} className="clickable" onClick={() => openDetail(item.id)}><td><strong>{item.name}</strong><small>{item.source_type === 'csv' ? 'CSV / Excel snapshot' : item.source_type === 'paste' ? 'Pasted-number snapshot' : 'CRM audience snapshot'}</small></td><td>{item.template_name}</td><td>{formatDate(item.scheduled_at)}<small>{item.schedule_type}</small></td><td>{item.total_recipients}</td><td><span className="delivery-copy">{item.delivered_count || 0} delivered · {item.read_count || 0} read<small>{item.failed_count || 0} failed</small></span></td><td><Status value={item.status} /></td><td onClick={(event) => event.stopPropagation()}><div className="row-actions">{['scheduled', 'running'].includes(item.status) && <button title="Pause" onClick={() => action(item.id, 'pause')}><Pause /></button>}{item.status === 'paused' && <button title="Resume" onClick={() => action(item.id, 'resume')}><Play /></button>}{['scheduled', 'running', 'paused'].includes(item.status) && <button title="Cancel" onClick={() => action(item.id, 'cancel')}><XCircle /></button>}{item.failed_count > 0 && <button title="Retry failed only" onClick={() => action(item.id, 'retry-failed')}><RotateCcw /></button>}</div></td></tr>)}</tbody></table>{!campaigns.length && <div className="empty"><Send size={30} /><h2>No campaigns yet</h2><p>Create a campaign from an approved Meta template and opted-in audience.</p></div>}</div></section>}
    <section className="panel audience-panel"><div className="panel-title"><div><h2>Saved CRM audiences</h2><p>Selected contacts stay fixed; dynamic audiences are matched from your filters when you schedule a campaign.</p></div></div><div className="audience-list">{audiences.map((item) => <article key={item.id}><div><strong>{item.name}</strong><small>{item.list_type} · {item.recipient_count} opted-in contacts</small></div><button className="secondary-button compact" onClick={() => { setContactSearch(''); setContactPage(1); setAudienceDraft({ ...item, filters: { ...blankAudience.filters, ...item.filters }, member_ids: item.member_ids || [] }) }}>Edit</button><button className="icon-button" aria-label={`Delete ${item.name}`} onClick={() => deleteAudience(item.id)}><X /></button></article>)}{!audiences.length && <div className="empty">No saved audiences yet.</div>}</div></section>

    {draft && <div className="drawer-backdrop" onClick={() => setDraft(null)}><aside className="drawer campaign-drawer" onClick={(event) => event.stopPropagation()}><button className="drawer-close" onClick={() => setDraft(null)} aria-label="Close"><X /></button><span className="eyebrow">NEW WABA CAMPAIGN</span><h2>Schedule an approved template</h2><p>Choose the message, choose who receives it, then schedule one send or a recurring campaign.</p>{error && <div className="alert error" role="alert">{typeof error === 'string' ? error : 'Check the fields and try again.'}</div>}<form className="campaign-form" onSubmit={createCampaign}>
      <div className="detail-grid"><label>Campaign name<input required value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} placeholder="November service reminder" /></label><label>Approved template<select required value={draft.template_id} onChange={(event) => { const count = variableCount(templates.find((item) => item.id === Number(event.target.value))); setDraft({ ...draft, template_id: event.target.value, asset_id: null, asset_name: '' }); setMapping(Array(count).fill('')) }}><option value="">Choose template</option>{templates.map((item) => <option key={item.id} value={item.id}>{item.name} · {headerFormat(item)}</option>)}</select></label></div>
      {selectedTemplate && <div className="template-preview"><strong>{selectedTemplate.header || selectedTemplate.name}</strong><p>{selectedTemplate.body}</p><small>{selectedTemplate.language} · {headerFormat(selectedTemplate)} header · {requiredVariables} variables</small></div>}
      <div className="source-tabs three"><button type="button" className={draft.source_type === 'csv' ? 'active' : ''} onClick={() => setDraft({ ...draft, source_type: 'csv' })}><FileSpreadsheet />CSV / Excel</button><button type="button" className={draft.source_type === 'paste' ? 'active' : ''} onClick={() => setDraft({ ...draft, source_type: 'paste' })}><Plus />Paste numbers</button><button type="button" className={draft.source_type === 'list' ? 'active' : ''} onClick={() => setDraft({ ...draft, source_type: 'list' })}><ListFilter />CRM audience</button></div>
      {draft.source_type === 'csv' ? <>
        <label className="upload-zone"><Upload /><strong>{busy ? 'Reading file…' : 'Upload CSV or Excel'}</strong><small>CSV, XLS, or XLSX · first row must contain headings · maximum 10,000 recipients</small><input type="file" accept=".csv,.xls,.xlsx,.xlsm" onChange={previewFile} /></label>
        {importData && <><div className="import-summary"><strong>{importData.row_count} rows loaded</strong><span>{importData.valid_phone_count} valid phone numbers auto-detected</span></div><div className="detail-grid"><label>Phone column<select required value={phoneColumn} onChange={(event) => setPhoneColumn(event.target.value)}><option value="">Choose column</option>{importData.columns.map((column) => <option key={column}>{column}</option>)}</select></label><label>Name column<select value={nameColumn} onChange={(event) => setNameColumn(event.target.value)}><option value="">Optional</option>{importData.columns.map((column) => <option key={column}>{column}</option>)}</select></label></div><div className="import-preview"><table><thead><tr>{importData.columns.slice(0, 5).map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{importData.rows.slice(0, 3).map((row, index) => <tr key={index}>{importData.columns.slice(0, 5).map((column) => <td key={column}>{row[column] || '—'}</td>)}</tr>)}</tbody></table></div></>}
        <div className="consent-box"><label className="check-row"><input type="checkbox" checked={draft.consent_confirmed} onChange={(event) => setDraft({ ...draft, consent_confirmed: event.target.checked })} /><span><strong>I confirm every imported recipient opted in to receive WhatsApp messages.</strong><small>This confirmation, its source, date, and operator are stored for audit.</small></span></label><div className="detail-grid"><label>Consent source<input required value={draft.consent_source} onChange={(event) => setDraft({ ...draft, consent_source: event.target.value })} placeholder="Website form / customer register" /></label><label>Consent captured on<input required type="date" value={draft.consent_captured_at} onChange={(event) => setDraft({ ...draft, consent_captured_at: event.target.value })} /></label></div></div>
      </> : draft.source_type === 'paste' ? <><label>Phone numbers<textarea required rows="7" value={pastedNumbers} onChange={(event) => setPastedNumbers(event.target.value)} placeholder={'919876543210\n919999999999'} /><small>One international-format number per line. Use a template without variables, or map only the phone field.</small></label><div className="consent-box"><label className="check-row"><input type="checkbox" checked={draft.consent_confirmed} onChange={(event) => setDraft({ ...draft, consent_confirmed: event.target.checked })} /><span><strong>I confirm every pasted recipient opted in.</strong><small>The confirmation is recorded with the campaign.</small></span></label><div className="detail-grid"><label>Consent source<input required value={draft.consent_source} onChange={(event) => setDraft({ ...draft, consent_source: event.target.value })} /></label><label>Consent captured on<input required type="date" value={draft.consent_captured_at} onChange={(event) => setDraft({ ...draft, consent_captured_at: event.target.value })} /></label></div></div></> : <label>CRM audience<select required value={draft.list_id} onChange={(event) => setDraft({ ...draft, list_id: event.target.value })}><option value="">Choose opted-in audience</option>{audiences.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.recipient_count} recipients</option>)}</select><small>The current audience is copied into a fixed campaign snapshot.</small></label>}
      {requiredVariables > 0 && <fieldset><legend>Template variable mapping</legend>{Array.from({ length: requiredVariables }, (_, index) => <label key={index}>Variable {`{{${index + 1}}}`}<select required value={mapping[index] || ''} onChange={(event) => setMapping((values) => values.map((value, position) => position === index ? event.target.value : value))}><option value="">Choose recipient field</option>{mappingOptions.map((column) => <option key={column}>{column}</option>)}</select></label>)}</fieldset>}
      {['IMAGE', 'VIDEO', 'DOCUMENT'].includes(headerFormat(selectedTemplate)) && <label className="upload-zone compact"><Upload /><strong>{draft.asset_name || `Upload ${headerFormat(selectedTemplate).toLowerCase()}`}</strong><small>This media becomes the approved template header.</small><input type="file" onChange={uploadMedia} /></label>}
      <div className="detail-grid three"><label>First send<select value={draft.schedule_type} onChange={(event) => setDraft({ ...draft, schedule_type: event.target.value })}><option value="once">Once</option><option value="daily">Daily</option><option value="weekly">Weekly</option></select></label><label>Date & time (IST)<input required type="datetime-local" value={draft.scheduled_at} onChange={(event) => setDraft({ ...draft, scheduled_at: event.target.value })} /></label><label>Throttle<select value={draft.throttle_seconds} onChange={(event) => setDraft({ ...draft, throttle_seconds: Number(event.target.value) })}>{[0, 1, 2, 3, 5].map((value) => <option key={value} value={value}>{value ? `${value} sec` : 'Meta managed'}</option>)}</select></label></div>
      <button className="primary-button wide" disabled={busy || !selectedTemplate}>{busy ? 'Scheduling…' : 'Schedule campaign'}</button>
    </form></aside></div>}

    {audienceDraft && <div className="drawer-backdrop" onClick={() => setAudienceDraft(null)}><aside className="drawer" onClick={(event) => event.stopPropagation()}><button className="drawer-close" onClick={() => setAudienceDraft(null)}><X /></button><span className="eyebrow">CRM AUDIENCE</span><h2>{audienceDraft.id ? 'Edit recipient list' : 'Create a recipient list'}</h2><p>Choose contacts manually, or use filters to build a list from matching opted-in contacts.</p>{error && <div className="alert error" role="alert">{typeof error === 'string' ? error : 'Check the fields and try again.'}</div>}<form className="campaign-form" onSubmit={saveAudience}><label>Name<input required value={audienceDraft.name} onChange={(event) => setAudienceDraft({ ...audienceDraft, name: event.target.value })} /></label><label>Description<textarea rows="3" value={audienceDraft.description} onChange={(event) => setAudienceDraft({ ...audienceDraft, description: event.target.value })} /></label><label>Audience type<select value={audienceDraft.list_type} onChange={(event) => setAudienceDraft({ ...audienceDraft, list_type: event.target.value })}><option value="dynamic">Dynamic segment</option><option value="static">Selected contacts</option></select></label>{audienceDraft.list_type === 'dynamic' ? <div className="detail-grid"><label>Lead stage<select value={audienceDraft.filters.lead_stage} onChange={(event) => setAudienceDraft({ ...audienceDraft, filters: { ...audienceDraft.filters, lead_stage: event.target.value } })}><option value="">Any</option>{['new', 'qualified', 'proposal', 'won', 'lost'].map((item) => <option key={item}>{item}</option>)}</select></label><label>City<input value={audienceDraft.filters.city} onChange={(event) => setAudienceDraft({ ...audienceDraft, filters: { ...audienceDraft.filters, city: event.target.value } })} /></label><label>Source<input value={audienceDraft.filters.source} onChange={(event) => setAudienceDraft({ ...audienceDraft, filters: { ...audienceDraft.filters, source: event.target.value } })} /></label></div> : <><label>Search contacts<input value={contactSearch} onChange={(event) => { setContactSearch(event.target.value); setContactPage(1) }} placeholder="Search name, phone or company" /></label><p>{audienceDraft.member_ids.length} selected. Only opted-in contacts receive campaigns.</p><div className="contact-picker">{contacts.map((contact) => <label key={contact.id}><input type="checkbox" checked={audienceDraft.member_ids.includes(contact.id)} onChange={(event) => setAudienceDraft({ ...audienceDraft, member_ids: event.target.checked ? [...audienceDraft.member_ids, contact.id] : audienceDraft.member_ids.filter((id) => id !== contact.id) })} /><span><strong>{contact.name}</strong><small>{contact.phone}</small></span></label>)}</div><div className="pagination"><span>Page {contactPage} · {contactTotal} contacts</span><button type="button" className="secondary-button compact" disabled={contactPage <= 1} onClick={() => setContactPage((page) => page - 1)}>Previous</button><button type="button" className="secondary-button compact" disabled={contactPage * 25 >= contactTotal} onClick={() => setContactPage((page) => page + 1)}>Next</button></div></>}<div className="consent-note">Only contacts with recorded <strong>opted-in</strong> consent are resolved into a campaign.</div><button className="primary-button wide" disabled={busy}>Save audience</button></form></aside></div>}

    {detail && <div className="drawer-backdrop" onClick={() => setDetail(null)}><aside className="drawer campaign-detail-drawer" onClick={(event) => event.stopPropagation()}><button className="drawer-close" onClick={() => setDetail(null)}><X /></button><span className="eyebrow">CAMPAIGN #{detail.id}</span><h2>{detail.name}</h2><div className="campaign-detail-head"><Status value={detail.status} /><span>{detail.template?.name}</span><span>{detail.total_recipients} recipients</span></div><div className="campaign-progress"><span style={{ width: `${detail.total_recipients ? Math.min(100, ((detail.delivered_count || 0) / detail.total_recipients) * 100) : 0}%` }} /></div><div className="campaign-metrics"><div><strong>{detail.sent_count || 0}</strong><small>Accepted</small></div><div><strong>{detail.delivered_count || 0}</strong><small>Delivered</small></div><div><strong>{detail.read_count || 0}</strong><small>Read</small></div><div><strong>{detail.failed_count || 0}</strong><small>Failed</small></div></div><div className="log-title"><h3>Latest run delivery log</h3><span><button className="secondary-button compact" onClick={copyLog}><Copy size={14} />Copy</button><button className="secondary-button compact" onClick={exportLog}><Download size={14} />Export CSV</button></span></div><div className="delivery-log">{detail.deliveries?.map((item) => <article key={item.id}><span className={`delivery-dot ${item.status}`} /><div><strong>{item.name || item.phone}</strong><small>{item.phone} · {item.status}</small>{item.error && <em>{item.error}</em>}</div></article>)}{!detail.deliveries?.length && <div className="empty">This campaign has not started yet.</div>}</div>{detail.runs?.length > 0 && <><h3>Run history</h3><div className="run-list">{detail.runs.map((run) => <div key={run.id}><span>Run #{run.run_number} · {formatDate(run.scheduled_for)}</span><Status value={run.status} /></div>)}</div></>}</aside></div>}
  </>
}
