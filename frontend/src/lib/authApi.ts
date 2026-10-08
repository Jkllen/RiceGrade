export type User = { id: number; email: string };
export type AuthReply = { access_token: string; token_type: 'bearer'; user: User };
const TOKEN_KEY = 'ricegrade-prototype-session';
export const getToken = () => sessionStorage.getItem(TOKEN_KEY);
export const saveToken = (token: string) => sessionStorage.setItem(TOKEN_KEY, token);
export const clearToken = () => sessionStorage.removeItem(TOKEN_KEY);

export async function apiRequest<T>(path: string, init: RequestInit = {}, token: string | null = getToken()): Promise<T> {
  const headers = new Headers(init.headers);
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  const response = await fetch(`/api${path}`, { ...init, headers });
  if (!response.ok) {
    let reason = `Request failed (${response.status})`;
    try { const payload = await response.json() as { detail?: string }; if (payload.detail) reason = payload.detail; } catch { /* no JSON response */ }
    throw new Error(reason);
  }
  return response.status === 204 ? undefined as T : response.json() as Promise<T>;
}
