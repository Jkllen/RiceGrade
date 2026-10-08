import { useState, type FormEvent } from 'react';
import { apiRequest, type AuthReply } from '../../../lib/authApi';
export type AuthMode = 'sign-in' | 'sign-up' | 'forgot-password' | 'reset-password';

type Props = { mode: AuthMode; onMode: (mode: AuthMode) => void; onSuccess: (reply: AuthReply) => void };
export function AuthPage({ mode, onMode, onSuccess }: Props) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const title = { 'sign-in': 'Sign In', 'sign-up': 'Sign Up', 'forgot-password': 'Forgot Password', 'reset-password': 'Reset Password' }[mode];
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError('');
    if (mode === 'forgot-password' || mode === 'reset-password') {
      setError('Password reset is awaiting an approved email-delivery mechanism. No reset email was sent.');
      return;
    }
    setBusy(true);
    try {
      const reply = await apiRequest<AuthReply>(`/auth/${mode}`, { method: 'POST', body: JSON.stringify({ email, password }) }, null);
      onSuccess(reply);
    } catch (err) { setError(err instanceof Error ? err.message : 'Authentication failed'); }
    finally { setBusy(false); }
  }
  return <main className="flex min-h-screen items-center justify-center bg-stone-100 px-4 py-8">
    <section className="w-full max-w-md rounded-2xl border border-stone-200 bg-white p-8 shadow-sm">
      <h1 className="text-3xl font-bold text-emerald-900">RiceGrade</h1>
      <p className="mt-1 text-sm text-stone-500">Test-mill evaluation research prototype</p>
      <h2 className="mt-8 text-xl font-semibold">{title}</h2>
      <form onSubmit={submit} className="mt-5 space-y-4">
        {mode !== 'reset-password' && <label className="block text-sm font-medium">Email address
          <input type="email" autoComplete="email" required value={email} onChange={e => setEmail(e.target.value)} className="mt-1 w-full rounded-lg border border-stone-300 p-3" />
        </label>}
        {(mode === 'sign-in' || mode === 'sign-up') && <label className="block text-sm font-medium">Password
          <input type="password" autoComplete={mode === 'sign-up' ? 'new-password' : 'current-password'} minLength={12} required value={password} onChange={e => setPassword(e.target.value)} className="mt-1 w-full rounded-lg border border-stone-300 p-3" />
          {mode === 'sign-up' && <span className="block mt-1 text-xs text-stone-500">At least 12 characters.</span>}
        </label>}
        {error && <p role="alert" className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">{error}</p>}
        <button disabled={busy} type="submit" className="w-full rounded-lg bg-emerald-800 px-4 py-3 font-semibold text-white disabled:opacity-60">{busy ? 'Please wait…' : title}</button>
      </form>
      <nav aria-label="Authentication actions" className="mt-6 flex flex-wrap gap-3 text-sm">
        {mode !== 'sign-in' && <button className="text-emerald-800 underline" onClick={() => { setError(''); onMode('sign-in'); }}>Sign In</button>}
        {mode !== 'sign-up' && <button className="text-emerald-800 underline" onClick={() => { setError(''); onMode('sign-up'); }}>Sign Up</button>}
        {mode !== 'forgot-password' && <button className="text-emerald-800 underline" onClick={() => { setError(''); onMode('forgot-password'); }}>Forgot Password?</button>}
      </nav>
      {(mode === 'forgot-password' || mode === 'reset-password') && <p className="mt-4 text-sm text-stone-600">This screen is scaffolded, but reset links cannot be issued until email delivery and token policies are approved.</p>}
    </section>
  </main>;
}
