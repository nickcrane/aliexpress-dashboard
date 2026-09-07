import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Mirrors production, where the SPA and the /api/* proxy
    // (aliexpress_dashboard/spa/app.py) share an origin -- see README.
    proxy: {
      "/api": "http://localhost:8503",
    },
  },
})
