import { CalendarClock, Copy, Download, FileSpreadsheet, GitBranch, ListFilter, Loader2, Pause, Play, Plus, RotateCcw, Send, Upload, X, XCircle } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import api from '../api'
import useDebouncedValue from '../hooks/useDebouncedValue'
import { PageTitle, Status } from './Dashboard'
import Hint from '../components/Hint'

const nowLocal = () => {
  const value = new Date(Date.now() + 15 * 60 * 1000)
  return value.toLocaleString('sv-SE', { timeZone: 'Asia/Kolkata' }).slice(0, 16).replace(' ', 'T')
}
const blankCampaign = (listId = '') => ({ name: '', template_id: '', dm_flow_version_id: '', source_type: 'list', list_id: listId, schedule_type: 'once', scheduled_at: nowLocal(), throttle_seconds: 1, consent_confirmed: false, consent_source: '', consent_captured_at: new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' }), consent_evidence: '', asset_id: null })
const blankAudience = () => ({ name: '', description: '', list_type: 'static', member_ids: [] })
const formatDate = (value) => value ? new Date(value).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Kolkata' }) : '—'
const approved = (template) => String(template.status || '').toUpperCase() === 'APPROVED'
const headerFormat = (template) => String(template?.header_format || (template?.header ? 'TEXT' : 'NONE')).toUpperCase()
const variableCount = (template) => Math.max(0, ...[...(template?.body?.matchAll(/\{\{(\d+)\}\}/g) || [])].map((match) => Number(match[1])))
const normalizePhone = (value) => { const digits = String(value || '').replace(/\D/g, ''); return /^[6-9]\d{9}$/.test(digits) ? `91${digits}` : digits }

export function requestErrorMessage(requestError, fallback) {
  const detail = requestError?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail)) {
    const messages = detail.map((item) => {
      if (typeof item === 'string') return item
      const field = (item?.loc || []).filter((part) => part !== 'body').join(' › ')
      const message = item?.msg || item?.message
      return message ? `${field ? `${field}: ` : ''}${message}` : ''
    }).filter(Boolean)
    if (messages.length) return messages.join(' ')
  }
  if (detail && typeof detail === 'object') {
    const message = detail.message || detail.msg
    if (typeof message === 'string' && message.trim()) return message
  }
  return requestError?.message || fallback
}

function prepareImportedRecipients(rows, phoneColumn, nameColumn = '') {
  const seen = new Set()
  const recipients = []
  let invalidCount = 0
  let duplicateCount = 0
  for (const row of rows || []) {
    const phone = normalizePhone(row?.[phoneColumn])
    if (phone.length < 7 || phone.length > 15) { invalidCount += 1; continue }
    if (seen.has(phone)) { duplicateCount += 1; continue }
    seen.add(phone)
    recipients.push({ phone, name: nameColumn ? row?.[nameColumn] || '' : '', variables: row })
  }
  return { recipients, invalidCount, duplicateCount }
}

function csvCell(value) {
  let text = String(value ?? '')
  if (/^\s*[=+@-]/.test(text)) text = `'${text}`
  return `"${text.replaceAll('"', '""')}"`
}

export default function Campaigns() {
  const [campaigns, setCampaigns] = useState([])
  const [templates, setTemplates] = useState([])
  const [dmFlows, setDmFlows] = useState([])
  const [audiences, setAudiences] = useState([])
  const [contacts, setContacts] = useState([])
  const [contactLoading, setContactLoading] = useState(false)
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
      const [campaignResult, templateResult, audienceResult, flowResult] = await Promise.all([
        api.get('/api/campaigns'), api.get('/api/templates'), api.get('/api/audiences'), api.get('/api/dm-flows', { params: { published_only: true } }),
      ])
      setCampaigns(campaignResult.data || [])
      setTemplates((templateResult.data || []).filter(approved))
      setAudiences(audienceResult.data || [])
      setDmFlows(flowResult.data || [])
    } catch (requestError) { setError(requestErrorMessage(requestError, 'Could not load campaigns.')) }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])
  useEffect(() => {
    const refreshPublishedFlows = () => {
      api.get('/api/dm-flows', { params: { published_only: true } })
        .then(({ data }) => setDmFlows(data || []))
        .catch(() => {})
    }
    window.addEventListener('focus', refreshPublishedFlows)
    return () => window.removeEventListener('focus', refreshPublishedFlows)
  }, [])
  useEffect(() => {
    if (!audienceDraft) return
    let active = true
    setContactLoading(true)
    api.get('/api/crm/contacts', { params: { q: debouncedContactSearch, page: contactPage, page_size: 25, consent_status: 'opted_in' } })
      .then(({ data }) => { if (active) { setContacts(data.items || []); setContactTotal(data.total || 0) } })
      .catch(() => { if (active) setError('Could not load contacts for this audience.') })
      .finally(() => { if (active) setContactLoading(false) })
    return () => { active = false }
  }, [Boolean(audienceDraft), debouncedContactSearch, contactPage])
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
  const selectedAudience = useMemo(() => audiences.find((item) => item.id === Number(draft?.list_id)), [audiences, draft?.list_id])
  const unavailableMembers = (audienceDraft?.unavailable_members || []).filter((member) => audienceDraft.member_ids.includes(member.id))
  const eligibleSelectedCount = (audienceDraft?.member_ids.length || 0) - unavailableMembers.length
  const requiredVariables = variableCount(selectedTemplate)
  const mappingOptions = draft?.source_type === 'csv' ? importData?.columns || [] : draft?.source_type === 'paste' ? ['phone'] : ['name', 'phone', 'email', 'company', 'designation', 'city', 'lead_stage', 'source']
  const importStats = useMemo(
    () => prepareImportedRecipients(importData?.rows || [], phoneColumn, nameColumn),
    [importData?.rows, phoneColumn, nameColumn],
  )

  function startDraft(listId = '') {
    setDraft(blankCampaign(listId)); setImportData(null); setPhoneColumn(''); setNameColumn(''); setMapping([]); setPastedNumbers(''); setError(''); setNotice('')
  }

  function startAudience(audience = null) {
    setContactSearch(''); setContactPage(1); setContacts([]); setContactTotal(0)
    setAudienceDraft(audience ? { ...audience, member_ids: audience.member_ids || [] } : blankAudience())
    setError(''); setNotice('')
  }

  function chooseSource(sourceType) {
    setDraft((current) => ({ ...current, source_type: sourceType }))
    setMapping(Array(requiredVariables).fill(''))
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
    } catch (requestError) { setError(requestErrorMessage(requestError, 'Could not read recipient file.')) }
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
    } catch (requestError) { setError(requestErrorMessage(requestError, 'Media upload failed.')) }
    finally { setBusy(false) }
  }

  async function createCampaign(event) {
    event.preventDefault(); setBusy(true); setError(''); setNotice('')
    try {
      if (!selectedTemplate) throw new Error('Choose an approved message.')
      if (mapping.length !== requiredVariables || mapping.some((field) => !field)) throw new Error('Choose a value for every numbered space in the message.')
      if (['IMAGE', 'VIDEO', 'DOCUMENT'].includes(headerFormat(selectedTemplate)) && !draft.asset_id) throw new Error('Upload the media for this message.')
      if (draft.source_type !== 'list' && (!draft.consent_confirmed || !draft.consent_source.trim() || !draft.consent_captured_at || !draft.consent_evidence.trim())) {
        throw new Error('Confirm WhatsApp permission and enter its source, date, and evidence reference.')
      }
      let recipients = []
      if (draft.source_type === 'csv') {
        if (!importData || !phoneColumn) throw new Error('Upload a file and select its phone column.')
        recipients = importStats.recipients
      } else if (draft.source_type === 'paste') {
        const pastedRows = pastedNumbers.split(/\r?\n|,/).map((value) => value.trim()).filter(Boolean).map((phone) => ({ phone }))
        recipients = prepareImportedRecipients(pastedRows, 'phone').recipients
      }
      if (new Date(`${draft.scheduled_at}:00+05:30`) <= new Date()) throw new Error('Choose a future date and time in India time.')
      let count = recipients.length
      if (draft.source_type === 'list') {
        const { data } = await api.get('/api/audiences')
        setAudiences(data || [])
        count = data?.find((item) => item.id === Number(draft.list_id))?.recipient_count || 0
      }
      if (!count) throw new Error('Choose at least one eligible recipient before scheduling.')
      if (!window.confirm(`Schedule ${draft.schedule_type} campaign “${draft.name}” using ${selectedTemplate.name} for ${count ?? 0} recipient(s) at ${draft.scheduled_at.replace('T', ' ')} IST?`)) return
      const payload = {
        ...draft, template_id: Number(draft.template_id), dm_flow_version_id: draft.dm_flow_version_id ? Number(draft.dm_flow_version_id) : null, list_id: draft.source_type === 'list' ? Number(draft.list_id) : null,
        expected_recipient_count: draft.source_type === 'list' ? count : null,
        scheduled_at: new Date(`${draft.scheduled_at}:00+05:30`).toISOString(), parameter_mapping: mapping,
        recipients,
        consent_source: draft.source_type === 'list' ? null : draft.consent_source,
        consent_captured_at: draft.source_type === 'list' ? null : draft.consent_captured_at ? new Date(`${draft.consent_captured_at}T00:00:00+05:30`).toISOString() : null,
        consent_evidence: draft.source_type === 'list' ? null : draft.consent_evidence,
      }
      const { data } = await api.post('/api/campaigns', payload)
      setDraft(null); setNotice(`Campaign scheduled for ${data.total_recipients} recipients.`); await load()
    } catch (requestError) {
      if (requestError.response?.status === 409 && draft.source_type === 'list') {
        api.get('/api/audiences').then(({ data }) => setAudiences(data || [])).catch(() => {})
      }
      setError(requestErrorMessage(requestError, 'Campaign could not be scheduled.'))
    }
    finally { setBusy(false) }
  }

  async function action(id, name) {
    if (name === 'cancel' && !window.confirm('Cancel this campaign? Remaining messages will not be sent.')) return
    if (name === 'retry-failed' && !window.confirm('Review the delivery log first. Retrying can send messages to these recipients again. Continue?')) return
    setBusy(true); setError('')
    try { await api.post(name === 'retry-failed' ? `/api/campaigns/${id}/deliveries/retry-failed` : `/api/campaigns/${id}/${name}`); await load(); if (detail?.id === id) await openDetail(id) }
    catch (requestError) { setError(requestErrorMessage(requestError, `Could not ${name} campaign.`)) }
    finally { setBusy(false) }
  }
  async function openDetail(id) {
    try { const { data } = await api.get(`/api/campaigns/${id}`); setDetail(data) }
    catch { setError('Could not load campaign details.') }
  }

  async function saveAudience(event) {
    event.preventDefault()
    if (!audienceDraft.member_ids.length) { setError('Choose at least one contact who opted in.'); return }
    const payload = {
      name: audienceDraft.name.trim(),
      description: audienceDraft.description?.trim() || null,
      list_type: 'static',
      member_ids: [...new Set(audienceDraft.member_ids)],
    }
    if (payload.name.length < 2) { setError('Enter an audience name with at least two letters.'); return }
    const createCampaignNext = Boolean(draft) || event.nativeEvent?.submitter?.value === 'campaign'
    setBusy(true); setError('')
    try {
      const { data } = audienceDraft.id
        ? await api.put(`/api/audiences/${audienceDraft.id}`, payload)
        : await api.post('/api/audiences', payload)
      await load()
      if (createCampaignNext) {
        setDraft((current) => current ? { ...current, source_type: 'list', list_id: data.id } : blankCampaign(data.id))
        if (draft?.source_type !== 'list') setMapping(Array(requiredVariables).fill(''))
      } else setNotice('Audience saved. Select “Use in campaign” when you are ready to send.')
      setAudienceDraft(null)
    }
    catch (requestError) { setError(requestErrorMessage(requestError, 'Audience could not be saved.')) }
    finally { setBusy(false) }
  }
  async function deleteAudience(id) {
    if (!window.confirm('Delete this saved audience? Existing campaigns keep their recipient snapshots.')) return
    setBusy(true); setError('')
    try { await api.delete(`/api/audiences/${id}`); setNotice('Audience deleted.'); await load() }
    catch (requestError) { setError(requestErrorMessage(requestError, 'Audience could not be deleted.')) }
    finally { setBusy(false) }
  }

  function deliveryCsv() {
    return ['Name,Phone,Status,Error', ...(detail?.deliveries || []).map((item) => [item.name, item.phone, item.status, item.error].map(csvCell).join(','))].join('\n')
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
    <PageTitle kicker="WHATSAPP MESSAGING" title="Campaigns" subtitle="Save a group of contacts, then choose an approved message and send time." action={<div className="page-actions"><Hint label="Choose contacts for a reusable audience"><button className="secondary-button" onClick={() => startAudience()}><ListFilter size={16} />New audience</button></Hint><Hint label="Choose a template, recipients, and send time"><button className="primary-button" onClick={() => startDraft()}><Plus size={16} />New campaign</button></Hint></div>} />
    <section className="workflow-guide campaign-guide" aria-label="Campaign guide"><div><strong>Send a campaign</strong><span>Choose contacts → Save audience → Choose an approved message → Schedule</span></div><details><summary>Other ways to add recipients</summary><div className="guide-copy"><p>You can also upload a spreadsheet or paste numbers in New campaign. Confirm that every recipient agreed to WhatsApp messages.</p><p>Each scheduled campaign keeps its recipient list, even if you edit the audience later.</p></div></details></section>
    {error && <div className="alert error">{typeof error === 'string' ? error : 'Request failed.'}</div>}
    {notice && <div className="alert success">{notice}</div>}
    <div className="campaign-stats"><article><Send /><span><strong>{campaigns.length}</strong>Total campaigns</span></article><article><CalendarClock /><span><strong>{campaigns.filter((item) => ['scheduled', 'running', 'paused'].includes(item.status)).length}</strong>Active schedules</span></article><article><ListFilter /><span><strong>{audiences.length}</strong>CRM audiences</span></article><article><FileSpreadsheet /><span><strong>{campaigns.reduce((sum, item) => sum + (item.delivered_count || 0), 0)}</strong>Delivered</span></article></div>
    {loading ? <section className="panel empty"><Loader2 className="spin" />Loading campaigns…</section> : <section className="panel no-pad"><div className="table-wrap"><table><thead><tr><th>Campaign</th><th>Template</th><th>Schedule</th><th>Recipients</th><th>Delivery</th><th>Status</th><th>Actions</th></tr></thead><tbody>{campaigns.map((item) => <tr key={item.id} className="clickable" onClick={() => openDetail(item.id)}><td><strong>{item.name}</strong><small>{item.source_type === 'csv' ? 'CSV / Excel snapshot' : item.source_type === 'paste' ? 'Pasted-number snapshot' : 'CRM audience snapshot'}</small></td><td>{item.template_name}</td><td>{formatDate(item.scheduled_at)}<small>{item.schedule_type}</small></td><td>{item.total_recipients}</td><td><span className="delivery-copy">{item.delivered_count || 0} delivered · {item.read_count || 0} read<small>{item.failed_count || 0} failed{item.uncertain_count ? ` · ${item.uncertain_count} need review` : ''}</small></span></td><td><Status value={item.status} /></td><td onClick={(event) => event.stopPropagation()}><div className="row-actions">{['scheduled', 'running'].includes(item.status) && <button title="Pause" onClick={() => action(item.id, 'pause')}><Pause /></button>}{item.status === 'paused' && <button title="Resume" onClick={() => action(item.id, 'resume')}><Play /></button>}{['scheduled', 'running', 'paused'].includes(item.status) && <button title="Cancel" onClick={() => action(item.id, 'cancel')}><XCircle /></button>}{item.failed_count > 0 && <button title="Retry failed only" onClick={() => action(item.id, 'retry-failed')}><RotateCcw /></button>}</div></td></tr>)}</tbody></table>{!campaigns.length && <div className="empty"><Send size={30} /><h2>No campaigns yet</h2><p>Create a campaign from an approved Meta template and opted-in audience.</p></div>}</div></section>}
    <section className="panel audience-panel"><div className="panel-title"><div><h2>Saved audiences</h2><p>Choose an audience below to start a campaign. Only contacts who opted in can receive it.</p></div></div><div className="audience-list">{audiences.map((item) => <article key={item.id}><div><strong>{item.name}</strong><small>{item.recipient_count} eligible {item.recipient_count === 1 ? 'contact' : 'contacts'}</small></div><div className="audience-actions"><button className="primary-button compact" disabled={!item.recipient_count} onClick={() => startDraft(item.id)}>Use in campaign</button><button className="secondary-button compact" onClick={() => startAudience(item)}>Edit</button><button className="icon-button" aria-label={`Delete ${item.name}`} onClick={() => deleteAudience(item.id)}><X /></button></div></article>)}{!audiences.length && <div className="empty">No audiences yet. Select New audience to choose contacts.</div>}</div></section>

    {draft && !audienceDraft && <div className="drawer-backdrop" onClick={() => setDraft(null)}><aside className="drawer campaign-drawer" onClick={(event) => event.stopPropagation()}><button className="drawer-close" onClick={() => setDraft(null)} aria-label="Close"><X /></button><span className="eyebrow">NEW CAMPAIGN</span><h2>Schedule a WhatsApp message</h2><p>Choose an approved message, recipients, and a send time.</p>{error && <div className="alert error" role="alert">{typeof error === 'string' ? error : 'Check the fields and try again.'}</div>}<form className="campaign-form" onSubmit={createCampaign}>
      <div className="detail-grid"><label>Campaign name<input required value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} placeholder="November service reminder" /></label><label>Approved template<select required value={draft.template_id} onChange={(event) => { const count = variableCount(templates.find((item) => item.id === Number(event.target.value))); setDraft({ ...draft, template_id: event.target.value, asset_id: null, asset_name: '' }); setMapping(Array(count).fill('')) }}><option value="">Choose template</option>{templates.map((item) => <option key={item.id} value={item.id}>{item.name} · {headerFormat(item)}</option>)}</select></label></div>
      {!templates.length && <p className="source-help">No approved messages yet. Create one on the <a href="/templates">Templates page</a> and wait for Meta approval.</p>}
      {selectedTemplate && <div className="template-preview"><strong>{selectedTemplate.header || selectedTemplate.name}</strong><p>{selectedTemplate.body}</p><small>{selectedTemplate.language} · {headerFormat(selectedTemplate)} header · {requiredVariables} variables</small></div>}
      <div className="campaign-flow-setting"><label>DM flow after reply <select value={draft.dm_flow_version_id} onChange={(event) => setDraft({ ...draft, dm_flow_version_id: event.target.value })}><option value="">Use the general CAM assistant</option>{dmFlows.map((flow) => <option key={flow.published_version.id} value={flow.published_version.id}>{flow.name} · version {flow.published_version.version}</option>)}</select></label><div className="campaign-flow-actions"><small>Published flows appear here. Replies enter the selected flow before the general assistant.</small><a className="secondary-button compact" href="/dm-flows" target="_blank" rel="noreferrer" aria-label="Setup DM Flow (opens in a new tab)"><GitBranch size={15} />Setup DM Flow</a></div></div>
      <div className="source-tabs three" aria-label="Choose recipients"><button type="button" aria-pressed={draft.source_type === 'list'} className={draft.source_type === 'list' ? 'active' : ''} onClick={() => chooseSource('list')}><ListFilter />Saved audience</button><button type="button" aria-pressed={draft.source_type === 'csv'} className={draft.source_type === 'csv' ? 'active' : ''} onClick={() => chooseSource('csv')}><FileSpreadsheet />CSV / Excel</button><button type="button" aria-pressed={draft.source_type === 'paste'} className={draft.source_type === 'paste' ? 'active' : ''} onClick={() => chooseSource('paste')}><Plus />Paste numbers</button></div>
      <p className="source-help">{draft.source_type === 'list' ? 'Choose a saved group of contacts who agreed to WhatsApp messages.' : draft.source_type === 'csv' ? 'Upload a spreadsheet of recipients.' : 'Enter a short list of phone numbers.'}</p>
      {draft.source_type === 'csv' ? <>
        <label className="upload-zone"><Upload /><strong>{busy ? 'Reading file…' : 'Upload CSV or Excel'}</strong><small>CSV, XLS, or XLSX · first row must contain headings · maximum 10,000 recipients</small><input type="file" accept=".csv,.xls,.xlsx,.xlsm" onChange={previewFile} /></label>
        {importData && <><div className="import-summary"><strong>{importStats.recipients.length} unique recipients ready</strong><span>{importStats.duplicateCount} duplicates and {importStats.invalidCount} invalid rows will be skipped</span></div><div className="detail-grid"><label>Phone column<select required value={phoneColumn} onChange={(event) => setPhoneColumn(event.target.value)}><option value="">Choose column</option>{importData.columns.map((column) => <option key={column}>{column}</option>)}</select></label><label>Name column<select value={nameColumn} onChange={(event) => setNameColumn(event.target.value)}><option value="">Optional</option>{importData.columns.map((column) => <option key={column}>{column}</option>)}</select></label></div><div className="import-preview"><table><thead><tr>{importData.columns.slice(0, 5).map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{importData.rows.slice(0, 3).map((row, index) => <tr key={index}>{importData.columns.slice(0, 5).map((column) => <td key={column}>{row[column] || '—'}</td>)}</tr>)}</tbody></table></div></>}
        <div className="consent-box"><label className="check-row"><input type="checkbox" checked={draft.consent_confirmed} onChange={(event) => setDraft({ ...draft, consent_confirmed: event.target.checked })} /><span><strong>I confirm every imported recipient opted in to receive WhatsApp messages.</strong><small>This confirmation, its source, date, evidence, and operator are stored for audit.</small></span></label><div className="detail-grid"><label>Consent source<input required value={draft.consent_source} onChange={(event) => setDraft({ ...draft, consent_source: event.target.value })} placeholder="Website form / customer register" /></label><label>Consent captured on<input required type="date" value={draft.consent_captured_at} onChange={(event) => setDraft({ ...draft, consent_captured_at: event.target.value })} /></label></div><label>Consent evidence reference<input required minLength="3" maxLength="500" value={draft.consent_evidence} onChange={(event) => setDraft({ ...draft, consent_evidence: event.target.value })} placeholder="Form URL, CRM export ID, or signed register page" /></label></div>
      </> : draft.source_type === 'paste' ? <><label>Phone numbers<textarea required rows="7" value={pastedNumbers} onChange={(event) => setPastedNumbers(event.target.value)} placeholder={'919876543210\n919999999999'} /><small>One phone number with country code per line. Invalid and duplicate numbers are skipped.</small></label><div className="consent-box"><label className="check-row"><input type="checkbox" checked={draft.consent_confirmed} onChange={(event) => setDraft({ ...draft, consent_confirmed: event.target.checked })} /><span><strong>I confirm every pasted recipient opted in.</strong><small>The confirmation and evidence are recorded with the campaign.</small></span></label><div className="detail-grid"><label>Consent source<input required value={draft.consent_source} onChange={(event) => setDraft({ ...draft, consent_source: event.target.value })} /></label><label>Consent captured on<input required type="date" value={draft.consent_captured_at} onChange={(event) => setDraft({ ...draft, consent_captured_at: event.target.value })} /></label></div><label>Consent evidence reference<input required minLength="3" maxLength="500" value={draft.consent_evidence} onChange={(event) => setDraft({ ...draft, consent_evidence: event.target.value })} placeholder="Form URL, CRM export ID, or signed register page" /></label></div></> : <div className="audience-choice"><label>Saved audience<select required value={draft.list_id} onChange={(event) => setDraft({ ...draft, list_id: event.target.value })}><option value="">Choose an audience</option>{audiences.map((item) => <option key={item.id} value={item.id} disabled={!item.recipient_count}>{item.name} · {item.recipient_count} eligible</option>)}</select></label>{selectedAudience && <p className="recipient-summary" role="status">{selectedAudience.recipient_count ? `${selectedAudience.recipient_count} ${selectedAudience.recipient_count === 1 ? 'contact' : 'contacts'} ready to receive this campaign.` : 'No contacts are currently eligible. Edit this audience before scheduling.'}</p>}<div className="audience-actions"><button type="button" className="secondary-button compact" onClick={() => startAudience()}>New audience</button>{selectedAudience && <button type="button" className="secondary-button compact" onClick={() => startAudience(selectedAudience)}>Edit selected</button>}</div><small>Recipients are fixed when you schedule, even if the audience changes later.</small></div>}
      {requiredVariables > 0 && <fieldset><legend>Personalise the message</legend><small className="fieldset-help">Choose the detail that fills each numbered space in the approved message.</small>{Array.from({ length: requiredVariables }, (_, index) => <label key={index}>Value for {`{{${index + 1}}}`}<select required value={mapping[index] || ''} onChange={(event) => setMapping((values) => values.map((value, position) => position === index ? event.target.value : value))}><option value="">Choose a contact detail</option>{mappingOptions.map((column) => <option key={column}>{column}</option>)}</select></label>)}</fieldset>}
      {['IMAGE', 'VIDEO', 'DOCUMENT'].includes(headerFormat(selectedTemplate)) && <label className="upload-zone compact"><Upload /><strong>{draft.asset_name || `Upload ${headerFormat(selectedTemplate).toLowerCase()}`}</strong><small>This media becomes the approved template header.</small><input type="file" onChange={uploadMedia} /></label>}
      <div className="detail-grid three"><label>How often<select value={draft.schedule_type} onChange={(event) => setDraft({ ...draft, schedule_type: event.target.value })}><option value="once">Once</option><option value="daily">Daily</option><option value="weekly">Weekly</option></select></label><label>First send (IST)<input required type="datetime-local" value={draft.scheduled_at} onChange={(event) => setDraft({ ...draft, scheduled_at: event.target.value })} /></label><label>Sending pace<select value={draft.throttle_seconds} onChange={(event) => setDraft({ ...draft, throttle_seconds: Number(event.target.value) })}>{[0, 1, 2, 3, 5].map((value) => <option key={value} value={value}>{value ? `${value} sec between messages` : 'Meta managed'}</option>)}</select></label></div>
      <button className="primary-button wide" disabled={busy || !selectedTemplate || (draft.source_type === 'list' && !selectedAudience?.recipient_count)}>{busy ? 'Scheduling…' : 'Schedule campaign'}</button>
    </form></aside></div>}

    {audienceDraft && <div className="drawer-backdrop" onClick={() => setAudienceDraft(null)}>
      <aside className="drawer" onClick={(event) => event.stopPropagation()}>
        <button className="drawer-close" onClick={() => setAudienceDraft(null)} aria-label="Close audience"><X /></button>
        <span className="eyebrow">AUDIENCE</span>
        <h2>{audienceDraft.id ? 'Edit audience' : 'Choose your audience'}</h2>
        <p>Select contacts who agreed to receive WhatsApp messages.</p>
        {error && <div className="alert error" role="alert">{typeof error === 'string' ? error : 'Check the fields and try again.'}</div>}
        <form className="campaign-form" onSubmit={saveAudience}>
          <label>Audience name<input required minLength="2" value={audienceDraft.name} onChange={(event) => setAudienceDraft({ ...audienceDraft, name: event.target.value })} placeholder="Interested customers" /></label>
          <label>Description <small>Optional</small><textarea rows="2" value={audienceDraft.description || ''} onChange={(event) => setAudienceDraft({ ...audienceDraft, description: event.target.value })} /></label>
          <div className="audience-picker-heading">
            <label>Find contacts<input value={contactSearch} onChange={(event) => { setContactSearch(event.target.value); setContactPage(1) }} placeholder="Search name, phone, or company" /></label>
            <strong>{eligibleSelectedCount} ready{unavailableMembers.length ? ` · ${unavailableMembers.length} unavailable` : ''}</strong>
          </div>
          {contactLoading ? <div className="empty">Loading contacts…</div> : contacts.length ? <div className="contact-picker">{contacts.map((contact) => <label key={contact.id}>
            <input type="checkbox" checked={audienceDraft.member_ids.includes(contact.id)} onChange={(event) => setAudienceDraft((current) => ({ ...current, member_ids: event.target.checked ? [...current.member_ids, contact.id] : current.member_ids.filter((id) => id !== contact.id) }))} />
            <span><strong>{contact.name}</strong><small>{contact.phone}</small></span>
          </label>)}</div> : <div className="empty">No opted-in contacts found. Add permission in CRM Contacts, then return here.</div>}
          {unavailableMembers.length > 0 && <div className="unavailable-members"><strong>Permission changed</strong><p>These saved contacts will not receive messages unless they opt in again.</p>{unavailableMembers.map((member) => <div key={member.id}><span>{member.name} · {member.phone}</span><button type="button" className="secondary-button compact" onClick={() => setAudienceDraft((current) => ({ ...current, member_ids: current.member_ids.filter((id) => id !== member.id) }))}>Remove</button></div>)}</div>}
          <div className="pagination"><span>Page {contactPage} · {contactTotal} eligible contacts</span><button type="button" className="secondary-button compact" disabled={contactPage <= 1} onClick={() => setContactPage((page) => page - 1)}>Previous</button><button type="button" className="secondary-button compact" disabled={contactPage * 25 >= contactTotal} onClick={() => setContactPage((page) => page + 1)}>Next</button></div>
          <p className="source-help">Contacts are checked again for WhatsApp permission when you schedule.</p>
          <div className="audience-form-actions">{draft ? <button type="submit" name="next" value="campaign" className="primary-button" disabled={busy || !eligibleSelectedCount}>Save & return to campaign</button> : <><button type="submit" name="next" value="save" className="secondary-button" disabled={busy || !audienceDraft.member_ids.length}>Save audience</button><button type="submit" name="next" value="campaign" className="primary-button" disabled={busy || !eligibleSelectedCount}>Save & create campaign</button></>}</div>
        </form>
      </aside>
    </div>}

    {detail && <div className="drawer-backdrop" onClick={() => setDetail(null)}><aside className="drawer campaign-detail-drawer" onClick={(event) => event.stopPropagation()}><button className="drawer-close" onClick={() => setDetail(null)}><X /></button><span className="eyebrow">CAMPAIGN #{detail.id}</span><h2>{detail.name}</h2><div className="campaign-detail-head"><Status value={detail.status} /><span>{detail.template?.name}</span><span>{detail.total_recipients} recipients</span>{detail.dm_flow && <span>{detail.dm_flow.name} · flow v{detail.dm_flow.version}</span>}</div><div className="campaign-progress"><span style={{ width: `${detail.total_recipients ? Math.min(100, ((detail.delivered_count || 0) / detail.total_recipients) * 100) : 0}%` }} /></div><div className="campaign-metrics"><div><strong>{detail.sent_count || 0}</strong><small>Accepted</small></div><div><strong>{detail.delivered_count || 0}</strong><small>Delivered</small></div><div><strong>{detail.read_count || 0}</strong><small>Read</small></div><div><strong>{detail.failed_count || 0}</strong><small>Failed</small></div><div><strong>{detail.uncertain_count || 0}</strong><small>Needs review</small></div></div>{detail.uncertain_count > 0 && <div className="alert error">Some sends stopped before their result was recorded. Verify them in Meta before sending again.</div>}<div className="log-title"><h3>Latest run delivery log</h3><span><button className="secondary-button compact" onClick={copyLog}><Copy size={14} />Copy</button><button className="secondary-button compact" onClick={exportLog}><Download size={14} />Export CSV</button></span></div><div className="delivery-log">{detail.deliveries?.map((item) => <article key={item.id}><span className={`delivery-dot ${item.status}`} /><div><strong>{item.name || item.phone}</strong><small>{item.phone} · {item.status}</small>{item.error && <em>{item.error}</em>}</div></article>)}{!detail.deliveries?.length && <div className="empty">This campaign has not started yet.</div>}</div>{detail.runs?.length > 0 && <><h3>Run history</h3><div className="run-list">{detail.runs.map((run) => <div key={run.id}><span>Run #{run.run_number} · {formatDate(run.scheduled_for)}</span><Status value={run.status} /></div>)}</div></>}{detail.events?.length > 0 && <><h3>Action history</h3><div className="run-list">{detail.events.map((event) => <div key={event.id}><span><strong>{event.action}</strong> by {event.actor}<small>{formatDate(event.created_at)}</small></span><span>{event.old_status} → {event.new_status}</span></div>)}</div></>}</aside></div>}
  </>
}
