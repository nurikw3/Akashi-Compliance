/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
  async rewrites() {
    const apiPort = process.env.API_PORT || '8000'
    const api =
      process.env.NEXT_PUBLIC_API_URL || `http://127.0.0.1:${apiPort}`
    return [
      {
        source: '/backend-api/:path*',
        destination: `${api}/:path*`,
      },
    ]
  },
}

export default nextConfig
