/** Bearer token bootstrap for the SPA.

The launcher hands the token via the URL fragment (`#token=...`): fragments
are never sent to the server. We move it into sessionStorage and scrub the
address bar so it does not leak via screenshots/history.
*/

export const TOKEN_STORAGE_KEY = 'cloudra.api_token';

export type TokenStorage = {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
};

export type HistoryLike = {
  replaceState(data: unknown, unused: string, url?: string | null): void;
};

/**
 * Pure bootstrap: given the current hash / path / search and a storage bag,
 * return the effective API token. When the hash carries `#token=...`, the
 * token is persisted and `history.replaceState` is called to scrub the hash.
 */
export function bootstrapApiToken(
  location: { hash: string; pathname: string; search: string },
  storage: TokenStorage,
  history: HistoryLike,
): string {
  const match = location.hash.match(/^#token=(.+)$/);
  if (match) {
    const token = decodeURIComponent(match[1]);
    storage.setItem(TOKEN_STORAGE_KEY, token);
    history.replaceState(null, '', location.pathname + location.search);
    return token;
  }
  return storage.getItem(TOKEN_STORAGE_KEY) ?? '';
}
