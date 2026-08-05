import { test, expect } from "@playwright/test";

test.describe("Navigasi Sidebar", () => {
  const navItems = [
    { href: "/", label: "Dashboard" },
    { href: "/stock", label: "Saham" },
    { href: "/portfolio", label: "Portofolio" },
    { href: "/backtest", label: "Backtest" },
    { href: "/screener", label: "Screener" },
    { href: "/scan", label: "Pola & Prediksi" },
    { href: "/automation", label: "Otomasi" },
    { href: "/reports", label: "Laporan" },
    { href: "/settings", label: "Pengaturan" },
  ];

  test("link sidebar tersedia untuk semua halaman", async ({ page }) => {
    await page.goto("/");
    for (const item of navItems) {
      const link = page.locator(`aside nav a[href="${item.href}"]`);
      await expect(link).toBeVisible();
    }
  });

  test("navigasi ke halaman tanpa API dependency", async ({ page }) => {
    const noApiPages = ["/", "/portfolio", "/backtest", "/settings"];
    for (const href of noApiPages) {
      await page.goto(href);
      await page.waitForURL(href, { timeout: 10_000 });
      await expect(page.locator("main h1")).toBeVisible();
    }
  });

  test("highlight nav item aktif", async ({ page }) => {
    await page.goto("/stock");
    await page.waitForLoadState("domcontentloaded");
    const stockLink = page.locator('aside nav a[href="/stock"]');
    await expect(stockLink).toHaveClass(/font-medium/);
  });

  test("menampilkan versi di footer sidebar", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("v0.1.0")).toBeVisible();
  });
});
