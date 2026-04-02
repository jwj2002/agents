import { defineConfig, devices } from "@playwright/test";

/**
 * Base Playwright config — shared across all projects.
 * Projects extend this with their own baseURL and webServer.
 *
 * Usage in project:
 *   import baseConfig from "~/agents/ui-testing/playwright.base.config";
 *   export default defineConfig({ ...baseConfig, baseURL: "..." });
 */
export default defineConfig({
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [
    ["list"],
    ["html", { open: "never", outputFolder: "e2e/results/html-report" }],
  ],
  use: {
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "desktop-chrome",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "desktop-safari",
      use: { ...devices["Desktop Safari"] },
    },
    {
      name: "mobile-chrome",
      use: { ...devices["Pixel 5"] },
    },
    {
      name: "mobile-safari",
      use: { ...devices["iPhone 13"] },
    },
  ],
});
