import { defineConfig, loadEnv } from 'vite';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'ADMIN_');
  // Backend still requires a loopback peer; Docker shares its network namespace.
  const dockerDev = process.env.ADMIN_DOCKER_DEV === 'true'
    && process.env.NODE_ENV === 'development' && mode === 'development';
  const hosts = ['localhost:3101', '127.0.0.1:3101', '[::1]:3101'];
  const origins = hosts.map(host => `http://${host}`);
  return {
    plugins: [tailwindcss(), {
      name: 'local-admin-only',
      configureServer(server) {
        server.middlewares.use((req, res, next) => {
          const peer = req.socket.remoteAddress || '';
          const local = ['::1', '127.0.0.1', '::ffff:127.0.0.1'].includes(peer);
          // Guard every path before proxy matching; never trust forwarding headers.
          const validOrigin = !req.headers.origin || origins.includes(req.headers.origin);
          if ((!local && !dockerDev) || !hosts.includes(req.headers.host || '')
              || !validOrigin || req.headers['sec-fetch-site'] === 'cross-site') {
            res.statusCode = 403;
            res.setHeader('Cache-Control', 'no-store');
            res.setHeader('Content-Type', 'application/json');
            res.end(JSON.stringify({ code: 10001, message: 'Local same-origin admin access required' }));
            return;
          }
          next();
        });
      },
    }],
    server: {
      port: 3101,
      strictPort: true,
      cors: { origin: origins },
      proxy: {
        '/api/v1/admin-console': {
          target: process.env.ADMIN_BACKEND_ORIGIN || env.ADMIN_BACKEND_ORIGIN || 'http://127.0.0.1:8000',
          changeOrigin: true,
          configure(proxy) {
            proxy.on('proxyReq', req => {
              for (const header of ['x-forwarded-for', 'x-forwarded-host', 'x-forwarded-proto', 'forwarded']) {
                req.removeHeader(header);
              }
            });
          },
        },
      },
    },
  };
});
