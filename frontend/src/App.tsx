import { useEffect, useState } from 'react';
import { AppShell, type ScreenKey } from './components/layout/AppShell';
import { AuthPage, type AuthMode } from './features/auth/pages/AuthPage';
import { DashboardPage } from './features/dashboard/pages/DashboardPage';
import { AnalysisPage } from './features/analysis/pages/AnalysisPage';
import { ReportsPage } from './features/reports/pages/ReportsPage';
import { HistoryPage } from './features/history/pages/HistoryPage';
import { ProfilePage } from './features/profile/pages/ProfilePage';
import { apiRequest, clearToken, getToken, saveToken, type AuthReply, type User } from './lib/authApi';

export function App() {
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);
  const [authMode, setAuthMode] = useState<AuthMode>('sign-in');
  const [screen, setScreen] = useState<ScreenKey>('dashboard');
  const [apiStatus, setApiStatus] = useState('checking');

  useEffect(() => {
    let alive = true;
    const token = getToken();
    if (!token) { setChecking(false); return; }
    apiRequest<User>('/auth/me', {}, token).then(value => { if (alive) setUser(value); })
      .catch(() => { if (alive) clearToken(); })
      .finally(() => { if (alive) setChecking(false); });
    return () => { alive = false; };
  }, []);
  useEffect(() => {
    if (!user) return;
    apiRequest<{ user: User }>('/dashboard').then(() => setApiStatus('connected'))
      .catch(() => setApiStatus('unavailable'));
  }, [user]);

  function authenticated(reply: AuthReply) { saveToken(reply.access_token); setUser(reply.user); setScreen('dashboard'); }
  async function logout() {
    try { await apiRequest<void>('/auth/logout', { method: 'POST' }); }
    finally { clearToken(); setUser(null); setAuthMode('sign-in'); setScreen('dashboard'); }
  }
  if (checking) return <main className="p-10" role="status">Checking your session…</main>;
  if (!user) return <AuthPage mode={authMode} onMode={setAuthMode} onSuccess={authenticated} />;
  let page;
  switch (screen) {
    case 'analysis': page = <AnalysisPage />; break;
    case 'reports': page = <ReportsPage />; break;
    case 'history': page = <HistoryPage />; break;
    case 'profile': page = <ProfilePage />; break;
    default: page = <DashboardPage onNavigate={setScreen} />;
  }
  return <AppShell active={screen} onNavigate={setScreen} onLogout={() => { void logout(); }} email={user.email}>
    {screen === 'dashboard' && <p role="status" className="mb-4 text-sm text-stone-600">Protected API connection: <strong>{apiStatus}</strong></p>}
    {page}
  </AppShell>;
}
