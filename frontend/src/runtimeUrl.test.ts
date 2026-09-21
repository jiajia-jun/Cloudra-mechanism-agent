import assert from 'node:assert/strict';
import { isTrustedAuthMessageOrigin, trustedRuntimeBase } from './runtimeUrl.ts';

const page = 'http://localhost:5173';
const vite = 'http://127.0.0.1:8000';

assert.equal(trustedRuntimeBase(null, page, vite), vite);
assert.equal(trustedRuntimeBase('http://127.0.0.1:8000', page, vite), 'http://127.0.0.1:8000');
assert.equal(trustedRuntimeBase('http://localhost:8000', page, ''), 'http://localhost:8000');
assert.equal(trustedRuntimeBase('https://evil.example/steal', page, vite), vite);
assert.equal(trustedRuntimeBase('https://evil.example/steal', page, ''), '');
assert.equal(trustedRuntimeBase('/relative', page, vite), '');
assert.equal(isTrustedAuthMessageOrigin('http://localhost:5173', 'http://localhost:5173'), true);
assert.equal(isTrustedAuthMessageOrigin('https://evil.example', 'http://localhost:5173'), false);
