# Prompting: Analisis Database untuk AI/ML/Predictive Analytics

## Prompt Utama

```
Bertindaklah sebagai Senior Data Scientist dan Ahli Strategi Pasar Finansial Global. Saya memiliki database yang berisi data pasar modal (Indonesia & Dunia), saham, komoditi, dan forex. Tugas Anda adalah menganalisis database ini secara mendalam untuk mempersiapkan arsitektur pengetahuan bagi model AI/ML/Predictive Analytics.

Lakukan analisis dan klasifikasikan pemahaman data berdasarkan 5 pilar berikut:

1. PEMETAAN ASET & PERBEDAAN WAKTU (TIMING MECHANISM)
- Identifikasi dan petakan seluruh instrumen: Pasar Modal (IHSG, NYSE, NASDAQ, dll), Saham individual, Komoditi (Emas, Minyak, CPO, dll), dan Forex.
- Sinkronisasikan perbedaan jam perdagangan (trading hours) antar negara/zona waktu (WIB, EST, GMT, dll). 
- Analisis bagaimana celah waktu (time-gap) pasar global memengaruhi pembukaan pasar domestik (efek riak/spillover effect).

2. ANALISIS KORELASI DAN KETERHUBUNGAN ANTAR-ASET (INTERMARKET ANALYSIS)
- Bedah hubungan kausalitas dan korelasi antar-instrumen (misal: pengaruh harga Minyak/CPO terhadap saham komoditas, pengaruh yield obligasi AS terhadap Forex dan Saham, Hubungan USD terhadap Emas).
- Petakan pola pergerakan modal (Capital Flow) saat terjadi kondisi Risk-On dan Risk-Off di pasar global.

3. STRUKTUR INDIKATOR PENENTU HARGA (PRICE DRIVERS)
- Ekstrak dan kategorikan faktor yang memengaruhi harga saham dari database menjadi:
  a. Faktor Makroekonomi (Suku bunga, Inflasi, PDB, Geopolitik).
  b. Faktor Mikro/Sentimen (Laporan Keuangan, Aksi Korporasi, Volume Transaksi, Order Book).

4. DETEKSI ANOMALI & RISIKO SISTEMIK (SUSPENSION & DELISTING ANATOMY)
- Analisis pola dan ciri-ciri historis saham yang mengalami Suspensi (Suspension) dan Penghapusan Pencatatan (Delisting).
- Klasifikasikan cirinya berdasarkan: risiko finansial (ekuitas negatif, gagal bayar), risiko legal/kepatuhan (terlambat laporan keuangan), dan manipulasi pasar (cornering, pom-pom).
- Berikan label/fitur (feature labeling) spesifik pada data yang menunjukkan gejala awal (early warning signs) sebelum status suspensi terjadi.

5. STRUKTURISASI DATA UNTUK PREDIKSI AI/ML
- Berdasarkan analisis di atas, formulasikan bagaimana pola-pola ini harus disusun dalam database agar model AI/ML dapat memahami arah prediksi (Predictive Direction) dan dependensi waktu secara akurat.

Periksa database saya sekarang, lakukan analisis mendalam, dan sajikan laporan terstruktur berdasarkan 5 pilar di atas.
```

## Prompt Ringkas

```
Periksa database saya dan lakukan analisis mendalam untuk kebutuhan pelatihan model AI/ML/Predictive Analytics. Analisis harus mencakup:
1. Pemetaan komprehensif pasar modal (Indonesia & Global), saham, komoditi, dan forex, lengkap dengan sinkronisasi perbedaan jam perdagangan lintas negara.
2. Analisis intermarket untuk menemukan hubungan saling memengaruhi antar-aset (cross-asset correlations & spillover effects).
3. Identifikasi faktor makro dan mikro yang menggerakkan harga saham.
4. Pola, ciri-ciri, dan indikator awal (early warning) pada saham yang terkena suspensi atau delisting.

Susun hasil analisis secara sistematis agar struktur data siap digunakan oleh gigantic AI untuk mengenali pola, dependensi waktu, dan arah prediksi pasar global.
```
