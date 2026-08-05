import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function ReportsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Laporan</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Pajak, dividen, trade log, dan statement
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {[
          { title: "Pajak", desc: "Pajak final saham 0.1% (jual), PPh untuk dividen" },
          { title: "Dividen", desc: "Riwayat dividen received dan yield" },
          { title: "Trade Log", desc: "Riwayat semua transaksi buy/sell" },
          { title: "Statement", desc: "Statement bulanan portofolio" },
        ].map((report) => (
          <Card key={report.title}>
            <CardHeader><CardTitle>{report.title}</CardTitle></CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground mb-4">{report.desc}</p>
              <button className="px-4 py-2 rounded-md border border-border text-sm hover:bg-accent">
                Generate
              </button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
