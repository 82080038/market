import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Pengaturan</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Parameter risiko, notifikasi, dan API key
        </p>
      </div>

      <Card>
        <CardHeader><CardTitle>Parameter Risiko</CardTitle></CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium block mb-1">Risk per Trade (%)</label>
              <input type="number" defaultValue={1} min={0.1} max={5} step={0.1}
                className="w-full px-3 py-2 rounded-md border border-input bg-background text-sm" />
            </div>
            <div>
              <label className="text-sm font-medium block mb-1">ATR Multiplier (SL)</label>
              <input type="number" defaultValue={1.5} min={0.5} max={5} step={0.1}
                className="w-full px-3 py-2 rounded-md border border-input bg-background text-sm" />
            </div>
            <div>
              <label className="text-sm font-medium block mb-1">Risk-Reward Ratio</label>
              <input type="number" defaultValue={2} min={1} max={5} step={0.5}
                className="w-full px-3 py-2 rounded-md border border-input bg-background text-sm" />
            </div>
            <div>
              <label className="text-sm font-medium block mb-1">Max Volatility (%)</label>
              <input type="number" defaultValue={50} min={10} max={100}
                className="w-full px-3 py-2 rounded-md border border-input bg-background text-sm" />
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Notifikasi</CardTitle></CardHeader>
        <CardContent>
          <div className="space-y-3">
            {[
              { label: "Telegram Alert", desc: "Kirim notifikasi via Telegram bot" },
              { label: "Email Alert", desc: "Kirim notifikasi via email" },
              { label: "In-App Alert", desc: "Tampilkan notifikasi di aplikasi" },
              { label: "Circuit Breaker Alert", desc: "Notifikasi saat drawdown melewati threshold" },
            ].map((item) => (
              <div key={item.label} className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium">{item.label}</p>
                  <p className="text-xs text-muted-foreground">{item.desc}</p>
                </div>
                <input type="checkbox" defaultChecked className="w-4 h-4" />
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>API Key</CardTitle></CardHeader>
        <CardContent>
          <div className="space-y-3">
            <div>
              <label className="text-sm font-medium block mb-1">Yahoo Finance API (opsional)</label>
              <input type="password" placeholder="••••••••••••"
                className="w-full px-3 py-2 rounded-md border border-input bg-background text-sm" />
            </div>
            <div>
              <label className="text-sm font-medium block mb-1">Broker API Key</label>
              <input type="password" placeholder="••••••••••••"
                className="w-full px-3 py-2 rounded-md border border-input bg-background text-sm" />
            </div>
            <p className="text-xs text-muted-foreground">
              API key disimpan di file .env dan tidak pernah di-commit ke git.
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Aktivasi Broker Real</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div className="rounded-md border border-yellow-500/30 bg-yellow-500/5 p-3">
              <p className="text-xs text-yellow-600 dark:text-yellow-500">
                ⚠️ Aktivasi broker real akan mengaktifkan trading dengan uang sungguhan.
                Pastikan paper trading telah berjalan minimal 30 hari dengan hasil yang memadai.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="text-sm font-medium block mb-1">Broker</label>
                <select className="w-full px-3 py-2 rounded-md border border-input bg-background text-sm">
                  <option value="">— Pilih Broker —</option>
                  <option value="sinarmas">Sinarmas Sekuritas</option>
                  <option value="bni">BNI Sekuritas</option>
                  <option value="mirae">Mirae Asset Sekuritas</option>
                </select>
              </div>
              <div>
                <label className="text-sm font-medium block mb-1">Environment</label>
                <select className="w-full px-3 py-2 rounded-md border border-input bg-background text-sm">
                  <option value="paper">Paper (simulasi)</option>
                  <option value="live">Live (uang sungguhan)</option>
                </select>
              </div>
              <div>
                <label className="text-sm font-medium block mb-1">Broker Username</label>
                <input type="text" placeholder="Broker account username"
                  className="w-full px-3 py-2 rounded-md border border-input bg-background text-sm" />
              </div>
              <div>
                <label className="text-sm font-medium block mb-1">Broker Password</label>
                <input type="password" placeholder="••••••••••••"
                  className="w-full px-3 py-2 rounded-md border border-input bg-background text-sm" />
              </div>
              <div>
                <label className="text-sm font-medium block mb-1">Broker API Token</label>
                <input type="password" placeholder="••••••••••••"
                  className="w-full px-3 py-2 rounded-md border border-input bg-background text-sm" />
              </div>
              <div>
                <label className="text-sm font-medium block mb-1">Approval Token File</label>
                <input type="text" placeholder="/path/to/approval.token"
                  className="w-full px-3 py-2 rounded-md border border-input bg-background text-sm" />
              </div>
            </div>

            <div className="space-y-2">
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" className="w-4 h-4" />
                Saya telah menjalankan paper trading minimal 30 hari
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" className="w-4 h-4" />
                Saya memahami risiko kehilangan modal
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" className="w-4 h-4" />
                Saya menyetujui daily loss limit dan max drawdown settings
              </label>
            </div>

            <button
              type="button"
              className="w-full px-4 py-2 rounded-md bg-yellow-600 text-white text-sm font-medium hover:bg-yellow-700 disabled:opacity-50"
            >
              Aktifkan Broker Real
            </button>
            <p className="text-xs text-muted-foreground">
              Aktivasi memerlukan approval token file yang ditandatangani manual.
              Lihat MEGAPLAN.md §6.4 Human-Gate Checklist.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
