import { useEffect, useState } from 'react';
import { AppShell, type ScreenKey } from './components/layout/AppShell';
import { DashboardPage } from './features/dashboard/pages/DashboardPage';
import { LotsPage } from './features/lots/pages/LotsPage';
import { SamplesPage } from './features/samples/pages/SamplesPage';
import { MeasurementsPage } from './features/measurements/pages/MeasurementsPage';
import { AnalysisPage } from './features/analysis/pages/AnalysisPage';
import { ReportsPage } from './features/reports/pages/ReportsPage';
import { HistoryPage } from './features/history/pages/HistoryPage';
import { AuthPage } from './features/auth/pages/AuthPage';

const screens = { dashboard: DashboardPage, lots: LotsPage, samples: SamplesPage, measurements: MeasurementsPage, analysis: AnalysisPage, reports: ReportsPage, history: HistoryPage, auth: AuthPage };

export function App() {
  const [screen, setScreen] = useState<ScreenKey>('dashboard');
  const [apiStatus, setApiStatus] = useState('checking');
  useEffect(() => {
    const controller = new AbortController();
    fetch('/api/health', { signal: controller.signal })
      .then((response) => { if (!response.ok) throw new Error('API unavailable'); return response.json() as Promise<{ status: string }>; })
      .then((data) => setApiStatus(data.status === 'ok' ? 'connected' : 'unavailable'))
      .catch((error: unknown) => { if (!(error instanceof DOMException && error.name === 'AbortError')) setApiStatus('unavailable'); });
    return () => controller.abort();
  }, []);
  const Screen = screens[screen];
  return (
    <AppShell active={screen} onNavigate={setScreen}>
      {screen === 'dashboard' && <p role="status" className="mb-4 text-sm text-stone-600">Backend connection: <strong>{apiStatus}</strong></p>}
      <Screen />
    </AppShell>
  );
}
