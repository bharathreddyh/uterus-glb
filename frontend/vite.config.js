import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
      '/thumbnails': 'http://localhost:8000',
      '/images': 'http://localhost:8000',
      '/events': 'http://localhost:8000',
    },
  },
  optimizeDeps: {
    exclude: ['cornerstone-wado-image-loader'],
  },
})
