"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  TrendingUp,
  Wallet,
  FlaskConical,
  Search,
  Settings,
  FileText,
  Bot,
  Scan,
  Database,
  BellRing,
  Orbit,
} from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/signals", label: "Sinyal", icon: BellRing },
  { href: "/stock", label: "Saham", icon: TrendingUp },
  { href: "/portfolio", label: "Portofolio", icon: Wallet },
  { href: "/backtest", label: "Backtest", icon: FlaskConical },
  { href: "/screener", label: "Screener", icon: Search },
  { href: "/scan", label: "Pola & Prediksi", icon: Scan },
  { href: "/automation", label: "Otomasi", icon: Bot },
  { href: "/reports", label: "Laporan", icon: FileText },
  { href: "/data", label: "Data & Sumber", icon: Database },
  { href: "/cosmos", label: "Kosmos", icon: Orbit },
  { href: "/settings", label: "Pengaturan", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-64 border-r border-border bg-card flex flex-col">
      <div className="p-6 border-b border-border">
        <h1 className="text-xl font-bold text-primary">Market</h1>
        <p className="text-xs text-muted-foreground mt-1">
          Decision Support System
        </p>
      </div>
      <nav className="flex-1 p-4 space-y-1">
        {navItems.map((item) => {
          const Icon = item.icon;
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors",
                active
                  ? "bg-primary/10 text-primary font-medium"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
              )}
            >
              <Icon className="w-4 h-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="p-4 border-t border-border">
        <p className="text-xs text-muted-foreground">
          v0.1.0 · Single-User · EOD
        </p>
      </div>
    </aside>
  );
}
