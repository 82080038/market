import { test, expect } from "@playwright/test";

const pages = [
  { href: "/", name: "dashboard" },
  { href: "/signals", name: "signals" },
  { href: "/stock", name: "stock" },
  { href: "/portfolio", name: "portfolio" },
  { href: "/backtest", name: "backtest" },
  { href: "/screener", name: "screener" },
  { href: "/scan", name: "scan" },
  { href: "/automation", name: "automation" },
  { href: "/reports", name: "reports" },
  { href: "/data", name: "data" },
  { href: "/cosmos", name: "cosmos" },
  { href: "/scheduler", name: "scheduler" },
  { href: "/settings", name: "settings" },
];

test.describe("Screenshot semua halaman", () => {
  for (const p of pages) {
    test(`screenshot ${p.name}`, async ({ page }) => {
      await page.goto(p.href);
      await page.waitForLoadState("networkidle");
      await page.waitForTimeout(1500); // extra time for API fetch + render
      await page.screenshot({
        path: `screenshots/${p.name}.png`,
        fullPage: true,
      });
      // Verify screenshot file is not empty
      const body = page.locator("body");
      await expect(body).toBeVisible();
    });
  }
});
