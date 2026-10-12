import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 构建产物直接输出到 Python 包内，由 FastAPI 静态托管。
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: '../meme_generator/web_dist',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:2233',
      '/memes': 'http://127.0.0.1:2233',
      '/meme': 'http://127.0.0.1:2233',
    },
  },
})
