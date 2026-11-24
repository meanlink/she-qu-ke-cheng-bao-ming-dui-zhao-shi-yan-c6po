export const state = {
  token: sessionStorage.getItem('community-token'),
  user: null,
  plans: [],
  dossier: null,
};

export function session(result) {
  state.token = result?.access_token ?? null;
  state.user = result?.user ?? null;
  if (state.token) sessionStorage.setItem('community-token', state.token);
  else sessionStorage.removeItem('community-token');
}

export async function api(path, {method = 'GET', body, download = false} = {}) {
  const headers = new Headers();
  if (state.token) headers.set('Authorization', `Bearer ${state.token}`);
  if (body) headers.set('Content-Type', 'application/json');
  const response = await fetch(`/api${path}`, {method, headers, cache: 'no-store', body: body ? JSON.stringify(body) : undefined});
  if (!response.ok) {
    const value = await response.json().catch(() => ({}));
    if (response.status === 401 && state.token) {
      session(null);
      window.dispatchEvent(new Event('sessionexpired'));
    }
    throw new Error(value.detail || '请求暂时失败，请重试');
  }
  if (response.status === 204) return null;
  return download ? response.blob() : response.json();
}

export const experiment = (code, suffix = '', options) => api(`/experiments/${encodeURIComponent(code)}${suffix}`, options);
