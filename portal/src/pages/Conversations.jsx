import { Bot, Headphones, Loader2, RefreshCw, Search, Send, UserRound, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import api from '../api'
import useDebouncedValue from '../hooks/useDebouncedValue'
import { PageTitle } from './Dashboard'
import SelectField from '../components/SelectField'
import Hint from '../components/Hint'

const first = (...values) => values.find((value) => value !== undefined && value !== null && value !== '')
const when = (value) => value ? new Date(value).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Kolkata' }) : 'No activity yet'
const person = (row = {}) => first(row.contact_name, row.profile_name, row.name, row.phone, row.wa_id, 'Unknown contact')
const phone = (row = {}) => first(row.phone, row.wa_id, row.contact_phone, '—')
const preview = (row = {}) => first(row.last_message, row.last_message_text, row.preview, row.message, 'No messages yet')
const isHuman = (row = {}) => Boolean(first(row.is_taken_over, row.human_takeover, row.is_manual, row.mode === 'human', row.control_mode === 'human'))
const messageText = (message = {}) => first(message.text, message.body, message.content, message.message, '')
const incoming = (message = {}) => first(message.direction, message.type) === 'inbound' || message.is_inbound === true || message.from_customer === true

function normalizeDetail(data) {
  if (data?.conversation) return { ...data.conversation, messages: data.messages || data.conversation.messages || [] }
  return { ...data, messages: data?.messages || [] }
}

export default function Conversations() {
  const [rows, setRows] = useState([])
  const [q, setQ] = useState('')
  const debouncedQ = useDebouncedValue(q)
  const [selected, setSelected] = useState(null)
  const [reply, setReply] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [templates, setTemplates] = useState([])
  const [templateId, setTemplateId] = useState('')
  const [parameters, setParameters] = useState([])
  const [offset, setOffset] = useState(0)
  const [hasMore, setHasMore] = useState(false)

  async function load(silent = false) {
    if (!silent) { setLoading(true); setError('') }
    try {
      const { data } = await api.get('/api/conversations', { params: { q: debouncedQ } })
      setRows(Array.isArray(data) ? data : data?.items || data?.conversations || [])
    } catch (requestError) {
      setError(requestError.response?.data?.detail || 'Could not load WhatsApp conversations.')
    } finally { if (!silent) setLoading(false) }
  }

  useEffect(() => { load() }, [debouncedQ])
  useEffect(() => {
    api.get('/api/templates').then(({ data }) => setTemplates(Array.isArray(data) ? data.filter((item) => item.status === 'APPROVED' && !['IMAGE', 'VIDEO', 'DOCUMENT'].includes(item.header_format)) : [])).catch(() => {})
  }, [])
  useEffect(() => { const timer = window.setInterval(() => load(true), 10000); return () => window.clearInterval(timer) }, [debouncedQ])
  useEffect(() => {
    if (!selected?.id) return undefined
    const id = selected.id
    const timer = window.setInterval(() => api.get(`/api/conversations/${id}`).then(({ data }) => {
      setSelected((current) => {
        if (current?.id !== id) return current
        const latest = normalizeDetail(data)
        const byId = new Map([...current.messages, ...latest.messages].map((message) => [message.id, message]))
        return { ...current, ...latest, messages: [...byId.values()].sort((a, b) => new Date(a.occurred_at) - new Date(b.occurred_at)) }
      })
    }).catch(() => {}), 10000)
    return () => window.clearInterval(timer)
  }, [selected?.id])

  async function open(id) {
    setError('')
    try { const { data } = await api.get(`/api/conversations/${id}`); if (selected?.id !== id) setReply(''); setSelected(normalizeDetail(data)); setOffset(0); setHasMore(Boolean(data.has_more_messages)); setTemplateId(''); setParameters([]) }
    catch (requestError) { setError(requestError.response?.data?.detail || 'Could not open this conversation.') }
  }

  async function loadOlder() {
    setBusy(true); setError('')
    try {
      const next = offset + 100
      const { data } = await api.get(`/api/conversations/${selected.id}`, { params: { message_offset: next } })
      setSelected((current) => ({ ...current, messages: [...data.messages, ...current.messages] }))
      setOffset(next); setHasMore(Boolean(data.has_more_messages))
    } catch { setError('Could not load older messages.') }
    finally { setBusy(false) }
  }

  async function changeControl(action) {
    setBusy(true); setError('')
    try {
      const { data } = await api.post(`/api/conversations/${selected.id}/${action}`)
      setSelected((current) => ({
        ...current,
        ...data,
        is_taken_over: action === 'take-over',
        human_takeover: action === 'take-over',
        control_mode: action === 'take-over' ? 'human' : 'bot',
      }))
      await Promise.all([open(selected.id), load()])
    } catch (requestError) { setError(requestError.response?.data?.detail || 'Could not change conversation control.') }
    finally { setBusy(false) }
  }

  async function send(event) {
    event.preventDefault()
    if (!templateId && !reply.trim()) return
    setBusy(true); setError('')
    try {
      await api.post(`/api/conversations/${selected.id}/messages`, { text: templateId ? null : reply.trim(), template_id: templateId ? Number(templateId) : null, parameters: templateId ? parameters : [] })
      setReply(''); await open(selected.id); await load()
    } catch (requestError) { setError(requestError.response?.data?.detail || 'Message could not be sent.') }
    finally { setBusy(false) }
  }

  const messages = selected?.messages || []
  return <>
    <PageTitle kicker="WHATSAPP INBOX" title="Conversations" subtitle="Monitor inbound enquiries, take over from automation, and reply from the CRM." action={<button className="secondary-button" onClick={() => { load(); if (selected) open(selected.id) }}><RefreshCw size={16} />Refresh</button>} />
    {error && <div className="alert error">{error}</div>}
    <div className="conversation-shell">
      <section className="conversation-list panel no-pad">
        <label className="search conversation-search"><Search size={17} /><input value={q} onChange={(event) => setQ(event.target.value)} placeholder="Search name, phone, or message…" aria-label="Search conversations" /></label>
        <div className="conversation-rows">{loading ? <div className="empty"><Loader2 className="spin" size={20} /> Loading conversations…</div> : rows.length ? rows.map((row) => (
          <button key={row.id} className={`conversation-row ${selected?.id === row.id ? 'active' : ''}`} onClick={() => open(row.id)}>
            <span className="conversation-avatar">{person(row).slice(0, 1).toUpperCase()}</span>
            <span className="conversation-copy"><strong>{person(row)}</strong><small>{preview(row)}</small><em>{when(first(row.last_message_at, row.updated_at, row.created_at))}</em></span>
            <span className={`control-dot ${isHuman(row) ? 'human' : 'bot'}`} title={isHuman(row) ? 'Human controlled' : 'Bot controlled'} />
          </button>
        )) : <div className="empty">No conversations match this search.</div>}</div>
      </section>
      <section className="conversation-detail panel no-pad">
        {selected ? <>
          <header className="conversation-head">
            <div><strong>{person(selected)}</strong><span>{phone(selected)}</span></div>
            <div className="conversation-actions">
              <span className="control-label">{isHuman(selected) ? <><Headphones size={15} />Human control</> : <><Bot size={15} />Bot control</>}</span>
              {isHuman(selected)
                ? <Hint label="Let the bot handle future replies"><button disabled={busy} className="secondary-button compact" onClick={() => changeControl('return-to-bot')}>Return to bot</button></Hint>
                : <Hint label="Pause the bot and reply manually"><button disabled={busy} className="primary-button compact" onClick={() => changeControl('take-over')}>Take over</button></Hint>}
              <button className="icon-button mobile-detail-close" aria-label="Close conversation" onClick={() => setSelected(null)}><X /></button>
            </div>
          </header>
          <div className="message-stream">
            {hasMore && <button className="secondary-button compact" disabled={busy} onClick={loadOlder}>Load earlier messages</button>}
            {messages.length ? messages.map((message, index) => (
              <article key={message.id || index} className={`message-bubble ${incoming(message) ? 'inbound' : 'outbound'}`}>
                <p>{messageText(message)}</p>
                <small>{when(first(message.occurred_at, message.sent_at, message.created_at, message.timestamp))}{!incoming(message) && message.status ? ` · ${message.status}` : ''}</small>
              </article>
            )) : <div className="empty"><UserRound size={24} /> No messages in this conversation yet.</div>}
          </div>
          <form className="message-composer" onSubmit={send}>
            <div className="reply-fields"><p className="muted composer-help">{selected.service_window_open === false ? 'Reply window closed. Choose an approved template.' : 'Take over to reply. Templates work outside the reply window.'}</p><label>Message type<SelectField aria-label="Message type" value={templateId} onChange={(id) => { const template = templates.find((item) => String(item.id) === id); const count = Math.max(0, ...[...(template?.body?.matchAll(/\{\{(\d+)\}\}/g) || [])].map((item) => Number(item[1]))); setTemplateId(id); setParameters(Array(count).fill('')) }} options={[{ value: '', label: 'Free text' }, ...templates.map((template) => ({ value: String(template.id), label: template.name }))]} /></label>
            {templateId ? <><p>{templates.find((item) => String(item.id) === templateId)?.body}</p>{parameters.map((value, index) => <label key={index}>Value for {`{{${index + 1}}}`}<input required value={value} onChange={(event) => setParameters((current) => current.map((item, position) => position === index ? event.target.value : item))} /></label>)}</> : <textarea aria-label="Reply message" rows="2" value={reply} onChange={(event) => setReply(event.target.value)} placeholder={isHuman(selected) ? 'Type a WhatsApp reply…' : 'Take over to send a manual reply…'} disabled={!isHuman(selected) || busy || selected.service_window_open === false} />}</div>
            <button className="primary-button" disabled={!isHuman(selected) || busy || (!templateId && (!reply.trim() || selected.service_window_open === false)) || (templateId && parameters.some((value) => !value.trim()))}><Send size={16} />Send</button>
          </form>
        </> : <div className="conversation-placeholder"><Bot size={34} /><h2>Select a conversation</h2><p>Messages and control options will appear here.</p></div>}
      </section>
    </div>
  </>
}
