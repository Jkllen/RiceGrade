/**
 * Cloudflare Pages Functions same-origin /api proxy.
 * The Python FastAPI API needs a separately hosted HTTPS origin with persistent SQLite.
 * Set RICEGRADE_API_ORIGIN in Cloudflare Pages -> Settings -> Environment variables.
 */
interface Env { RICEGRADE_API_ORIGIN?: string }
interface FunctionContext { request: Request; env: Env }
async function proxy({ request, env }: FunctionContext): Promise<Response> {
  const backend = env.RICEGRADE_API_ORIGIN?.replace(/\/$/, '');
  if (!backend || !/^https:\/\/[^/]+$/i.test(backend)) {
    return Response.json({detail: 'Backend connection is not configured for this Cloudflare deployment'},
      {status: 503, headers: {'Cache-Control': 'no-store'}});
  }
  const original = new URL(request.url);
  const destination = new URL(`${backend}${original.pathname}${original.search}`);
  const headers = new Headers(request.headers);
  headers.delete('host');
  headers.delete('content-length');
  // The access token remains on the server-to-server request, never in a URL.
  try {
  const upstream = await fetch(destination.toString(), {
    method: request.method,
    headers,
    body: ['GET','HEAD'].includes(request.method) ? undefined : request.body,
    redirect: 'manual',
  });
  const responseHeaders = new Headers(upstream.headers);
  responseHeaders.delete('set-cookie'); // bearer-token API; no cross-domain cookies
  responseHeaders.set('Cache-Control','private, no-store');
  responseHeaders.set('X-Content-Type-Options','nosniff');
  return new Response(upstream.body,{status:upstream.status,statusText:upstream.statusText,headers:responseHeaders});
  } catch {
    return Response.json({detail:'The RiceGrade backend is currently unavailable'},
      {status:502,headers:{'Cache-Control':'no-store'}});
  }
}
export const onRequest = proxy;
