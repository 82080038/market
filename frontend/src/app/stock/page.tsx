import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function StockPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Detail Saham</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Chart, indikator, skor, dan rekomendasi
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Pencarian Saham</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex gap-4">
            <input
              type="text"
              placeholder="Masukkan ticker (contoh: BBCA.JK)"
              className="flex-1 px-4 py-2 rounded-md border border-input bg-background text-sm"
            />
            <button className="px-6 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90">
              Analisis
            </button>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Chart Harga</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-64 flex items-center justify-center text-muted-foreground">
              Chart akan ditampilkan setelah data tersedia
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Skor Faktor</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {[
                { label: "Teknikal", value: 0, color: "bg-blue-500" },
                { label: "Fundamental", value: 0, color: "bg-green-500" },
                { label: "Makro", value: 0, color: "bg-yellow-500" },
                { label: "Global", value: 0, color: "bg-purple-500" },
                { label: "Relasi", value: 0, color: "bg-pink-500" },
                { label: "Sentiment", value: 0, color: "bg-orange-500" },
              ].map((factor) => (
                <div key={factor.label}>
                  <div className="flex justify-between text-sm mb-1">
                    <span>{factor.label}</span>
                    <span className="font-medium">{factor.value}/100</span>
                  </div>
                  <div className="h-2 rounded-full bg-muted">
                    <div
                      className={`h-2 rounded-full ${factor.color}`}
                      style={{ width: `${factor.value}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Rekomendasi & XAI</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground text-sm">
            Pilih saham untuk melihat rekomendasi dengan penjelasan (XAI).
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
