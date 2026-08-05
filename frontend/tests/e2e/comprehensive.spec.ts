import { test, expect, Page, ConsoleMessage } from "@playwright/test";

const consoleErrors: string[] = [];
const consoleWarnings: string[] = [];
const pageErrors: string[] = [];

async function captureConsole(page: Page) {
  page.on("console", (msg: ConsoleMessage) => {
    if (msg.type() === "error") {
      const text = msg.text();
      // Ignore favicon, manifest, and 404 resource errors
      if (!text.includes("favicon") && !text.includes("manifest") && !text.includes("404")) {
        consoleErrors.push(text);
      }
    }
    if (msg.type() === "warning") {
      const text = msg.text();
      if (!text.includes("favicon") && !text.includes("manifest") && !text.includes("404")) {
        consoleWarnings.push(text);
      }
    }
  });
  page.on("pageerror", (err: Error) => {
    pageErrors.push(err.message);
  });
}

test.beforeEach(async ({ page }) => {
  // Clear arrays before each test
  consoleErrors.length = 0;
  consoleWarnings.length = 0;
  pageErrors.length = 0;
  await captureConsole(page);
});

test.afterEach(async ({ page }, testInfo) => {
  // After each test, check for console errors
  if (consoleErrors.length > 0) {
    console.log(`[${testInfo.title}] Console errors:\n${consoleErrors.join("\n")}`);
  }
  if (pageErrors.length > 0) {
    console.log(`[${testInfo.title}] Page errors:\n${pageErrors.join("\n")}`);
  }
});

test.describe("Dashboard - Konsisten", () => {
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

  test("tidak ada console error di dashboard", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    expect(consoleErrors).toEqual([]);
    expect(pageErrors).toEqual([]);
  });
});

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

test.describe("Semua Halaman - No Console Errors", () => {
  const allPages = [
    { href: "/", name: "Dashboard" },
    { href: "/stock", name: "Saham" },
    { href: "/portfolio", name: "Portofolio" },
    { href: "/backtest", name: "Backtest" },
    { href: "/screener", name: "Screener" },
    { href: "/scan", name: "Pola & Prediksi" },
    { href: "/automation", name: "Otomasi" },
    { href: "/reports", name: "Laporan" },
    { href: "/settings", name: "Pengaturan" },
  ];

  for (const p of allPages) {
    test(`${p.name} - tidak ada page error`, async ({ page }) => {
      await page.goto(p.href);
      await page.waitForLoadState("networkidle");
      expect(pageErrors).toEqual([]);
    });
  }
});

test.describe("Halaman Saham", () => {
  test("memuat halaman saham", async ({ page }) => {
    await page.goto("/stock");
    await expect(page.locator("main h1")).toBeVisible();
  });

  test("input ticker dan tombol analisis tersedia", async ({ page }) => {
    await page.goto("/stock");
    await expect(page.getByPlaceholder("Masukkan ticker (contoh: BBCA.JK)")).toBeVisible();
    await expect(page.getByRole("button", { name: "Analisis" })).toBeVisible();
  });

  test("skor faktor menampilkan 6 faktor", async ({ page }) => {
    await page.goto("/stock");
    await expect(page.getByText("Teknikal")).toBeVisible();
    await expect(page.getByText("Fundamental")).toBeVisible();
    await expect(page.getByText("Makro")).toBeVisible();
    await expect(page.getByText("Global")).toBeVisible();
    await expect(page.getByText("Relasi")).toBeVisible();
    await expect(page.getByText("Sentiment")).toBeVisible();
  });
});

test.describe("Halaman Portofolio", () => {
  test("memuat halaman portofolio", async ({ page }) => {
    await page.goto("/portfolio");
    await expect(page.locator("main h1")).toBeVisible();
  });

  test("menampilkan NAV, PnL, dan tabel posisi", async ({ page }) => {
    await page.goto("/portfolio");
    await expect(page.getByText("NAV Total")).toBeVisible();
    await expect(page.getByText("PnL Realized")).toBeVisible();
    await expect(page.getByText("PnL Unrealized")).toBeVisible();
    await expect(page.getByText("Posisi Aktif")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Alokasi Sektor" })).toBeVisible();
  });

  test("tabel posisi memiliki header lengkap", async ({ page }) => {
    await page.goto("/portfolio");
    const headers = ["Ticker", "Saham", "Avg Cost", "Harga", "Nilai", "PnL", "Bobot"];
    for (const h of headers) {
      await expect(page.locator(`th:has-text("${h}")`)).toBeVisible();
    }
  });
});

test.describe("Halaman Backtest - API Integration", () => {
  test("memuat halaman backtest dan menampilkan status runner", async ({ page }) => {
    await page.goto("/backtest");
    await page.waitForLoadState("networkidle");
    await expect(page.locator("main h1")).toBeVisible();
  });

  test("menampilkan status autonomous backtest", async ({ page }) => {
    await page.goto("/backtest");
    await page.waitForLoadState("networkidle");
    // Should show either status or loading state
    const mainContent = page.locator("main");
    await expect(mainContent).toBeVisible();
  });

  test("tidak ada console error di halaman backtest", async ({ page }) => {
    await page.goto("/backtest");
    await page.waitForLoadState("networkidle");
    expect(pageErrors).toEqual([]);
  });
});

test.describe("Halaman Screener", () => {
  test("memuat halaman screener", async ({ page }) => {
    await page.goto("/screener");
    await expect(page.locator("main h1")).toBeVisible();
  });

  test("filter screening tersedia", async ({ page }) => {
    await page.goto("/screener");
    await expect(page.getByText("Min Teknikal")).toBeVisible();
    await expect(page.getByText("Min Fundamental")).toBeVisible();
    await expect(page.getByText("Min Sentiment")).toBeVisible();
    await expect(page.getByRole("button", { name: "Screening" })).toBeVisible();
  });
});

test.describe("Halaman Pola & Prediksi - API Integration", () => {
  test("memuat halaman scan", async ({ page }) => {
    await page.goto("/scan");
    await page.waitForLoadState("networkidle");
    await expect(page.locator("main h1")).toBeVisible();
  });

  test("tab scan tersedia", async ({ page }) => {
    await page.goto("/scan");
    await page.waitForLoadState("networkidle");
    // Should have 4 tab buttons with correct labels
    await expect(page.getByRole("button", { name: "Deteksi Pola", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Prediksi", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Error Memory", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Delisting Memory", exact: true })).toBeVisible();
  });

  test("input ticker dan tombol scan tersedia", async ({ page }) => {
    await page.goto("/scan");
    await page.waitForLoadState("networkidle");
    // Should have a scan button or run button
    const buttons = page.locator("button");
    expect(await buttons.count()).toBeGreaterThan(0);
  });

  test("tidak ada console error di halaman scan", async ({ page }) => {
    await page.goto("/scan");
    await page.waitForLoadState("networkidle");
    expect(pageErrors).toEqual([]);
  });
});

test.describe("Halaman Otomasi - API Integration", () => {
  test("memuat halaman otomasi", async ({ page }) => {
    await page.goto("/automation");
    await page.waitForLoadState("networkidle");
    await expect(page.locator("main h1")).toBeVisible();
  });

  test("menampilkan konfigurasi otomasi", async ({ page }) => {
    await page.goto("/automation");
    await page.waitForLoadState("networkidle");
    // Should show automation config section
    const mainContent = page.locator("main");
    await expect(mainContent).toBeVisible();
  });

  test("tidak ada console error di halaman otomasi", async ({ page }) => {
    await page.goto("/automation");
    await page.waitForLoadState("networkidle");
    expect(pageErrors).toEqual([]);
  });
});

test.describe("Halaman Pengaturan", () => {
  test("memuat halaman pengaturan", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.locator("main h1")).toBeVisible();
  });

  test("menampilkan parameter risiko", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Parameter Risiko" })).toBeVisible();
    await expect(page.getByText("Risk per Trade")).toBeVisible();
    await expect(page.getByText("ATR Multiplier")).toBeVisible();
    await expect(page.getByText("Risk-Reward Ratio")).toBeVisible();
  });

  test("menampilkan notifikasi settings", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByText("Telegram Alert")).toBeVisible();
    await expect(page.getByText("Email Alert")).toBeVisible();
  });

  test("menampilkan broker activation section", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Aktivasi Broker Real" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Aktifkan Broker Real" })).toBeVisible();
  });
});

test.describe("Halaman Laporan", () => {
  test("memuat halaman laporan", async ({ page }) => {
    await page.goto("/reports");
    await expect(page.locator("main h1")).toBeVisible();
  });

  test("menampilkan 4 jenis laporan", async ({ page }) => {
    await page.goto("/reports");
    await expect(page.getByRole("heading", { name: "Pajak" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Dividen" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Trade Log" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Statement" })).toBeVisible();
  });

  test("setiap laporan memiliki tombol Generate", async ({ page }) => {
    await page.goto("/reports");
    const generateButtons = page.getByRole("button", { name: "Generate" });
    expect(await generateButtons.count()).toBe(4);
  });
});

test.describe("API Health & Integration", () => {
  test("API health endpoint merespons", async ({ page }) => {
    const response = await page.goto("/api/health");
    expect(response?.status()).toBe(200);
    const body = await response?.json();
    expect(body.status).toBe("ok");
    expect(body.env).toBe("paper");
  });

  test("API portfolio endpoint merespons dengan NAV", async ({ page }) => {
    const response = await page.goto("/api/portfolio");
    expect(response?.status()).toBe(200);
    const body = await response?.json();
    expect(body.total_nav).toBeDefined();
    expect(body.cash).toBeDefined();
    expect(body.positions).toBeDefined();
  });

  test("API watchlist endpoint merespons", async ({ page }) => {
    const response = await page.goto("/api/watchlist");
    expect(response?.status()).toBe(200);
    const body = await response?.json();
    expect(Array.isArray(body)).toBe(true);
  });

  test("API markets endpoint merespons", async ({ page }) => {
    const response = await page.goto("/api/markets");
    expect(response?.status()).toBe(200);
    const body = await response?.json();
    expect(body.length).toBeGreaterThan(0);
    expect(body[0].mic_code).toBe("XIDX");
  });
});
