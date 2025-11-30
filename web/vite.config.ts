import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: 'localhost',
  },
  define: {
    'process.env': {}, // some libs assume process.env exists
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) {
            return;
          }

          if (id.includes('@tiptap') || id.includes('tiptap-markdown')) {
            return 'chunk-tiptap';
          }

          if (id.includes('@mui') || id.includes('@emotion')) {
            return 'chunk-mui';
          }

          if (id.includes('@clerk')) {
            return 'chunk-clerk';
          }

          if (id.includes('lucide-react')) {
            return 'chunk-icons';
          }

          if (id.includes('framer-motion')) {
            return 'chunk-framer-motion';
          }

          if (id.includes('zustand')) {
            return 'chunk-zustand';
          }

          if (id.includes('react-dom') || id.includes('react')) {
            return 'chunk-react';
          }

          const match = id.match(/node_modules\/(?:\.pnpm\/)?((?:@[^/]+\/)?[^/]+)/);
          if (match?.[1]) {
            return `chunk-${match[1].replace(/[@/]/g, '-')}`;
          }

          return 'chunk-vendor';
        },
      },
    },
  },
})
