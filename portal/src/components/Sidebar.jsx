import { BarChart3, CalendarDays, ContactRound, FileText, LogOut, MessagesSquare, Radio, Settings, Webhook } from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

const links = [
  ['/', 'Dashboard', BarChart3],
  ['/conversations', 'Conversations', MessagesSquare],
  ['/meetings', 'Meetings', CalendarDays],
  ['/crm', 'CRM Contacts', ContactRound],
  ['/waba', 'WABA Status', Radio],
  ['/templates', 'Templates', FileText],
  ['/webhook-status', 'Webhook', Webhook],
  ['/settings', 'Settings', Settings],
]

export default function Sidebar({ onNavigate }) {
  const { user, logout } = useAuth()
  return (
    <div className="sidebar">
      <div className="brand"><div className="brand-mark">MS</div><div><strong>Mechman</strong><span>Meeting CRM</span></div></div>
      <nav>
        <p className="nav-label">Workspace</p>
        {links.map(([to, label, Icon]) => (
          <NavLink key={to} to={to} end={to === '/'} onClick={onNavigate} className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            <Icon size={18} />{label}
          </NavLink>
        ))}
      </nav>
      <div className="sidebar-footer">
        <div className="user-block"><span>{user?.full_name}</span><small>{user?.role}</small></div>
        <button className="nav-link danger" onClick={logout}><LogOut size={18} />Sign out</button>
      </div>
    </div>
  )
}
