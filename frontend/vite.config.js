import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'node:path';
export default defineConfig({
    plugins: [react()],
    build: {
        outDir: 'dist',
        emptyOutDir: true,
        rollupOptions: {
            input: {
                candidate: resolve(__dirname, 'candidate.html'),
                admin: resolve(__dirname, 'admin.html'),
                interview: resolve(__dirname, 'interview.html'),
            },
        },
    },
    server: {
        port: 5173,
        proxy: { '/api': 'http://localhost:8001', '/jobs': 'http://localhost:8001', '/auth': 'http://localhost:8001', '/candidate': 'http://localhost:8001' },
    },
});
