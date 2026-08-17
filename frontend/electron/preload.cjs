const { contextBridge } = require('electron');

// The main process cannot pass env vars to this renderer process, so the
// runtime base URL arrives as a `?runtime=` query parameter on the page URL.
const params = new URLSearchParams(window.location.search);

contextBridge.exposeInMainWorld('cloudraRuntime', {
  runtimeBaseUrl: params.get('runtime') || '',
  platform: process.platform,
});
