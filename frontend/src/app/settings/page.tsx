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
    </div>
  );
}
