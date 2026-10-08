import type { ReactNode } from 'react';
export type ScreenKey = 'dashboard' | 'analysis' | 'reports' | 'history' | 'profile';
const navigation: { key: ScreenKey; label: string }[] = [
  { key: 'dashboard', label: 'Dashboard' },
  { key: 'analysis', label: 'New Rice Analysis' },
  { key: 'reports', label: 'Screening Report' },
  { key: 'history', label: 'Assessment History' },
  { key: 'profile', label: 'Profile Management' },
];
type Props = { active: ScreenKey; onNavigate: (screen: ScreenKey) => void; onLogout: () => void; email: string; children: ReactNode };
export function AppShell({ active, onNavigate, onLogout, email, children }: Props) {
  return <div className="min-h-screen bg-stone-50 text-stone-900 md:flex">
    <aside className="border-b border-stone-200 bg-white p-5 md:min-h-screen md:w-64 md:shrink-0 md:border-b-0 md:border-r">
      <h1 className="text-2xl font-bold">RiceGrade</h1>
      <p className="mt-1 text-xs text-stone-500">Test-mill research prototype</p>
      <nav aria-label="Main navigation" className="mt-6 flex gap-1 overflow-x-auto md:flex-col">
        {navigation.map(({ key, label }) => <button key={key} type="button" onClick={() => onNavigate(key)} aria-current={active === key ? 'page' : undefined}
          className={`shrink-0 rounded-lg px-3 py-2 text-left text-sm ${active === key ? 'bg-emerald-100 font-semibold text-emerald-900' : 'text-stone-600 hover:bg-stone-100'}`}>{label}</button>)}
      </nav>
      <div className="mt-8 border-t border-stone-200 pt-4"><p className="break-all text-xs text-stone-500">Signed in: {email}</p>
        <button className="mt-3 rounded-lg border px-3 py-2 text-sm" onClick={onLogout}>Log Out</button>
      </div>
    </aside>
    <main className="w-full min-w-0 p-5 md:p-10"><div className="mx-auto max-w-5xl">
      <p className="mb-4 text-xs font-semibold uppercase text-stone-500">Development workspace · No research results</p>{children}
    </div></main>
  </div>;
}
