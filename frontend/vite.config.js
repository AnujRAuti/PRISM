import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api/v1': {
        target: process.env.VITE_BACKEND_PROXY_TARGET || 'http://localhost:8000',
        changeOrigin: true,
      },
      '/health': process.env.VITE_BACKEND_PROXY_TARGET || 'http://localhost:8000',
      '/ready': process.env.VITE_BACKEND_PROXY_TARGET || 'http://localhost:8000',
      '/healthz': process.env.VITE_BACKEND_PROXY_TARGET || 'http://localhost:8000',
      '/metrics': process.env.VITE_BACKEND_PROXY_TARGET || 'http://localhost:8000',
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules')) {
            if (id.includes('react-router-dom') || id.includes('@remix-run')) {
              return 'react-router';
            }
            if (id.includes('react') || id.includes('react-dom')) {
              return 'react-core';
            }
            if (id.includes('axios')) {
              return 'network';
            }
            return 'vendor';
          }
        },
      },
    },
    chunkSizeWarningLimit: 600,
  },
});
