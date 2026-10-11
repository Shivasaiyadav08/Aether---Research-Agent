import { defineConfig } from "vitest/config";
export default defineConfig({
  test: {
    include: ["lib/**/*.test.ts", "stores/**/*.test.ts"],
    environment: "node",
  },
});
