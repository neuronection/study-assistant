/// <reference types="vitest/config" />
import fs from 'node:fs'
import { fileURLToPath, URL } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'

const LIBRARY_SCOPE = '@neuronection/assistant-ui'

function assistantUiHotswap(): Plugin {
  return {
    name: `assistant-ui-hotswap`,
    apply: () => process.env.VITEST === undefined,
    configureServer(server) {
      const scopeDir = fileURLToPath(
        new URL(`./node_modules/${LIBRARY_SCOPE}`, import.meta.url),
      )
      let restartTimer: NodeJS.Timeout | undefined
      const scheduleRestart = () => {
        clearTimeout(restartTimer)
        restartTimer = setTimeout(() => {
          server.config.logger.info(
            `${LIBRARY_SCOPE} changed on disk — restarting the dev server`,
            { timestamp: true },
          )
          void server.restart()
        }, 500)
      }
      try {
        fs.watch(scopeDir, scheduleRestart).unref()
      } catch {
        return
      }
      try {
        const distDir = fs.realpathSync(`${scopeDir}/dist`)
        fs.watch(distDir, { recursive: true }, scheduleRestart).unref()
      } catch {
        void 0
      }
    },
  }
}

export default defineConfig({
  plugins: [react(), tailwindcss(), assistantUiHotswap()],
  resolve: {
    dedupe: ['react', 'react-dom'],
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  optimizeDeps: {
    exclude: ['@neuronection/assistant-ui'],
  },
  build: {
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            {
              name: 'react-vendor',
              test: /[\\/]node_modules[\\/](react|react-dom|scheduler)[\\/]/,
              priority: 40,
            },
            {
              name: 'framer-motion',
              test: /[\\/]node_modules[\\/]framer-motion[\\/]/,
              priority: 30,
            },
            {
              name: 'katex',
              test: /[\\/]node_modules[\\/]katex[\\/]/,
              priority: 20,
            },
          ],
        },
      },
    },
  },
  server: {
    // Family dev-port bands (dev/guidelines/dev-ports.md): study is slot 2 —
    // backend 8200 / frontend 3200. Proxy follows SA_PORT so run-dev.sh
    // overrides stay consistent; strictPort fails loud instead of silently
    // bumping onto a port another family app may own.
    strictPort: true,
    proxy: {
      '/api': `http://127.0.0.1:${process.env.SA_PORT || 8200}`,
      '/ws': {
        target: `ws://127.0.0.1:${process.env.SA_PORT || 8200}`,
        ws: true,
      },
    },
  },
  test: {
    exclude: [
      '**/node_modules/**',
      '**/dist/**',
      '**/cypress/**',
      '**/.{idea,git,cache,output,temp}/**',
      'e2e/**',
    ],
    environment: 'jsdom',
    setupFiles: ['src/test/setup.ts'],
    testTimeout: 15_000,
    hookTimeout: 15_000,
  },
})
