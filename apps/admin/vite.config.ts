import { defineConfig, loadEnv } from 'vite';
import tailwindcss from '@tailwindcss/vite';
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'ADMIN_');
  return { plugins: [tailwindcss(), { name: 'local-admin-only', configureServer(server) {
    server.middlewares.use((req, res, next) => {
      const peer = req.socket.remoteAddress || '';
      if (req.url?.startsWith('/api/v1/admin-console') && !(peer === '::1' || peer === '127.0.0.1' || peer === '::ffff:127.0.0.1')) {
        res.statusCode = 403; res.setHeader('Cache-Control', 'no-store'); res.setHeader('Content-Type', 'application/json');
        res.end(JSON.stringify({code:10001,message:'本地管理端仅允许 loopback 访问'})); return;
      }
      next();
    });
  } }], server: { port: 3101, strictPort: true, proxy: {
    '/api/v1/admin-console': { target: process.env.ADMIN_BACKEND_ORIGIN || env.ADMIN_BACKEND_ORIGIN || 'http://127.0.0.1:8000', changeOrigin: true, configure(proxy) { proxy.on('proxyReq', req => { req.removeHeader('x-forwarded-for'); req.removeHeader('x-forwarded-proto'); req.removeHeader('forwarded'); }); } }
  } } };
});
