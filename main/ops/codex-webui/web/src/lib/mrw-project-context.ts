const LOCAL_PARENT_ORIGINS = [
  'http://127.0.0.1:5173',
  'http://127.0.0.1:5174',
  'http://localhost:5173',
  'http://localhost:5174',
];

let projectKey: string | undefined;

export function getMrwProjectKey(): string | undefined {
  return projectKey;
}

export function attachMrwProjectContext(host: Window = window): () => void {
  if (host.parent === host) return () => {};
  const configured = String(import.meta.env.VITE_MRW_PARENT_ORIGINS ?? '')
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean);
  const allowed = new Set([
    host.location.origin,
    ...LOCAL_PARENT_ORIGINS,
    ...configured,
  ]);
  const receive = (event: MessageEvent) => {
    if (event.source !== host.parent || !allowed.has(event.origin)) return;
    const data: unknown = event.data;
    if (!data || typeof data !== 'object') return;
    const message = data as Record<string, unknown>;
    if (message.type !== 'mrw.project-context') return;
    if (
      typeof message.projectKey !== 'string' ||
      !/^[A-Za-z0-9_.-]{1,128}$/.test(message.projectKey)
    ) return;
    // This is a project selection, not an authorization or a thread rebind.
    projectKey = message.projectKey;
  };
  host.addEventListener('message', receive);
  if (host.document.referrer) {
    const parentOrigin = new URL(host.document.referrer).origin;
    if (allowed.has(parentOrigin)) {
      host.parent.postMessage({ type: 'mrw.project-context-ready' }, parentOrigin);
    }
  }
  return () => host.removeEventListener('message', receive);
}
