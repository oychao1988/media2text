/// <reference types="vite/client" />

declare module 'flv.js' {
  namespace flvjs {
    enum Events {
      ERROR = 'error',
    }
    interface Player {
      attachMediaElement(element: HTMLMediaElement): void;
      load(): void;
      play(): Promise<void>;
      destroy(): void;
      on(event: Events, listener: () => void): void;
    }
    function isSupported(): boolean;
    function createPlayer(config: { type: string; url: string; isLive?: boolean }): Player;
  }
  export default flvjs;
}
