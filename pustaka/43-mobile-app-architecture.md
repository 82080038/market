# Mobile App Architecture untuk Aplikasi Trading IDX

> **Dokumen 43** | Pustaka Pengetahuan Pasar Modal Indonesia
>
> **Fokus:** Arsitektur mobile app untuk trading IDX — React Native vs Flutter vs Native, offline support, biometric auth, push notification, security, app store deployment, dan optimisasi untuk pasar Indonesia.
>
> **Konteks:** Investor ritel Indonesia akses pasar modal via HP, bukan desktop. IDX Mobile sudah 510K+ users. Aplikasi trading harus mobile-first: ringan, hemat data, work di jaringan tidak stabil, dan aman.

---

## Daftar Isi

1. [Mobile-First untuk Pasar Indonesia](#1-mobile-first-untuk-pasar-indonesia)
2. [Pilihan Tech Stack](#2-pilihan-tech-stack)
3. [Offline Support & Sync](#3-offline-support--sync)
4. [Biometric Authentication](#4-biometric-authentication)
5. [Push Notification Architecture](#5-push-notification-architecture)
6. [Security Mobile](#6-security-mobile)
7. [App Store Deployment](#7-app-store-deployment)
8. [Performance & Data Optimization](#8-performance--data-optimization)
9. [Implementasi](#9-implementasi)
10. [Adopsi dari Codebase Existing](#10-adopsi-dari-codebase-existing)
11. [Checklist Implementasi](#11-checklist-implementasi)

---

## 1. Mobile-First untuk Pasar Indonesia

### 1.1 Profil User Indonesia

| Metrik | Nilai | Dampak ke App |
|--------|-------|--------------|
| Smartphone penetration | 78% populasi | Mobile wajib, desktop opsional |
| Android vs iOS | 88% vs 12% | Android-first, iOS secondary |
| Internet speed median | 20-25 Mbps (4G) | Optimisasi bandwidth |
| Jaringan tidak stabil | Frequent di area non-urban | Offline support critical |
| Data plan terbatas | Banyak user pakai data kecil | Minimize data usage |
| Device low-end | Banyak RAM 3-4 GB | App ringan, <50MB |
| Literasi digital | Banyak investor baru | UI sederhana, edukasi inline |

### 1.2 Prinsip Desain

1. **Android-first** — 88% market share Indonesia
2. **Low-end friendly** — Support Android 8+ (API 26+), RAM 2GB+
3. **Data-efficient** — Delta updates, compression, lazy loading
4. **Offline-tolerant** — Cache data, queue orders, sync saat online
5. **Biometric-ready** — Face ID / fingerprint untuk login & transaksi
6. **Battery-efficient** — Minimal background polling, push notification
7. **Bahasa Indonesia** — Default language, bukan English

---

## 2. Pilihan Tech Stack

### 2.1 Comparison

| Kriteria | React Native | Flutter | Native (Kotlin/Swift) |
|----------|-------------|---------|----------------------|
| **Performance** | Good (JS bridge) | Excellent (compiled) | Best |
| **Code sharing** | 80-90% | 90-95% | 0% (separate codebase) |
| **Bundle size** | ~15-25MB | ~20-30MB | ~10-15MB |
| **Hot reload** | ✅ | ✅ | ❌ |
| **Chart library** | Good (react-native-gifted-charts) | Excellent (fl_chart) | Best (MPAndroidChart) |
| **WebSocket support** | Good | Good | Excellent |
| **Biometric** | Good (expo-local-auth) | Good (local_auth) | Excellent |
| **Community Indonesia** | Large | Growing | Large |
| **Time to market** | Fast | Fast | Slow (2 codebases) |
| **Maintenance** | 1 team | 1 team | 2 teams (Android + iOS) |

### 2.2 Rekomendasi

**Flutter** untuk aplikasi trading ritel IDX:

- **Performance**: Compiled to native ARM — critical untuk real-time price updates
- **Chart rendering**: `fl_chart` dan `syncfusion_flutter_charts` sangat smooth
- **Bundle size**: Acceptable untuk Indonesia (20-30MB)
- **Single codebase**: 95% code sharing, 1 team maintain
- **Widget system**: UI konsisten across platforms
- **Dart language**: Type-safe, async-friendly, good untuk financial logic

**Alternatif: React Native** jika:
- Team sudah expert di JavaScript/TypeScript
- Ingin reuse code dari web frontend (Next.js)
- Community support lebih penting

### 2.3 Arsitektur Flutter

```
┌──────────────────────────────────────────────────────────────┐
│                    FLUTTER TRADING APP                       │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                   PRESENTATION LAYER                  │   │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐        │   │
│  │  │Dashboard│ │ Watchlist│ │ Portfolio│ │ Settings│   │   │
│  │  └────────┘ └────────┘ └────────┘ └────────┘        │   │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐        │   │
│  │  │ Stock  │ │ Order  │ │ Chart  │ │ Support│        │   │
│  │  │ Detail │ │ Entry  │ │ View   │ │ Chat   │        │   │
│  │  └────────┘ └────────┘ └────────┘ └────────┘        │   │
│  └──────────────────────────────────────────────────────┘   │
│                         │                                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                   STATE MANAGEMENT                    │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │   │
│  │  │  Bloc /  │  │  Repository│  │  Local Cache     │   │   │
│  │  │  Riverpod│  │  Pattern  │  │  (Hive/SQLite)   │   │   │
│  │  └──────────┘  └──────────┘  └──────────────────┘   │   │
│  └──────────────────────────────────────────────────────┘   │
│                         │                                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                   DATA LAYER                          │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │   │
│  │  │  REST    │  │WebSocket │  │  Local Storage   │   │   │
│  │  │  API     │  │  Stream  │  │  (Offline DB)    │   │   │
│  │  └──────────┘  └──────────┘  └──────────────────┘   │   │
│  └──────────────────────────────────────────────────────┘   │
│                         │                                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                   PLATFORM LAYER                      │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │   │
│  │  │Biometric │  │Push Notif│  │  Secure Storage  │   │   │
│  │  │(local_   │  │(FCM/APNs)│  │  (Keychain/      │   │   │
│  │  │ auth)    │  │          │  │   Keystore)      │   │   │
│  │  └──────────┘  └──────────┘  └──────────────────┘   │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. Offline Support & Sync

### 3.1 Strategi Offline

| Data | Offline Strategy |
|------|-----------------|
| **Watchlist** | Cache di local DB, refresh saat online |
| **Portfolio** | Cache last-known state, update saat online |
| **Stock detail** | Cache last price + chart data |
| **Orders** | Queue offline orders, sync saat online |
| **Notifications** | Store locally, show saat app dibuka |
| **KYC data** | Cache status, tidak cache dokumen |

### 3.2 Offline Order Queue

```dart
// Flutter: Offline order queue
class OfflineOrderQueue {
  final Box<Map> _box;  // Hive box

  Future<String> queueOrder({
    required String ticker,
    required String side,
    required int quantity,
    required double price,
    required String orderType,
  }) async {
    final orderId = const Uuid().v4();
    await _box.put(orderId, {
      'order_id': orderId,
      'ticker': ticker,
      'side': side,
      'quantity': quantity,
      'price': price,
      'order_type': orderType,
      'status': 'queued_offline',
      'queued_at': DateTime.now().toIso8601String(),
      'idempotency_key': orderId,  // Prevent duplicate saat sync
    });
    return orderId;
  }

  Future<void> syncOrders() async {
    final connectivity = await Connectivity().checkConnectivity();
    if (connectivity == ConnectivityResult.none) return;

    final queued = _box.values.where(
      (o) => o['status'] == 'queued_offline',
    ).toList();

    for (final order in queued) {
      try {
        final response = await _api.submitOrder(
          ticker: order['ticker'],
          side: order['side'],
          quantity: order['quantity'],
          price: order['price'],
          orderType: order['order_type'],
          idempotencyKey: order['idempotency_key'],
        );

        // Update local status
        order['status'] = 'synced';
        order['server_order_id'] = response['order_id'];
        await _box.put(order['order_id'], order);
      } catch (e) {
        order['status'] = 'sync_failed';
        order['error'] = e.toString();
        await _box.put(order['order_id'], order);
      }
    }
  }
}
```

### 3.3 Conflict Resolution

| Scenario | Resolution |
|----------|-----------|
| Order queued offline, price changed saat online | Confirm dengan user sebelum submit |
| Portfolio cache vs server | Server wins (authoritative) |
| Watchlist modified offline + online | Merge (union, no duplicates) |
| Notification read status | Server wins |

---

## 4. Biometric Authentication

### 4.1 Use Cases

| Use Case | Biometric | Fallback |
|----------|-----------|----------|
| **Login** | Face ID / Fingerprint | PIN |
| **Order confirmation** | Face ID / Fingerprint | PIN + OTP |
| **Withdrawal** | Face ID + OTP | PIN + OTP + SMS |
| **Settings change** | Face ID / Fingerprint | PIN |

### 4.2 Implementasi (Flutter)

```dart
class BiometricAuthService {
  final LocalAuthentication _auth = LocalAuthentication();

  Future<bool> isBiometricAvailable() async {
    final canCheck = await _auth.canCheckBiometrics;
    final isDeviceSupported = await _auth.isDeviceSupported();
    return canCheck && isDeviceSupported;
  }

  Future<bool> authenticate({required String reason}) async {
    try {
      return await _auth.authenticate(
        localizedReason: reason,
        options: const AuthenticationOptions(
          biometricOnly: false,  // Allow device PIN as fallback
          stickyAuth: true,
          useErrorDialogs: true,
        ),
      );
    } catch (e) {
      return false;
    }
  }

  Future<bool> authenticateForOrder({
    required String ticker,
    required String side,
    required int quantity,
  }) async {
    final reason = 'Konfirmasi $side $quantity $ticker dengan biometrik';
    return await authenticate(reason: reason);
  }
}
```

### 4.3 Security Considerations

- Biometric data **tidak boleh** disimpan di server — hanya di device (Secure Enclave / Keystore)
- Biometric authentication = **local verification only**, server tetap verify dengan token
- Setelah biometric success, kirim signed challenge ke server untuk dapat session token
- Fallback PIN wajib ada (biometric bisa gagal: jari basah, wajah berubah)

---

## 5. Push Notification Architecture

### 5.1 Notification Types

| Type | Trigger | Priority | TTL |
|------|---------|----------|-----|
| **Order fill** | Order executed | High | 1 jam |
| **Price alert** | Price hits target | High | 30 menit |
| **Auto-reject** | Stock hits auto-reject | Medium | 1 jam |
| **DES change** | Saham masuk/keluar DES | Medium | 24 jam |
| **News alert** | Breaking news untuk ticker | Medium | 2 jam |
| **Market open/close** | Jam perdagangan | Low | 15 menit |
| **Dividend** | Dividen dikredit | Low | 24 jam |
| **Corporate action** | Stock split, right issue | Medium | 24 jam |
| **Support reply** | Agent reply ticket | Medium | 24 jam |
| **Marketing** | Promo, edukasi | Low | 7 hari |

### 5.2 Implementasi (Flutter + FCM)

```dart
class PushNotificationService {
  final FirebaseMessaging _fcm = FirebaseMessaging.instance;

  Future<void> initialize() async {
    // Request permission
    await _fcm.requestPermission(
      alert: true,
      badge: true,
      sound: true,
    );

    // Get token
    final token = await _fcm.getToken();
    if (token != null) {
      await _api.registerDeviceToken(token);
    }

    // Listen to token refresh
    _fcm.onTokenRefresh.listen(_api.registerDeviceToken);

    // Foreground messages
    FirebaseMessaging.onMessage.listen(_handleForegroundMessage);

    // Background messages
    FirebaseMessaging.onBackgroundMessage(_handleBackgroundMessage);

    // Notification tap (app opened from notification)
    FirebaseMessaging.onMessageOpenedApp.listen(_handleNotificationTap);
  }

  void _handleForegroundMessage(RemoteMessage message) {
    final notification = message.notification;
    final data = message.data;

    // Show in-app notification banner
    if (notification != null) {
      _showInAppBanner(
        title: notification.title ?? '',
        body: notification.body ?? '',
        type: data['type'] ?? 'general',
        onTap: () => _handleNotificationTap(message),
      );
    }
  }

  Future<void> subscribeToTicker(String ticker) async {
    await _fcm.subscribeToTopic('ticker_$ticker');
  }

  Future<void> unsubscribeFromTicker(String ticker) async {
    await _fcm.unsubscribeFromTopic('ticker_$ticker');
  }
}
```

### 5.3 Server-Side (Python)

```python
class PushNotificationSender:
    """Send push notifications via FCM."""

    def __init__(self, fcm_credentials_path: str):
        self.creds = credentials.Certificate(fcm_credentials_path)
        self.fcm_app = initialize_app(self.creds)

    def send_order_fill_notification(self, user_id: str, order_data: dict):
        """Send order fill push notification."""
        tokens = self.storage.get_user_device_tokens(user_id)
        if not tokens:
            return

        message = multicast.MulticastMessage(
            tokens=tokens,
            notification=messaging.Notification(
                title=f"Order Terksekusi: {order_data['side']} {order_data['ticker']}",
                body=f"{order_data['filled_qty']} lembar @ Rp {order_data['fill_price']:,.0f}",
            ),
            data={
                "type": "order_fill",
                "order_id": order_data["order_id"],
                "ticker": order_data["ticker"],
            },
            android=messaging.AndroidConfig(
                priority="high",
                notification=messaging.AndroidNotification(
                    channel_id="order_updates",
                    icon="@mipmap/ic_launcher",
                ),
            ),
            apns=messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        badge=1,
                        sound="default",
                    ),
                ),
            ),
        )
        messaging.send_multicast(message)
```

---

## 6. Security Mobile

### 6.1 Security Checklist

| Security Measure | Implementasi |
|-----------------|-------------|
| **Certificate pinning** | Pin API certificate untuk prevent MITM |
| **Root/jailbreak detection** | Block app di rooted/jailbroken device |
| **App attestation** | Verify app integrity (Play Integrity / DeviceCheck) |
| **Secure storage** | Token, PIN di Keychain (iOS) / Keystore (Android) |
| **Code obfuscation** | ProGuard (Android) / iXGuard (iOS) |
| **Anti-screenshot** | Block screenshot di halaman sensitif (PIN, OTP) |
| **Screen security** | FLAG_SECURE (Android) untuk hide dari recents |
| **Device binding** | Max 2 device per account |
| **Session timeout** | Auto-logout setelah 15 menit inactivity |
| **PIN lock** | 6-digit PIN, 3x salah = lock 30 menit |

### 6.2 Implementasi Certificate Pinning (Flutter)

```dart
class SecureHttpClient extends http.BaseClient {
  final http.Client _inner = http.Client();

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    // Certificate pinning check
    final sslCert = await _getServerCertificate(request.url);
    if (!_verifyCertificatePin(sslCert)) {
      throw SecurityException('Certificate verification failed');
    }
    return _inner.send(request);
  }

  bool _verifyCertificatePin(String cert) {
    // Compare with pinned certificate hash
    const pinnedHash = 'sha256/XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX=';
    return _computeCertHash(cert) == pinnedHash;
  }
}
```

### 6.3 Root Detection (Android)

```dart
class SecurityChecker {
  Future<bool> isDeviceRooted() async {
    try {
      final result = await Process.run('which', ['su']);
      return result.exitCode == 0;
    } catch (_) {
      // Check common root paths
      const rootPaths = [
        '/system/app/Superuser.apk',
        '/sbin/su',
        '/system/bin/su',
        '/system/xbin/su',
      ];
      for (final path in rootPaths) {
        if (await File(path).exists()) return true;
      }
      return false;
    }
  }

  Future<void> checkSecurity() async {
    if (await isDeviceRooted()) {
      // Show warning, disable trading features
      _showRootWarning();
    }
  }
}
```

---

## 7. App Store Deployment

### 7.1 Google Play Store

| Requirement | Detail |
|-------------|--------|
| **ESO Registration** | Wajib registrasi di Kemkominfo (PP 71/2019) |
| **Data localization** | Data center di Indonesia (OJK Reg 3/2024) |
| **Target SDK** | Android 14 (API 34) minimum |
| **Min SDK** | Android 8.0 (API 26) |
| **Bundle format** | AAB (Android App Bundle) |
| **Size limit** | <150MB (AAB), use Dynamic Delivery untuk larger |
| **Privacy Policy** | Wajib, Bahasa Indonesia |
| **Data Safety form** | Deklarasi data yang dikumpulkan |
| **Content rating** | PEGI 12+ (financial content) |

### 7.2 Apple App Store

| Requirement | Detail |
|-------------|--------|
| **Min iOS** | iOS 14+ |
| **App Store Connect** | Developer account ($99/year) |
| **App Review** | Review process 1-7 days |
| **Privacy Nutrition Label** | Deklarasi data usage |
| **App Tracking Transparency** | Request permission untuk tracking |
| **Encryption export** | Declare use of encryption |

### 7.3 CI/CD Pipeline

```
┌──────────────────────────────────────────────────────────────┐
│                   MOBILE CI/CD PIPELINE                      │
│                                                              │
│  1. Code commit → GitHub                                     │
│     ↓                                                        │
│  2. CI: lint + test (Flutter test)                           │
│     ↓                                                        │
│  3. Build: Flutter build appbundle / ipa                     │
│     ↓                                                        │
│  4. Security scan: obfuscation, dependency check             │
│     ↓                                                        │
│  5. Internal testing: Firebase App Distribution              │
│     ↓                                                        │
│  6. QA: Manual + automated (integration test)                │
│     ↓                                                        │
│  7. Staging: Play Console Internal Track / TestFlight        │
│     ↓                                                        │
│  8. Production: Play Store Production / App Store            │
│     ↓                                                        │
│  9. Monitor: Crashlytics, Performance Monitoring             │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 8. Performance & Data Optimization

### 8.1 Data Usage Optimization

| Technique | Impact | Implementasi |
|-----------|--------|-------------|
| **Delta updates** | -70% data | Hanya kirim perubahan, bukan full snapshot |
| **Response compression** | -60% data | Gzip/Brotli di API |
| **Image compression** | -80% data | WebP, lazy load, thumbnail |
| **Chart data sampling** | -90% data | Downsample untuk zoom out |
| **Pagination** | -95% data | Load 20 items per page |
| **Conditional polling** | -50% battery | Poll hanya saat app foreground |

### 8.2 Chart Rendering Optimization

```dart
class OptimizedChart extends StatelessWidget {
  final List<CandleData> candles;

  @override
  Widget build(BuildContext context) {
    // Downsample untuk performance
    final displayData = _downsample(candles, maxPoints: 200);

    return FlChart(
      data: LineChartData(
        lineBarsData: [
          LineChartBarData(
            spots: displayData.map((c) => FlSpot(c.x, c.close)).toList(),
            isCurved: false,
            barWidth: 1.5,
            isStrokeCapRound: true,
            dotData: FlDotData(show: false),  // Hide dots untuk performance
          ),
        ],
        titlesData: FlTitlesData(
          show: true,
          // Minimal titles untuk reduce rendering
          topTitles: AxisTitles(sideTitles: SideTitles(showTitles: false)),
          rightTitles: AxisTitles(sideTitles: SideTitles(showTitles: false)),
        ),
        gridData: FlGridData(show: false),  // Hide grid untuk performance
        borderData: FlBorderData(show: false),
        clipData: true,  // Clip untuk prevent overdraw
      ),
    );
  }

  List<CandleData> _downsample(List<CandleData> data, {required int maxPoints}) {
    if (data.length <= maxPoints) return data;
    final step = data.length ~/ maxPoints;
    return data.where((_, i) => i % step == 0).toList();
  }
}
```

### 8.3 Memory Management

| Strategy | Implementasi |
|----------|-------------|
| **Lazy loading** | Load stock data hanya saat dibuka |
| **Cache eviction** | LRU cache, max 50 stock di memory |
| **Image cache** | CachedNetworkImage, max 100MB |
| **Dispose controllers** | Dispose StreamControllers saat widget unmount |
| **Avoid memory leaks** | Use `const` constructors, avoid global state |

---

## 9. Implementasi

### 9.1 Project Structure (Flutter)

```
trading_app/
├── lib/
│   ├── main.dart
│   ├── app.dart                    # App widget, routing
│   ├── core/
│   │   ├── api/
│   │   │   ├── api_client.dart     # REST API client
│   │   │   ├── websocket_client.dart  # WebSocket for real-time
│   │   │   └── interceptors.dart   # Auth, logging, error
│   │   ├── security/
│   │   │   ├── biometric.dart      # Biometric auth
│   │   │   ├── secure_storage.dart # Keychain/Keystore
│   │   │   └── certificate_pinning.dart
│   │   ├── notifications/
│   │   │   └── push_service.dart   # FCM push notification
│   │   └── utils/
│   │       ├── connectivity.dart   # Online/offline detection
│   │       └── formatters.dart     # Currency, date, number
│   ├── features/
│   │   ├── auth/                   # Login, register, KYC
│   │   ├── dashboard/              # Main dashboard
│   │   ├── watchlist/              # Watchlist management
│   │   ├── stock_detail/           # Stock detail + chart
│   │   ├── order_entry/            # Buy/sell order
│   │   ├── portfolio/              # Portfolio view
│   │   ├── screener/               # Stock screener
│   │   ├── syariah/                # Sharia mode
│   │   ├── support/                # Customer support chat
│   │   └── settings/               # App settings
│   ├── models/                     # Data models
│   ├── repositories/               # Data repositories
│   └── widgets/                    # Shared widgets
├── assets/
│   ├── images/
│   ├── icons/
│   └── fonts/
├── test/                           # Unit & widget tests
├── android/                        # Android-specific
├── ios/                            # iOS-specific
└── pubspec.yaml
```

---

## 10. Adopsi dari Codebase Existing

### 10.1 Frontend Existing (Next.js)

Codebase sudah punya frontend Next.js di `frontend/`. Mobile app bisa:

1. **Share API layer** — API endpoints sama untuk web dan mobile
2. **Share data models** — TypeScript types → Dart classes (dengan codegen)
3. **Share business logic** — Decision engine, risk engine tetap di backend (Python)

### 10.2 API yang Sudah Ada

| API Existing | Mobile Usage |
|--------------|-------------|
| `GET /api/tickers` | Stock list |
| `GET /api/data/ohlcv` | Chart data |
| `GET /api/recommend/{ticker}` | Recommendation |
| `GET /api/explain/{ticker}` | XAI narrative |
| `POST /api/scores/compute` | Compute scores |
| `POST /api/backtest` | Backtest |
| `GET /api/monitor` | System health |
| `WS /ws/orders` | Real-time order updates |
| `WS /ws/prices` | Real-time price feed |

### 10.3 Yang Perlu Ditambah di Backend

| Endpoint | Untuk Mobile |
|----------|-------------|
| `POST /api/devices/register` | Register FCM/APNs token |
| `POST /api/devices/unregister` | Unregister device |
| `GET /api/user/preferences` | User preferences (sharia mode, etc.) |
| `PUT /api/user/preferences` | Update preferences |
| `POST /api/biometric/challenge` | Biometric auth challenge |
| `POST /api/biometric/verify` | Verify biometric signature |

---

## 11. Checklist Implementasi

### Phase 1: Foundation (4-6 minggu)

- [ ] Flutter project setup dengan routing (GoRouter)
- [ ] API client dengan interceptors (auth, error, logging)
- [ ] WebSocket client untuk real-time data
- [ ] Secure storage (token, PIN)
- [ ] Login + biometric auth
- [ ] Basic dashboard + watchlist

### Phase 2: Trading Features (4-6 minggu)

- [ ] Stock detail + chart (candlestick)
- [ ] Order entry (buy/sell) dengan biometric confirm
- [ ] Portfolio view dengan PnL
- [ ] Screener dengan filter
- [ ] Price alert setup

### Phase 3: Offline & Notifications (3-4 minggu)

- [ ] Offline order queue
- [ ] Local cache (Hive/SQLite)
- [ ] Push notification (FCM)
- [ ] Connectivity detection + auto-sync
- [ ] Conflict resolution

### Phase 4: Security & Polish (3-4 minggu)

- [ ] Certificate pinning
- [ ] Root/jailbreak detection
- [ ] App attestation (Play Integrity)
- [ ] Anti-screenshot di halaman sensitif
- [ ] Performance optimization (chart, memory)
- [ ] Crashlytics integration

### Phase 5: Deployment (2-3 minggu)

- [ ] ESO registration (Kemkominfo)
- [ ] Google Play Store submission
- [ ] Apple App Store submission
- [ ] Privacy policy (Bahasa Indonesia)
- [ ] Data Safety form
- [ ] CI/CD pipeline setup

---

## Referensi

### Internal
- `32-ui-ux-design-trading-app.md` — UI/UX design untuk trading app
- `37-bahasa-pemrograman-tech-stack.md` — Tech stack recommendation
- `28-api-design-integration-patterns.md` — API design patterns
- `36-gap-data-timezone-global-idx.md` — Data delay & timezone

### External
- Flutter — https://flutter.dev
- React Native — https://reactnative.dev
- Firebase Cloud Messaging — https://firebase.google.com/docs/cloud-messaging
- Google Play Console — https://play.google.com/console
- Apple App Store Connect — https://appstoreconnect.apple.com
- PP 71/2019 — Penyelenggaraan Sistem dan Transaksi Elektronik
- OJK Reg 3/2024 — Fintech data localization

---

> **Catatan:** Mobile app untuk investor ritel Indonesia harus Android-first, low-end friendly, dan data-efficient. Offline support bukan nice-to-have melainkan necessity mengingat kualitas jaringan di Indonesia. Security mobile (certificate pinning, root detection, secure storage) wajib untuk aplikasi yang menangani transaksi finansial.
