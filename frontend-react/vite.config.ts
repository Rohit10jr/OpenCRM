import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'

// The Vue app gets its `/api` proxy from frappe-ui's vite plugin. There is no React
// equivalent, so the proxy is spelled out here — same target, same paths.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, 'src') },
  },
  server: {
    // Explicitly IPv4: on this machine Vite's default `localhost` bound only to [::1],
    // and Chrome resolves localhost to 127.0.0.1 first, so the page never loaded.
    host: '127.0.0.1',
    port: 5174, // 5173 is the Vue app's; both must be able to run at once
    // Fail rather than drift to 5175 if the port is taken — a silently moved dev server
    // sends the verification script at a stale build.
    strictPort: true,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/files': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      // `/ws`, not `/socket.io`. This port's realtime layer is Django Channels over a raw
      // WebSocket at `/ws/realtime` (`socket.js`, phase 6); `/socket.io` is upstream
      // Frappe's path and nothing here serves or requests it. Run 1 copied the wrong one,
      // which went unnoticed because nothing had a socket yet.
      '/ws': { target: 'http://127.0.0.1:8000', ws: true },
    },
  },
})
