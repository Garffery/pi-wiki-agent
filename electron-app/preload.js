const { contextBridge } = require('electron');

// Expose minimal API to renderer if needed in the future.
// Currently the frontend communicates directly with the FastAPI backend via HTTP.
contextBridge.exposeInMainWorld('electron', {
  platform: process.platform,
});
