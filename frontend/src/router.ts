export type RouteHandler = () => void | Promise<void>;

interface Route {
  pattern: RegExp;
  handler: RouteHandler;
}

const routes: Route[] = [];

export function registerRoute(path: string, handler: RouteHandler): void {
  const pattern = new RegExp(
    '^' + path.replace(/\*/g, '.*').replace(/\//g, '\\/') + '$'
  );
  routes.push({ pattern, handler });
}

export function navigateTo(path: string): void {
  window.location.hash = '#' + path;
}

function parseHash(): { path: string; query: Record<string, string> } {
  const raw = window.location.hash.slice(1) || '/';
  const [pathPart, queryPart] = raw.split('?');
  const query: Record<string, string> = {};
  if (queryPart) {
    for (const pair of queryPart.split('&')) {
      const [k, v] = pair.split('=');
      if (k) query[decodeURIComponent(k)] = decodeURIComponent(v || '');
    }
  }
  return { path: pathPart, query };
}

export let currentQuery: Record<string, string> = {};

async function dispatch(): Promise<void> {
  const { path, query } = parseHash();
  currentQuery = query;
  for (const route of routes) {
    if (route.pattern.test(path)) {
      await route.handler();
      return;
    }
  }
  // 404 fallback
  const app = document.getElementById('app');
  if (app) app.innerHTML = '<div class="error-view"><h1>404</h1><p>Page not found.</p></div>';
}

export function initRouter(): void {
  window.addEventListener('hashchange', dispatch);
  dispatch().catch(console.error);
}
