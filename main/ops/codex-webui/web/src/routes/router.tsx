/**
 * TanStack Router configuration with code-based route tree.
 * Auth guard bootstraps a WebUI session when no valid token is stored.
 */
import {
  createRouter,
  createRoute,
  createRootRoute,
  redirect,
  Outlet,
} from '@tanstack/react-router';
import { getApiToken, setApiToken } from '@/auth-token';
import { AuthenticatedLayout } from './authenticated-layout';
import { ChatView } from './chat-view';
import { ThreadView } from './thread-view';
import { FilesRoute } from './files-route';
import { TerminalRoute } from './terminal-route';
import { DiagnosticsRoute } from './diagnostics-route';
import { SettingsPage } from '@/components/settings/settings-page';
import { IntegrationsPage } from '@/components/integrations/integrations-page';
import { BASE_PATH, withBasePath } from '@/base-path';

export type IntegrationsSearch = { tab: 'plugins' | 'apps' | 'mcps' };

const INTEGRATION_TABS = ['plugins', 'apps', 'mcps'] as const;

function sanitizeIntegrationsSearch(
  search: Record<string, unknown>,
): IntegrationsSearch {
  const tab = search.tab;
  return {
    tab: INTEGRATION_TABS.includes(tab as IntegrationsSearch['tab'])
      ? (tab as IntegrationsSearch['tab'])
      : 'plugins',
  };
}

function isEmbeddedCodexDeployment(): boolean {
  if (BASE_PATH !== '/codex') return false;
  const pathname = new URL(window.location.href).pathname;
  return pathname === '/codex' || pathname.startsWith('/codex/');
}

async function bootstrapEmbeddedSession(): Promise<void> {
  const response = await fetch('/api/v1/codex-auth/webui/bootstrap', {
    method: 'POST',
    cache: 'no-store',
    credentials: 'same-origin',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
  });
  if (!response.ok)
    throw new Error(`WebUI authentication failed (${response.status})`);
  const payload: { data?: { accessToken?: unknown } } = await response.json();
  const accessToken = payload.data?.accessToken;
  if (typeof accessToken !== 'string' || !accessToken) {
    throw new Error('WebUI authentication returned no session token');
  }
  setApiToken(accessToken);
}

async function bootstrapSession(): Promise<void> {
  if (isEmbeddedCodexDeployment()) {
    await bootstrapEmbeddedSession();
    return;
  }

  const response = await fetch(withBasePath('/api/auth/bootstrap'), {
    cache: 'no-store',
    credentials: 'same-origin',
  });
  if (!response.ok)
    throw new Error(`WebUI authentication failed (${response.status})`);
  const payload: { accessToken?: unknown } = await response.json();
  if (typeof payload.accessToken !== 'string' || !payload.accessToken) {
    throw new Error('WebUI authentication returned no session token');
  }
  setApiToken(payload.accessToken);
}

/** Bare root — just renders child routes. */
const rootRoute = createRootRoute({
  component: () => <Outlet />,
});

/** Keep old bookmarks working while removing the manual login screen. */
const legacyLoginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/login',
  beforeLoad: () => {
    throw redirect({ to: '/' });
  },
});

/** Authenticated layout — sidebar + header + outlet. */
const authenticatedRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: 'authenticated',
  beforeLoad: async () => {
    if (!getApiToken()) {
      await bootstrapSession();
    }
  },
  component: AuthenticatedLayout,
  errorComponent: AuthBootstrapError,
});

function AuthBootstrapError() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-3 bg-background p-6 text-center">
      <h1 className="text-lg font-semibold">Codex WebUI 暂时无法连接</h1>
      <p className="text-sm text-muted-foreground">
        自动获取入口认证失败，请检查服务状态后重试。
      </p>
      <button
        className="rounded-md border border-border px-4 py-2 text-sm hover:bg-muted"
        onClick={() => void router.invalidate()}
      >
        重试
      </button>
    </main>
  );
}

/** Index route — empty chat state (no thread selected). */
const indexRoute = createRoute({
  getParentRoute: () => authenticatedRoute,
  path: '/',
  component: ChatView,
});

/** Thread route — specific thread by id. */
export const threadRoute = createRoute({
  getParentRoute: () => authenticatedRoute,
  path: '/t/$threadId',
  component: ThreadView,
});

/** Global files view. */
const filesRoute = createRoute({
  getParentRoute: () => authenticatedRoute,
  path: '/files',
  component: FilesRoute,
});

/** Global terminal view. */
const terminalRoute = createRoute({
  getParentRoute: () => authenticatedRoute,
  path: '/terminal',
  component: TerminalRoute,
});

/** Diagnostics panel. */
const diagnosticsRoute = createRoute({
  getParentRoute: () => authenticatedRoute,
  path: '/diagnostics',
  component: DiagnosticsRoute,
});

/** Settings page. */
const settingsRoute = createRoute({
  getParentRoute: () => authenticatedRoute,
  path: '/settings',
  component: SettingsPage,
});

/** Integrations page (plugins, apps, MCPs). */
const integrationsRoute = createRoute({
  getParentRoute: () => authenticatedRoute,
  path: '/integrations',
  validateSearch: sanitizeIntegrationsSearch,
  component: IntegrationsPage,
});

const routeTree = rootRoute.addChildren([
  legacyLoginRoute,
  authenticatedRoute.addChildren([
    indexRoute,
    threadRoute,
    filesRoute,
    terminalRoute,
    diagnosticsRoute,
    settingsRoute,
    integrationsRoute,
  ]),
]);

export const router = createRouter({
  routeTree,
  basepath: BASE_PATH || '/',
});

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router;
  }
}
