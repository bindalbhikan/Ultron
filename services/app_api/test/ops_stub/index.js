// Answers like worker/agent.js /api/app/*: only with the app API's WORKER_TOKEN.
export default {
  async fetch(request) {
    if (request.headers.get('Authorization') !== 'Bearer test-worker-token') return new Response('forbidden', { status: 403 });
    const path = new URL(request.url).pathname;
    if (path === '/api/app/workspace' && request.method === 'GET') return Response.json({ workflows: [], runs: [], github: 'ok' });
    if (path === '/api/app/run' && request.method === 'POST') return Response.json({ started: 'sale.yml' });
    if (path === '/api/app/chat' || path === '/api/app/chat/history') {
      const input = await request.json();
      if (path.endsWith('/history')) return Response.json({ messages: [{ id: 'test', question: input.userId, answer: 'A private reply', status: 'completed' }] });
      return Response.json({ id: input.userId, status: 'queued' }, { status: 202 });
    }
    if (path === '/api/app/decide') return Response.json({ error: 'expired or already decided' }, { status: 404 });
    return new Response('not found', { status: 404 });
  },
};
