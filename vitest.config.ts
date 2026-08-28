import react from '@vitejs/plugin-react'
import { configDefaults, defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/renderer/src/setupTests.ts'],
    exclude: [...configDefaults.exclude, 'website/tests/**/*.test.mjs'],
  },
})
