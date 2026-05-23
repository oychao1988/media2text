const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("zhuanzhu", {
  openclaw: {
    /**
     * @param {{ message: string, sessionKey?: string }} opts
     */
    chat(opts) {
      return ipcRenderer.invoke("openclaw:chat", opts || {});
    },
    /**
     * SSE 流式聊天；失败时 main 进程自动 fallback 非流式 HTTP。
     * @param {{ message: string, sessionKey?: string, onDelta?: (chunk: string) => void }} opts
     */
    chatStream(opts = {}) {
      const streamId = `stream-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
      const { onDelta, ...rest } = opts;

      return new Promise((resolve, reject) => {
        const onChunk = (_event, payload) => {
          if (payload.streamId !== streamId) return;
          if (payload.delta && typeof onDelta === "function") {
            onDelta(payload.delta);
          }
          if (payload.done) {
            cleanup();
            if (payload.ok) resolve(payload);
            else reject(new Error(payload.error || "流式聊天失败"));
          }
        };

        const cleanup = () => {
          ipcRenderer.removeListener("openclaw:chat-chunk", onChunk);
        };

        ipcRenderer.on("openclaw:chat-chunk", onChunk);
        ipcRenderer.invoke("openclaw:chat-stream", { ...rest, streamId }).catch((err) => {
          cleanup();
          reject(err);
        });
      });
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
    getVersion() {
      return ipcRenderer.invoke("app:get-version");
    },
    isPackaged() {
      return ipcRenderer.invoke("app:is-packaged");
    },
    getUpdateState() {
      return ipcRenderer.invoke("app:get-update-state");
    },
    checkForUpdates() {
      return ipcRenderer.invoke("app:check-updates");
    },
    downloadUpdate() {
      return ipcRenderer.invoke("app:download-update");
    },
    quitAndInstall() {
      return ipcRenderer.invoke("app:quit-and-install");
    },
    onUpdateStatus(callback) {
      const listener = (_event, payload) => callback(payload);
      ipcRenderer.on("app:update-status", listener);
      return () => ipcRenderer.removeListener("app:update-status", listener);
    },
  },
  media2text: {
    run(argv, options) {
      return ipcRenderer.invoke("media2text:run", { argv, ...options });
    },
    archiveSearch(query, options) {
      return ipcRenderer.invoke("media2text:archive-search", {
        query,
        ...options,
      });
    },
    listTranscriptRefs(options) {
      return ipcRenderer.invoke("media2text:list-transcript-refs", options || {});
    },
    doctor() {
      return ipcRenderer.invoke("media2text:doctor");
    },
    complianceStatus() {
      return ipcRenderer.invoke("media2text:compliance-status");
    },
  },
});
