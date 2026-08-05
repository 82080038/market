import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function BacktestPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Backtest</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Validasi strategi dengan data historis
        </p>
      </div>

      <Card>
        <CardHeader><CardTitle>Konfigurasi</CardTitle></CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="text-sm font-medium block mb-1">Ticker</label>
              <input
                type="text"
                placeholder="BBCA.JK"
                className="w-full px-3 py-2 rounded-md border border-input bg-background text-sm"
              />
            </div>
            <div>
              <label className="text-sm font-medium block mb-1">Strategi</label>
              <select className="w-full px-3 py-2 rounded-md border border-input bg-background text-sm">
                <option value="buy_hold">Buy & Hold</option>
                <option value="ma_crossover">MA Crossover</option>
                <option value="conviction">Conviction</option>
              </select>
            </div>
            <div>
              <label className="text-sm font-medium block mb-1">Periode (hari)</label>
              <input
                type="number"
                defaultValue={100}
                min={30}
                max={1000}
                className="w-full px-3 py-2 rounded-md border border-input bg-background text-sm"
              />
            </div>
          </div>
          <button className="mt-4 px-6 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90">
            Jalankan Backtest
          </button>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {[
          { label: "Total Return", value: "—" },
          { label: "Sharpe Ratio", value: "—" },
          { label: "Max Drawdown", value: "—" },
          { label: "Win Rate", value: "—" },
        ].map((metric) => (
          <Card key={metric.label}>
            <CardHeader><CardTitle>{metric.label}</CardTitle></CardHeader>
            <CardContent>
              <p className="text-2xl font-bold">{metric.value}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader><CardTitle>Equity Curve</CardTitle></CardHeader>
        <CardContent>
          <div className="h-64 flex items-center justify-center text-muted-foreground">
            Jalankan backtest untuk melihat equity curve
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
