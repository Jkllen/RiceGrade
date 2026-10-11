import type { ReactNode } from 'react';

export function Icon({ name, size = 20 }: { name: string; size?: number }) {
  const props = { viewBox: '0 0 24 24', width: size, height: size, fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, 'aria-hidden': true as const };
  const paths: Record<string, ReactNode> = {
    dashboard: <><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></>,
    analysis: <><path d="M12 3v18M3 12h18"/><circle cx="12" cy="12" r="8.5"/></>,
    reports: <><path d="M8 3h7l4 4v14H5V3zM14 3v5h5M8 12h8M8 16h8"/></>,
    history: <><circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 2"/></>,
    profile: <><circle cx="12" cy="8" r="4"/><path d="M4 21c0-5 3-8 8-8s8 3 8 8"/></>,
    logout: <><path d="M10 4H5v16h5M15 8l4 4-4 4M8 12h11"/></>,
    arrow: <><path d="M4 12h16m-6-6 6 6-6 6"/></>,
    check: <path d="m4 12 5 5L20 6"/>,
    photo: <><rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="m4 18 6-5 4 3 3-5 4 6"/></>,
    shield: <><path d="m12 2 9 4v6c0 6-4 9-9 10-5-1-9-4-9-10V6z"/><path d="m8 12 3 3 5-6"/></>,
    chart: <><path d="M4 20V10m6 10V4m6 16v-8m4 8H3"/></>,
    menu: <path d="M4 6h16M4 12h16M4 18h16"/>,
    close: <path d="M5 5 19 19M19 5 5 19"/>,
    search: <><circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/></>,
    lock: <><rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></>,
    warning: <><path d="M12 3 2 21h20L12 3z"/><path d="M12 9v5m0 3v.5"/></>,
  };
  return <svg {...props}>{paths[name] ?? paths.dashboard}</svg>;
}
export function Header({ eyebrow, title, description, actions }: { eyebrow: string; title: string; description: string; actions?: ReactNode }) {
  return <header className="page-heading"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p className="page-description">{description}</p></div>{actions && <div className="header-actions">{actions}</div>}</header>;
}
export function Notice({ tone = 'info', children }: { tone?: 'info' | 'warning' | 'success'; children: ReactNode }) {
  return <div className={`notice notice-${tone}`} role={tone === 'warning' ? 'alert' : 'status'}><span className="notice-icon"><Icon name={tone === 'warning' ? 'warning' : tone === 'success' ? 'check' : 'shield'} size={19}/></span><div>{children}</div></div>;
}
export function Empty({ icon = 'history', title, description, children }: { icon?: string; title: string; description: string; children?: ReactNode }) {
  return <div className="empty-state"><div className="empty-icon"><Icon name={icon} size={28}/></div><h3>{title}</h3><p>{description}</p>{children}</div>;
}
export function Busy({ label = 'Loading…' }: { label?: string }) { return <div className="loading" role="status"><span className="spinner"/>{label}</div>; }
export function StatusPill({ children }: { children: ReactNode }) { return <span className="status-pill"><span className="status-dot"/>{children}</span>; }
