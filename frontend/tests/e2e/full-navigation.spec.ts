import { test, expect } from "@playwright/test";

test.describe("Navigasi Sidebar — Semua Halaman", () => {
  const navItems = [
    { href: "/", label: "Dashboard" },
    { href: "/signals", label: "Sinyal" },
    { href: "/stock", label: "Saham" },
    { href: "/portfolio", label: "Portofolio" },
    { href: "/backtest", label: "Backtest" },
    { href: "/screener", label: "Screener" },
    { href: "/scan", label: "Pola & Prediksi" },
    { href: "/automation", label: "Otomasi" },
    { href: "/reports", label: "Laporan" },
    { href: "/data", label: "Data & Sumber" },
    { href: "/cosmos", label: "Kosmos" },
    { href: "/scheduler", label: "Scheduler" },
    { href: "/settings", label: "Pengaturan" },
  ];

  test("link sidebar tersedia untuk semua halaman", async ({ page }) => {
    await page.goto("/");
    for (const item of navItems) {
      const link = page.locator(`aside nav a[href="${item.href}"]`);
      await expect(link).toBeVisible();
      await expect(link).toContainText(item.label);
    }
  });

  test("navigasi ke setiap halaman — heading terlihat", async ({ page }) => {
    for (const item of navItems) {
      await page.goto(item.href);
      await page.waitForLoadState("domcontentloaded");
      // Cosmos is full-screen without standard main/h1 — just check page loaded
      if (item.href === "/cosmos") {
        await expect(page.locator("body")).toBeVisible();
        continue;
      }
      const heading = page.locator("main h1").first();
      await expect(heading).toBeVisible({ timeout: 10_000 });
    }
  });

  test("highlight nav item aktif", async ({ page }) => {
    for (const item of navItems) {
      await page.goto(item.href);
      await page.waitForLoadState("domcontentloaded");
      const link = page.locator(`aside nav a[href="${item.href}"]`);
      await expect(link).toHaveClass(/font-medium/);
    }
  });

  test("menampilkan versi di footer sidebar", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("v0.1.0")).toBeVisible();
  });
});

test.describe("Konten Halaman — Validasi Isi", () => {
  test("Dashboard menampilkan konten utama", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    const h1 = page.locator("main h1");
    await expect(h1).toBeVisible();
    // Dashboard should have some cards or content
    const content = page.locator("main");
    await expect(content).not.toBeEmpty();
  });

  test("Sinyal menampilkan heading", async ({ page }) => {
    await page.goto("/signals");
    await page.waitForLoadState("networkidle");
    await expect(page.locator("main h1")).toContainText(/Sinyal|Signal/i);
  });

  test("Saham menampilkan heading", async ({ page }) => {
    await page.goto("/stock");
    await page.waitForLoadState("networkidle");
    await expect(page.locator("main h1")).toBeVisible();
  });

  test("Portofolio menampilkan heading", async ({ page }) => {
    await page.goto("/portfolio");
    await page.waitForLoadState("networkidle");
    await expect(page.locator("main h1")).toContainText(/Portofolio/i);
  });

  test("Backtest menampilkan heading", async ({ page }) => {
    await page.goto("/backtest");
    await page.waitForLoadState("networkidle");
    await expect(page.locator("main h1")).toContainText(/Backtest/i);
  });

  test("Screener menampilkan heading", async ({ page }) => {
    await page.goto("/screener");
    await page.waitForLoadState("networkidle");
    await expect(page.locator("main h1")).toContainText(/Screener/i);
  });

  test("Pola & Prediksi menampilkan heading", async ({ page }) => {
    await page.goto("/scan");
    await page.waitForLoadState("networkidle");
    await expect(page.locator("main h1")).toBeVisible();
  });

  test("Otomasi menampilkan heading", async ({ page }) => {
    await page.goto("/automation");
    await page.waitForLoadState("networkidle");
    await expect(page.locator("main h1")).toContainText(/Otomasi/i);
  });

  test("Laporan menampilkan heading", async ({ page }) => {
    await page.goto("/reports");
    await page.waitForLoadState("networkidle");
    await expect(page.locator("main h1")).toContainText(/Laporan/i);
  });

  test("Data & Sumber menampilkan tab sumber data", async ({ page }) => {
    await page.goto("/data");
    await page.waitForLoadState("networkidle");
    await expect(page.locator("main h1")).toContainText(/Data/i);
    // Check tabs exist — use role button to be specific
    await expect(page.getByRole("button", { name: /Sumber Data/i })).toBeVisible();
  });

  test("Kosmos menampilkan heading", async ({ page }) => {
    await page.goto("/cosmos");
    await page.waitForLoadState("networkidle");
    // Cosmos is full-screen layout without standard main/h1
    // Just verify the page loaded and has some content
    await expect(page.locator("body")).toBeVisible();
    const content = page.locator("body");
    await expect(content).not.toBeEmpty();
  });

  test("Scheduler menampilkan summary cards", async ({ page }) => {
    await page.goto("/scheduler");
    await page.waitForLoadState("networkidle");
    await expect(page.locator("main h1")).toContainText(/Scheduler/i);
    // Summary cards should be visible
    await expect(page.getByText("Total Tasks")).toBeVisible({ timeout: 10_000 });
    // Tabs — use role button to avoid strict mode violation
    await expect(page.getByRole("button", { name: "Task Scheduler" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Cron Jobs" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Event Pipeline" })).toBeVisible();
  });

  test("Scheduler — tab Cron Jobs", async ({ page }) => {
    await page.goto("/scheduler");
    await page.waitForLoadState("networkidle");
    await page.getByRole("button", { name: "Cron Jobs" }).click();
    await expect(page.getByText("Catch-up Mechanism")).toBeVisible({ timeout: 5_000 });
  });

  test("Scheduler — tab Event Pipeline", async ({ page }) => {
    await page.goto("/scheduler");
    await page.waitForLoadState("networkidle");
    await page.getByRole("button", { name: "Event Pipeline" }).click();
    await expect(page.getByRole("heading", { name: /Event-Driven Pipeline/i })).toBeVisible({ timeout: 5_000 });
  });

  test("Pengaturan menampilkan parameter risiko", async ({ page }) => {
    await page.goto("/settings");
    await page.waitForLoadState("networkidle");
    await expect(page.locator("main h1")).toContainText(/Pengaturan/i);
    await expect(page.getByRole("heading", { name: /Parameter Risiko/i })).toBeVisible();
  });
});

test.describe("API Health Check", () => {
  test("API /api/health merespons ok", async ({ request }) => {
    const res = await request.get("/api/health");
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.status).toBe("ok");
  });

  test("API /api/scheduler/status merespons dengan 22 tasks", async ({ request }) => {
    const res = await request.get("/api/scheduler/status");
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body.summary.total_tasks).toBe(22);
    expect(body.tasks).toHaveLength(22);
    expect(body.cron_jobs.length).toBeGreaterThan(0);
    expect(body.pipeline_phases.length).toBeGreaterThan(0);
  });
});
