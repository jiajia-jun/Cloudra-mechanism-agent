const { app, BrowserWindow, dialog } = require('electron');
const { spawn } = require('node:child_process');
const http = require('node:http');
const net = require('node:net');
const path = require('node:path');
const fs = require('node:fs');

const isDev = !app.isPackaged;
let runtime = null;

function freePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.listen(0, '127.0.0.1', () => {
      const port = srv.address().port;
      srv.close(() => resolve(port));
    });
    srv.on('error', reject);
  });
}

function waitHealthy(url, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve, reject) => {
    const poll = () => {
      const req = http.get(`${url}/api/v2/runtime/health`, (res) => {
        res.resume();
        if (res.statusCode >= 200 && res.statusCode < 300) resolve();
        else retry();
      });
      req.on('error', retry);
      req.setTimeout(1000, () => { req.destroy(); retry(); });
      function retry() {
        if (Date.now() > deadline) reject(new Error('runtime did not become healthy'));
        else setTimeout(poll, 250);
      }
    };
    poll();
  });
}

async function startRuntime() {
  const port = await freePort();
  const dataDir = app.getPath('userData');
  const storePath = path.join(dataDir, 'runtime-v2.db');
  const python = process.env.CLOUDRA_PYTHON || 'python3';
  runtime = spawn(python, [
    '-m', 'uvicorn', 'cloudra.services.api_v2:create_default_v2_app',
    '--factory', '--host', '127.0.0.1', '--port', String(port), '--log-level', 'warning',
  ], {
    env: { ...process.env, CLOUDRA_RUNTIME_STORE: storePath },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  runtime.stdout.pipe(fs.createWriteStream(path.join(dataDir, 'runtime.log'), { flags: 'a' }));
  runtime.stderr.pipe(fs.createWriteStream(path.join(dataDir, 'runtime.log'), { flags: 'a' }));
  const baseUrl = `http://127.0.0.1:${port}`;
  await waitHealthy(baseUrl);
  return baseUrl;
}

async function createWindow() {
  const baseUrl = await startRuntime();
  const win = new BrowserWindow({
    width: 1480,
    height: 960,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  process.env.CLOUDRA_RUNTIME_URL = baseUrl;
  if (isDev) {
    win.loadURL('http://localhost:5173');
    win.webContents.openDevTools({ mode: 'detach' });
  } else {
    win.loadFile(path.join(__dirname, '..', 'dist', 'index.html'));
  }
}

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    const [win] = BrowserWindow.getAllWindows();
    if (win) { if (win.isMinimized()) win.restore(); win.focus(); }
  });
  app.whenReady().then(createWindow);
  app.on('window-all-closed', () => app.quit());
  app.on('before-quit', () => { if (runtime) runtime.kill(); });
}
