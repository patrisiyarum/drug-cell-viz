import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Mol* calls ReactDOM.createRoot() on the container it receives. Strict
  // Mode double-invokes effects in dev, which causes createRoot to run twice
  // on the same DOM node and throw. Disabling strict mode here is the
  // pragmatic fix the Mol* community recommends for Next integrations.
  reactStrictMode: false,
  // Mol* ships ESM from its own package; transpiling keeps webpack happy.
  transpilePackages: ["molstar"],
};

export default nextConfig;
