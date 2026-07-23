import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined;
          if (id.includes('react-dom') || id.includes('react\\') || id.includes('/react/')) return 'react-vendor';
          if (id.includes('lucide-react')) return 'icon-vendor';
          return 'vendor';
        },
      },
    },
  },
});
