"""Leverage Advisor (pustaka/18 §6.1, pustaka/31, pustaka/07).

Memberikan saran leverage yang terukur dan dapat dipertanggungjawabkan
berdasarkan:
- Kelly criterion (theoretical optimal leverage)
- Volatility regime (haircut untuk vol tinggi)
- Drawdown saat ini (haircut jika DD mendekati threshold)
- Confidence sinyal (haircut untuk confidence rendah)
- Asset class max leverage (InstrumentSpec.leverage_max)
- Circuit breaker (leverage = 1.0 jika triggered)
- Win rate dan risk-reward profile

Prinsip: konservatif. Tidak pernah merekomendasikan leverage > asset_max.
Selalu memberikan rasional dan peringatan risiko.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class LeverageLevel(Enum):
    """Kategori level leverage."""

    NONE = "none"          # 1.0x — tidak ada leverage
    CONSERVATIVE = "conservative"  # 1.0x-2.0x
    MODERATE = "moderate"  # 2.0x-5.0x
    AGGRESSIVE = "aggressive"  # 5.0x-10.0x
    EXTREME = "extreme"    # >10.0x (hanya untuk forex/derivatif)


@dataclass
class LeverageConfig:
    """Konfigurasi leverage yang dipilih user via toggle.

    User dapat mengaktifkan/menonaktifkan leverage dan membatasi maksimum.
    """

    enabled: bool = False
    max_leverage: float = 2.0
    auto_apply: bool = False
    confirmed_risk: bool = False
    confirmed_margin_call: bool = False
    confirmed_liquidation: bool = False

    def is_ready(self) -> bool:
        """Apakah semua konfirmasi sudah dicentang."""
        return (
            self.enabled
            and self.confirmed_risk
            and self.confirmed_margin_call
            and self.confirmed_liquidation
        )


@dataclass
class LeverageHaircut:
    """Satu faktor haircut yang diterapkan."""

    name: str
    factor: float
    detail: str


@dataclass
class LeverageRecommendation:
    """Saran leverage dengan justifikasi lengkap."""

    ticker: str
    recommended_leverage: float
    level: LeverageLevel
    theoretical_kelly_leverage: float
    asset_class_max: float
    user_max: float
    haircuts: list[LeverageHaircut] = field(default_factory=list)
    rationale: str = ""
    warnings: list[str] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)
    margin_required: float = 0.0
    liquidation_price: float = 0.0
    max_loss_at_leverage: float = 0.0
    effective_capital: float = 0.0
    leveraged_position_value: float = 0.0
    can_apply: bool = False
    rejection_reason: str | None = None


class LeverageAdvisor:
    """Advisor leverage berbasis Kelly criterion dengan haircuts konservatif.

    Pipeline:
    1. Hitung theoretical Kelly leverage dari win_rate, avg_win, avg_loss
    2. Ambil asset_class_max dari InstrumentSpec
    3. Terapkan haircuts:
       a. Volatility haircut (target 20% annual vol)
       b. Drawdown haircut (semakin dekat ke threshold, semakin besar haircut)
       c. Confidence haircut (semakin rendah, semakin besar haircut)
       d. Circuit breaker (leverage = 1.0 jika triggered)
    4. Cap pada min(theoretical, asset_max, user_max)
    5. Floor pada 1.0 (tidak pernah short leverage)
    6. Hitung margin, liquidation price, max loss
    7. Hasilkan rationale dan warnings
    """

    TARGET_VOL_PCT = 20.0
    MAX_DRAWDOWN_PCT = 10.0
    MIN_CONFIDENCE_FOR_LEVERAGE = 70.0

    def __init__(
        self,
        target_vol_pct: float = 20.0,
        max_drawdown_pct: float = 10.0,
        min_confidence: float = 70.0,
    ) -> None:
        self.target_vol_pct = target_vol_pct
        self.max_drawdown_pct = max_drawdown_pct
        self.min_confidence = min_confidence

    def advise(
        self,
        ticker: str,
        capital: float,
        price: float,
        asset_class_max: float = 1.0,
        kelly_fraction: float | None = None,
        win_rate: float | None = None,
        avg_win: float | None = None,
        avg_loss: float | None = None,
        volatility_pct: float | None = None,
        drawdown_pct: float = 0.0,
        confidence: float = 100.0,
        circuit_breaker_triggered: bool = False,
        leverage_config: LeverageConfig | None = None,
        stop_loss: float = 0.0,
    ) -> LeverageRecommendation:
        """Berikan saran leverage untuk satu instrumen.

        Args:
            ticker: Ticker instrumen.
            capital: Modal yang dialokasikan (IDR).
            price: Harga saat ini.
            asset_class_max: Leverage maksimum untuk asset class ini.
            kelly_fraction: Kelly fraction (0-1) jika sudah dihitung.
            win_rate: Win rate historis (0-1) untuk menghitung Kelly.
            avg_win: Rata-rata win (%) untuk Kelly.
            avg_loss: Rata-rata loss (%) untuk Kelly.
            volatility_pct: Volatilitas annualized (%).
            drawdown_pct: Drawdown saat ini (%).
            confidence: Confidence sinyal (0-100).
            circuit_breaker_triggered: Apakah circuit breaker aktif.
            leverage_config: Konfigurasi leverage user.
            stop_loss: Stop loss price untuk hitung max loss.

        Returns:
            LeverageRecommendation dengan saran dan justifikasi.
        """
        config = leverage_config or LeverageConfig()
        haircuts: list[LeverageHaircut] = []
        warnings: list[str] = []
        conditions: list[str] = []
        rejection_reason: str | None = None

        # --- Gate 0: Leverage disabled ---
        if not config.enabled:
            return self._no_leverage(
                ticker, capital, price, asset_class_max, config.max_leverage,
                "Leverage tidak diaktifkan oleh user.", can_apply=False,
                rejection_reason="LEVERAGE_DISABLED",
            )

        # --- Gate 1: Circuit breaker ---
        if circuit_breaker_triggered:
            return self._no_leverage(
                ticker, capital, price, asset_class_max, config.max_leverage,
                "Circuit breaker aktif — leverage dinonaktifkan.",
                can_apply=False,
                rejection_reason="CIRCUIT_BREAKER",
            )

        # --- Gate 2: Asset class tidak mendukung leverage ---
        if asset_class_max <= 1.0:
            return self._no_leverage(
                ticker, capital, price, asset_class_max, config.max_leverage,
                f"Asset class ini tidak mendukung leverage (max: {asset_class_max}x).",
                can_apply=False,
                rejection_reason="ASSET_NO_LEVERAGE",
            )

        # --- Gate 3: Konfirmasi user ---
        if not config.is_ready():
            missing = []
            if not config.confirmed_risk:
                missing.append("pemahaman risiko leverage")
            if not config.confirmed_margin_call:
                missing.append("pemahaman margin call")
            if not config.confirmed_liquidation:
                missing.append("pemahaman likuidasi paksa")
            return self._no_leverage(
                ticker, capital, price, asset_class_max, config.max_leverage,
                f"Konfirmasi belum lengkap: {', '.join(missing)}.",
                can_apply=False,
                rejection_reason="CONFIRMATION_INCOMPLETE",
            )

        # --- Step 1: Theoretical Kelly Leverage ---
        if kelly_fraction is not None and kelly_fraction > 0:
            # Kelly leverage = 1 / (1 - kelly_fraction) for full Kelly
            # We use half-Kelly which is already in kelly_fraction
            theoretical = 1.0 / (1.0 - kelly_fraction) if kelly_fraction < 1.0 else 10.0
        elif (
            win_rate is not None
            and avg_win is not None
            and avg_loss is not None
            and avg_loss != 0
        ):
            b = abs(avg_win / avg_loss)
            w = win_rate
            q = 1 - w
            kelly = (b * w - q) / b
            half_kelly = max(0.0, kelly * 0.5)
            theoretical = 1.0 / (1.0 - half_kelly) if half_kelly < 1.0 else 10.0
        else:
            theoretical = 1.0

        theoretical = max(1.0, theoretical)

        # --- Step 2: Apply haircuts ---
        leverage = theoretical

        # Haircut a: Volatility
        if volatility_pct is not None and volatility_pct > self.target_vol_pct:
            vol_factor = self.target_vol_pct / volatility_pct
            vol_factor = max(0.25, vol_factor)  # Floor at 25%
            leverage *= vol_factor
            haircuts.append(LeverageHaircut(
                name="volatility",
                factor=vol_factor,
                detail=f"Vol {volatility_pct:.1f}% > target {self.target_vol_pct}% — "
                       f"haircut {vol_factor:.2f}x",
            ))
            if volatility_pct > 50:
                warnings.append(
                    f"Volatilitas sangat tinggi ({volatility_pct:.1f}%) — "
                    f"leverage berisiko besar."
                )

        # Haircut b: Drawdown
        if drawdown_pct > 0:
            dd_factor = max(0.0, 1.0 - (drawdown_pct / self.max_drawdown_pct))
            leverage *= dd_factor
            haircuts.append(LeverageHaircut(
                name="drawdown",
                factor=dd_factor,
                detail=f"Drawdown {drawdown_pct:.1f}% / max {self.max_drawdown_pct}% — "
                       f"haircut {dd_factor:.2f}x",
            ))
            if drawdown_pct > self.max_drawdown_pct * 0.7:
                warnings.append(
                    f"Drawdown {drawdown_pct:.1f}% mendekati threshold "
                    f"({self.max_drawdown_pct}%). Leverage dikurangi signifikan."
                )

        # Haircut c: Confidence
        if confidence < 100:
            conf_factor = max(0.3, confidence / 100.0)
            leverage *= conf_factor
            haircuts.append(LeverageHaircut(
                name="confidence",
                factor=conf_factor,
                detail=f"Confidence {confidence:.1f}% — haircut {conf_factor:.2f}x",
            ))
            if confidence < self.min_confidence:
                warnings.append(
                    f"Confidence {confidence:.1f}% di bawah minimum "
                    f"{self.min_confidence}% untuk leverage."
                )

        # --- Step 3: Cap ---
        leverage = min(leverage, asset_class_max, config.max_leverage)
        leverage = max(1.0, leverage)

        # --- Step 4: Round to reasonable precision ---
        leverage = round(leverage, 2)

        # --- Step 5: Determine level ---
        level = self._classify_level(leverage, asset_class_max)

        # --- Step 6: Calculate margin and risk ---
        effective_capital = capital
        leveraged_value = capital * leverage
        margin_required = leveraged_value / leverage if leverage > 0 else capital

        # Liquidation price: price drop that wipes out margin
        # For leverage L, a price drop of (1/L) = 100% loss
        liquidation_pct = 1.0 / leverage if leverage > 0 else 1.0
        liquidation_price = price * (1.0 - liquidation_pct)

        # Max loss at leverage (if stop loss hit)
        if stop_loss > 0 and stop_loss < price:
            loss_per_share = price - stop_loss
            shares = leveraged_value / price
            max_loss = loss_per_share * shares
        else:
            max_loss = leveraged_value  # Worst case: total loss

        # --- Step 7: Rationale ---
        rationale_parts: list[str] = []
        rationale_parts.append(
            f"Kelly theoretical: {theoretical:.2f}x."
        )
        if haircuts:
            haircut_summary = ", ".join(
                f"{h.name}({h.factor:.2f})" for h in haircuts
            )
            rationale_parts.append(f"Haircuts: {haircut_summary}.")
        rationale_parts.append(
            f"Cap: asset_max={asset_class_max}x, user_max={config.max_leverage}x."
        )
        rationale_parts.append(
            f"Final: {leverage:.2f}x ({level.value})."
        )
        rationale_parts.append(
            f"Modal Rp {capital:,.0f} → posisi Rp {leveraged_value:,.0f}."
        )

        # --- Step 8: Conditions ---
        conditions.append(
            f"Stop loss wajib pada Rp {stop_loss:,.0f}" if stop_loss > 0 else
            "Stop loss wajib dipasang."
        )
        conditions.append(
            f"Liquidation price: Rp {liquidation_price:,.0f} "
            f"({-liquidation_pct*100:.1f}% dari harga saat ini)."
        )
        conditions.append(
            f"Max loss jika SL hit: Rp {max_loss:,.0f}."
        )
        if leverage > 2.0:
            conditions.append(
                "Monitor posisi secara real-time — leverage >2x berisiko margin call."
            )

        # --- Step 9: Can apply ---
        can_apply = (
            leverage > 1.0
            and config.is_ready()
            and not circuit_breaker_triggered
            and asset_class_max > 1.0
        )

        if not can_apply and leverage <= 1.0:
            warnings.append("Leverage efektif 1.0x — tidak ada leverage yang diterapkan.")

        return LeverageRecommendation(
            ticker=ticker,
            recommended_leverage=leverage,
            level=level,
            theoretical_kelly_leverage=round(theoretical, 2),
            asset_class_max=asset_class_max,
            user_max=config.max_leverage,
            haircuts=haircuts,
            rationale=" ".join(rationale_parts),
            warnings=warnings,
            conditions=conditions,
            margin_required=round(margin_required, 2),
            liquidation_price=round(liquidation_price, 2),
            max_loss_at_leverage=round(max_loss, 2),
            effective_capital=round(effective_capital, 2),
            leveraged_position_value=round(leveraged_value, 2),
            can_apply=can_apply,
            rejection_reason=rejection_reason,
        )

    def _no_leverage(
        self,
        ticker: str,
        capital: float,
        price: float,
        asset_class_max: float,
        user_max: float,
        reason: str,
        can_apply: bool = False,
        rejection_reason: str | None = None,
    ) -> LeverageRecommendation:
        """Return recommendation with no leverage."""
        return LeverageRecommendation(
            ticker=ticker,
            recommended_leverage=1.0,
            level=LeverageLevel.NONE,
            theoretical_kelly_leverage=1.0,
            asset_class_max=asset_class_max,
            user_max=user_max,
            rationale=reason,
            conditions=["Tidak ada leverage yang diterapkan."],
            margin_required=capital,
            liquidation_price=0.0,
            max_loss_at_leverage=capital,
            effective_capital=capital,
            leveraged_position_value=capital,
            can_apply=can_apply,
            rejection_reason=rejection_reason,
        )

    def _classify_level(
        self, leverage: float, asset_class_max: float,
    ) -> LeverageLevel:
        """Klasifikasi level leverage."""
        if leverage <= 1.0:
            return LeverageLevel.NONE
        if leverage <= 2.0:
            return LeverageLevel.CONSERVATIVE
        if leverage <= 5.0:
            return LeverageLevel.MODERATE
        if leverage <= 10.0:
            return LeverageLevel.AGGRESSIVE
        return LeverageLevel.EXTREME


def get_asset_class_leverage_max(asset_class: str) -> float:
    """Get leverage max for asset class string.

    Args:
        asset_class: Asset class string (equity, etf, bond, commodity, forex, crypto, derivative).

    Returns:
        Maximum leverage for that asset class.
    """
    from market.multi_asset import INSTRUMENT_SPECS, AssetClass

    try:
        ac = AssetClass(asset_class)
        return INSTRUMENT_SPECS[ac].leverage_max
    except (ValueError, KeyError):
        return 1.0
