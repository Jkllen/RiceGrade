import type { ReactNode } from 'react';

export type ScreenKey = 'dashboard' | 'lots' | 'samples' | 'measurements' | 'analysis' | 'reports' | 'history' | 'auth';

const navigation: { key: ScreenKey; label: string }[] = [
  { key: 'dashboard', label: 'Dashboard' },
  { key: 'lots', label: 'Lots & Batches' },
  { key: 'samples', label: 'Samples' },
  { key: 'measurements', label: 'Measurements' },
  { key: 'analysis', label: 'Visual Analysis' },
  { key: 'reports', label: 'Reports' },
  { key: 'history', label: 'Assessment History' },
  { key: 'auth', label: 'Account' },
];

type Props = { active: ScreenKey; onNavigate: (screen: ScreenKey) => void; children: ReactNode };
export function AppShell({ active, onNavigate, children }: Props) {
  return (
    <div className="min-h-screen bg-stone-50 text-stone-900 md:flex">
      <aside className="border-b border-stone-200 bg-white p-5 md:min-h-screen md:w-64 md:shrink-0 md:border-b-0 md:border-r">
        <h1 className="text-2xl font-bold tracking-tight">RiceGrade</h1>
        <p className="mt-1 text-xs text-stone-500">Test-mill research prototype</p>
        <nav aria-label="Main navigation" className="mt-6 flex gap-1 overflow-x-auto md:flex-col">
          {navigation.map(({ key, label }) => (
            <button key={key} type="button" onClick={() => onNavigate(key)} aria-current={active === key ? 'page' : undefined}
              className={`shrink-0 rounded-lg px-3 py-2 text-left text-sm transition-colors ${active === key ? 'bg-emerald-100 font-semibold text-emerald-900' : 'text-stone-600 hover:bg-stone-100'}`}>
              {label}
            </button>
          ))}
        </nav>
      </aside>
      <main className="w-full min-w-0 p-5 md:p-10">
        <div className="mx-auto max-w-5xl">
          <p className="mb-4 text-xs font-semibold uppercase tracking-wide text-stone-500">Development workspace · No research results</p>
          {children}
        </div>
      </main>
    </div>
  );
}
