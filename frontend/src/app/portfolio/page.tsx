import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function PortfolioPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Portofolio</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Posisi, PnL, alokasi, dan riwayat
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardHeader><CardTitle>NAV Total</CardTitle></CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">Rp 0</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>PnL Realized</CardTitle></CardHeader>
          <CardContent>
            <p className="text-2xl font-bold text-muted-foreground">Rp 0</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>PnL Unrealized</CardTitle></CardHeader>
          <CardContent>
            <p className="text-2xl font-bold text-muted-foreground">Rp 0</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle>Posisi Aktif</CardTitle></CardHeader>
        <CardContent>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-muted-foreground">
                <th className="text-left py-2">Ticker</th>
                <th className="text-right">Saham</th>
                <th className="text-right">Avg Cost</th>
                <th className="text-right">Harga</th>
                <th className="text-right">Nilai</th>
                <th className="text-right">PnL</th>
                <th className="text-right">Bobot</th>
              </tr>
            </thead>
            <tbody>
              <tr className="text-muted-foreground">
                <td colSpan={7} className="text-center py-8">
                  Belum ada posisi. Mulai paper trading untuk menambah posisi.
                </td>
              </tr>
            </tbody>
          </table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Alokasi Sektor</CardTitle></CardHeader>
        <CardContent>
          <p className="text-muted-foreground text-sm">
            Grafik alokasi sektor akan ditampilkan setelah posisi tersedia.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
