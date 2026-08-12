"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Orbit,
  Satellite,
  Sparkles,
  TrendingDown,
  TrendingUp,
  Activity,
  Globe2,
} from "lucide-react";

// ── Tipe data dari /api/cosmos ────────────────────────────────────────────────

interface Body {
  name: string;
  kind: string;
  lon_deg: number;
  zodiac: string;
  distance_au: number;
  orbit_ring: number;
  retrograde?: boolean;
  phase?: number;
  phase_name?: string;
  illumination_pct?: number;
  age_days?: number;
}

interface ActiveCycle {
  cycle_type: string;
  title: string;
  start_at: string;
  end_at: string;
  potential_impact: string;
  expected_reversal: string;
  description: string;
}

interface AstronacciResponse {
  as_of: string;
  bodies: Body[];
  zodiac_signs: string[];
  active_cycles: ActiveCycle[];
  signal: {
    active_cycles: string[];
    time_signal: number;
    volatility_signal: number;
    confidence: number;
    cycle_count: number;
  };
}

interface LatestObs {
  metric: string;
  value: number;
  date: string | null;
  source: string;
}

interface SatelliteItem {
  location_name: string;
  lat: number;
  lon: number;
  sector: string | null;
  ticker: string | null;
  source: string;
  metrics: string[];
  latest: LatestObs[];
}

interface SatellitesResponse {
  as_of: string;
  count: number;
  satellites: SatelliteItem[];
  metric_legend: { code: string; label: string }[];
}

interface ExchangeIndex {
  ticker: string;
  name: string;
  close: number;
  open: number;
  high: number;
  low: number;
  change_pct: number | null;
  timestamp: string | null;
}

interface Exchange {
  mic: string;
  city: string;
  lat: number;
  lon: number;
  country_code: string;
  timezone: string;
  currency: string;
  trading_hours: string;
  index: ExchangeIndex | null;
  market_status: {
    is_open: boolean;
    local_time: string | null;
    reason: string;
  };
}

interface ExchangesResponse {
  as_of: string;
  open_count: number;
  total_count: number;
  exchanges: Exchange[];
}

// ── Konstanta visual ──────────────────────────────────────────────────────────

const PLANET_COLORS: Record<string, string> = {
  SUN: "#FFD23F",
  MOON: "#E8E8E8",
  MERCURY: "#A9A9A9",
  VENUS: "#E8B873",
  EARTH: "#4A90D9",
  MARS: "#E27B58",
  JUPITER: "#D8A47F",
  SATURN: "#E3C28B",
  URANUS: "#9DD9D2",
  NEPTUNE: "#5B7FFF",
  PLUTO: "#B8A088",
};

const PLANET_RADIUS: Record<string, number> = {
  SUN: 10,
  MOON: 3,
  MERCURY: 2.5,
  VENUS: 3,
  EARTH: 3.5,
  MARS: 2.5,
  JUPITER: 5,
  SATURN: 4,
  URANUS: 3.5,
  NEPTUNE: 3.5,
  PLUTO: 2,
};

const ORBIT_SPEED: Record<number, number> = {
  1: 0.35, 2: 0.22, 3: 0.16, 4: 0.12, 5: 0.07, 6: 0.05, 7: 0.035, 8: 0.025, 9: 0.018,
};

const IMPACT_COLOR: Record<string, string> = {
  CRITICAL: "#FF3B3B",
  HIGH: "#FF8C42",
  MEDIUM: "#FFD23F",
  LOW: "#6CB4EE",
};

const REVERSAL_ICON: Record<string, string> = {
  BEARISH_REVERSAL: "▼",
  BULLISH_REVERSAL: "▲",
  VOLATILITY: "◆",
  NEUTRAL: "●",
};

type LandPolygon = number[][];

// ── Komponen utama ────────────────────────────────────────────────────────────

export default function CosmosPage() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const starsRef = useRef<{ x: number; y: number; r: number; tw: number }[]>([]);
  const animRef = useRef<number>(0);
  const startTimeRef = useRef<number>(0);
  const landRef = useRef<LandPolygon[]>([]);
  const dataRef = useRef<{
    astro: AstronacciResponse | null;
    sats: SatelliteItem[];
    exchanges: Exchange[];
  }>({ astro: null, sats: [], exchanges: [] });

  const [astro, setAstro] = useState<AstronacciResponse | null>(null);
  const [sats, setSats] = useState<SatelliteItem[]>([]);
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<string>("");
  const [paused, setPaused] = useState(false);

  // ── Fetch data ──
  const fetchData = useCallback(async () => {
    try {
      const [aRes, sRes, eRes] = await Promise.all([
        fetch("/api/cosmos/astronacci?days=7"),
        fetch("/api/cosmos/satellites?limit=80"),
        fetch("/api/cosmos/exchanges"),
      ]);
      if (!aRes.ok || !sRes.ok || !eRes.ok)
        throw new Error(`HTTP ${aRes.status}/${sRes.status}/${eRes.status}`);
      const a: AstronacciResponse = await aRes.json();
      const s: SatellitesResponse = await sRes.json();
      const e: ExchangesResponse = await eRes.json();
      setAstro(a);
      setSats(s.satellites);
      setExchanges(e.exchanges);
      dataRef.current = { astro: a, sats: s.satellites, exchanges: e.exchanges };
      setLastUpdate(new Date().toLocaleTimeString("id-ID", { hour12: false }));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal memuat data kosmos");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const id = setInterval(fetchData, 60_000);
    return () => clearInterval(id);
  }, [fetchData]);

  // ── Fetch land polygon data sekali ──
  useEffect(() => {
    let cancelled = false;
    fetch("/world-land-simple.json")
      .then((r) => r.json())
      .then((data) => {
        if (!cancelled && data.polygons) {
          landRef.current = data.polygons as LandPolygon[];
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  // ── Generate starfield sekali ──
  useEffect(() => {
    const stars: { x: number; y: number; r: number; tw: number }[] = [];
    for (let i = 0; i < 200; i++) {
      stars.push({
        x: Math.random(),
        y: Math.random(),
        r: Math.random() * 1.2 + 0.2,
        tw: Math.random() * Math.PI * 2,
      });
    }
    starsRef.current = stars;
  }, []);

  // ── Orthographic projection helper ──
  const project = (
    lonDeg: number,
    latDeg: number,
    rotation: number,
    cx: number,
    cy: number,
    r: number,
  ) => {
    const lonRad = (lonDeg * Math.PI) / 180 + rotation;
    const latRad = (latDeg * Math.PI) / 180;
    const x3d = Math.cos(latRad) * Math.cos(lonRad);
    const y3d = Math.cos(latRad) * Math.sin(lonRad);
    const z3d = Math.sin(latRad);
    return {
      x: cx + y3d * r,
      y: cy - z3d * r,
      visible: x3d > -0.02,
      depth: x3d,
    };
  };

  // ── Main canvas: EARTH GLOBE (full screen) ──
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      canvas.width = window.innerWidth * dpr;
      canvas.height = window.innerHeight * dpr;
      canvas.style.width = `${window.innerWidth}px`;
      canvas.style.height = `${window.innerHeight}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    window.addEventListener("resize", resize);

    if (!startTimeRef.current) startTimeRef.current = performance.now();

    const draw = (now: number) => {
      const t = paused ? 0 : (now - startTimeRef.current) / 1000;
      const W = window.innerWidth;
      const H = window.innerHeight;
      const cx = W / 2;
      const cy = H / 2;
      const earthR = Math.min(W, H) * 0.38; // globe besar di tengah
      const rotation = t * 0.08;

      // Background
      ctx.fillStyle = "#05060f";
      ctx.fillRect(0, 0, W, H);

      // Stars (background)
      const stars = starsRef.current;
      for (const s of stars) {
        const sx = s.x * W;
        const sy = s.y * H;
        const alpha = 0.3 + 0.5 * Math.abs(Math.sin(s.tw + t * 0.3));
        ctx.fillStyle = `rgba(255,255,255,${alpha * 0.6})`;
        ctx.beginPath();
        ctx.arc(sx, sy, s.r, 0, Math.PI * 2);
        ctx.fill();
      }

      // Atmosphere glow (outer)
      const atmGrad = ctx.createRadialGradient(cx, cy, earthR, cx, cy, earthR + 30);
      atmGrad.addColorStop(0, "rgba(100,180,255,0.25)");
      atmGrad.addColorStop(1, "rgba(100,180,255,0)");
      ctx.fillStyle = atmGrad;
      ctx.beginPath();
      ctx.arc(cx, cy, earthR + 30, 0, Math.PI * 2);
      ctx.fill();

      // Ocean base
      const oceanGrad = ctx.createRadialGradient(
        cx - earthR * 0.3,
        cy - earthR * 0.3,
        earthR * 0.1,
        cx,
        cy,
        earthR,
      );
      oceanGrad.addColorStop(0, "#3a7bd5");
      oceanGrad.addColorStop(0.6, "#1a4a8a");
      oceanGrad.addColorStop(1, "#0a2a5a");
      ctx.fillStyle = oceanGrad;
      ctx.beginPath();
      ctx.arc(cx, cy, earthR, 0, Math.PI * 2);
      ctx.fill();

      // ── Continents ──
      ctx.save();
      ctx.beginPath();
      ctx.arc(cx, cy, earthR, 0, Math.PI * 2);
      ctx.clip();

      const landPolygons = landRef.current;
      for (const polygon of landPolygons) {
        if (polygon.length < 3) continue;
        const projected = polygon.map((pt) =>
          project(pt[0], pt[1], rotation, cx, cy, earthR),
        );
        const anyVisible = projected.some((p) => p.visible);
        if (!anyVisible) continue;

        ctx.beginPath();
        let started = false;
        for (const p of projected) {
          if (!p.visible) {
            if (started) {
              ctx.fill();
              ctx.beginPath();
              started = false;
            }
            continue;
          }
          if (!started) {
            ctx.moveTo(p.x, p.y);
            started = true;
          } else {
            ctx.lineTo(p.x, p.y);
          }
        }
        if (started) {
          const visiblePts = projected.filter((p) => p.visible);
          const avgDepth =
            visiblePts.reduce((s, p) => s + p.depth, 0) / visiblePts.length;
          const shade = 0.5 + avgDepth * 0.4;
          ctx.fillStyle = `rgba(${Math.round(55 * shade)}, ${Math.round(130 * shade)}, ${Math.round(
            68 * shade,
          )}, 0.9)`;
          ctx.fill();
          ctx.strokeStyle = `rgba(35, 80, 45, ${0.3 * shade})`;
          ctx.lineWidth = 0.5;
          ctx.stroke();
        }
      }

      // Graticule
      ctx.strokeStyle = "rgba(100,140,200,0.06)";
      ctx.lineWidth = 0.5;
      for (let lon = -180; lon < 180; lon += 30) {
        ctx.beginPath();
        let first = true;
        for (let lat = -90; lat <= 90; lat += 5) {
          const p = project(lon, lat, rotation, cx, cy, earthR);
          if (p.visible) {
            if (first) { ctx.moveTo(p.x, p.y); first = false; }
            else ctx.lineTo(p.x, p.y);
          } else first = true;
        }
        ctx.stroke();
      }
      for (let lat = -60; lat <= 60; lat += 30) {
        ctx.beginPath();
        let first = true;
        for (let lon = -180; lon <= 180; lon += 5) {
          const p = project(lon, lat, rotation, cx, cy, earthR);
          if (p.visible) {
            if (first) { ctx.moveTo(p.x, p.y); first = false; }
            else ctx.lineTo(p.x, p.y);
          } else first = true;
        }
        ctx.stroke();
      }
      // Equator
      ctx.strokeStyle = "rgba(255,200,100,0.1)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      let first = true;
      for (let lon = -180; lon <= 180; lon += 5) {
        const p = project(lon, 0, rotation, cx, cy, earthR);
        if (p.visible) {
          if (first) { ctx.moveTo(p.x, p.y); first = false; }
          else ctx.lineTo(p.x, p.y);
        } else first = true;
      }
      ctx.stroke();

      // ── Exchange markers ──
      const exchanges = dataRef.current.exchanges;
      for (const ex of exchanges) {
        const p = project(ex.lon, ex.lat, rotation, cx, cy, earthR);
        if (!p.visible) continue;

        const isOpen = ex.market_status.is_open;
        const markerColor = isOpen ? "#22c55e" : "#64748b";
        const glowColor = isOpen ? "rgba(34,197,94,0.4)" : "rgba(100,116,139,0.2)";

        // Pulsing glow for open markets
        if (isOpen) {
          const pulse = 0.5 + 0.5 * Math.sin(t * 2.5 + ex.lon * 0.05);
          const glowR = 8 + pulse * 4;
          const glow = ctx.createRadialGradient(p.x, p.y, 2, p.x, p.y, glowR);
          glow.addColorStop(0, `rgba(34,197,94,${0.5 + pulse * 0.3})`);
          glow.addColorStop(1, "rgba(34,197,94,0)");
          ctx.fillStyle = glow;
          ctx.beginPath();
          ctx.arc(p.x, p.y, glowR, 0, Math.PI * 2);
          ctx.fill();
        }

        // Marker dot
        ctx.fillStyle = markerColor;
        ctx.beginPath();
        ctx.arc(p.x, p.y, isOpen ? 4 : 3, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = "rgba(255,255,255,0.6)";
        ctx.lineWidth = 0.8;
        ctx.stroke();

        // Label: city name + index value
        const idx = ex.index;
        const changeStr = idx?.change_pct != null
          ? `${idx.change_pct > 0 ? "+" : ""}${idx.change_pct}%`
          : "";
        const changeColor = idx?.change_pct != null
          ? idx.change_pct > 0
            ? "#4ade80"
            : idx.change_pct < 0
              ? "#f87171"
              : "#94a3b8"
          : "#94a3b8";

        // Label background
        const label1 = ex.city;
        const label2 = idx ? `${idx.close.toLocaleString("en-US", { maximumFractionDigits: 0 })} ${changeStr}` : "—";
        ctx.font = "11px monospace";
        const labelW = Math.max(ctx.measureText(label1).width, ctx.measureText(label2).width) + 8;
        const labelH = 28;
        const labelX = p.x + 8;
        const labelY = p.y - labelH / 2;

        ctx.fillStyle = "rgba(0,0,0,0.6)";
        ctx.fillRect(labelX, labelY, labelW, labelH);
        ctx.strokeStyle = `${markerColor}66`;
        ctx.lineWidth = 0.5;
        ctx.strokeRect(labelX, labelY, labelW, labelH);

        ctx.textAlign = "left";
        ctx.textBaseline = "top";
        ctx.fillStyle = "rgba(255,255,255,0.9)";
        ctx.font = "bold 10px monospace";
        ctx.fillText(label1, labelX + 4, labelY + 3);
        ctx.fillStyle = changeColor;
        ctx.font = "9px monospace";
        ctx.fillText(label2, labelX + 4, labelY + 15);
      }

      // ── Satellite markers (small dots) ──
      const sats = dataRef.current.sats;
      const maxSats = Math.min(sats.length, 60);
      for (let i = 0; i < maxSats; i++) {
        const s = sats[i];
        const p = project(s.lon, s.lat, rotation, cx, cy, earthR);
        if (!p.visible) continue;
        const hasObs = s.latest.length > 0;
        ctx.fillStyle = hasObs ? "rgba(120,220,255,0.7)" : "rgba(120,180,220,0.3)";
        ctx.beginPath();
        ctx.arc(p.x, p.y, hasObs ? 1.5 : 1, 0, Math.PI * 2);
        ctx.fill();
      }

      ctx.restore(); // end clip

      // Day/night terminator — sun from right side
      ctx.save();
      ctx.beginPath();
      ctx.arc(cx, cy, earthR, 0, Math.PI * 2);
      ctx.clip();
      const nightGrad = ctx.createLinearGradient(cx - earthR, cy, cx + earthR * 0.35, cy);
      nightGrad.addColorStop(0, "rgba(0,0,20,0.55)");
      nightGrad.addColorStop(0.5, "rgba(0,0,20,0.2)");
      nightGrad.addColorStop(1, "rgba(0,0,20,0)");
      ctx.fillStyle = nightGrad;
      ctx.fillRect(cx - earthR, cy - earthR, earthR * 2, earthR * 2);

      // City lights on night side (small yellow dots at exchange locations)
      for (const ex of exchanges) {
        const p = project(ex.lon, ex.lat, rotation, cx, cy, earthR);
        if (!p.visible) continue;
        // Check if on night side (x < cx + earthR*0.1)
        if (p.x > cx + earthR * 0.1) continue;
        const flicker = 0.6 + 0.4 * Math.sin(t * 3 + ex.lon * 0.1);
        ctx.fillStyle = `rgba(255,220,100,${flicker * 0.5})`;
        ctx.beginPath();
        ctx.arc(p.x, p.y, 1.5, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.restore();

      // Rim light
      ctx.strokeStyle = "rgba(120,200,255,0.35)";
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.arc(cx, cy, earthR, 0, Math.PI * 2);
      ctx.stroke();

      // ── Moon orbiting Earth ──
      const moon = dataRef.current.astro?.bodies.find((b) => b.name === "MOON");
      if (moon) {
        const moonOrbitR = earthR + 40;
        const moonAng = (moon.lon_deg * Math.PI) / 180 + t * 0.3;
        const mx = cx + Math.cos(moonAng) * moonOrbitR;
        const my = cy + Math.sin(moonAng) * moonOrbitR * 0.35;
        ctx.strokeStyle = "rgba(232,232,232,0.1)";
        ctx.lineWidth = 0.5;
        ctx.beginPath();
        ctx.ellipse(cx, cy, moonOrbitR, moonOrbitR * 0.35, 0, 0, Math.PI * 2);
        ctx.stroke();
        // Moon glow
        const moonGlow = ctx.createRadialGradient(mx, my, 1, mx, my, 12);
        moonGlow.addColorStop(0, "rgba(232,232,232,0.4)");
        moonGlow.addColorStop(1, "rgba(232,232,232,0)");
        ctx.fillStyle = moonGlow;
        ctx.beginPath();
        ctx.arc(mx, my, 12, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = "#E8E8E8";
        ctx.beginPath();
        ctx.arc(mx, my, 5, 0, Math.PI * 2);
        ctx.fill();
        if (moon.phase !== undefined) {
          const illum = moon.phase <= 0.5 ? moon.phase * 2 : (1 - moon.phase) * 2;
          if (illum < 0.95) {
            ctx.fillStyle = `rgba(10,10,30,${1 - illum})`;
            ctx.beginPath();
            ctx.arc(mx + (1 - illum) * 2.5, my, 5, 0, Math.PI * 2);
            ctx.fill();
          }
        }
      }

      animRef.current = requestAnimationFrame(draw);
    };

    animRef.current = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(animRef.current);
      window.removeEventListener("resize", resize);
    };
  }, [paused, project]);

  // ── Derived display values ──
  const moonBody = useMemo(() => astro?.bodies.find((b) => b.name === "MOON"), [astro]);
  const signal = astro?.signal;
  const openExchanges = useMemo(
    () => exchanges.filter((e) => e.market_status.is_open),
    [exchanges],
  );

  const signalTone =
    signal && signal.time_signal < -0.05
      ? "bearish"
      : signal && signal.time_signal > 0.05
        ? "bullish"
        : "neutral";

  return (
    <div className="fixed inset-0 z-50 bg-[#05060f] overflow-hidden">
      <canvas ref={canvasRef} className="absolute inset-0" />

      {/* ── Tombol kembali ── */}
      <Link
        href="/"
        className="absolute top-4 left-4 z-10 flex items-center gap-2 px-3 py-2 rounded-md bg-white/5 hover:bg-white/10 border border-white/10 text-white/80 text-sm backdrop-blur-sm transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Dashboard
      </Link>

      {/* ── Judul ── */}
      <div className="absolute top-4 left-1/2 -translate-x-1/2 z-10 text-center pointer-events-none">
        <h1 className="text-white text-lg font-semibold tracking-wide flex items-center justify-center gap-2">
          <Globe2 className="w-5 h-5 text-sky-300" />
          Bursa Global & Alam Semesta
        </h1>
        <p className="text-white/40 text-xs mt-0.5">
          {lastUpdate ? `Update ${lastUpdate} WIB` : "memuat…"} · {openExchanges.length}/{exchanges.length} bursa buka
        </p>
      </div>

      {/* ── Tombol pause ── */}
      <button
        onClick={() => setPaused((p) => !p)}
        className="absolute top-4 right-[15rem] z-10 px-3 py-2 rounded-md bg-white/5 hover:bg-white/10 border border-white/10 text-white/80 text-xs backdrop-blur-sm transition-colors"
      >
        {paused ? "▶ Lanjut" : "⏸ Jeda"}
      </button>

      {/* ── Mini Cosmos panel (kanan atas) ── */}
      <div className="absolute top-4 right-4 z-10 w-56 rounded-lg bg-black/40 border border-white/10 backdrop-blur-md p-3">
        <div className="flex items-center gap-2 mb-2">
          <Orbit className="w-4 h-4 text-amber-300" />
          <h2 className="text-white/90 text-sm font-semibold">Tata Surya</h2>
        </div>
        <MiniCosmos astro={astro} paused={paused} />
        <div className="mt-2 text-[10px] text-white/40">
          {astro?.active_cycles.length ?? 0} siklus Astronacci aktif
        </div>
      </div>

      {/* ── Panel kiri: Siklus Astronacci aktif ── */}
      <div className="absolute top-20 left-4 z-10 w-72 max-h-[calc(100vh-7rem)] overflow-y-auto rounded-lg bg-black/40 border border-white/10 backdrop-blur-md p-3">
        <div className="flex items-center gap-2 mb-2">
          <Sparkles className="w-4 h-4 text-amber-300" />
          <h2 className="text-white/90 text-sm font-semibold">Siklus Astronacci Aktif</h2>
        </div>
        {loading && <p className="text-white/40 text-xs">memuat…</p>}
        {error && <p className="text-red-400 text-xs">{error}</p>}
        {!loading && !error && (astro?.active_cycles.length ?? 0) === 0 && (
          <p className="text-white/40 text-xs">Tidak ada siklus aktif 7 hari ke depan.</p>
        )}
        <div className="space-y-2">
          {astro?.active_cycles.map((c) => (
            <div
              key={c.cycle_type + c.start_at}
              className="rounded-md bg-white/5 border border-white/5 p-2"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-white/90 text-xs font-medium">{c.title}</span>
                <span
                  className="text-[10px] px-1.5 py-0.5 rounded font-mono"
                  style={{
                    color: IMPACT_COLOR[c.potential_impact] ?? "#888",
                    background: `${IMPACT_COLOR[c.potential_impact] ?? "#888"}22`,
                  }}
                >
                  {c.potential_impact}
                </span>
              </div>
              <div className="flex items-center gap-1.5 mt-1 text-[10px] text-white/50">
                <span style={{ color: IMPACT_COLOR[c.potential_impact] ?? "#888" }}>
                  {REVERSAL_ICON[c.expected_reversal] ?? "●"}
                </span>
                <span>{c.expected_reversal.replace(/_/g, " ")}</span>
                <span className="ml-auto">
                  {new Date(c.start_at).toLocaleDateString("id-ID", { day: "2-digit", month: "short" })}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Panel kanan (di bawah mini cosmos): Sinyal ── */}
      <div className="absolute top-[16rem] right-4 z-10 w-56 rounded-lg bg-black/40 border border-white/10 backdrop-blur-md p-3">
        <div className="flex items-center gap-2 mb-2">
          <Activity className="w-4 h-4 text-sky-300" />
          <h2 className="text-white/90 text-sm font-semibold">Sinyal Astronacci</h2>
        </div>
        {signal ? (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-white/50 text-xs">Time Signal</span>
              <span
                className={`text-sm font-mono font-bold flex items-center gap-1 ${
                  signalTone === "bearish"
                    ? "text-red-400"
                    : signalTone === "bullish"
                      ? "text-emerald-400"
                      : "text-white/70"
                }`}
              >
                {signalTone === "bearish" ? (
                  <TrendingDown className="w-3.5 h-3.5" />
                ) : signalTone === "bullish" ? (
                  <TrendingUp className="w-3.5 h-3.5" />
                ) : null}
                {signal.time_signal.toFixed(3)}
              </span>
            </div>
            <Bar label="Volatilitas" value={signal.volatility_signal} color="#FFD23F" />
            <Bar label="Confidence" value={signal.confidence} color="#6CB4EE" />
          </div>
        ) : (
          <p className="text-white/40 text-xs">memuat…</p>
        )}
      </div>

      {/* ── Panel kanan (di bawah sinyal): Daftar Bursa ── */}
      <div className="absolute top-[26rem] right-4 z-10 w-56 max-h-[calc(100vh-29rem)] overflow-y-auto rounded-lg bg-black/40 border border-white/10 backdrop-blur-md p-3">
        <div className="flex items-center gap-2 mb-2">
          <Globe2 className="w-4 h-4 text-emerald-400" />
          <h2 className="text-white/90 text-sm font-semibold">Bursa Global</h2>
        </div>
        <div className="space-y-1.5">
          {exchanges.map((ex) => {
            const idx = ex.index;
            const isOpen = ex.market_status.is_open;
            const changeColor =
              idx?.change_pct != null
                ? idx.change_pct > 0
                  ? "text-emerald-400"
                  : idx.change_pct < 0
                    ? "text-red-400"
                    : "text-white/50"
                : "text-white/50";
            return (
              <div
                key={ex.mic}
                className="flex items-center justify-between gap-2 rounded bg-white/5 px-2 py-1.5"
              >
                <div className="flex items-center gap-1.5 min-w-0">
                  <span
                    className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                      isOpen ? "bg-emerald-400 animate-pulse" : "bg-slate-500"
                    }`}
                  />
                  <div className="min-w-0">
                    <div className="text-white/80 text-[11px] font-medium truncate">
                      {ex.city}
                    </div>
                    <div className="text-white/30 text-[9px] truncate">
                      {ex.mic} · {ex.currency}
                    </div>
                  </div>
                </div>
                <div className="text-right shrink-0">
                  <div className="text-white/70 text-[10px] font-mono">
                    {idx ? idx.close.toLocaleString("en-US", { maximumFractionDigits: 0 }) : "—"}
                  </div>
                  <div className={`text-[9px] font-mono ${changeColor}`}>
                    {idx?.change_pct != null
                      ? `${idx.change_pct > 0 ? "+" : ""}${idx.change_pct}%`
                      : ""}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Panel kiri bawah: Bulan + Satelit ── */}
      <div className="absolute bottom-4 left-4 z-10 w-72 rounded-lg bg-black/40 border border-white/10 backdrop-blur-md p-3">
        {moonBody && (
          <>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-base">🌙</span>
              <h2 className="text-white/90 text-sm font-semibold">Fase Bulan</h2>
            </div>
            <div className="text-white/80 text-sm">{moonBody.phase_name}</div>
            <div className="text-white/50 text-xs">
              Iluminasi {moonBody.illumination_pct?.toFixed(1)}% · Usia {moonBody.age_days?.toFixed(1)} hari · {moonBody.zodiac}
            </div>
          </>
        )}
        <div className="mt-3 pt-2 border-t border-white/10">
          <div className="flex items-center gap-2 mb-1">
            <Satellite className="w-4 h-4 text-sky-300" />
            <h2 className="text-white/90 text-sm font-semibold">Satelit Observasi</h2>
          </div>
          <div className="text-white/60 text-xs">
            {sats.length} lokasi · {sats.filter((s) => s.latest.length > 0).length} dgn observasi
          </div>
        </div>
      </div>

      {/* ── Legenda ── */}
      <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-10 flex items-center gap-4 px-4 py-2 rounded-lg bg-black/40 border border-white/10 backdrop-blur-md text-[10px] text-white/60">
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-emerald-400 inline-block animate-pulse" /> Bursa buka
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-slate-500 inline-block" /> Bursa tutup
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-sky-400 inline-block" /> Satelit dgn observasi
        </span>
        <span className="flex items-center gap-1">
          <span className="text-amber-300">●</span> City lights (malam)
        </span>
      </div>
    </div>
  );
}

// ── Sub-komponen: progress bar ────────────────────────────────────────────────

function Bar({ label, value, color }: { label: string; value: number; color: string }) {
  const pct = Math.round((value ?? 0) * 100);
  return (
    <div>
      <div className="flex items-center justify-between text-[10px] text-white/50 mb-0.5">
        <span>{label}</span>
        <span className="font-mono">{pct}%</span>
      </div>
      <div className="h-1.5 rounded-full bg-white/10 overflow-hidden">
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
    </div>
  );
}

// ── MiniCosmos: tata surya ringkas di panel ───────────────────────────────────

function MiniCosmos({
  astro,
  paused,
}: {
  astro: AstronacciResponse | null;
  paused: boolean;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const animRef = useRef<number>(0);
  const startTimeRef = useRef<number>(0);
  const astroRef = useRef(astro);
  astroRef.current = astro;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const SIZE = 180;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = SIZE * dpr;
    canvas.height = SIZE * dpr;
    canvas.style.width = `${SIZE}px`;
    canvas.style.height = `${SIZE}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    if (!startTimeRef.current) startTimeRef.current = performance.now();

    const draw = (now: number) => {
      const t = paused ? 0 : (now - startTimeRef.current) / 1000;
      const cx = SIZE / 2;
      const cy = SIZE / 2;
      const baseR = 8;
      const ringStep = 7;

      ctx.clearRect(0, 0, SIZE, SIZE);

      // Orbit rings
      ctx.strokeStyle = "rgba(120,140,200,0.1)";
      ctx.lineWidth = 0.5;
      for (let r = 1; r <= 9; r++) {
        ctx.beginPath();
        ctx.arc(cx, cy, baseR + r * ringStep, 0, Math.PI * 2);
        ctx.stroke();
      }

      // Sun
      const sunGrad = ctx.createRadialGradient(cx, cy, 2, cx, cy, 18);
      sunGrad.addColorStop(0, "rgba(255,235,120,1)");
      sunGrad.addColorStop(0.4, "rgba(255,180,40,0.6)");
      sunGrad.addColorStop(1, "rgba(255,120,0,0)");
      ctx.fillStyle = sunGrad;
      ctx.beginPath();
      ctx.arc(cx, cy, 18, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = PLANET_COLORS.SUN;
      ctx.beginPath();
      ctx.arc(cx, cy, PLANET_RADIUS.SUN, 0, Math.PI * 2);
      ctx.fill();

      // Planets
      const data = astroRef.current;
      if (data) {
        for (const b of data.bodies) {
          if (b.name === "SUN") continue;
          const ring = b.orbit_ring;
          if (ring === 0) continue;
          const baseAngle = (b.lon_deg - 90) * (Math.PI / 180);
          const drift = t * (ORBIT_SPEED[ring] ?? 0.05);
          const angle = baseAngle + drift;
          const r = baseR + ring * ringStep;
          const px = cx + Math.cos(angle) * r;
          const py = cy + Math.sin(angle) * r;

          // Glow
          const pr = PLANET_RADIUS[b.name] ?? 2.5;
          const g = ctx.createRadialGradient(px, py, 0.5, px, py, pr * 2);
          g.addColorStop(0, `${PLANET_COLORS[b.name] ?? "#888"}aa`);
          g.addColorStop(1, `${PLANET_COLORS[b.name] ?? "#888"}00`);
          ctx.fillStyle = g;
          ctx.beginPath();
          ctx.arc(px, py, pr * 2, 0, Math.PI * 2);
          ctx.fill();
          // Body
          ctx.fillStyle = PLANET_COLORS[b.name] ?? "#888";
          ctx.beginPath();
          ctx.arc(px, py, pr, 0, Math.PI * 2);
          ctx.fill();
          // Retrograde marker
          if (b.retrograde) {
            ctx.strokeStyle = "#FF3B3B";
            ctx.lineWidth = 0.8;
            ctx.beginPath();
            ctx.arc(px, py, pr + 2, 0, Math.PI * 2);
            ctx.stroke();
          }
        }
      }

      animRef.current = requestAnimationFrame(draw);
    };

    animRef.current = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(animRef.current);
  }, [paused]);

  return <canvas ref={canvasRef} className="mx-auto" />;
}
