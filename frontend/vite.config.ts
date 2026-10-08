import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  build: { chunkSizeWarningLimit: 550 },
  server: {
    host: '127.0.0.1',
    port: 5207,
    proxy: {
      '/api': 'http://127.0.0.1:8060',
      '/health': 'http://127.0.0.1:8060',
      '/provider': 'http://127.0.0.1:8060',
      '/.well-known': 'http://127.0.0.1:9083',
      '/ai-market': 'http://127.0.0.1:9083',
    },
  },
});
