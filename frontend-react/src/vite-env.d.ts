/// <reference types="vite/client" />

interface ImportMetaEnv {
  /**
   * Overrides the WebSocket origin for a dev server that is not proxying `/ws`.
   * Ported from the Vue app's `socket.js`, which reads the same variable.
   */
  readonly VITE_WS_ORIGIN?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
