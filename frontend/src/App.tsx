import { useEffect, useState } from 'react';
import { AppShell, type ScreenKey } from './components/layout/AppShell';
import { AuthPage, type AuthMode } from './features/auth/pages/AuthPage';
import { DashboardPage } from './features/dashboard/pages/DashboardPage';
import { AnalysisPage } from './features/analysis/pages/AnalysisPage';
import { ReportsPage } from './features/reports/pages/ReportsPage';
import { HistoryPage } from './features/history/pages/HistoryPage';
import { ProfilePage } from './features/profile/pages/ProfilePage';
import { apiRequest, clearToken, getToken, saveToken, type AuthReply, type User } from './lib/authApi';

const routes: ScreenKey[] = ['dashboard','analysis','reports','history','profile'];
const fromHash = (): ScreenKey => { const key=window.location.hash.slice(1) as ScreenKey;return routes.includes(key) ? key : 'dashboard'; };
export function App() {
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);
  const [authMode, setAuthMode] = useState<AuthMode>(new URLSearchParams(window.location.search).has('reset_token')?'reset-password':'sign-in');
  const [resetToken, setResetToken] = useState<string | null>(new URLSearchParams(window.location.search).get('reset_token'));
  const [screen, setScreen] = useState<ScreenKey>(fromHash);
  const [refresh, setRefresh] = useState(0);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  useEffect(() => { let alive = true; const token = getToken(); if (!token) { setChecking(false); return; }
    apiRequest<User>('/auth/me', {}, token).then(value=>{if(alive)setUser(value)}).catch(()=>{if(alive)clearToken()}).finally(()=>{if(alive)setChecking(false)});
    return ()=>{alive=false}; }, []);
  useEffect(()=>{const onHash=()=>setScreen(fromHash());window.addEventListener('hashchange',onHash);return()=>{window.removeEventListener('hashchange',onHash);};},[]);
  function navigate(next:ScreenKey){setScreen(next);window.location.hash=next;if(next!=='history')setSelectedId(null);}
  function authenticated(reply:AuthReply){saveToken(reply.access_token);setUser(reply.user);navigate('dashboard');}
  function clearReset(){setResetToken(null);setUser(null);clearToken();window.history.replaceState({},'',window.location.pathname+window.location.hash);}
  async function logout(){try{await apiRequest<void>('/auth/logout',{method:'POST'});}catch{/* clear local token even if API unavailable */}finally{clearToken();setUser(null);setAuthMode('sign-in');navigate('dashboard');}}
  const touched=()=>setRefresh(v=>v+1);
  if(checking)return <main className="auth-loading">Checking your secure session…</main>;
  if(!user||resetToken)return <AuthPage mode={authMode} onMode={setAuthMode} onSuccess={authenticated} resetToken={resetToken} clearReset={clearReset}/>;
  let page;
  switch(screen){
    case 'analysis':page=<AnalysisPage onCreated={touched} onHistory={()=>navigate('history')}/>;break;
    case 'reports':page=<ReportsPage onNew={()=>navigate('analysis')} onHistory={(id)=>{setSelectedId(id??null);navigate('history');}} refresh={refresh}/>;break;
    case 'history':page=<HistoryPage onNew={()=>navigate('analysis')} refresh={refresh} selectedId={selectedId} clearSelected={()=>setSelectedId(null)} onSelect={setSelectedId} onChanged={touched}/>;break;
    case 'profile':page=<ProfilePage user={user} onUpdated={setUser}/>;break;
    default:page=<DashboardPage onNavigate={navigate} onSelect={id=>{setSelectedId(id);navigate('history');}} user={user} refresh={refresh}/>;
  }
  return <AppShell active={screen} onNavigate={navigate} onLogout={()=>void logout()} userName={user.full_name} email={user.email}>{page}<footer className="content-footer">RiceGrade research prototype · Physical recovery available · Visual screening pending validation</footer></AppShell>;
}
