import { Container } from '@cloudflare/containers';
import { env as workerEnv } from 'cloudflare:workers';

export class RiceGradeModelContainer extends Container {
  defaultPort = 8080;
  sleepAfter = '5m';
  envVars = { RICEGRADE_ML_TOKEN: workerEnv.RICEGRADE_ML_TOKEN }; 
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === 'GET' && url.pathname === '/health') {
      return Response.json({ status: 'ok', service: 'ricegrade-model-gateway' });
    }
    if (request.method !== 'POST' || url.pathname !== '/predict/image') {
      return Response.json({ detail: 'Not found' }, { status: 404 });
    }
    // The Pages Function owns user authentication; the gateway also authenticates
    // service-to-service requests before paying the cost of starting a container.
    const configured = env.RICEGRADE_ML_TOKEN;
    const supplied = request.headers.get('X-RiceGrade-Service-Key') || '';
    if (!configured || configured.length < 32 || !supplied || supplied !== configured) {
      return Response.json({ detail: 'Unauthorized' }, { status: 401 });
    }
    const size = Number(request.headers.get('content-length') || '0');
    if (size > 5 * 1024 * 1024) return Response.json({ detail: 'Image too large' }, { status: 413 });
    const container = env.ML_CONTAINER.getByName('ricegrade-model');
    // Expose the same token to the container, so it can enforce authentication too.
    // Pass the token through the request header; no token is written into the image or logs.
    return container.fetch(request);
  },
};
