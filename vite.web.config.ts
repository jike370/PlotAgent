import { resolve } from 'node:path'

import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  root: 'src/renderer',
  resolve: {
    alias: {
      '@renderer': resolve('src/renderer/src'),
    },
  },
  plugins: [react()],
  build: {
    outDir: '../../out/web',
    emptyOutDir: true,
  },
})
