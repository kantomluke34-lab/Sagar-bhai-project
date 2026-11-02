import { CheckCircle2, Copy, Radio, RefreshCw, ShieldCheck, Webhook, XCircle } from 'lucide-react'
import { useEffect, useState } from 'react'
import api, { API_BASE_URL } from '../api'
import { PageTitle } from './Dashboard'

const first = (...values) => values.find((value) => value !== undefined && value !== null && value !== '')
const yes = (value) => value === true || ['connected', 'configured', 'ready', 'active', 'verified'].includes(String(value || '').toLowerCase())

function HealthItem({ label, value, healthy }) {
  return <div className={`health-item ${healthy ? 'healthy' : 'unhealthy'}`}><span>{healthy ? <CheckCircle2 /> : <XCircle />}</span><div><small>{label}</small><strong>{value}</strong></div></div>
}

export default function Waba() {
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)
  const webhookUrl = `${API_BASE_URL || window.location.origin}/webhook`

  async function load() {
    setLoading(true); setError('')
    try { const { data } = await api.get('/api/waba/status'); setStatus(data) }
    catch (requestError) { setError(requestError.response?.data?.detail || 'Could not load WABA status.') }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])
  async function copyWebhook() { await navigator.clipboard.writeText(webhookUrl); setCopied(true); setTimeout(() => setCopied(false), 1800) }

  const connection = first(status?.status, status?.connection_status, status?.connected ? 'connected' : '', 'unknown')
  const connected = yes(status?.connected) || yes(connection)
  const phone = first(status?.display_phone_number, status?.phone_number, status?.verified_name, 'Not reported')
  const quality = first(status?.quality_rating, status?.quality, 'Not reported')
  const appConfigured = first(status?.app_secret_configured, status?.webhook_signature_configured, status?.signature_verification, false)
  const verifyConfigured = first(status?.verify_token_configured, status?.webhook_verify_token_configured, false)
  return <>
    <PageTitle kicker="META WHATSAPP CLOUD API" title="WABA status" subtitle="Connection health, sender identity, webhook readiness, and production configuration." action={<button className="secondary-button" onClick={load}><RefreshCw size={16} />Refresh</button>} />
    {error && <div className="alert error">{error}</div>}
    <section className={`waba-hero ${connected ? 'connected' : ''}`}>
      <div className="waba-icon"><Radio /></div>
      <div><span className="eyebrow">{connected ? 'CONNECTED' : loading ? 'CHECKING' : 'ACTION REQUIRED'}</span><h2>{loading ? 'Checking Meta connection…' : connected ? 'WhatsApp Business is connected.' : 'WhatsApp Business needs attention.'}</h2><p>{phone}</p></div>
      <span className={`status ${connected ? 'status-completed' : 'status-cancelled'}`}>{connection}</span>
    </section>
    <div className="health-grid">
      <HealthItem label="Cloud API connection" value={connected ? 'Ready' : 'Not ready'} healthy={connected} />
      <HealthItem label="Phone quality" value={quality} healthy={!/red|blocked|unknown/i.test(String(quality))} />
      <HealthItem label="App secret" value={yes(appConfigured) ? 'Configured' : 'Check server'} healthy={yes(appConfigured)} />
      <HealthItem label="Webhook verify token" value={yes(verifyConfigured) ? 'Configured' : 'Check server'} healthy={yes(verifyConfigured)} />
    </div>
    <section className="panel webhook-panel">
      <div className="settings-heading"><Webhook /><div><h2>Meta webhook</h2><p>Use this callback in the Meta App dashboard and subscribe to WhatsApp messages.</p></div></div>
      <label>Callback URL<div className="copy-field"><input readOnly value={webhookUrl} /><button className="secondary-button" onClick={copyWebhook}><Copy size={15} />{copied ? 'Copied' : 'Copy'}</button></div></label>
      <div className="webhook-checks"><span><ShieldCheck />GET verifies the callback challenge</span><span><ShieldCheck />POST receives messages and delivery events</span><span><ShieldCheck />App-secret signature validation runs server-side</span></div>
    </section>
  </>
}
