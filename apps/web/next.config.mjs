/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  reactStrictMode: true,
  allowedDevOrigins: [
    'localhost',
    '127.0.0.1',
    '*.ngrok-free.app',
    '*.ngrok-free.dev',
    '*.ngrok.app',
    '*.ngrok.io',
    '*.ngrok.dev',
  ],
};

export default nextConfig;
