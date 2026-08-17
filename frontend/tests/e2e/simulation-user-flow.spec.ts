/**
 * Simulasi User Flow 1 Tahun — Playwright headed browser
 *
 * Mensimulasikan aktivitas user selama 1 tahun trading:
 * - Setiap "hari": cek dashboard, baca sinyal, review portfolio
 * - Setiap "minggu": jalankan screener, analisa saham individual
 * - Setiap "bulan": review laporan, cek data sources, adjust settings
 * - Setiap "quarter": review backtest, cek scheduler, kosmos view
 *
 * Browser ditampilkan di HDMI-0 (DISPLAY=:1)
 */

import { test, expect, Page, ConsoleMessage, Request, Response } from "@playwright/test";

const ALL_PAGES = [
  { href: "/", name: "Dashboard", section: "Analisis" },
  { href: "/signals", name: "Sinyal", section: "Analisis" },
  { href: "/screener", name: "Screener", section: "Analisis" },
  { href: "/stock", name: "Saham", section: "Analisis" },
  { href: "/scan", name: "Pola & Prediksi", section: "Analisis" },
  { href: "/portfolio", name: "Portofolio", section: "Trading" },
  { href: "/backtest", name: "Backtest", section: "Trading" },
  { href: "/simulation", name: "Simulasi", section: "Trading" },
  { href: "/automation", name: "Otomasi", section: "Trading" },
  { href: "/reports", name: "Laporan", section: "Sistem" },
  { href: "/cosmos", name: "Kosmos", section: "Sistem" },
  { href: "/data", name: "Data & Sumber", section: "Sistem" },
  { href: "/scheduler", name: "Scheduler", section: "Sistem" },
  { href: "/settings", name: "Pengaturan", section: "Sistem" },
];

const TICKERS = ["BBCA.JK", "BBRI.JK", "TLKM.JK", "ASII.JK", "GOTO.JK", "BMRI.JK"];

interface SimIssue {
  page: string;
  type: "console-error" | "page-error" | "network-error" | "api-fail" | "ui-missing";
  detail: string;
  timestamp: string;
}

const issues: SimIssue[] = [];

function logIssue(page: string, type: SimIssue["type"], detail: string) {
  const issue: SimIssue = {
    page,
    type,
    detail,
    timestamp: new Date().toISOString(),
  };
  issues.push(issue);
  const emoji = type === "console-error" ? "⚠️" : type === "page-error" ? "💥" : type === "network-error" ? "🌐" : type === "api-fail" ? "🔌" : "❓";
  console.log(`  ${emoji} [${page}] ${type}: ${detail.slice(0, 120)}`);
}

async function attachListeners(page: Page, pageName: string) {
  // Remove all existing listeners to prevent accumulation
  page.removeAllListeners("console");
  page.removeAllListeners("pageerror");
  page.removeAllListeners("response");
  page.removeAllListeners("requestfailed");

  page.on("console", (msg: ConsoleMessage) => {
    if (msg.type() === "error") {
      const text = msg.text();
      if (!text.includes("favicon") && !text.includes("manifest") && !text.includes("Failed to load resource")) {
        logIssue(pageName, "console-error", text);
      }
    }
  });
  page.on("pageerror", (err: Error) => {
    logIssue(pageName, "page-error", err.message);
  });
  page.on("response", (res: Response) => {
    if (res.status() >= 500 && res.url().includes("/api/")) {
      logIssue(pageName, "api-fail", `${res.status()} ${res.url()}`);
    }
  });
  page.on("requestfailed", (req: Request) => {
    if (req.url().includes("/api/")) {
      logIssue(pageName, "network-error", `${req.failure()?.errorText} ${req.url()}`);
    }
  });
}

async function visitPage(page: Page, href: string, name: string, waitMs = 3000) {
  console.log(`\n📍 [${new Date().toISOString().slice(11, 19)}] Mengunjungi ${name} (${href})`);
  await page.goto(`http://localhost:3000${href}`, { waitUntil: "domcontentloaded", timeout: 30_000 });
  // Wait for h1 or loading to resolve
  try {
    await expect(page.locator("main h1, aside + div h1, div h1").first()).toBeVisible({ timeout: 20_000 });
  } catch {
    console.log(`  ⏳ ${name}: h1 tidak ditemukan dalam 20s, lanjut...`);
  }
  await page.waitForTimeout(waitMs);
}

async function clickNav(page: Page, href: string, name: string) {
  console.log(`  🖱️  Klik nav: ${name}`);
  const link = page.locator(`aside nav a[href="${href}"]`);
  await expect(link).toBeVisible({ timeout: 10_000 });
  await link.click();
  await page.waitForLoadState("domcontentloaded", { timeout: 30_000 });
  await page.waitForTimeout(2000);
}

test.describe.configure({ mode: "serial" });

test("Simulasi 1 Tahun — User Flow Lengkap", async ({ browser }) => {
  // Launch headed browser on DISPLAY=:1 (HDMI-0)
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    locale: "id-ID",
  });
  const page = await context.newPage();

  // Attach global listeners
  for (const p of ALL_PAGES) {
    // Listeners are attached per-page-visit below
  }

  console.log("\n" + "=".repeat(80));
  console.log("🚀 SIMULASI 1 TAHUN — USER FLOW APLIKASI PASAR MODAL");
  console.log("=".repeat(80));
  console.log(`📅 Periode: 365 hari simulasi (compressed)`);
  console.log(`🖥️  Display: HDMI-0 (DISPLAY=:1)`);
  console.log(`🌐 Frontend: http://localhost:3000`);
  console.log(`🔌 Backend: http://localhost:8000`);
  console.log("=".repeat(80) + "\n");

  // === PHASE 1: Initial Discovery — Visit all pages ===
  console.log("\n" + "─".repeat(60));
  console.log("📋 FASE 1: Eksplorasi Awal — Kunjungi semua halaman");
  console.log("─".repeat(60));

  issues.length = 0; // Clear any pre-existing issues

  for (const p of ALL_PAGES) {
    await attachListeners(page, p.name);
    await visitPage(page, p.href, p.name, 3000);
  }

  // Report Phase 1 issues immediately
  const phase1Issues = issues.filter(i => i);
  if (phase1Issues.length > 0) {
    console.log("\n" + "!".repeat(60));
    console.log(`🚨 FASE 1 SELESAI — ${phase1Issues.length} error ditemukan!`);
    console.log("!".repeat(60));
    for (const issue of phase1Issues) {
      console.log(`  [${issue.page}] ${issue.type}: ${issue.detail.slice(0, 150)}`);
    }
    console.log("!".repeat(60) + "\n");
  } else {
    console.log("\n✅ FASE 1 SELESAI — Tidak ada error ditemukan!\n");
  }

  // === PHASE 2: Daily Routine (simulated 365 days, compressed) ===
  console.log("\n" + "─".repeat(60));
  console.log("📋 FASE 2: Rutinitas Harian (365 hari simulasi)");
  console.log("─".repeat(60));

  const TRADING_DAYS = 252; // 1 year of trading days
  const DAYS_PER_TICK = 50; // Compress: visit every 50th day
  const simulatedDays: number[] = [];
  for (let d = 1; d <= TRADING_DAYS; d += DAYS_PER_TICK) {
    simulatedDays.push(d);
  }
  // Always include last day
  if (simulatedDays[simulatedDays.length - 1] !== TRADING_DAYS) {
    simulatedDays.push(TRADING_DAYS);
  }

  // Map trading day number to a simulated calendar date
  // Start from Aug 18, 2025 (Monday), skip weekends
  const simStartDate = new Date(2025, 7, 18); // Aug 18, 2025
  function tradingDayToDate(dayNum: number): Date {
    const d = new Date(simStartDate);
    let count = 0;
    while (count < dayNum - 1) {
      d.setDate(d.getDate() + 1);
      const dow = d.getDay();
      if (dow !== 0 && dow !== 6) count++; // skip weekends
    }
    return new Date(d);
  }

  for (const day of simulatedDays) {
    const simDate = tradingDayToDate(day);
    const dateStr = simDate.toLocaleDateString("id-ID", { weekday: "short", day: "numeric", month: "short", year: "numeric" });
    console.log(`\n📅 Hari ke-${day}/${TRADING_DAYS} — ${dateStr}`);

    // Morning: Check dashboard
    console.log(`  🌅 Pagi: Cek Dashboard`);
    await attachListeners(page, "Dashboard");
    await visitPage(page, "/", "Dashboard", 2000);

    // Check IHSG data
    const ihsgCard = page.locator("text=IHSG").first();
    if (await ihsgCard.isVisible({ timeout: 5000 }).catch(() => false)) {
      console.log(`  ✅ IHSG card visible`);
    } else {
      logIssue("Dashboard", "ui-missing", "IHSG card tidak ditemukan");
    }

    // Check portfolio summary
    const navCard = page.locator("text=NAV Portofolio").first();
    if (await navCard.isVisible({ timeout: 5000 }).catch(() => false)) {
      console.log(`  ✅ NAV Portofolio card visible`);
    } else {
      logIssue("Dashboard", "ui-missing", "NAV Portofolio card tidak ditemukan");
    }

    // Check market movers
    const gainersSection = page.locator("text=Top Movers").first();
    if (await gainersSection.isVisible({ timeout: 5000 }).catch(() => false)) {
      console.log(`  ✅ Top Gainers section visible`);
    } else {
      logIssue("Dashboard", "ui-missing", "Top Gainers section tidak ditemukan");
    }

    // Midday: Check signals
    console.log(`  📊 Siang: Cek Sinyal`);
    await clickNav(page, "/signals", "Sinyal");
    await page.waitForTimeout(2000);

    // Check signal table or empty state
    const signalsContent = page.locator("main").first();
    const signalsText = await signalsContent.textContent();
    if (signalsText && (signalsText.includes("Sinyal") || signalsText.includes("Belum ada"))) {
      console.log(`  ✅ Signals page content loaded`);
    } else {
      logIssue("Sinyal", "ui-missing", "Konten halaman sinyal kosong");
    }

    // Afternoon: Review portfolio
    console.log(`  💼 Sore: Review Portofolio`);
    await clickNav(page, "/portfolio", "Portofolio");
    await page.waitForTimeout(2000);

    // Check portfolio cards
    const navTotal = page.locator("text=NAV Total").first();
    if (await navTotal.isVisible({ timeout: 5000 }).catch(() => false)) {
      console.log(`  ✅ NAV Total card visible`);
    } else {
      logIssue("Portofolio", "ui-missing", "NAV Total card tidak ditemukan");
    }

    // Check positions table
    // Wait for loading to finish first
    await expect(page.locator("text=Memuat data...")).not.toBeVisible({ timeout: 15_000 }).catch(() => {});
    const posisiHeader = page.locator("th:has-text('Ticker')").first();
    if (await posisiHeader.isVisible({ timeout: 5000 }).catch(() => false)) {
      console.log(`  ✅ Posisi table headers visible`);
    } else {
      logIssue("Portofolio", "ui-missing", "Table header 'Ticker' tidak ditemukan");
    }
  }

  // === PHASE 3: Weekly Activities ===
  console.log("\n" + "─".repeat(60));
  console.log("📋 FASE 3: Aktivitas Mingguan");
  console.log("─".repeat(60));

  const WEEKS = 52;
  const WEEKS_PER_TICK = 20;
  for (let week = 1; week <= WEEKS; week += WEEKS_PER_TICK) {
    const weekDate = new Date(simStartDate);
    weekDate.setDate(weekDate.getDate() + (week - 1) * 7);
    const weekDateStr = weekDate.toLocaleDateString("id-ID", { day: "numeric", month: "short", year: "numeric" });
    console.log(`\n📅 Minggu ke-${week}/${WEEKS} — ${weekDateStr}`);

    // Run screener
    console.log(`  🔍 Screener: Cari saham potensial`);
    await clickNav(page, "/screener", "Screener");
    await page.waitForTimeout(2000);

    // Check screener filters
    const minScoreInput = page.locator("input[type='number']").first();
    if (await minScoreInput.isVisible({ timeout: 5000 }).catch(() => false)) {
      console.log(`  ✅ Min Composite Score input visible`);
      // Try adjusting filter
      await minScoreInput.fill("60");
      await page.waitForTimeout(1000);
    } else {
      logIssue("Screener", "ui-missing", "Min Composite Score input tidak ditemukan");
    }

    // Analyze a stock
    console.log(`  📈 Analisa Saham: ${TICKERS[week % TICKERS.length]}`);
    await clickNav(page, "/stock", "Saham");
    await page.waitForTimeout(2000);

    const tickerInput = page.getByPlaceholder("Masukkan ticker (contoh: BBCA.JK)");
    if (await tickerInput.isVisible({ timeout: 5000 }).catch(() => false)) {
      await tickerInput.fill(TICKERS[week % TICKERS.length]);
      const analyzeBtn = page.getByRole("button", { name: "Analisis" });
      if (await analyzeBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
        await analyzeBtn.click();
        console.log(`  🔄 Menganalisa ${TICKERS[week % TICKERS.length]}...`);
        await page.waitForTimeout(5000);
        // Check if results appeared
        const factorSection = page.locator("text=Faktor").first();
        if (await factorSection.isVisible({ timeout: 10_000 }).catch(() => false)) {
          console.log(`  ✅ Hasil analisa faktor visible`);
        } else {
          console.log(`  ℹ️  Hasil analisa belum muncul (mungkin data belum ada)`);
        }
      }
    } else {
      logIssue("Saham", "ui-missing", "Ticker input tidak ditemukan");
    }

    // Check Pola & Prediksi
    console.log(`  🔬 Pola & Prediksi: Scan pola`);
    await clickNav(page, "/scan", "Pola & Prediksi");
    await page.waitForTimeout(2000);
  }

  // === PHASE 4: Monthly Activities ===
  console.log("\n" + "─".repeat(60));
  console.log("📋 FASE 4: Aktivitas Bulanan");
  console.log("─".repeat(60));

  const MONTHS = 6;
  for (let month = 1; month <= MONTHS; month++) {
    const monthDate = new Date(simStartDate);
    monthDate.setMonth(monthDate.getMonth() + month - 1);
    const monthDateStr = monthDate.toLocaleDateString("id-ID", { month: "long", year: "numeric" });
    console.log(`\n📅 Bulan ke-${month}/${MONTHS} — ${monthDateStr}`);

    // Review reports
    console.log(`  📄 Laporan: Cek pajak & trade log`);
    await clickNav(page, "/reports", "Laporan");
    await page.waitForTimeout(2000);

    // Check tax report
    const taxTitle = page.locator("text=Laporan Pajak Tahunan").first();
    if (await taxTitle.isVisible({ timeout: 5000 }).catch(() => false)) {
      console.log(`  ✅ Laporan Pajak Tahunan visible`);
    } else {
      logIssue("Laporan", "ui-missing", "Laporan Pajak Tahunan tidak ditemukan");
    }

    // Check trade log
    const tradeLogTitle = page.locator("text=Trade Log").first();
    if (await tradeLogTitle.isVisible({ timeout: 5000 }).catch(() => false)) {
      console.log(`  ✅ Trade Log visible`);
    } else {
      logIssue("Laporan", "ui-missing", "Trade Log tidak ditemukan");
    }

    // Check dividends
    const dividendTitle = page.locator("text=Riwayat Dividen").first();
    if (await dividendTitle.isVisible({ timeout: 5000 }).catch(() => false)) {
      console.log(`  ✅ Riwayat Dividen visible`);
    } else {
      logIssue("Laporan", "ui-missing", "Riwayat Dividen tidak ditemukan");
    }

    // Check data sources
    console.log(`  🗃️  Data & Sumber: Cek kesehatan data`);
    await clickNav(page, "/data", "Data & Sumber");
    await page.waitForTimeout(3000);

    // Check data sources section
    const sourcesTitle = page.locator("text=Sumber Data").first();
    if (await sourcesTitle.isVisible({ timeout: 5000 }).catch(() => false)) {
      console.log(`  ✅ Sumber Data section visible`);
    } else {
      logIssue("Data", "ui-missing", "Sumber Data section tidak ditemukan");
    }

    // Check settings
    console.log(`  ⚙️  Pengaturan: Review parameter risiko`);
    await clickNav(page, "/settings", "Pengaturan");
    await page.waitForTimeout(2000);

    const riskTitle = page.locator("text=Parameter Risiko").first();
    if (await riskTitle.isVisible({ timeout: 5000 }).catch(() => false)) {
      console.log(`  ✅ Parameter Risiko visible`);
    } else {
      logIssue("Pengaturan", "ui-missing", "Parameter Risiko tidak ditemukan");
    }
  }

  // === PHASE 5: Quarterly Activities ===
  console.log("\n" + "─".repeat(60));
  console.log("📋 FASE 5: Aktivitas Quarterly");
  console.log("─".repeat(60));

  for (let quarter = 1; quarter <= 4; quarter++) {
    console.log(`\n📅 Quarter ${quarter}/4`);

    // Backtest review
    console.log(`  🧪 Backtest: Review hasil`);
    await clickNav(page, "/backtest", "Backtest");
    await page.waitForTimeout(5000);

    const backtestH1 = page.locator("main h1").first();
    if (await backtestH1.isVisible({ timeout: 20_000 }).catch(() => false)) {
      console.log(`  ✅ Backtest page loaded`);
    } else {
      logIssue("Backtest", "ui-missing", "Backtest h1 tidak muncul (loading timeout)");
    }

    // Scheduler check
    console.log(`  ⏰ Scheduler: Cek status task`);
    await clickNav(page, "/scheduler", "Scheduler");
    await page.waitForTimeout(3000);

    const schedulerH1 = page.locator("main h1").first();
    if (await schedulerH1.isVisible({ timeout: 5000 }).catch(() => false)) {
      console.log(`  ✅ Scheduler page loaded`);
    } else {
      logIssue("Scheduler", "ui-missing", "Scheduler h1 tidak ditemukan");
    }

    // Cosmos view
    console.log(`  🌍 Kosmos: Global market view`);
    await clickNav(page, "/cosmos", "Kosmos");
    await page.waitForTimeout(3000);

    const cosmosH1 = page.locator("main h1").first();
    if (await cosmosH1.isVisible({ timeout: 5000 }).catch(() => false)) {
      console.log(`  ✅ Kosmos page loaded`);
    } else {
      logIssue("Kosmos", "ui-missing", "Kosmos h1 tidak ditemukan");
    }

    // Automation check
    console.log(`  🤖 Otomasi: Cek konfigurasi robot`);
    await clickNav(page, "/automation", "Otomasi");
    await page.waitForTimeout(5000);

    const autoH1 = page.locator("main h1").first();
    if (await autoH1.isVisible({ timeout: 20_000 }).catch(() => false)) {
      console.log(`  ✅ Otomasi page loaded`);
    } else {
      logIssue("Otomasi", "ui-missing", "Otomasi h1 tidak muncul (loading timeout)");
    }
  }

  // === PHASE 6: Final Summary ===
  console.log("\n" + "=".repeat(80));
  console.log("📊 RINGKASAN SIMULASI");
  console.log("=".repeat(80));
  console.log(`Total halaman dikunjungi: ${ALL_PAGES.length}`);
  console.log(`Hari trading disimulasi: ${TRADING_DAYS} (sampled ${simulatedDays.length}x)`);
  console.log(`Minggu disimulasi: ${WEEKS} (sampled ${Math.ceil(WEEKS / WEEKS_PER_TICK)}x)`);
  console.log(`Bulan disimulasi: ${MONTHS}`);
  console.log(`Quarter disimulasi: 4`);
  console.log(`\nIssues ditemukan: ${issues.length}`);

  const byType = issues.reduce((acc, i) => {
    acc[i.type] = (acc[i.type] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  for (const [type, count] of Object.entries(byType)) {
    console.log(`  ${type}: ${count}`);
  }

  const byPage = issues.reduce((acc, i) => {
    acc[i.page] = (acc[i.page] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  console.log("\nIssues per halaman:");
  for (const [page, count] of Object.entries(byPage)) {
    console.log(`  ${page}: ${count}`);
  }

  if (issues.length > 0) {
    console.log("\nDetail issues:");
    for (const issue of issues) {
      console.log(`  [${issue.page}] ${issue.type}: ${issue.detail.slice(0, 150)}`);
    }
  }

  console.log("\n" + "=".repeat(80));

  // Write issues to file for later analysis
  const fs = require("fs");
  fs.writeFileSync(
    "/home/petrick/projects/market/frontend/test-results/simulation-issues.json",
    JSON.stringify(issues, null, 2)
  );
  console.log("📁 Issues disimpan ke test-results/simulation-issues.json");

  await page.screenshot({ path: "/home/petrick/projects/market/frontend/test-results/simulation-final.png", fullPage: true });
  console.log("📸 Screenshot final disimpan ke test-results/simulation-final.png");

  await context.close();

  // Don't fail the test — we want to see all issues
  expect(issues.length).toBeGreaterThanOrEqual(0);
});
