import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function ScreenerPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Screener</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Filter saham berdasarkan skor faktor
        </p>
      </div>

      <Card>
        <CardHeader><CardTitle>Filter</CardTitle></CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="text-sm font-medium block mb-1">Min Teknikal</label>
              <input type="number" defaultValue={0} min={0} max={100}
                className="w-full px-3 py-2 rounded-md border border-input bg-background text-sm" />
            </div>
            <div>
              <label className="text-sm font-medium block mb-1">Min Fundamental</label>
              <input type="number" defaultValue={0} min={0} max={100}
                className="w-full px-3 py-2 rounded-md border border-input bg-background text-sm" />
            </div>
            <div>
              <label className="text-sm font-medium block mb-1">Min Sentiment</label>
              <input type="number" defaultValue={0} min={0} max={100}
                className="w-full px-3 py-2 rounded-md border border-input bg-background text-sm" />
            </div>
          </div>
          <button className="mt-4 px-6 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90">
            Screening
          </button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Hasil Screening</CardTitle></CardHeader>
        <CardContent>
          <p className="text-muted-foreground text-sm">
            Jalankan screening untuk melihat saham yang lolos filter.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
