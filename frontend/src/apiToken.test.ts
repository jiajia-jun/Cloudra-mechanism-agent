import assert from 'node:assert/strict';
import { TOKEN_STORAGE_KEY, bootstrapApiToken } from './apiToken.ts';

function memStorage(initial: Record<string, string> = {}) {
  const bag = { ...initial };
  return {
    getItem(key: string) {
      return Object.prototype.hasOwnProperty.call(bag, key) ? bag[key] : null;
    },
    setItem(key: string, value: string) {
      bag[key] = value;
    },
    bag,
  };
}

// #token= is persisted and the hash is scrubbed (path+search kept).
{
  const storage = memStorage();
  const replaced: string[] = [];
  const token = bootstrapApiToken(
    { hash: '#token=sekrit%2B1', pathname: '/app', search: '?runtime=http://127.0.0.1:8000' },
    storage,
    { replaceState: (_d, _u, url) => replaced.push(String(url)) },
  );
  assert.equal(token, 'sekrit+1');
  assert.equal(storage.bag[TOKEN_STORAGE_KEY], 'sekrit+1');
  assert.deepEqual(replaced, ['/app?runtime=http://127.0.0.1:8000']);
}

// No hash → fall back to sessionStorage.
{
  const storage = memStorage({ [TOKEN_STORAGE_KEY]: 'cached' });
  const replaced: string[] = [];
  const token = bootstrapApiToken(
    { hash: '', pathname: '/', search: '' },
    storage,
    { replaceState: (_d, _u, url) => replaced.push(String(url)) },
  );
  assert.equal(token, 'cached');
  assert.deepEqual(replaced, []);
}

// Empty storage + no hash → empty string (Bearer omitted).
{
  const storage = memStorage();
  assert.equal(
    bootstrapApiToken(
      { hash: '#other=1', pathname: '/', search: '' },
      storage,
      { replaceState: () => {} },
    ),
    '',
  );
}

console.log('apiToken.test.ts: ok');
