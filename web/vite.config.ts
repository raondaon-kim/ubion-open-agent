import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Vite dev 가 사용자가 보는 *유일한* 엔드포인트.
    // - 0.0.0.0 으로 LAN 노출 (모바일 같은 Wi-Fi 접속 허용)
    // - 8803 포트 (사용자 결정 2026-05-13: 단일 포트 정책)
    // - /v1, /health 는 내부 FastAPI(127.0.0.1:9000) 로 proxy
    host: '0.0.0.0',
    port: 8803,
    strictPort: true,
    proxy: {
      '/v1': {
        target: 'http://127.0.0.1:9000',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://127.0.0.1:9000',
        changeOrigin: true,
      },
    },
  },
})
