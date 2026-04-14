import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const proxyTarget = process.env.VITE_API_PROXY_TARGET || 'http://localhost:8000'

function inDeps(id: string, segments: string[]) {
  return segments.some((segment) => id.includes(segment))
}

export default defineConfig({
  plugins: [react()],
  build: {
    target: 'es2020',
    // GraphPage's 3D engine is already route- and feature-lazy-loaded.
    // Keep the warning threshold just above that isolated chunk to avoid noisy false positives.
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          if (inDeps(id, ['/react/', '/react-dom/', '/scheduler/', '/use-sync-external-store/'])) return 'react-vendor'
          if (inDeps(id, ['/echarts/', '/zrender/'])) return 'echarts-vendor'
          if (inDeps(id, ['/@tanstack/react-query/', '/@tanstack/query-core/'])) return 'query-vendor'
          if (inDeps(id, ['/lucide-react/'])) return 'icons-vendor'
          return
        },
      },
    },
  },
  server: {
    host: '0.0.0.0',
    port: Number(process.env.PORT || 5173),
    proxy: {
      '/api': {
        target: proxyTarget,
        changeOrigin: true,
      },
    },
  },
})
