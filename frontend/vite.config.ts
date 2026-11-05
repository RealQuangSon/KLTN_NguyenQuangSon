import { createReadStream, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
// MapLibre GL v6 tách worker thành file riêng và tự dựng URL từ
// import.meta.url — trong dev, deps được pre-bundle nên file kề bên không
// tồn tại ("Worker failed to load"); trong build, Rollup không thấy tham
// chiếu asset tĩnh. Phục vụ file worker chính chủ tại URL cố định cho cả
// hai chế độ, MapView sẽ setWorkerUrl tới đây.
const MAPLIBRE_WORKER_URL = "/maplibre-gl-worker.mjs";
function maplibreWorkerAsset(): Plugin {
  const workerPath = resolve(
    import.meta.dirname,
    "node_modules/maplibre-gl/dist/maplibre-gl-worker.mjs",
  );
  return {
    name: "maplibre-worker-asset",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (req.url?.split("?")[0] !== MAPLIBRE_WORKER_URL) return next();
        res.setHeader("Content-Type", "text/javascript");
        createReadStream(workerPath).pipe(res);
      });
    },
    generateBundle() {
      this.emitFile({
        type: "asset",
        fileName: "maplibre-gl-worker.mjs",
        source: readFileSync(workerPath),
      });
    },
  };
}
export default defineConfig({
  plugins: [react(), maplibreWorkerAsset()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
