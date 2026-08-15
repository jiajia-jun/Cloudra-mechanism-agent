const { contextBridge } = require('electron');

contextBridge.exposeInMainWorld('cloudraRuntime', {
  runtimeBaseUrl: process.env.CLOUDRA_RUNTIME_URL || 'http://127.0.0.1:8765',
  platform: process.platform,
});
