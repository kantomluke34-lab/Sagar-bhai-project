import { useEffect, useRef, useState } from 'react'
import { Menu, X } from 'lucide-react'
import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import PwaInstallPrompt from './PwaInstallPrompt'

const compactViewport = () => window.matchMedia?.('(max-width: 760px)')

export default function Layout() {
  const [open, setOpen] = useState(false)
  const [compact, setCompact] = useState(() => compactViewport()?.matches ?? false)
  const menuButton = useRef(null)

  useEffect(() => {
    const query = compactViewport()
    if (!query) return undefined
    const updateCompactLayout = () => {
      setCompact(query.matches)
      if (!query.matches) setOpen(false)
    }
    query.addEventListener('change', updateCompactLayout)
    return () => query.removeEventListener('change', updateCompactLayout)
  }, [])

  useEffect(() => {
    if (!open) return undefined
    const closeOnEscape = (event) => {
      if (event.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [open])

  function closeMenu() {
    setOpen(false)
    window.setTimeout(() => menuButton.current?.focus(), 0)
  }

  return (
    <div className="app-shell">
      <aside id="main-navigation" className={`sidebar-wrap ${open ? 'open' : ''}`} aria-hidden={compact && !open ? 'true' : undefined} inert={compact && !open ? '' : undefined}><Sidebar onNavigate={closeMenu} /></aside>
      {open && <button className="scrim" aria-label="Close menu overlay" onClick={closeMenu} />}
      <section className="app-main">
        <header className="mobile-header">
          <div className="brand-mark small">MS</div><strong>Mechman CRM</strong>
          <button ref={menuButton} className="icon-button menu-button" aria-label={open ? 'Close menu' : 'Open menu'} aria-controls="main-navigation" aria-expanded={open} onClick={() => setOpen((value) => !value)}>{open ? <X aria-hidden="true" /> : <Menu aria-hidden="true" />}</button>
        </header>
        <main className="page"><Outlet /></main>
      </section>
      <PwaInstallPrompt />
    </div>
  )
}
