import { Page, expect } from "@playwright/test";

/**
 * Common navigation helpers for UI tests.
 */

/**
 * Navigate to a route and wait for the page to be ready.
 */
export async function navigateTo(page: Page, path: string) {
  await page.goto(path);
  await page.waitForLoadState("networkidle");
}

/**
 * Wait for API response to complete (useful after mutations).
 */
export async function waitForApi(page: Page, urlPattern: string | RegExp) {
  return page.waitForResponse(
    (response) =>
      (typeof urlPattern === "string"
        ? response.url().includes(urlPattern)
        : urlPattern.test(response.url())) && response.status() < 400,
  );
}

/**
 * Wait for a toast/notification message to appear.
 */
export async function waitForToast(page: Page, text?: string | RegExp) {
  const toast = page.locator("[role='status'], [data-sonner-toast], .toast");
  if (text) {
    await expect(toast.filter({ hasText: text })).toBeVisible({ timeout: 5000 });
  } else {
    await expect(toast.first()).toBeVisible({ timeout: 5000 });
  }
}

/**
 * Click a sidebar/nav link by text.
 */
export async function clickNavLink(page: Page, text: string) {
  await page.getByRole("link", { name: new RegExp(text, "i") }).click();
  await page.waitForLoadState("networkidle");
}

/**
 * Open a dialog/modal by clicking a trigger button.
 */
export async function openDialog(page: Page, triggerText: string) {
  await page.getByRole("button", { name: new RegExp(triggerText, "i") }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
}

/**
 * Close a dialog/modal.
 */
export async function closeDialog(page: Page) {
  // Try common close patterns
  const closeBtn = page.getByRole("button", { name: /close|cancel|×/i });
  if (await closeBtn.isVisible()) {
    await closeBtn.click();
  } else {
    await page.keyboard.press("Escape");
  }
  await expect(page.getByRole("dialog")).not.toBeVisible();
}

/**
 * Check if an element is visible on the current viewport (responsive check).
 */
export async function isVisibleOnViewport(
  page: Page,
  selector: string,
): Promise<boolean> {
  const element = page.locator(selector);
  return await element.isVisible();
}
