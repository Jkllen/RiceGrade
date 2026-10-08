import type { ScreenKey } from '../../../components/layout/AppShell';
type Props = { onNavigate: (screen: ScreenKey) => void };
export function DashboardPage({ onNavigate }: Props) {
  const cards: { key: ScreenKey; label: string; description: string }[] = [
    { key: 'analysis', label: 'New Rice Analysis', description: 'Register a test-milled sample, enter measurements and analyze an image.' },
    { key: 'reports', label: 'Screening Report', description: 'View saved evaluation reports.' },
    { key: 'history', label: 'Assessment History', description: 'Review previous test-mill assessments.' },
    { key: 'profile', label: 'Profile Management', description: 'Manage account information.' },
  ];
  return <section><h2 className="text-2xl font-semibold">Dashboard</h2>
    <p className="mt-2 text-stone-600">Select an action. The analysis and report modules are currently empty scaffolds.</p>
    <div className="mt-6 grid gap-4 sm:grid-cols-2">{cards.map(({ key, label, description }) =>
      <button key={key} type="button" onClick={() => onNavigate(key)} className="rounded-xl border border-stone-200 bg-white p-5 text-left hover:border-emerald-600">
        <strong className="block text-lg">{label}</strong><span className="mt-2 block text-sm text-stone-600">{description}</span>
      </button>)}</div>
  </section>;
}
