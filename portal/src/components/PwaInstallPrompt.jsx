import { Download, RefreshCw, WifiOff, X } from 'lucide-react'
import { useEffect, useState } from 'react'

const isAppleMobile = () => /iPhone|iPad|iPod/i.test(navigator.userAgent)
const isIosSafari = () => isAppleMobile() && /Safari/i.test(navigator.userAgent) && !/CriOS|FxiOS|EdgiOS/i.test(navigator.userAgent)
const isStandalone = () => window.matchMedia?.('(display-mode: standalone)').matches || window.navigator.standalone === true

export default function PwaInstallPrompt() {
  const [installEvent, setInstallEvent] = useState(null)
  const [showIosHint, setShowIosHint] = useState(false)
  const [offline, setOffline] = useState(!navigator.onLine)
  const [refresh, setRefresh] = useState(null)

  useEffect(() => {
    const receiveInstallEvent = (event) => {
      event.preventDefault()
      setInstallEvent(event)
    }
    const receiveRefresh = (event) => setRefresh(() => event.detail)
    const showOffline = () => setOffline(true)
    const showOnline = () => setOffline(false)
    window.addEventListener('beforeinstallprompt', receiveInstallEvent)
    window.addEventListener('mechman-pwa-update', receiveRefresh)
    window.addEventListener('offline', showOffline)
    window.addEventListener('online', showOnline)
    return () => {
      window.removeEventListener('beforeinstallprompt', receiveInstallEvent)
      window.removeEventListener('mechman-pwa-update', receiveRefresh)
      window.removeEventListener('offline', showOffline)
      window.removeEventListener('online', showOnline)
    }
  }, [])

  async function install() {
    if (installEvent) {
      await installEvent.prompt()
      setInstallEvent(null)
      return
    }
    setShowIosHint(true)
  }

  if (offline) return <div className="connection-banner" role="status"><WifiOff size={16} aria-hidden="true" />You are offline. Reconnect to update CRM data.</div>
  if (refresh) return <div className="pwa-prompt" role="status"><div><RefreshCw size={18} aria-hidden="true" /><span><strong>An update is ready</strong><small>Refresh to use the latest version.</small></span></div><button className="secondary-button compact" onClick={() => refresh(true)}>Refresh</button></div>
  if (showIosHint) return <div className="pwa-prompt" role="dialog" aria-label="Install Mechman CRM"><div><Download size={18} aria-hidden="true" /><span><strong>Add Mechman to your home screen</strong><small>In Safari, tap Share, then choose Add to Home Screen.</small></span></div><button className="icon-button dismiss-prompt" aria-label="Dismiss install instructions" onClick={() => setShowIosHint(false)}><X size={18} aria-hidden="true" /></button></div>
  if (!installEvent && (!isIosSafari() || isStandalone())) return null
  return <div className="pwa-prompt" role="status"><div><Download size={18} aria-hidden="true" /><span><strong>Install Mechman CRM</strong><small>Keep the workspace on your home screen.</small></span></div><button className="primary-button compact" onClick={install}>Install</button></div>
}
