import { Edit3, FileText, Loader2, Plus, RefreshCw, Send, Trash2, Upload } from 'lucide-react'
import { useEffect, useState } from 'react'
import api from '../api'
import { PageTitle, Status } from './Dashboard'
import SelectField from '../components/SelectField'
import Hint from '../components/Hint'
import Drawer from '../components/Drawer'

const blank = { name: '', language: 'en_US', category: 'UTILITY', header_format: 'NONE', header: '', header_sample_handle: '', header_sample_name: '', body: '', footer: '', variables: [], buttons: [] }
const normalize = (item = {}) => ({ ...blank, ...item, header_format: item.header_format === 'NONE' && item.header ? 'TEXT' : item.header_format || 'NONE', variables: Array.isArray(item.variables) ? item.variables : [], buttons: item.buttons || [] })
const state = (item = {}) => String(item.status || item.meta_status || item.approval_status || 'draft').toLowerCase()
const rejectionReason = (item) => state(item) === 'rejected' && !['', 'none', 'null'].includes(String(item.rejection_reason || '').trim().toLowerCase()) ? item.rejection_reason : ''
const mediaHeader = (format) => ['IMAGE', 'VIDEO', 'DOCUMENT'].includes(format)
const placeholderCount = (body = '') => Math.max(0, ...[...body.matchAll(/\{\{(\d+)\}\}/g)].map((match) => Number(match[1])))

export default function Templates() {
  const [rows, setRows] = useState([])
  const [draft, setDraft] = useState(null)
  const [draftBaseline, setDraftBaseline] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  async function load() {
    setLoading(true); setError('')
    try { const { data } = await api.get('/api/templates'); setRows(Array.isArray(data) ? data : data?.items || data?.templates || []) }
    catch (requestError) { setError(requestError.response?.data?.detail || 'Could not load WhatsApp templates.') }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  function openDraft(value) {
    setDraft(value)
    setDraftBaseline(JSON.stringify(value))
  }

  function closeDraft() {
    if (busy) return
    if (draft && JSON.stringify(draft) !== draftBaseline && !window.confirm('Discard unsaved template changes?')) return
    setDraft(null); setDraftBaseline('')
  }

  async function sync() {
    setBusy(true); setError(''); setNotice('')
    try { const { data } = await api.post('/api/templates/sync'); setNotice(`Templates synced${data?.updated !== undefined ? ` · ${data.updated} updated` : ''}.`); await load() }
    catch (requestError) { setError(requestError.response?.data?.detail || 'Template sync failed.') }
    finally { setBusy(false) }
  }

  async function save(event) {
    event.preventDefault(); setBusy(true); setError(''); setNotice('')
    const payload = {
      name: draft.name.trim().toLowerCase().replace(/[^a-z0-9_]+/g, '_'), language: draft.language,
      category: draft.category, header_format: draft.header_format,
      header: draft.header_format === 'TEXT' ? draft.header.trim() || null : null,
      header_sample_handle: mediaHeader(draft.header_format) ? draft.header_sample_handle || null : null,
      body: draft.body.trim(), footer: draft.footer.trim() || null,
      variables: draft.variables.map((item) => item.trim()), buttons: draft.buttons || [],
    }
    try {
      if (draft.id) await api.put(`/api/templates/${draft.id}`, payload)
      else await api.post('/api/templates', payload)
      setDraft(null); setDraftBaseline(''); setNotice('Template saved.'); await load()
    } catch (requestError) { setError(requestError.response?.data?.detail || 'Template could not be saved.') }
    finally { setBusy(false) }
  }

  async function uploadHeaderSample(event) {
    const file = event.target.files?.[0]
    if (!file) return
    setBusy(true); setError(''); setNotice('')
    try {
      const form = new FormData(); form.append('upload', file)
      const { data } = await api.post('/api/templates/media-sample', form)
      if (data.header_format !== draft.header_format) {
        throw new Error(`Choose ${data.header_format.toLowerCase()} header before uploading this file.`)
      }
      setDraft((current) => ({ ...current, header_sample_handle: data.header_sample_handle, header_sample_name: data.original_name }))
      setNotice('Media sample uploaded. Save the template, then submit it for review.')
    } catch (requestError) { setError(requestError.response?.data?.detail || requestError.message || 'Media sample upload failed.') }
    finally { setBusy(false); event.target.value = '' }
  }

  async function submit(item) {
    setBusy(true); setError(''); setNotice('')
    try { await api.post(`/api/templates/${item.id}/submit`); setNotice(`${item.name} submitted to Meta for approval.`); await load() }
    catch (requestError) { setError(requestError.response?.data?.detail || 'Template could not be submitted.') }
    finally { setBusy(false) }
  }

  async function recoverSubmission(item) {
    setBusy(true); setError(''); setNotice('')
    try { await api.post(`/api/templates/${item.id}/recover-submission`); setNotice(`${item.name} status checked with Meta.`); await load() }
    catch (requestError) { setError(requestError.response?.data?.detail || 'Template status could not be recovered.') }
    finally { setBusy(false) }
  }

  return <>
    <PageTitle kicker="META MESSAGE TEMPLATES" title="Templates" subtitle="Create and manage approved WhatsApp messages." action={<div className="page-actions"><Hint label="Refresh approval status from Meta"><button className="secondary-button" disabled={busy} onClick={sync}><RefreshCw size={16} />Sync with Meta</button></Hint><button className="primary-button" onClick={() => openDraft({ ...blank })}><Plus size={16} />New template</button></div>} />
    <section className="template-guide" aria-label="Template guide"><div><strong>Template workflow</strong><span>Write → Save draft → Submit to Meta → Use after approval</span></div><details><summary>How approval, media, and placeholders work</summary><div className="template-guide-copy"><p>Meta reviews a submitted template. Use Sync with Meta to refresh its status. Only approved templates can be used in campaigns.</p><p>For an image, video, or document header, upload one sample file for Meta to review. You choose the actual campaign file later.</p><p>Write placeholders in order, then add one matching example for each one.</p><code>Hello {'{{1}}'}, your meeting is on {'{{2}}'}.</code><small>Examples: Customer name, Tuesday at 3:00 PM</small></div></details></section>
    {error && <div className="alert error" role="alert">{typeof error === 'string' ? error : 'Template request failed.'}</div>}
    {notice && <div className="alert success" role="status">{notice}</div>}
    {loading ? <div className="panel empty"><Loader2 className="spin" /> Loading templates…</div> : rows.length ? <div className="template-grid">{rows.map((item) => <article className="template-card" key={item.id || item.name}>
      <header><div className="template-icon"><FileText /></div><div><h2>{item.name}</h2><span>{item.language || 'en_US'} · {item.category || 'UTILITY'}</span></div><Status value={state(item)} /></header>
      {item.header && <strong className="template-header">{item.header}</strong>}{mediaHeader(item.header_format) && <small>Media header · {String(item.header_format).toLowerCase()}</small>}<p>{item.body || 'No template body.'}</p>{item.footer && <small>{item.footer}</small>}
      {rejectionReason(item) && <p className="alert error">Meta's reason: {rejectionReason(item)}</p>}
      {state(item) === 'submission_unknown' && <p className="alert error">Meta did not confirm this submission. Sync status before taking another action.</p>}
      <footer>{['approved', 'pending', 'submitting', 'submission_unknown'].includes(state(item)) ? <Hint label="Use this template as a starting point"><button className="secondary-button compact" onClick={() => openDraft({ ...normalize(item), id: undefined, name: `${item.name}_copy` })}><Edit3 size={15} />Duplicate</button></Hint> : <button className="secondary-button compact" onClick={() => openDraft(normalize(item))}><Edit3 size={15} />Edit</button>}{['submitting', 'submission_unknown'].includes(state(item)) && <button className="primary-button compact" disabled={busy} onClick={() => recoverSubmission(item)}><RefreshCw size={15} />Check Meta status</button>}{!['approved', 'pending', 'submitting', 'submission_unknown'].includes(state(item)) && <Hint label="Submit this draft to Meta for review"><button className="primary-button compact" disabled={busy} onClick={() => submit(item)}><Send size={15} />Submit for review</button></Hint>}</footer>
    </article>)}</div> : <section className="panel empty"><FileText size={30} /><h2>No templates yet</h2><p>Create a draft or sync approved templates from Meta.</p></section>}
    {draft && <Drawer open onOpenChange={(open) => { if (!open) closeDraft() }} kicker={draft.id ? `TEMPLATE #${draft.id}` : 'NEW TEMPLATE'} title={draft.id ? 'Edit message template' : 'Create message template'} description="Choose Utility for customer updates, Marketing for promotions, or Authentication for verification. Meta reviews the saved message only after you submit it.">{error && <div className="alert error" role="alert">{typeof error === 'string' ? error : 'Check the template fields and try again.'}</div>}<form className="template-form" onSubmit={save}>
      <label>Name<input required minLength="3" pattern="[a-z0-9_]+" value={draft.name} onChange={(event) => setDraft((value) => ({ ...value, name: event.target.value.toLowerCase().replace(/\s+/g, '_') }))} placeholder="meeting_confirmation" /></label>
      <div className="detail-grid"><label>Language<input value={draft.language} onChange={(event) => setDraft((value) => ({ ...value, language: event.target.value }))} /></label><label>Category<SelectField value={draft.category} onChange={(value) => setDraft((current) => ({ ...current, category: value }))} aria-label="Template category" options={['UTILITY', 'MARKETING', 'AUTHENTICATION']} /></label></div>
      <label>Header type<SelectField value={draft.header_format} onChange={(value) => setDraft((current) => ({ ...current, header_format: value, header: value === 'TEXT' ? current.header : '', header_sample_handle: value === current.header_format ? current.header_sample_handle : '', header_sample_name: value === current.header_format ? current.header_sample_name : '' }))} aria-label="Header type" options={[{ value: 'NONE', label: 'No header' }, { value: 'TEXT', label: 'Text header' }, { value: 'IMAGE', label: 'Image header' }, { value: 'VIDEO', label: 'Video header' }, { value: 'DOCUMENT', label: 'Document header' }]} /></label>
      {draft.header_format === 'TEXT' && <label>Header text <small>Maximum 60 characters</small><input required maxLength="60" value={draft.header} onChange={(event) => setDraft((value) => ({ ...value, header: event.target.value }))} /></label>}
      {mediaHeader(draft.header_format) && <label className="upload-zone compact"><Upload /><strong>{draft.header_sample_name || `Upload ${draft.header_format === 'IMAGE' ? 'an' : 'a'} ${draft.header_format.toLowerCase()} sample`}</strong><small>Meta reviews this sample. You upload the campaign file later. JPG/PNG up to 5 MB, MP4 up to 16 MB, or PDF.</small><input required={!draft.header_sample_handle} type="file" accept={draft.header_format === 'IMAGE' ? 'image/jpeg,image/png' : draft.header_format === 'VIDEO' ? 'video/mp4' : 'application/pdf,.pdf'} disabled={busy} onChange={uploadHeaderSample} /></label>}
      <label>Body <small>Use numbered placeholders in order: {'{{1}}'}, {'{{2}}'}, {'{{3}}'}.</small><textarea required rows="8" maxLength="1024" value={draft.body} onChange={(event) => { const body = event.target.value; const count = placeholderCount(body); setDraft((value) => ({ ...value, body, variables: Array.from({ length: count }, (_, index) => value.variables[index] || '') })) }} placeholder="Hello {{1}}, your meeting is confirmed for {{2}}." /></label>
      {placeholderCount(draft.body) > 0 && <fieldset className="template-examples"><legend>Placeholder examples</legend><small>Meta uses these examples during review. They are not sent to customers.</small>{draft.variables.map((example, index) => <label key={index}>Example for {`{{${index + 1}}}`}<input required value={example} onChange={(event) => setDraft((value) => ({ ...value, variables: value.variables.map((current, position) => position === index ? event.target.value : current) }))} placeholder={index === 0 ? 'Customer name' : 'Tuesday at 3:00 PM'} /></label>)}</fieldset>}
      <fieldset className="template-buttons"><legend>Quick-reply buttons <small>Optional · up to 3</small></legend><small>Customers can tap these replies. Use the same labels when routing campaign DM flows.</small>{draft.buttons.map((button, index) => <div key={index}><label>Button {index + 1}<input required maxLength="20" value={button.text || ''} onChange={(event) => setDraft((value) => ({ ...value, buttons: value.buttons.map((current, position) => position === index ? { type: 'QUICK_REPLY', text: event.target.value } : current) }))} placeholder="Yes" /></label><button type="button" className="icon-button danger" aria-label={`Remove button ${index + 1}`} onClick={() => setDraft((value) => ({ ...value, buttons: value.buttons.filter((_, position) => position !== index) }))}><Trash2 size={16} /></button></div>)}{draft.buttons.length < 3 && <button type="button" className="secondary-button compact" onClick={() => setDraft((value) => ({ ...value, buttons: [...value.buttons, { type: 'QUICK_REPLY', text: '' }] }))}><Plus size={15} />Add quick reply</button>}</fieldset>
      <label>Footer <small>Optional · maximum 60 characters</small><input maxLength="60" value={draft.footer} onChange={(event) => setDraft((value) => ({ ...value, footer: event.target.value }))} /></label>
      <button className="primary-button wide" disabled={busy}>{busy ? 'Saving…' : 'Save template'}</button>
    </form></Drawer>}
  </>
}
