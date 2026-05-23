const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("zhuanzhu", {
  openclaw: {
  /**
   * @param {{ message: string, sessionKey?: string }} opts
   * @returns {Promise<{ ok: boolean, content?: string, error?: string, sessionKey?: string }>}
   */
    chat(opts) {
      return ipcRenderer.invoke("openclaw:chat", opts || {});
    },
  },
});
