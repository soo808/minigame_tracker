import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  base: "/minigame-tracker/",
  server: {
    port: 5173,
    proxy: {
      "^/minigame-tracker/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/minigame-tracker\/api/, "/api"),
      },
    },
  },
});
