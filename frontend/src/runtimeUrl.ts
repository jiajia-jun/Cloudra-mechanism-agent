/** `?runtime=` is attacker-controlled. Only same-origin or loopback bases
 *  may receive the session bearer; anything else falls back to the Vite
 *  build-time URL (or same-origin). */
export function isLoopbackHost(hostname: string): boolean {
  const host = hostname.toLowerCase().replace(/^\[|\]$/g, '');
  return host === 'localhost' || host === '127.0.0.1' || host === '::1';
}

export function trustedRuntimeBase(
  queryRuntime: string | null,
  pageOrigin: string,
  viteRuntimeUrl: string,
): string {
  if (queryRuntime) {
    try {
      const resolved = new URL(queryRuntime, pageOrigin);
      const page = new URL(pageOrigin);
      if (resolved.origin === page.origin || isLoopbackHost(resolved.hostname)) {
        return resolved.origin === page.origin ? '' : resolved.origin;
      }
    } catch {
      /* ignore poisoned / unparseable query */
    }
  }
  return viteRuntimeUrl || '';
}

/** OpenRouter popup postMessage: only the page's own origin may deliver a code. */
export function isTrustedAuthMessageOrigin(
  eventOrigin: string,
  pageOrigin: string,
): boolean {
  return eventOrigin === pageOrigin;
}
