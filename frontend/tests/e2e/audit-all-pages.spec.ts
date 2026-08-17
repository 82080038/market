import { test, expect, Page, ConsoleMessage, Request, Response } from "@playwright/test";

interface PageResult {
  page: string;
  status: "pass" | "fail";
  consoleErrors: string[];
  consoleWarnings: string[];
  pageErrors: string[];
  networkErrors: string[];
  networkStatusMismatches: string[];
}

const results: PageResult[] = [];

const ALL_PAGES = [
  { href: "/", name: "Dashboard" },
  { href: "/signals", name: "Sinyal" },
  { href: "/stock", name: "Saham" },
  { href: "/portfolio", name: "Portofolio" },
  { href: "/backtest", name: "Backtest" },
  { href: "/simulation", name: "Simulasi" },
  { href: "/screener", name: "Screener" },
  { href: "/scan", name: "Pola & Prediksi" },
  { href: "/automation", name: "Otomasi" },
  { href: "/reports", name: "Laporan" },
  { href: "/data", name: "Data & Sumber" },
  { href: "/cosmos", name: "Kosmos" },
  { href: "/scheduler", name: "Scheduler" },
  { href: "/settings", name: "Pengaturan" },
];

test.describe("Audit Semua Halaman FE", () => {
  for (const p of ALL_PAGES) {
    test(`${p.name} (${p.href}) - audit lengkap`, async ({ page }) => {
      const consoleErrors: string[] = [];
      const consoleWarnings: string[] = [];
      const pageErrors: string[] = [];
      const networkErrors: string[] = [];
      const networkStatusMismatches: string[] = [];

      page.on("console", (msg: ConsoleMessage) => {
        const text = msg.text();
        if (msg.type() === "error") {
          // Ignore favicon/manifest/extension noise
          if (!text.includes("favicon") && !text.includes("manifest") &&
              !text.includes("Could not establish connection") &&
              !text.includes("Receiving end does not exist")) {
            consoleErrors.push(text);
          }
        }
        if (msg.type() === "warning") {
          if (!text.includes("favicon") && !text.includes("manifest") &&
              !text.includes("Could not establish connection")) {
            consoleWarnings.push(text);
          }
        }
      });

      page.on("pageerror", (err: Error) => {
        pageErrors.push(err.message);
      });

      page.on("response", (response: Response) => {
        const url = response.url();
        const status = response.status();
        // Only track API calls
        if (url.includes("/api/")) {
          if (status >= 500) {
            networkErrors.push(`${status} ${url}`);
          } else if (status === 404) {
            networkErrors.push(`${status} ${url}`);
          } else if (status === 405) {
            networkErrors.push(`${status} ${url}`);
          }
        }
      });

      await page.goto(p.href, { waitUntil: "domcontentloaded", timeout: 30_000 });
      // Wait for API calls to settle
      await page.waitForTimeout(5000);

      const result: PageResult = {
        page: p.name,
        status: consoleErrors.length > 0 || pageErrors.length > 0 || networkErrors.length > 0 ? "fail" : "pass",
        consoleErrors,
        consoleWarnings,
        pageErrors,
        networkErrors,
        networkStatusMismatches,
      };
      results.push(result);

      // Log results
      if (consoleErrors.length > 0) {
        console.log(`\n[${p.name}] CONSOLE ERRORS:\n${consoleErrors.map(e => `  - ${e}`).join("\n")}`);
      }
      if (pageErrors.length > 0) {
        console.log(`\n[${p.name}] PAGE ERRORS:\n${pageErrors.map(e => `  - ${e}`).join("\n")}`);
      }
      if (networkErrors.length > 0) {
        console.log(`\n[${p.name}] NETWORK ERRORS:\n${networkErrors.map(e => `  - ${e}`).join("\n")}`);
      }
      if (consoleWarnings.length > 0) {
        console.log(`\n[${p.name}] WARNINGS:\n${consoleWarnings.map(e => `  - ${e}`).join("\n")}`);
      }

      // Don't fail the test — we want to collect all results
      expect(true).toBe(true);
    });
  }

  test.afterAll(() => {
    console.log("\n\n========== AUDIT SUMMARY ==========");
    const failed = results.filter(r => r.status === "fail");
    const passed = results.filter(r => r.status === "pass");
    console.log(`Total: ${results.length} | PASS: ${passed.length} | FAIL: ${failed.length}`);
    if (failed.length > 0) {
      console.log("\nFailed pages:");
      for (const f of failed) {
        console.log(`  - ${f.page}: ${f.consoleErrors.length} console errors, ${f.pageErrors.length} page errors, ${f.networkErrors.length} network errors`);
      }
    }
    console.log("===================================\n");
  });
});
