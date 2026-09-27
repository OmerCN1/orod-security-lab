import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

const API_TARGET = process.env.OROD_API_TARGET ?? 'http://127.0.0.1:8000'
const TOKEN_PATH =
  process.env.OROD_API_TOKEN_PATH ?? fileURLToPath(new URL('../data/api-token', import.meta.url))

/**
 * The API token, read on every proxied request so the backend may start - and create the
 * token file - after this dev server. The token stays in this process: the browser talks
 * to the API same-origin through the proxy and never sees it.
 */
function apiToken(): string | null {
  if (process.env.OROD_API_TOKEN) return process.env.OROD_API_TOKEN
  try {
    return readFileSync(TOKEN_PATH, 'utf8').trim() || null
  } catch {
    return null
  }
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // Loopback only. Vite also refuses unknown Host headers, which keeps DNS-rebinding
    // pages away from the proxy that adds the token.
    host: 'localhost',
    proxy: {
      '/api': {
        target: API_TARGET,
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on('proxyReq', (proxyRequest) => {
            const token = apiToken()
            if (token) proxyRequest.setHeader('Authorization', `Bearer ${token}`)
          })
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
  },
})
