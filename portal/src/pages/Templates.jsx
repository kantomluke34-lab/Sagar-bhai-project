import { Edit3, FileText, Loader2, Plus, RefreshCw, Send, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import api from '../api'
import { PageTitle, Status } from './Dashboard'
import SelectField from '../components/SelectField'
import Hint from '../components/Hint'

const blank = { name: '', language: 'en_US', category: 'UTILITY', header: '', body: '', footer: '', variables: '', buttons: [] }
const normalize = (item = {}) => ({ ...blank, ...item, variables: Array.isArray(item.variables) ? item.variables.join(', ') : item.variables || '', buttons: item.buttons || [] })
const state = (item = {}) => String(item.status || item.meta_status || item.approval_status || 'draft').toLowerCase()
const rejectionReason = (item) => state(item) === 'rejected' && !['', 'none', 'null'].includes(String(item.rejection_reason || '').trim().toLowerCase()) ? item.rejection_reason : ''

export default function Templates() {
  const [rows, setRows] = useState([])
  const [draft, setDraft] = useState(null)
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
      category: draft.category, header: draft.header.trim() || null, body: draft.body.trim(), footer: draft.footer.trim() || null,
      variables: draft.variables.split(',').map((item) => item.trim()).filter(Boolean), buttons: draft.buttons || [],
    }
    try {
      if (draft.id) await api.put(`/api/templates/${draft.id}`, payload)
      else await api.post('/api/templates', payload)
      setDraft(null); setNotice('Template saved.'); await load()
    } catch (requestError) { setError(requestError.response?.data?.detail || 'Template could not be saved.') }
    finally { setBusy(false) }
  }

  async function submit(item) {
    setBusy(true); setError(''); setNotice('')
    try { await api.post(`/api/templates/${item.id}/submit`); setNotice(`${item.name} submitted to Meta for approval.`); await load() }
    catch (requestError) { setError(requestError.response?.data?.detail || 'Template could not be submitted.') }
    finally { setBusy(false) }
  }

  return <>
    <PageTitle kicker="META MESSAGE TEMPLATES" title="Templates" subtitle="Create and manage approved WhatsApp messages." action={<div className="page-actions"><Hint label="Refresh approval status from Meta"><button className="secondary-button" disabled={busy} onClick={sync}><RefreshCw size={16} />Sync with Meta</button></Hint><button className="primary-button" onClick={() => setDraft({ ...blank })}><Plus size={16} />New template</button></div>} />
    <div className="template-guide"><div><strong>Using templates</strong><span>Draft → Submit for approval → Send once approved</span></div><details><summary>About approval and variables</summary><p>Meta reviews submitted templates. Use Sync with Meta to refresh approval. For each variable such as {'{{1}}'}, add an example in the order it appears.</p></details></div>
    {error && <div className="alert error">{typeof error === 'string' ? error : 'Template request failed.'}</div>}
    {notice && <div className="alert success">{notice}</div>}
    {loading ? <div className="panel empty"><Loader2 className="spin" /> Loading templates…</div> : rows.length ? <div className="template-grid">{rows.map((item) => <article className="template-card" key={item.id || item.name}>
      <header><div className="template-icon"><FileText /></div><div><h2>{item.name}</h2><span>{item.language || 'en_US'} · {item.category || 'UTILITY'}</span></div><Status value={state(item)} /></header>
      {item.header && <strong className="template-header">{item.header}</strong>}<p>{item.body || 'No template body.'}</p>{item.footer && <small>{item.footer}</small>}
      {rejectionReason(item) && <p className="alert error">Meta's reason: {rejectionReason(item)}</p>}
      <footer>{['approved', 'pending'].includes(state(item)) ? <Hint label="Use this template as a starting point"><button className="secondary-button compact" onClick={() => setDraft({ ...normalize(item), id: undefined, name: `${item.name}_copy` })}><Edit3 size={15} />Duplicate</button></Hint> : <button className="secondary-button compact" onClick={() => setDraft(normalize(item))}><Edit3 size={15} />Edit</button>}{!['approved', 'pending'].includes(state(item)) && <Hint label="Submit this draft to Meta for review"><button className="primary-button compact" disabled={busy} onClick={() => submit(item)}><Send size={15} />Submit for review</button></Hint>}</footer>
    </article>)}</div> : <section className="panel empty"><FileText size={30} /><h2>No templates yet</h2><p>Create a draft or sync approved templates from Meta.</p></section>}
    {draft && <div className="drawer-backdrop" onClick={() => setDraft(null)}><aside className="drawer" onClick={(event) => event.stopPropagation()}><button className="drawer-close" aria-label="Close template editor" onClick={() => setDraft(null)}><X /></button><span className="eyebrow">{draft.id ? `TEMPLATE #${draft.id}` : 'NEW TEMPLATE'}</span><h2>{draft.id ? 'Edit message template' : 'Create message template'}</h2><p>Choose Utility for an existing customer transaction or Marketing for promotional messages. Meta reviews the category and message.</p>{error && <div className="alert error" role="alert">{typeof error === 'string' ? error : 'Check the template fields and try again.'}</div>}<form className="template-form" onSubmit={save}>
      <label>Name<input required minLength="3" pattern="[a-z0-9_]+" value={draft.name} onChange={(event) => setDraft((value) => ({ ...value, name: event.target.value.toLowerCase().replace(/\s+/g, '_') }))} placeholder="meeting_confirmation" /></label>
      <div className="detail-grid"><label>Language<input value={draft.language} onChange={(event) => setDraft((value) => ({ ...value, language: event.target.value }))} /></label><label>Category<SelectField value={draft.category} onChange={(value) => setDraft((current) => ({ ...current, category: value }))} aria-label="Template category" options={['UTILITY', 'MARKETING', 'AUTHENTICATION']} /></label></div>
      <label>Header <small>Optional · maximum 60 characters</small><input maxLength="60" value={draft.header} onChange={(event) => setDraft((value) => ({ ...value, header: event.target.value }))} /></label>
      <label>Body<textarea required rows="8" maxLength="1024" value={draft.body} onChange={(event) => setDraft((value) => ({ ...value, body: event.target.value }))} placeholder="Hello {{1}}, your meeting is confirmed for {{2}}." /></label>
      <label>Variables <small>Comma-separated examples in placeholder order</small><input value={draft.variables} onChange={(event) => setDraft((value) => ({ ...value, variables: event.target.value }))} placeholder="Customer name, Tuesday 3:00 PM" /></label>
      <label>Footer <small>Optional · maximum 60 characters</small><input maxLength="60" value={draft.footer} onChange={(event) => setDraft((value) => ({ ...value, footer: event.target.value }))} /></label>
      <button className="primary-button wide" disabled={busy}>{busy ? 'Saving…' : 'Save template'}</button>
    </form></aside></div>}
  </>
}
