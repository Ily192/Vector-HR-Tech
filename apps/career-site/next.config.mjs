/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  transpilePackages: [
    "@vortex/ui",
    "@vortex/design-tokens",
    "@vortex/types",
    "@vortex/supabase-client",
  ],
  typedRoutes: true,
  experimental: {
    serverActions: {
      // El formulario de aplicación lleva el CV adentro (hasta 4 MB). Next corta las
      // Server Actions en 1 MB por defecto, y Vercel no deja pasar más de 4.5 MB por
      // función ("FUNCTION_PAYLOAD_TOO_LARGE").
      bodySizeLimit: "5mb",
    },
  },
  // /contacto era la página comercial; el sitio de candidatos no la tiene (ADR-017).
  async redirects() {
    return [{ source: "/contacto", destination: "/", permanent: false }];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          {
            key: "Strict-Transport-Security",
            value: "max-age=63072000; includeSubDomains; preload",
          },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
  },
};

export default nextConfig;
