# UI/UX Design untuk Aplikasi Trading

> **Tujuan:** Dokumen ini adalah referensi definitif untuk desain UI/UX aplikasi trading — dari information architecture, dashboard design, data visualization, real-time updates, mobile-first approach, user journey, hingga accessibility — dengan fokus pada aplikasi trading pasar modal Indonesia (IDX).

---

## Daftar Isi

1. [Design Principles](#1-design-principles)
2. [Information Architecture](#2-information-architecture)
3. [Dashboard Design](#3-dashboard-design)
4. [Data Visualization](#4-data-visualization)
5. [Real-Time Updates](#5-real-time-updates)
6. [Mobile-First Design](#6-mobile-first-design)
7. [User Journey & Flows](#7-user-journey--flows)
8. [Design System](#8-design-system)
9. [Accessibility](#9-accessibility)
10. [Performance UX](#10-performance-ux)
11. [Implementasi untuk IDX](#11-implementasi-untuk-idx)
12. [Checklist Implementasi](#12-checklist-implementasi)

---

## 1. Design Principles

### 1.1 Core Principles untuk Trading UI

| Principle | Description | Rationale |
|-----------|-------------|-----------|
| **Clarity over cleverness** | Data harus langsung dipahami | Kesalahan membaca data = kesalahan keputusan |
| **Speed is feature** | UI harus responsif < 200ms | Trader butuh keputusan cepat |
| **Progressive disclosure** | Tampilkan detail on-demand | Hindari cognitive overload |
| **Consistent mental model** | Pola UI konsisten di seluruh app | Kurangi learning curve |
| **Error prevention** | Konfirmasi untuk aksi irreversibel | Cegah salah klik BUY/SELL |
| **Data density balanced** | Padat tapi tidak berantakan | Trader butuh banyak info, tapi tetap readable |
| **Dark mode first** | Trading = jam depan layar | Kurangi eye strain |

### 1.2 Trading-Specific UX Rules

```
1. NEVER use same button color for BUY and SELL
2. ALWAYS show confirmation dialog for orders
3. ALWAYS display current price before order submission
4. NEVER auto-submit orders (require explicit click)
5. ALWAYS show position PnL in real-time
6. ALWAYS display market status (open/closed/auto-reject)
7. NEVER hide fees — show total cost before confirmation
8. ALWAYS allow quick exit (close position) in 1-2 clicks
```

---

## 2. Information Architecture

### 2.1 Navigation Structure

```
┌─────────────────────────────────────────────┐
│                TOP BAR                       │
│  Logo │ Market Status │ Search │ Profile     │
├──────────┬──────────────────────────────────┤
│ SIDEBAR  │           MAIN CONTENT            │
│          │                                   │
│ Dashboard│  ┌──────────────────────────┐    │
│ Watchlist│  │                          │    │
│ Portfolio│  │     Page Content         │    │
│ Orders   │  │                          │    │
│ Backtest │  │                          │    │
│ Analysis │  │                          │    │
│ Settings │  └──────────────────────────┘    │
│          │                                   │
└──────────┴──────────────────────────────────┘
```

### 2.2 Page Structure

| Page | Purpose | Key Components |
|------|---------|----------------|
| **Dashboard** | Overview | Portfolio summary, watchlist, market status, top movers |
| **Stock Detail** | Deep dive | Chart, indicators, scores, recommendation, fundamental |
| **Portfolio** | Position management | Open positions, PnL, allocation, history |
| **Orders** | Trade management | Active orders, order history, trade log |
| **Backtest** | Strategy testing | Configuration, results, equity curve |
| **Analysis** | Screeners & scores | Screener, factor analysis, heatmap |
| **Settings** | Configuration | Risk params, API key, notifications |

### 2.3 Component Hierarchy

```
App
├── Layout
│   ├── TopBar (market status, search, profile)
│   ├── Sidebar (navigation)
│   └── ContentArea
│       ├── Dashboard
│       │   ├── PortfolioSummary
│       │   ├── WatchlistWidget
│       │   ├── MarketStatusWidget
│       │   ├── TopMoversWidget
│       │   └── NewsWidget
│       ├── StockDetail
│       │   ├── PriceChart
│       │   ├── IndicatorPanel
│       │   ├── ScoreCard
│       │   ├── RecommendationCard
│       │   ├── FundamentalTable
│       │   └── NewsList
│       ├── Portfolio
│       │   ├── PositionTable
│       │   ├── AllocationChart
│       │   ├── PnLChart
│       │   └── TradeHistory
│       └── ...
```

---

## 3. Dashboard Design

### 3.1 Dashboard Layout

```
┌─────────────────────────────────────────────────────────────┐
│  DASHBOARD                                    [Market: OPEN] │
├──────────────────────┬──────────────────────────────────────┤
│  PORTFOLIO SUMMARY   │  WATCHLIST                            │
│  ┌────────┐         │  ┌────────────────────────────────┐  │
│  │ Rp 127M│         │  │ BBCA  8,025  ▲ +1.2%          │  │
│  │ +27%   │         │  │ TLKM  3,150  ▼ -0.8%          │  │
│  └────────┘         │  │ ASII  5,200  ▲ +0.5%          │  │
│                      │  │ UNVR  4,100  —  0.0%          │  │
│  NAV: Rp 127,000,000│  └────────────────────────────────┘  │
│  Cash: Rp 12,000,000│                                       │
│  Invested: Rp 115M  │  TOP MOVERS                           │
│                      │  ┌────────────┬───────────────┐     │
│  P&L TODAY           │  │ GAINERS    │ LOSERS        │     │
│  ┌──────────────┐   │  │ BRPT +9.8% │ BUMI -7.2%   │     │
│  │ +Rp 1.2M     │   │  │ ANTM +7.5% │ PTBA -5.1%   │     │
│  │ +0.95%       │   │  │ INCO +5.2% │ ADRO -3.8%   │     │
│  └──────────────┘   │  └────────────┴───────────────┘     │
│                      │                                       │
│  ALLOCATION          │  LATEST NEWS                          │
│  ┌────────────┐     │  ┌────────────────────────────────┐  │
│  │ BBCA 30%   │     │  │ "BI Pertahankan Rate 6%"       │  │
│  │ TLKM 20%   │     │  │ "BBCA Laba Bersih Naik 15%"    │  │
│  │ ASII 15%   │     │  │ "Foreign Net Buy Rp 500M"      │  │
│  │ Cash 10%   │     │  └────────────────────────────────┘  │
│  └────────────┘     │                                       │
└──────────────────────┴──────────────────────────────────────┘
```

### 3.2 Key Dashboard Components

```typescript
// Dashboard widget types
interface DashboardWidget {
  id: string;
  type: 'portfolio_summary' | 'watchlist' | 'top_movers' | 'news' | 'chart' | 'scores';
  title: string;
  position: { row: number; col: number; width: number; height: number };
  config: Record<string, any>;
}

// Portfolio summary widget
interface PortfolioSummary {
  nav: number;
  cash: number;
  invested: number;
  today_pnl: number;
  today_pnl_pct: number;
  total_return: number;
  total_return_pct: number;
  open_positions: number;
}

// Market status indicator
interface MarketStatus {
  status: 'open' | 'closed' | 'pre_open' | 'pre_close' | 'auto_reject';
  session: string;
  next_event: string;
  time_to_close: string;
}
```

---

## 4. Data Visualization

### 4.1 Chart Types untuk Trading

| Chart Type | Use Case | Library |
|------------|----------|---------|
| **Candlestick** | Price movement | Recharts, Lightweight Charts |
| **Line chart** | Equity curve, NAV | Recharts |
| **Area chart** | Portfolio value | Recharts |
| **Bar chart** | Volume, scores | Recharts |
| **Heatmap** | Sector performance, correlation | D3, Nivo |
| **Treemap** | Portfolio allocation | D3, Recharts |
| **Scatter plot** | Risk-return analysis | Recharts |
| **Gauge** | Fear & Greed, conviction | Custom SVG |

### 4.2 Candlestick Chart

```typescript
interface CandlestickData {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

// Color scheme
const CANDLE_COLORS = {
  bullish: '#22c55e',    // green
  bearish: '#ef4444',    // red
  volume_bullish: '#22c55e80',
  volume_bearish: '#ef444480',
};
```

### 4.3 Score Visualization

```
Score Card:
┌─────────────────────────────────┐
│  BBCA.JK          Rp 8,025     │
│  ┌───────────────────────────┐ │
│  │ Technical      65/100    │ │
│  │ ████████████████░░░░░░░░  │ │
│  │                           │ │
│  │ Fundamental    80/100    │ │
│  │ ████████████████████░░░░  │ │
│  │                           │ │
│  │ Macro          70/100    │ │
│  │ ██████████████████░░░░░░  │ │
│  │                           │ │
│  │ Global         55/100    │ │
│  │ ███████████████░░░░░░░░░  │ │
│  │                           │ │
│  │ Sentiment      60/100    │ │
│  │ ████████████████░░░░░░░░  │ │
│  └───────────────────────────┘ │
│  CONVICTION: 72.5              │
│  RECOMMENDATION: BUY           │
└─────────────────────────────────┘
```

### 4.4 Color Palette

```typescript
const TRADING_COLORS = {
  // Price movement
  bullish: '#22c55e',
  bearish: '#ef4444',
  neutral: '#6b7280',
  
  // Scores (0-100)
  score_high: '#22c55e',     // 70-100
  score_medium: '#eab308',   // 40-69
  score_low: '#ef4444',      // 0-39
  
  // Conviction
  conviction_very_high: '#16a34a',
  conviction_high: '#22c55e',
  conviction_medium: '#eab308',
  conviction_low: '#f97316',
  conviction_very_low: '#ef4444',
  
  // Actions
  buy: '#22c55e',
  sell: '#ef4444',
  hold: '#eab308',
  watchlist: '#3b82f6',
  
  // UI
  bg_dark: '#0f172a',
  bg_card: '#1e293b',
  bg_hover: '#334155',
  text_primary: '#f1f5f9',
  text_secondary: '#94a3b8',
  border: '#334155',
};
```

---

## 5. Real-Time Updates

### 5.1 WebSocket Integration

```typescript
class RealTimeManager {
  private ws: WebSocket | null = null;
  private subscribers: Map<string, Set<(data: any) => void>> = new Map();
  
  connect(channel: string, callback: (data: any) => void) {
    if (!this.subscribers.has(channel)) {
      this.subscribers.set(channel, new Set());
    }
    this.subscribers.get(channel)!.add(callback);
    
    if (!this.ws) {
      this.ws = new WebSocket(`ws://localhost:8000/ws/${channel}`);
      this.ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        const subs = this.subscribers.get(data.channel);
        subs?.forEach(cb => cb(data));
      };
    }
  }
  
  disconnect(channel: string, callback: (data: any) => void) {
    this.subscribers.get(channel)?.delete(callback);
  }
}
```

### 5.2 Update Patterns

| Data Type | Update Method | Frequency | UI Treatment |
|-----------|--------------|-----------|-------------|
| **Price tick** | WebSocket push | On change | Flash green/red briefly |
| **Portfolio PnL** | WebSocket push | On price change | Smooth number transition |
| **Order status** | WebSocket push | On event | Status badge update |
| **News** | WebSocket push | On new article | Slide-in notification |
| **Scores** | REST poll | On compute | Fade-in new values |
| **Chart data** | REST poll | On page load | Initial load + live append |

### 5.3 Price Flash Animation

```typescript
function usePriceFlash(price: number) {
  const [flash, setFlash] = useState<'up' | 'down' | null>(null);
  const prevPrice = useRef(price);
  
  useEffect(() => {
    if (price > prevPrice.current) {
      setFlash('up');
    } else if (price < prevPrice.current) {
      setFlash('down');
    }
    prevPrice.current = price;
    
    const timer = setTimeout(() => setFlash(null), 500);
    return () => clearTimeout(timer);
  }, [price]);
  
  return flash;
}

// CSS
// .price-up { animation: flash-green 0.5s; }
// .price-down { animation: flash-red 0.5s; }
// @keyframes flash-green { 0% { background: #22c55e40; } 100% { background: transparent; } }
// @keyframes flash-red { 0% { background: #ef444440; } 100% { background: transparent; } }
```

---

## 6. Mobile-First Design

### 6.1 Responsive Breakpoints

| Breakpoint | Width | Layout |
|------------|-------|--------|
| **Mobile** | < 640px | Single column, bottom nav |
| **Tablet** | 640-1024px | Two column, collapsible sidebar |
| **Desktop** | > 1024px | Multi-column, full sidebar |

### 6.2 Mobile Layout

```
┌─────────────────────────┐
│  TOP BAR (compact)      │
│  ☰  BBCA  Rp 8,025  👤  │
├─────────────────────────┤
│                         │
│   MAIN CONTENT          │
│   (single column)       │
│                         │
│   ┌─────────────────┐  │
│   │ Price Chart     │  │
│   └─────────────────┘  │
│   ┌─────────────────┐  │
│   │ Score Card      │  │
│   └─────────────────┘  │
│   ┌─────────────────┐  │
│   │ Recommendation  │  │
│   └─────────────────┘  │
│                         │
├─────────────────────────┤
│  BOTTOM NAV             │
│  📊  ⭐  📦  📋  ⚙️   │
│  Dash Watch Port Order  │
└─────────────────────────┘
```

### 6.3 Mobile-Specific Features

| Feature | Implementation |
|---------|---------------|
| **Swipe to navigate** | Swipe left/right between stocks |
| **Pull to refresh** | Refresh data on pull down |
| **Long press for context** | Long press stock → quick actions menu |
| **Haptic feedback** | Vibrate on order confirmation |
| **Push notifications** | Price alerts, signal notifications |
| **Offline mode** | Cache last data, show "offline" banner |

---

## 7. User Journey & Flows

### 7.1 Key User Flows

```
Flow 1: Stock Analysis → Decision
  Search → Stock Detail → View Chart → View Scores → View Recommendation → Action

Flow 2: Order Execution
  Stock Detail → Click BUY/SELL → Order Form → Review → Confirm → Execution

Flow 3: Portfolio Review
  Dashboard → Portfolio → View Positions → Check PnL → Adjust

Flow 4: Backtest
  Backtest Page → Configure Strategy → Run → View Results → Analyze

Flow 5: Alert Setup
  Stock Detail → Set Alert → Choose Condition → Save → Receive Notification
```

### 7.2 Order Entry Flow (Critical)

```
Step 1: Click BUY button
  ↓
Step 2: Order Form
  ┌─────────────────────────┐
  │  BUY BBCA.JK            │
  │                         │
  │  Current Price: 8,025   │
  │  Quantity: [1000] lot   │
  │  Order Type: [LIMIT]    │
  │  Price: [8,000]         │
  │                         │
  │  Est. Total: Rp 8,000K  │
  │  Est. Fee: Rp 12,000    │
  │  Est. Total: Rp 8,012K  │
  │                         │
  │  [CANCEL]  [REVIEW]     │
  └─────────────────────────┘
  ↓
Step 3: Confirmation Dialog
  ┌─────────────────────────┐
  │  CONFIRM ORDER          │
  │                         │
  │  BUY 1000 BBCA.JK       │
  │  @ Rp 8,000             │
  │  Total: Rp 8,012,000    │
  │                         │
  │  Are you sure?          │
  │                         │
  │  [NO]     [YES, BUY]    │
  └─────────────────────────┘
  ↓
Step 4: Order Submitted
  ┌─────────────────────────┐
  │  ✓ Order Submitted      │
  │  Order ID: #12345       │
  │  Status: PENDING        │
  └─────────────────────────┘
```

---

## 8. Design System

### 8.1 Typography

```css
/* Font stack */
font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;

/* Monospace for numbers */
font-family: 'JetBrains Mono', 'Fira Code', monospace;

/* Sizes */
text-xs:   12px   /* labels, timestamps */
text-sm:   14px   /* secondary text */
text-base: 16px   /* body text */
text-lg:   18px   /* section headers */
text-xl:   20px   /* page titles */
text-2xl:  24px   /* key metrics */
text-3xl:  30px   /* hero numbers */
```

### 8.2 Spacing System

```
4px   = 1 unit (minimal)
8px   = 2 units (compact)
12px  = 3 units (default)
16px  = 4 units (comfortable)
24px  = 6 units (section gap)
32px  = 8 units (page sections)
48px  = 12 units (major sections)
```

### 8.3 Component Library

| Component | Purpose | Variants |
|-----------|---------|----------|
| **Button** | Actions | primary, secondary, danger, ghost |
| **Input** | Form fields | text, number, select, date |
| **Table** | Data display | sortable, paginated, sticky header |
| **Card** | Container | default, outlined, elevated |
| **Badge** | Status | success, warning, error, info |
| **Modal** | Dialogs | confirm, form, info |
| **Tabs** | Navigation | horizontal, vertical |
| **Chart** | Visualization | candlestick, line, bar, area |
| **Gauge** | Single metric | conviction, fear/greed |
| **Progress bar** | Score display | 0-100 scale |

---

## 9. Accessibility

### 9.1 WCAG Compliance

| Guideline | Implementation |
|-----------|---------------|
| **Color contrast** | Minimum 4.5:1 for text, 3:1 for large text |
| **Keyboard navigation** | All actions accessible via keyboard |
| **Screen reader** | ARIA labels for all interactive elements |
| **Focus indicators** | Visible focus ring on all focusable elements |
| **Alt text** | All charts have text alternative |
| **Reduced motion** | Respect `prefers-reduced-motion` |

### 9.2 Color Blindness

```typescript
// Don't rely on color alone — use icons + color
const SIGNAL_ICONS = {
  buy: { icon: '▲', color: '#22c55e', label: 'BUY' },
  sell: { icon: '▼', color: '#ef4444', label: 'SELL' },
  hold: { icon: '■', color: '#eab308', label: 'HOLD' },
};
```

---

## 10. Performance UX

### 10.1 Loading States

| State | UI Treatment |
|-------|-------------|
| **Initial load** | Skeleton placeholders |
| **Data fetching** | Spinner or progress bar |
| **Chart loading** | Animated grid before data |
| **Table loading** | Row skeletons |
| **Background refresh** | Subtle indicator (no blocking) |

### 10.2 Optimistic Updates

```typescript
// Update UI immediately, reconcile with server
function placeOrder(order: Order) {
  // 1. Optimistic: show order as "pending" immediately
  addOrderToUI({ ...order, status: 'pending' });
  
  // 2. Send to server
  api.placeOrder(order)
    .then(result => {
      // 3. Reconcile: update with real status
      updateOrderInUI(result);
    })
    .catch(error => {
      // 4. Rollback on error
      removeOrderFromUI(order.id);
      showError(error.message);
    });
}
```

### 10.3 Virtual Scrolling

```typescript
// For large lists (1000+ tickers, 10000+ trades)
// Use virtual scrolling to render only visible items
import { FixedSizeList as List } from 'react-window';

function TickerList({ tickers }: { tickers: Ticker[] }) {
  return (
    <List height={600} itemCount={tickers.length} itemSize={40}>
      {({ index, style }) => (
        <div style={style}>
          <TickerRow ticker={tickers[index]} />
        </div>
      )}
    </List>
  );
}
```

---

## 11. Implementasi untuk IDX

### 11.1 IDX-Specific UI Elements

| Element | Description |
|---------|-------------|
| **Market status banner** | "BEI: OPEN (09:00-15:50 WIB)" or "BEI: CLOSED" |
| **Auto-reject indicator** | Warning badge when stock hits ±15% |
| **Lot size display** | Show quantity in lots (1 lot = 100 shares) |
| **Rupiah formatting** | "Rp 8.025.000.000" (Indonesian format) |
| **Indonesian language** | UI labels in Bahasa Indonesia |
| **IHSG ticker** | Always visible composite index |
| **Foreign flow indicator** | Green (net buy) / Red (net sell) per stock |
| **Sector tags** | IDX-IC sector classification |

### 11.2 Number Formatting

```typescript
// Indonesian Rupiah formatting
function formatIDR(value: number): string {
  return new Intl.NumberFormat('id-ID', {
    style: 'currency',
    currency: 'IDR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}
// Rp 8.025.000.000

// Percentage
function formatPct(value: number): string {
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}%`;
}
// +1.25%

// Lot formatting
function formatLot(shares: number): string {
  const lots = shares / 100;
  return `${lots.toLocaleString('id-ID')} lot (${shares.toLocaleString('id-ID')} lembar)`;
}
// 10 lot (1.000 lembar)
```

---

## 12. Checklist Implementasi

### Layout
- [ ] Responsive layout (mobile, tablet, desktop)
- [ ] Sidebar navigation (desktop) / bottom nav (mobile)
- [ ] Top bar with market status, search, profile
- [ ] Grid-based dashboard with widgets

### Dashboard
- [ ] Portfolio summary (NAV, cash, PnL)
- [ ] Watchlist widget
- [ ] Top movers (gainers/losers)
- [ ] Market status indicator
- [ ] News feed widget
- [ ] Allocation chart

### Stock Detail
- [ ] Candlestick chart with volume
- [ ] Technical indicator panel
- [ ] Score card (6 factors + conviction)
- [ ] Recommendation card
- [ ] Fundamental data table
- [ ] News list for ticker
- [ ] Foreign flow indicator

### Trading
- [ ] Order entry form (BUY/SELL)
- [ ] Order confirmation dialog
- [ ] Position table with real-time PnL
- [ ] Order history
- [ ] Stop-loss / take-profit display

### Visualization
- [ ] Candlestick chart
- [ ] Equity curve (line chart)
- [ ] Allocation treemap
- [ ] Score bars (0-100)
- [ ] Conviction gauge
- [ ] Sector heatmap
- [ ] Correlation matrix heatmap

### Real-Time
- [ ] WebSocket connection
- [ ] Price flash animation
- [ ] PnL real-time update
- [ ] Order status push
- [ ] News notification

### Mobile
- [ ] Bottom navigation
- [ ] Touch-optimized controls
- [ ] Swipe gestures
- [ ] Pull to refresh
- [ ] Responsive charts

### Accessibility
- [ ] WCAG color contrast
- [ ] Keyboard navigation
- [ ] ARIA labels
- [ ] Color + icon for signals
- [ ] Focus indicators

### Performance
- [ ] Skeleton loading states
- [ ] Virtual scrolling for large lists
- [ ] Chart lazy loading
- [ ] Optimistic UI updates
- [ ] Debounced search input

### IDX-Specific
- [ ] Indonesian number formatting
- [ ] Market hours display (WIB)
- [ ] Lot size display
- [ ] Auto-reject warning
- [ ] IHSG ticker
- [ ] Foreign flow indicator
- [ ] Indonesian language support

---

## 13. Bahasa Indonesia & Tooltip System

### 13.1 Kebijakan Bahasa

Aplikasi ini menggunakan **Bahasa Indonesia** sebagai bahasa utama untuk seluruh antarmuka pengguna.

| Kategori | Kebijakan | Contoh |
|----------|-----------|--------|
| **Menu & Navigasi** | 100% Bahasa Indonesia | "Dasbor", "Daftar Saham", "Portofolio", "Pesanan", "Uji Strategi", "Pengaturan" |
| **Button & Action** | 100% Bahasa Indonesia | "Beli", "Jual", "Hitung Skor", "Jalankan Backtest", "Simpan" |
| **Label & Header** | 100% Bahasa Indonesia | "Skor Teknikal", "Skor Fundamental", "Skor Makro", "Keyakinan", "Nilai Pasar" |
| **Status & Message** | 100% Bahasa Indonesia | "Pasar Buka", "Pasar Tutup", "Data Tersedia", "Sumber Terputus" |
| **Istilah Teknis Pasar Modal** | Tetap dalam bahasa asli + **tooltip wajib** | "RSI", "MACD", "VaR", "Sharpe Ratio", "P/E", "EBITDA" |
| **Singkatan Bursa/Lembaga** | Tetap dalam bahasa asli + **tooltip wajib** | "IDX", "BEI", "OJK", "KSEI", "KPEI", "IPO" |
| **Istilah Trading Universal** | Tetap dalam bahasa asli + **tooltip wajib** | "ticker", "OHLCV", "bid-ask spread", "slippage", "drawdown" |

### 13.2 Tooltip System

Setiap istilah atau singkatan yang tidak diterjemahkan **wajib** memiliki tooltip yang menjelaskan artinya dalam Bahasa Indonesia.

#### Spesifikasi Tooltip

| Aspek | Desktop | Mobile |
|-------|---------|--------|
| **Trigger** | Hover (mouse over) | Tap pada istilah (dotted underline) |
| **Delay** | 300ms setelah hover | Instan pada tap |
| **Posisi** | Auto-position (top/bottom berdasarkan viewport) | Bottom sheet |
| **Dismiss** | Mouse leave atau Esc | Tap di luar tooltip |
| **Style** | Dark background, light text, rounded | Same, full-width |

#### Implementasi Component

```typescript
// components/Tooltip.tsx
interface TooltipProps {
  term: string;        // Istilah yang ditampilkan (misal: "RSI")
  explanation: string; // Penjelasan dalam Bahasa Indonesia
  children?: React.ReactNode;
}

// Contoh penggunaan:
// <Tooltip term="RSI" explanation="Relative Strength Index — indikator momentum yang mengukur kecepatan dan perubahan pergerakan harga. Skala 0-100. >70 dianggap overbought, <30 oversold.">
//   RSI
// </Tooltip>
```

#### Glosarium Istilah Pasar Modal (Wajib Tooltip)

Berikut adalah daftar istilah dan singkatan yang **wajib** memiliki tooltip di seluruh aplikasi:

**Analisis Teknikal:**

| Istilah | Penjelasan Tooltip |
|---------|-------------------|
| **RSI** | *Relative Strength Index* — indikator momentum 0-100. >70 overbought, <30 oversold. |
| **MACD** | *Moving Average Convergence Divergence* — indikator tren berbasis perbedaan MA 12 dan 26. |
| **ADX** | *Average Directional Index* — mengukur kekuatan tren. >25 = tren kuat. |
| **ATR** | *Average True Range* — mengukur volatilitas. Semakin tinggi, semakin volatil. |
| **Bollinger Bands** | Band statistik di atas/bawah MA berdasarkan deviasi standar. Menunjukkan range normal. |
| **OBV** | *On-Balance Volume* — indikator volume kumulatif yang mengkonfirmasi tren. |
| **Ichimoku** | Sistem indikator komprehensif dari Jepang untuk tren, support/resistance, dan momentum. |
| **Stochastic** | Oscillator yang membandingkan harga penutupan dengan range periode tertentu. |
| **Williams %R** | Indikator momentum mirip stochastic, skala -100 sampai 0. |

**Analisis Fundamental:**

| Istilah | Penjelasan Tooltip |
|---------|-------------------|
| **P/E** | *Price-to-Earnings Ratio* — harga saham dibagi laba per saham. P/E rendah = undervalued. |
| **P/B** | *Price-to-Book Ratio* — harga saham dibanding nilai buku per saham. P/B < 1 = di bawah nilai aset. |
| **ROE** | *Return on Equity* — laba bersih dibanding ekuitas. Mengukur efisiensi modal. >15% baik. |
| **ROA** | *Return on Assets* — laba bersih dibanding total aset. Mengukur efisiensi aset. |
| **ROIC** | *Return on Invested Capital* — return dari modal yang diinvestasikan. >WACC = menciptakan nilai. |
| **EPS** | *Earnings Per Share* — laba bersih per saham. |
| **EBITDA** | *Earnings Before Interest, Taxes, Depreciation, Amortization* — ukuran profitabilitas operasional. |
| **DER** | *Debt-to-Equity Ratio* — total hutang dibanding ekuitas. >1 = berisiko tinggi. |
| **EV/EBITDA** | *Enterprise Value to EBITDA* — valuasi perusahaan termasuk hutang. Alternatif P/E. |
| **DCF** | *Discounted Cash Flow* — metode valuasi berbasis proyeksi arus kas masa depan. |

**Manajemen Risiko:**

| Istilah | Penjelasan Tooltip |
|---------|-------------------|
| **VaR** | *Value at Risk* — estimasi kerugian maksimum pada tingkat kepercayaan tertentu (misal: 95%) dalam periode tertentu. |
| **CVaR** | *Conditional Value at Risk* — rata-rata kerugian jika kerugian melebihi VaR. Lebih konservatif dari VaR. |
| **Sharpe Ratio** | Return excess (di atas risk-free) dibanding volatilitas. >1 baik, >2 sangat baik. |
| **Sortino Ratio** | Mirip Sharpe, hanya mempertimbangkan downside volatility. Lebih akurat untuk asymmetrical returns. |
| **Calmar Ratio** | CAGR dibanding max drawdown. Mengukur return vs risiko penurunan terbesar. |
| **Max Drawdown** | Penurunan terbesar dari puncak equity. Mengukur worst-case loss historis. |
| **Kelly Criterion** | Formula untuk position sizing optimal berdasarkan win rate dan payoff ratio. |
| **Beta** | Sensitivitas saham terhadap pasar. Beta >1 = lebih volatil dari pasar, <1 = kurang volatil. |
| **Alpha** | Return di atas yang diharapkan dari beta. Alpha >0 = outperform risk-adjusted. |

**Trading & Market Microstructure:**

| Istilah | Penjelasan Tooltip |
|---------|-------------------|
| **ticker** | Kode singkat unik untuk saham di bursa (misal: BBCA.JK untuk Bank Central Asia di IDX). |
| **OHLCV** | *Open, High, Low, Close, Volume* — data harga standar untuk analisis teknikal. |
| **bid-ask spread** | Selisih antara harga jual terbaik (ask) dan harga beli terbaik (bid). Semakin kecil, semakin likuid. |
| **slippage** | Selisih antara harga yang diharapkan dan harga eksekusi aktual. |
| **drawdown** | Penurunan nilai portofolio dari puncak terakhir. |
| **position sizing** | Penentuan ukuran posisi (jumlah lot/saham) berdasarkan toleransi risiko. |
| **walk-forward** | Metode validasi: train periode A, test periode B > A, lalu geser. Mencegah overfitting. |
| **purged TSS** | *Purged TimeSeries Split* — cross-validation dengan gap untuk mencegah data leakage. |
| **auto-reject** | Mekanisme BEI yang menghentikan perdagangan saham jika harga bergerak ±15% dari referensi. |
| **lot** | Unit perdagangan di IDX. 1 lot = 100 lembar saham. |

**Bursa & Lembaga:**

| Istilah | Penjelasan Tooltip |
|---------|-------------------|
| **IDX** | *Indonesia Stock Exchange* — Bursa Efek Indonesia, tempat perdagangan saham. |
| **BEI** | Bursa Efek Indonesia (nama resmi dalam bahasa Indonesia). |
| **OJK** | *Otoritas Jasa Keuangan* — regulator pasar modal dan jasa keuangan Indonesia. |
| **KSEI** | *Kustodian Sentral Efek Indonesia* — penyimpanan dan penyelesaian transaksi. |
| **KPEI** | *Kliring Penjaminan Efek Indonesia* — lembaga kliring dan penjaminan transaksi. |
| **IPO** | *Initial Public Offering* — penawaran saham pertama ke publik. |
| **SPO** | *Secondary Public Offering* — penawaran saham tambahan oleh perusahaan yang sudah listed. |
| **REITs** | *Real Estate Investment Trusts* — instrumen investasi properti yang diperdagangkan di bursa. |
| **ETF** | *Exchange-Traded Fund* — reksa dana yang diperdagangkan di bursa seperti saham. |
| **DPS** | *Dewan Pengawas Syariah* — dewan yang mengawasi kepatuhan syariah instrumen keuangan. |

**AI/ML:**

| Istilah | Penjelasan Tooltip |
|---------|-------------------|
| **LSTM** | *Long Short-Term Memory* — jenis neural network untuk data sekuensial seperti harga saham. |
| **regime** | Kondisi pasar saat ini (misal: easing, tightening, risk-off). Memengaruhi strategi optimal. |
| **ensemble** | Kombinasi beberapa model ML untuk prediksi yang lebih robust. |
| **feature engineering** | Proses membuat variabel input (fitur) dari data mentah untuk training model ML. |
| **overfitting** | Model terlalu cocok dengan data historis tapi gagal di data baru. Backtest bagus, live gagal. |
| **XAI** | *Explainable AI* — AI yang dapat menjelaskan alasan setiap rekomendasi/keputusan. |

### 13.3 Implementasi Glosarium

```typescript
// lib/glossary.ts
export const GLOSSARY: Record<string, string> = {
  // Analisis Teknikal
  "RSI": "Relative Strength Index — indikator momentum 0-100. >70 overbought, <30 oversold.",
  "MACD": "Moving Average Convergence Divergence — indikator tren berbasis perbedaan MA 12 dan 26.",
  "ADX": "Average Directional Index — mengukur kekuatan tren. >25 = tren kuat.",
  "ATR": "Average True Range — mengukur volatilitas. Semakin tinggi, semakin volatil.",
  // ... (lengkap sesuai tabel di atas)
};

// Komponen <Term> yang otomatis lookup glosarium
export function Term({ children }: { children: string }) {
  const explanation = GLOSSARY[children];
  if (!explanation) return <>{children}</>;
  return <Tooltip term={children} explanation={explanation}>{children}</Tooltip>;
}

// Penggunaan: <Term>RSI</Term> → tampil "RSI" dengan dotted underline + tooltip
```

### 13.4 Aturan Tambahan

1. **Jangan terjemahkan istilah yang sudah umum** — "ticker", "OHLCV", "backtest" sudah dipahami komunitas trading Indonesia. Cukup beri tooltip.
2. **Format angka tetap Indonesia** — pemisah ribuan dengan titik (Rp 8.025.000.000), desimal dengan koma (12,5%).
3. **Nama saham tidak diterjemahkan** — BBCA.JK tetap BBCA.JK, bukan "Bank Central Asia".
4. **Tanggal dalam format Indonesia** — "29 Juli 2026" atau "29/07/2026", bukan "July 29, 2026".
5. **Tooltip harus concise** — maksimal 2 kalimat. Jika butuh penjelasan panjang, beri link "Pelajari lebih lanjut" ke halaman edukasi.

---

## Referensi

1. `frontend/` — Next.js frontend implementation
2. `frontend/app/components/TerminalLayout.tsx` — Main layout
3. `frontend/app/lib/api.ts` — API layer with safeApiFetch
4. `frontend/AGENTS.md` — Frontend-specific rules
5. `pustaka/17-aplikasi-retail-pribadi.md` — Retail app features
6. `pustaka/18-modul-engine-data-wajib.md` — Module registry
7. `pustaka/19-flow-logic-testing-kpi.md` — UI flow & rules
8. `pustaka/28-api-design-integration-patterns.md` — API & WebSocket
9. Tailwind CSS: https://tailwindcss.com
10. Recharts: https://recharts.org
11. TradingView Lightweight Charts: https://www.tradingview.com/lightweight-charts

---

> **Catatan:** UI/UX untuk trading app bukan tentang membuat tampilan cantik, tetapi tentang membuat keputusan tepat lebih cepat. Setiap detik yang dihemat dari UI yang baik adalah keuntungan yang tidak terlewat.
