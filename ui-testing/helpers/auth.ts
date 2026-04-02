import { Page, expect } from "@playwright/test";

/**
 * Shared authentication helpers for UI tests.
 * Works with any FastAPI + JWT app that follows the DocketIQ auth pattern.
 */

export interface LoginCredentials {
  email: string;
  password: string;
}

/**
 * Log in via the UI login form.
 * Assumes: /login route with email + password fields.
 */
export async function login(page: Page, credentials: LoginCredentials) {
  await page.goto("/login");
  await page.getByLabel(/email/i).fill(credentials.email);
  await page.getByLabel(/password/i).fill(credentials.password);
  await page.getByRole("button", { name: /sign in|log in/i }).click();

  // Wait for redirect away from login page
  await expect(page).not.toHaveURL(/\/login/);
}

/**
 * Log out via UI.
 */
export async function logout(page: Page) {
  // Try common logout patterns
  const userMenu = page.getByRole("button", { name: /user|account|profile/i });
  if (await userMenu.isVisible()) {
    await userMenu.click();
    await page.getByRole("menuitem", { name: /log out|sign out/i }).click();
  } else {
    await page.getByRole("button", { name: /log out|sign out/i }).click();
  }

  await expect(page).toHaveURL(/\/login/);
}

/**
 * Get auth token from localStorage/sessionStorage for API calls.
 */
export async function getAuthToken(page: Page): Promise<string | null> {
  return await page.evaluate(() => {
    return (
      sessionStorage.getItem("access_token") ||
      localStorage.getItem("access_token") ||
      null
    );
  });
}

/**
 * Check if user is on a protected page (not login/public).
 */
export async function assertAuthenticated(page: Page) {
  await expect(page).not.toHaveURL(/\/login/);
  const token = await getAuthToken(page);
  expect(token).toBeTruthy();
}
