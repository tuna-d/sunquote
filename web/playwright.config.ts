import { defineConfig, devices } from "@playwright/test";

/**
 * The smoke test runs the real web app against a mocked API (`e2e/mock-api.mjs`): no database,
 * no network, no Gemini. Two ports are used; set `E2E_WEB_PORT` / `E2E_API_PORT` to move them
 * (several worktrees can run it side by side).
 */
const webPort = Number(process.env.E2E_WEB_PORT ?? 3210);
const apiPort = Number(process.env.E2E_API_PORT ?? 8210);
const onCi = Boolean(process.env.CI);

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: onCi ? 1 : 0,
  reporter: onCi ? [["github"], ["list"]] : "list",
  use: {
    // `localhost`, not 127.0.0.1: the Next dev server blocks other origins' dev resources (and with
    // them hydration).
    baseURL: `http://localhost:${webPort}`,
    locale: "tr-TR",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "node e2e/mock-api.mjs",
      url: `http://127.0.0.1:${apiPort}/health`,
      env: { E2E_API_PORT: String(apiPort) },
      reuseExistingServer: !onCi,
    },
    {
      // The dev server reads SUNQUOTE_API_URL at start, so the `/api` rewrite and the pages'
      // server-side calls both reach the mock.
      command: `npx next dev --port ${webPort}`,
      url: `http://localhost:${webPort}/quotes/new`,
      env: { SUNQUOTE_API_URL: `http://127.0.0.1:${apiPort}`, NEXT_TELEMETRY_DISABLED: "1" },
      timeout: 240_000,
      reuseExistingServer: !onCi,
    },
  ],
});
