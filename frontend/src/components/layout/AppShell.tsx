import { useState, type ReactNode } from 'react';
import { Icon } from '../ui/Elements';
export type ScreenKey = 'dashboard' | 'analysis' | 'reports' | 'history' | 'profile';
const navigation: { key: ScreenKey; label: string; icon: string }[] = [
  { key: 'dashboard', label: 'Dashboard', icon: 'dashboard' },
  { key: 'analysis', label: 'Test-Mill Evaluation', icon: 'analysis' },
  { key: 'reports', label: 'Evaluation Reports', icon: 'reports' },
  { key: 'history', label: 'Assessment History', icon: 'history' },
  { key: 'profile', label: 'My Profile', icon: 'profile' },
];
type Props = { active: ScreenKey; onNavigate: (screen: ScreenKey) => void; onLogout: () => void; userName: string; email: string; children: ReactNode };
export function AppShell({ active, onNavigate, onLogout, userName, email, children }: Props) {
  const [open, setOpen] = useState(false);
  function navigate(next: ScreenKey) { onNavigate(next); setOpen(false); window.scrollTo(0, 0); }
  const links = navigation.map(item => <button className={`nav-link ${item.key === active ? 'active' : ''}`} key={item.key}
    onClick={() => navigate(item.key)} aria-current={item.key === active ? 'page' : undefined} type="button">
    <Icon name={item.icon} size={19}/><span>{item.label}</span>{item.key === active && <span className="nav-indicator"/>}</button>);
  return <div className="app-frame">
    <header className="mobile-topbar"><button className="icon-button" aria-label="Open navigation" onClick={() => setOpen(true)}><Icon name="menu"/></button><span className="brand-mark small"/><strong>RiceGrade</strong><span className="mobile-spacer"/><span className="avatar small-avatar">{userName.trim().charAt(0).toUpperCase() || 'R'}</span></header>
    {open && <button className="sidebar-overlay" aria-label="Close navigation" onClick={() => setOpen(false)}/>}
    <aside className={`sidebar ${open ? 'sidebar-open' : ''}`}>
      <div className="brand"><span className="brand-mark"/><div><strong>RiceGrade</strong><span>Quality screening platform</span></div><button className="icon-button sidebar-close" aria-label="Close menu" onClick={() => setOpen(false)}><Icon name="close"/></button></div>
      <p className="sidebar-label">WORKSPACE</p><nav aria-label="Main navigation" className="sidebar-nav">{links}</nav>
      <div className="sidebar-bottom"><div className="account-identity"><span className="avatar">{userName.trim().charAt(0).toUpperCase() || 'R'}</span><div><strong>{userName || 'Account'}</strong><span title={email}>{email}</span></div></div><button onClick={onLogout} className="logout-button"><Icon name="logout" size={18}/>Sign out</button></div>
    </aside>
    <main className="content"><div className="content-container">{children}</div></main>
    <nav className="mobile-bottom-nav" aria-label="Mobile navigation">{navigation.map(item => <button key={item.key} className={item.key === active ? 'active' : ''} onClick={() => navigate(item.key)} aria-label={item.label} aria-current={item.key === active ? 'page' : undefined}><Icon name={item.icon} size={21}/><span>{item.key === 'analysis' ? 'New Test' : item.key === 'reports' ? 'Reports' : item.key === 'dashboard' ? 'Home' : item.key === 'history' ? 'History' : 'Profile'}</span></button>)}</nav>
  </div>;
}
