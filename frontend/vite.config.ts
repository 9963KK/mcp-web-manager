import { defineConfig } from 'vite'

// https://vitejs.dev/config/
export default defineConfig({
  root: 'public',  // 设置 public 为根目录
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8765',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8765',
        ws: true,
      },
    },
  },
  build: {
    outDir: '../dist',  // 输出到 frontend/dist
    sourcemap: true,
    rollupOptions: {
      input: 'index.html'  // 明确指定入口文件
    }
  },
})