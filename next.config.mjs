/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      { source: "/daw", destination: "/" },
      { source: "/daw/index.html", destination: "/" }
    ];
  }
};

export default nextConfig;
