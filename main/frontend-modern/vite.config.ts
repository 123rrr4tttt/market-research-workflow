import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const proxyTarget = process.env.VITE_API_PROXY_TARGET || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  build: {
    target: 'es2020',
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          if (id.includes('/echarts/')) return 'echarts-vendor'
          if (id.includes('/react/') || id.includes('/react-dom/') || id.includes('/scheduler/')) return 'react-vendor'
          if (id.includes('/@tanstack/react-query/')) return 'query-vendor'
          if (id.includes('/lucide-react/')) return 'icons-vendor'
          if (
            id.includes('/react-force-graph-3d/')
            || id.includes('/3d-force-graph/')
            || id.includes('/three/')
            || id.includes('/three-spritetext/')
            || id.includes('/three-render-objects/')
            || id.includes('/three-forcegraph/')
            || id.includes('/d3-force-3d/')
          ) return 'force-graph-vendor'
          return 'vendor'
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
