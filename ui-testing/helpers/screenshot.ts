import { Page } from "@playwright/test";
import * as path from "path";

/**
 * Screenshot utilities for manual testing workflow.
 * Captures screenshots at key test points for user verification.
 */

/**
 * Take a labeled screenshot and save to test results.
 */
export async function captureStep(
  page: Page,
  testId: string,
  stepName: string,
  outputDir: string = "e2e/results/screenshots",
) {
  const filename = `${testId}-${stepName.replace(/\s+/g, "-").toLowerCase()}.png`;
  await page.screenshot({
    path: path.join(outputDir, filename),
    fullPage: false,
  });
  return filename;
}

/**
 * Take a full-page screenshot for documentation.
 */
export async function captureFullPage(
  page: Page,
  testId: string,
  label: string,
  outputDir: string = "e2e/results/screenshots",
) {
  const filename = `${testId}-${label.replace(/\s+/g, "-").toLowerCase()}-full.png`;
  await page.screenshot({
    path: path.join(outputDir, filename),
    fullPage: true,
  });
  return filename;
}

/**
 * Capture the current viewport for a specific device context.
 */
export async function captureViewport(
  page: Page,
  testId: string,
  viewport: string,
  outputDir: string = "e2e/results/screenshots",
) {
  const filename = `${testId}-${viewport}.png`;
  await page.screenshot({
    path: path.join(outputDir, filename),
    fullPage: false,
  });
  return filename;
}
