import { contextBridge } from "electron";

contextBridge.exposeInMainWorld("electronAPI", {
  getBackendPort: () => {
    const params = new URLSearchParams(globalThis.location.search);
    return params.get("backendPort") || "9876";
  },
  platform: process.platform,
});
