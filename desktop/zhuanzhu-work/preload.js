const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("zhuanzhu", {
  openclaw: {
    /**
     * @param {{ message: string, sessionKey?: string }} opts
     */
    chat(opts) {
      return ipcRenderer.invoke("openclaw:chat", opts || {});
    },
  },
  app: {
    getBootstrap() {
      return ipcRenderer.invoke("app:get-bootstrap");
    },
    acceptCompliance() {
      return ipcRenderer.invoke("app:accept-compliance");
    },
    openConfigDir() {
      return ipcRenderer.invoke("app:open-config-dir");
    },
    enterMain() {
      return ipcRenderer.invoke("app:enter-main");
    },
    onBootstrapStatus(callback) {
      const listener = (_event, payload) => callback(payload);
      ipcRenderer.on("bootstrap:status", listener);
      return () => ipcRenderer.removeListener("bootstrap:status", listener);
    },
  },
});
