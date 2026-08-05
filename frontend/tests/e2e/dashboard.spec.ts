import { test, expect } from "@playwright/test";

test.describe("Dashboard", () => {
  test("menampilkan judul dan kartu ringkasan", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("main h1")).toContainText("Dashboard");
    await expect(page.getByText("NAV Portofolio")).toBeVisible();
    await expect(page.getByText("Return Hari Ini")).toBeVisible();
    await expect(page.getByText("Posisi Aktif", { exact: true })).toBeVisible();
    await expect(page.getByText("Watchlist", { exact: true })).toBeVisible();
  });

  test("menampilkan status pasar IDX", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Status Pasar IDX")).toBeVisible();
    await expect(page.getByText("Regular (09:00-15:50 WIB)")).toBeVisible();
  });

  test("menampilkan top movers placeholder", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Top Movers")).toBeVisible();
    await expect(page.getByText("Belum ada data")).toBeVisible();
  });
});
