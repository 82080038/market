import { test, expect } from "@playwright/test";

test.describe("Halaman Saham", () => {
  test("memuat halaman saham", async ({ page }) => {
    await page.goto("/stock");
    await expect(page.locator("main h1")).toBeVisible();
  });
});

test.describe("Halaman Portofolio", () => {
  test("memuat halaman portofolio", async ({ page }) => {
    await page.goto("/portfolio");
    await expect(page.locator("main h1")).toBeVisible();
  });
});

test.describe("Halaman Backtest", () => {
  test("memuat halaman backtest", async ({ page }) => {
    await page.goto("/backtest");
    await expect(page.locator("main h1")).toBeVisible();
  });
});

test.describe("Halaman Screener", () => {
  test("memuat halaman screener", async ({ page }) => {
    await page.goto("/screener");
    await expect(page.locator("main h1")).toBeVisible();
  });
});

test.describe("Halaman Otomasi", () => {
  test("memuat halaman otomasi", async ({ page }) => {
    await page.goto("/automation");
    await expect(page.locator("main h1")).toBeVisible();
  });
});

test.describe("Halaman Pengaturan", () => {
  test("memuat halaman pengaturan", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.locator("main h1")).toBeVisible();
  });
});

test.describe("Halaman Laporan", () => {
  test("memuat halaman laporan", async ({ page }) => {
    await page.goto("/reports");
    await expect(page.locator("main h1")).toBeVisible();
  });
});

test.describe("Halaman Pola & Prediksi", () => {
  test("memuat halaman scan", async ({ page }) => {
    await page.goto("/scan");
    await expect(page.locator("main h1")).toBeVisible();
  });
});
