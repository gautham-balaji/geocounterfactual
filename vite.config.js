import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    open: true,
    allowedHosts: ['preradio-simonne-unprefixal.ngrok-free.dev'],
    // Proxy to the FastAPI backend so the browser sees one origin and no
    // CORS preflight is involved. /static carries the generated PNGs.
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        // SSE must not be buffered or the terminal would only update once,
        // at the end of the run.
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            if (String(proxyRes.headers['content-type'] || '')
                  .includes('text/event-stream')) {
              proxyRes.headers['cache-control'] = 'no-cache, no-transform';
            }
          });
        },
      },
      '/static': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    }
  }
});
