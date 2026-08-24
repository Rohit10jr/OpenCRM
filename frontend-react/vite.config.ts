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
      '/socket.io': { target: 'http://127.0.0.1:8000', ws: true },
    },
  },
})
