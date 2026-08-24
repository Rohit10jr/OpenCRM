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
    port: 5174, // 5173 is the Vue app's; both must be able to run at once
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/files': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/socket.io': { target: 'http://127.0.0.1:8000', ws: true },
    },
  },
})
