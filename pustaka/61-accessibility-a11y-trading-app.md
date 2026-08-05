# Accessibility (a11y) untuk Trading App

> **Dokumen 61** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** WCAG 2.1 AA compliance, screen reader support, keyboard navigation, color-blind friendly charts, high contrast mode.
>
> **Konteks:** Dokumen 32 bahas UI/UX design. Tapi belum ada doc tentang accessibility: bagaimana user dengan disability bisa menggunakan trading app.

---

## Daftar Isi

1. [Kenapa Accessibility untuk Trading App](#1-kenapa-accessibility-untuk-trading-app)
2. [WCAG 2.1 AA Requirements](#2-wcag-21-aa-requirements)
3. [Screen Reader Support](#3-screen-reader-support)
4. [Keyboard Navigation](#4-keyboard-navigation)
5. [Color-Blind Friendly Charts](#5-color-blind-friendly-charts)
6. [Implementation Checklist](#6-implementation-checklist)

---

## 1. Kenapa Accessibility untuk Trading App

### 1.1 Kenapa Penting

| Alasan | Detail |
|--------|--------|
| **Inclusion** | 15% populasi punya disability — mereka juga investor |
| **Regulation** | UU 8/2016 tentang Penyandang Disabilitas |
| **Market opportunity** | User dengan disability = market yang underserved |
| **Better UX for all** | a11y features benefit semua user (keyboard nav, high contrast) |

### 1.2 Trading-Specific Challenges

| Challenge | Solution |
|-----------|----------|
| Chart data visual only | Screen reader: "BBCA.JK naik 2.5% ke 7,850" |
| Color-coded signals (green/red) | Color-blind palette + icon + text label |
| Real-time data updates | ARIA live region untuk price changes |
| Complex tables (scores) | Proper table semantics, row/column headers |
| Interactive charts | Keyboard-accessible chart controls |

---

## 2. WCAG 2.1 AA Requirements

### 2.1 Key Principles (POUR)

| Principle | Requirement | Trading App Implementation |
|-----------|-------------|---------------------------|
| **Perceivable** | Content dapat dipersepsi semua user | Alt text untuk chart, caption untuk data |
| **Operable** | Interface dapat dioperasikan semua user | Keyboard nav, no time limits |
| **Understandable** | Content dan operation dapat dipahami | Clear labels, Bahasa Indonesia, tooltips |
| **Robust** | Content dapat diinterpretasi berbagai tools | Semantic HTML, ARIA attributes |

### 2.2 Specific Requirements

| Requirement | WCAG Criterion | Implementation |
|-------------|----------------|----------------|
| Color contrast ≥ 4.5:1 | 1.4.3 | High contrast theme, test with contrast checker |
| No color-only information | 1.4.1 | Green/red + icon (▲/▼) + text (UP/DOWN) |
| Keyboard accessible | 2.1.1 | All interactive elements reachable via Tab |
| No keyboard trap | 2.1.2 | Modal/dialog: Esc to close, focus return |
| Focus visible | 2.4.7 | Focus outline (2px solid blue) |
| Page titled | 2.4.2 | `<title>` per page: "BBCA.JK - Trading System" |
| Link purpose clear | 2.4.4 | Link text describes destination |
| Error identification | 3.3.1 | Form errors: text + icon + ARIA |
| Status messages | 4.1.3 | ARIA live region untuk alerts |

---

## 3. Screen Reader Support

### 3.1 Chart Data Accessibility

```html
<!-- Instead of only visual chart -->
<div role="img" aria-label="BBCA.JK chart: naik 2.5% dari 7,650 ke 7,850 dalam 5 hari">
  <canvas id="chart"></canvas>
</div>

<!-- Data table alongside chart -->
<table aria-label="Data OHLCV BBCA.JK 5 hari terakhir">
  <thead>
    <tr>
      <th scope="col">Tanggal</th>
      <th scope="col">Open</th>
      <th scope="col">High</th>
      <th scope="col">Low</th>
      <th scope="col">Close</th>
      <th scope="col">Volume</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th scope="row">2026-08-05</th>
      <td>7,650</td>
      <td>7,900</td>
      <td>7,600</td>
      <td>7,850</td>
      <td>1.2M</td>
    </tr>
  </tbody>
</table>
```

### 3.2 Price Update Live Region

```html
<div aria-live="polite" aria-atomic="true" id="price-update">
  <!-- Screen reader reads: "BBCA.JK: 7,850, naik 2.5 persen" -->
</div>
```

### 3.3 Recommendation Accessibility

```html
<div role="region" aria-label="Rekomendasi BBCA.JK">
  <h3>BBCA.JK — WATCHLIST</h3>
  <p>Conviction: <strong>55 dari 100</strong></p>
  <p>Aksi: Watchlist (pantau, belum beli)</p>
  <p>Entry: Rp 7,820 - Rp 7,880</p>
  <p>Stop Loss: Rp 7,600</p>
  <p>Take Profit: Rp 8,500</p>
  <p>Faktor utama: Fundamental (80), Technical (56)</p>
</div>
```

---

## 4. Keyboard Navigation

### 4.1 Tab Order

```
1. Skip to main content link
2. Sidebar navigation (Data Inspection)
3. Ticker search input
4. Ticker result list
5. Data table (row by row)
6. Chart controls (zoom, pan)
7. Footer
```

### 4.2 Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Tab` | Next focusable element |
| `Shift+Tab` | Previous focusable element |
| `Enter` | Activate button/link |
| `Esc` | Close modal/dialog |
| `/` | Focus search |
| `g` then `d` | Go to dashboard |
| `g` then `w` | Go to watchlist |

### 4.3 Implementation

```typescript
// frontend/app/components/KeyboardNav.tsx
export function useKeyboardShortcuts() {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === '/' && document.activeElement?.tagName !== 'INPUT') {
        e.preventDefault();
        document.getElementById('ticker-search')?.focus();
      }
      if (e.key === 'Escape') {
        // Close any open modal
        const modal = document.querySelector('[role="dialog"]');
        if (modal) modal.dispatchEvent(new Event('close'));
      }
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, []);
}
```

---

## 5. Color-Blind Friendly Charts

### 5.1 Color Palette

| Element | Standard | Color-Blind Safe | Additional Cue |
|---------|----------|-----------------|----------------|
| **Up/positive** | Green (#00C853) | Blue (#2196F3) | ▲ icon + "UP" text |
| **Down/negative** | Red (#FF1744) | Orange (#FF9800) | ▼ icon + "DOWN" text |
| **Neutral** | Gray (#9E9E9E) | Gray (#9E9E9E) | — text |
| **Buy signal** | Green | Blue + ▲ | "BUY" label |
| **Sell signal** | Red | Orange + ▼ | "SELL" label |

### 5.2 Chart Patterns (not just color)

```typescript
// Use patterns + colors for chart series
const seriesStyles = {
  ohlcv: { color: '#2196F3', pattern: 'solid' },
  sma20: { color: '#FF9800', pattern: 'dashed' },
  sma50: { color: '#9C27B0', pattern: 'dotted' },
  volume: { color: '#795548', pattern: 'bars' },
};
```

---

## 6. Implementation Checklist

### 6.1 Semantic HTML

- [ ] Use `<table>`, `<thead>`, `<tbody>`, `<th scope>` for all data tables
- [ ] Use `<nav>`, `<main>`, `<aside>`, `<footer>` for page structure
- [ ] Use `<button>` for actions, `<a>` for navigation
- [ ] Use `<form>`, `<label>` for all inputs

### 6.2 ARIA

- [ ] `aria-label` on all icon-only buttons
- [ ] `aria-live` for real-time updates (price, alerts)
- [ ] `role="region"` + `aria-label` for major sections
- [ ] `role="img"` + `aria-label` for charts
- [ ] `aria-expanded` for collapsible sections
- [ ] `aria-busy` for loading states

### 6.3 Visual

- [ ] Color contrast ≥ 4.5:1 (test with WebAIM Contrast Checker)
- [ ] Focus indicator visible (2px outline minimum)
- [ ] No color-only information (always + icon or text)
- [ ] Font size ≥ 14px base, scalable to 200%
- [ ] Touch targets ≥ 44×44px (mobile)

### 6.4 Keyboard

- [ ] All interactive elements reachable via Tab
- [ ] No keyboard traps
- [ ] Logical tab order (left-to-right, top-to-bottom)
- [ ] Skip link at top of page
- [ ] Keyboard shortcuts documented

### 6.5 Testing

- [ ] Test with NVDA (Windows) or VoiceOver (macOS)
- [ ] Test with keyboard only (no mouse)
- [ ] Test with high contrast mode
- [ ] Test with 200% zoom
- [ ] Run axe DevTools or Lighthouse accessibility audit

---

## 7. Hubungan dengan Dokumen Lain

| Dokumen | Hubungan |
|---------|----------|
| **32** (UI/UX Design) | a11y is part of UX design |
| **43** (Mobile App) | Mobile a11y (VoiceOver/TalkBack) |
| **61** (this doc) | Accessibility implementation guide |

---

## Referensi

1. `frontend/app/page.tsx` — Data Inspection Dashboard (section IDs for accessibility)
2. `frontend/app/components/TerminalLayout.tsx` — Layout & navigation
3. `pustaka/32-ui-ux-design-trading-app.md` — UI/UX design
4. `pustaka/43-mobile-app-architecture.md` — Mobile app accessibility
5. WCAG 2.1: https://www.w3.org/TR/WCAG21/
6. ARIA Authoring Practices: https://www.w3.org/WAI/ARIA/apg/
7. Deque axe-core: Accessibility testing tool

---

> **Catatan:** Accessibility bukan fitur tambahan — adalah requirement. "Akses untuk semua adalah akses untuk lebih banyak orang." Trading app yang accessible melayani investor yang tidak terlayani oleh kompetitor.
