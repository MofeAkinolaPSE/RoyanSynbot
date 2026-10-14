import { defineConfig, Plugin, loadEnv } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import { pathToFileURL } from "url";

// https://vitejs.dev/config/
export default defineConfig(({ mode, command }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const backendTarget = env.VITE_API_BASE_URL || "http://localhost:8000";

  return {
  server: {
    host: "::",
    port: 8080,
    fs: {
      allow: ["./client", "./shared"],
      deny: [".env", ".env.*", "*.{crt,pem}", "**/.git/**", "server/**"],
    },
    proxy: {
      "/api": {
        target: backendTarget,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
      "/dashboard": { target: backendTarget, changeOrigin: true },
      "/inventory": { target: backendTarget, changeOrigin: true },
      "/staff": { target: backendTarget, changeOrigin: true },
      "/users": { target: backendTarget, changeOrigin: true },
      "/timesheets": { target: backendTarget, changeOrigin: true },
      "/sage": { target: backendTarget, changeOrigin: true },
      "/chat": { target: backendTarget, changeOrigin: true },
      "/analytics": { target: backendTarget, changeOrigin: true },
      "/intelligence": { target: backendTarget, changeOrigin: true },
      "/reports": { target: backendTarget, changeOrigin: true },
      "/workflow": { target: backendTarget, changeOrigin: true },
      "/audit": { target: backendTarget, changeOrigin: true },
      "/stock": { target: backendTarget, changeOrigin: true },
      "/hr": { target: backendTarget, changeOrigin: true },
      "/workspace": { target: backendTarget, changeOrigin: true },
      "/ops": { target: backendTarget, changeOrigin: true },
      "/crm": { target: backendTarget, changeOrigin: true },
      "/procurement": { target: backendTarget, changeOrigin: true, ws: true },
      "/auth": { target: backendTarget, changeOrigin: true },
      "/token": { target: backendTarget, changeOrigin: true },
      "/refresh": { target: backendTarget, changeOrigin: true },
      "/logout": { target: backendTarget, changeOrigin: true },
      "/appointments": { target: backendTarget, changeOrigin: true },
      "/calendar": { target: backendTarget, changeOrigin: true },
      "/tasks": { target: backendTarget, changeOrigin: true },
      "/queue": { target: backendTarget, changeOrigin: true },
      "/patients": { target: backendTarget, changeOrigin: true },
      "/realtime": { target: backendTarget, changeOrigin: true, ws: true },
      "/billing_hospital": { target: backendTarget, changeOrigin: true },
      "/fin": { target: backendTarget, changeOrigin: true },
      "/lab": { target: backendTarget, changeOrigin: true },
      "/pharmacy": { target: backendTarget, changeOrigin: true },
      "/wards": { target: backendTarget, changeOrigin: true },
      "/frontdesk": { target: backendTarget, changeOrigin: true },
      "/knowledge": { target: backendTarget, changeOrigin: true },
      "/threads": { target: backendTarget, changeOrigin: true },
      "/eos": { target: backendTarget, changeOrigin: true },
      "/agents": { target: backendTarget, changeOrigin: true },
      "/kg": { target: backendTarget, changeOrigin: true },
      "/docs": { target: backendTarget, changeOrigin: true },
      "/digital-twin": { target: backendTarget, changeOrigin: true },
    },
  },
  build: {
    outDir: "dist/spa",
  },
  plugins: [react(), ...(command === "serve" ? [expressPlugin()] : [])],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./client"),
      "@shared": path.resolve(__dirname, "./shared"),
    },
  },
  test: {
    // Run in node environment by default (no DOM needed for existing spec files).
    // Switch individual files to "jsdom" via `@vitest-environment jsdom` docblock
    // when writing React component tests.
    environment: "node",
    include: [
      "client/**/*.{test,spec}.{ts,tsx}",
      "server/**/*.{test,spec}.ts",
      "shared/**/*.{test,spec}.ts",
    ],
    globals: true,
  },
};
});

function expressPlugin(): Plugin {
  return {
    name: "express-plugin",
    apply: "serve", // Only apply during development (serve mode)
    async configureServer(server) {
      // Non-literal import path prevents esbuild from resolving this at config-load time.
      // apply:"serve" already stops this running during builds; the variable just
      // prevents the static-analysis error when ./server is absent in Docker.
      //
      // Must be an ABSOLUTE file:// URL, not "./server". Vitest transforms this
      // config into node_modules/.vite-temp/ and then runs it from there, so a
      // relative specifier resolved to .vite-temp/server and threw
      // ERR_MODULE_NOT_FOUND — which broke `npx vitest --run` for every spec in
      // the repo, not just new ones. pathToFileURL also keeps the dynamic
      // import working on Windows, where a bare absolute path is not a legal
      // ESM specifier.
      const serverEntry = pathToFileURL(path.resolve(__dirname, "./server/index.ts")).href;
      try {
        const { createServer } = await import(/* @vite-ignore */ serverEntry);
        const app = createServer();

        // Add Express app as middleware to Vite dev server
        server.middlewares.use(app);
      } catch (err) {
        // ./server is intentionally absent in some deployments (Docker builds
        // the SPA only). Dev server should still come up serving the frontend.
        console.warn("[express-plugin] optional API server not mounted:", (err as Error).message);
      }
    },
  };
}
