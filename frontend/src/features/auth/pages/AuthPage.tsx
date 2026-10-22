import { BrandLogo } from '../../../components/ui/BrandLogo';
import { useState, type FormEvent } from 'react';
import { apiRequest, type AuthReply } from '../../../lib/authApi';
import { Icon, Notice } from '../../../components/ui/Elements';
export type AuthMode = 'sign-in' | 'sign-up' | 'forgot-password' | 'reset-password';
type Props = { mode: AuthMode; onMode: (mode: AuthMode) => void; onSuccess: (reply: AuthReply) => void; resetToken?: string | null; clearReset: () => void };
export function AuthPage({ mode, onMode, onSuccess, resetToken, clearReset }: Props) {
  const [fullName, setFullName] = useState('');
  const [role, setRole] = useState<'operator' | 'qa'>('operator');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const title = { 'sign-in': 'Welcome back', 'sign-up': 'Create your account', 'forgot-password': 'Reset your password', 'reset-password': 'Choose a new password' }[mode];
  function change(next: AuthMode) { setError(''); setMessage(''); setPassword(''); setConfirmPassword(''); onMode(next); if (mode === 'reset-password') clearReset(); }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(''); setMessage('');
    if ((mode === 'sign-up' || mode === 'reset-password') && password !== confirmPassword) { setError('Passwords do not match'); return; }
    setBusy(true);
    try {
      if (mode === 'forgot-password') {
        const reply = await apiRequest<{message:string}>('/auth/forgot-password', { method:'POST', body:JSON.stringify({ email }) }, null);
        setMessage(reply.message);
      } else if (mode === 'reset-password') {
        const reply = await apiRequest<{message:string}>('/auth/reset-password', { method:'POST', body:JSON.stringify({ token:resetToken, new_password:password }) }, null);
        clearReset(); onMode('sign-in'); setMessage(reply.message); setPassword(''); setConfirmPassword('');
      } else {
        const body = mode === 'sign-up' ? { full_name: fullName, role, email, password } : { email, password };
        const reply = await apiRequest<AuthReply>(`/auth/${mode}`, { method:'POST', body:JSON.stringify(body) }, null);
        onSuccess(reply);
      }
    } catch (err) { setError(err instanceof Error ? err.message : 'Account request failed'); }
    finally { setBusy(false); }
  }
  return <main className="auth-layout"><section className="auth-intro"><div className="auth-brand"><BrandLogo/><strong>RiceGrade</strong></div><div className="auth-intro-copy"><span className="intro-tag">MILLED RICE QUALITY ASSESSMENT</span><h1>Better decisions begin with a better test.</h1><p>One secure workspace for test-mill measurements, visual quality screening, and evidence-based milling decisions.</p><div className="auth-facts"><span><Icon name="shield" size={18}/>Image & recovery insights</span><span><Icon name="chart" size={18}/>Measurement-first</span></div></div><p className="auth-footnote">RiceGrade · Test-mill quality assessment</p></section>
    <section className="auth-form-panel"><div className="auth-card"><div className="auth-mobile-brand"><BrandLogo/><strong>RiceGrade</strong></div><p className="eyebrow">ACCOUNT ACCESS</p><h2>{title}</h2><p className="auth-description">{mode === 'sign-in' ? 'Sign in to continue to your RiceGrade workspace.' : mode === 'sign-up' ? 'Create an account to organize your test-mill assessments.' : mode === 'forgot-password' ? 'Enter your registered email to receive a reset link.' : 'Enter a new password to regain access to your account.'}</p>
      <form onSubmit={submit} className="form-stack">
        {mode === 'sign-up' && <><label className="field">Full name<input autoComplete="name" required minLength={2} maxLength={120} value={fullName} onChange={e => setFullName(e.target.value)} placeholder="Full name"/></label><label className="field">Account type<select value={role} onChange={e => setRole(e.target.value as 'operator' | 'qa')}><option value="operator">Milling Operator</option><option value="qa">QA/QC Personnel</option></select></label></>}
        {mode !== 'reset-password' && <label className="field">Email address<input type="email" autoComplete="email" required value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com"/></label>}
        {mode !== 'forgot-password' && <label className="field">{mode === 'reset-password' ? 'New password' : 'Password'}<input type="password" minLength={mode === 'sign-in' ? undefined : 12} required autoComplete={mode === 'sign-in' ? 'current-password' : 'new-password'} value={password} onChange={e => setPassword(e.target.value)} placeholder="Enter your password"/>{mode !== 'sign-in' && <small>At least 12 characters.</small>}</label>}
        {(mode === 'sign-up' || mode === 'reset-password') && <label className="field">Confirm password<input type="password" minLength={12} required autoComplete="new-password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} placeholder="Confirm your password"/></label>}
        {error && <Notice tone="warning">{error}</Notice>}{message && <Notice tone="success">{message}</Notice>}
        {mode === 'sign-in' && <div className="password-help-row"><button type="button" className="text-button" onClick={() => change('forgot-password')}>Forgot password?</button></div>}
        <button className="button button-primary wide" disabled={busy} type="submit">{busy ? 'Please wait…' : mode === 'sign-in' ? 'Sign in' : mode === 'sign-up' ? 'Create account' : mode === 'forgot-password' ? 'Send reset link' : 'Reset password'}<Icon name="arrow" size={18}/></button>
      </form>
      {mode === 'forgot-password' && message && <p className="auth-reset-hint">If the address belongs to a RiceGrade account, check your inbox and spam folder. Reset links expire after 30 minutes.</p>}
      <div className="auth-actions">{mode !== 'sign-in' && <button type="button" onClick={() => change('sign-in')}>Back to sign in</button>}{mode === 'sign-in' && <><span>New here? <button onClick={() => change('sign-up')}>Create an account</button></span></>}{mode === 'sign-up' && <span>Already have an account? <button onClick={() => change('sign-in')}>Sign in</button></span>}</div>
    </div></section>
  </main>;
}
