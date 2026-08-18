#!/usr/bin/env python3
"""
Colombian Stocks Technical Analysis Report
Merlin's Market Toolkit — All 8 Indicators
Data: Yahoo Finance (.CL suffix for local BVC / .COL legacy / or ADR)
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# ──────────────────────────────────────────────────────────
# CONFIGURATION
# ──────────────────────────────────────────────────────────
# Format: (ticker, display_name, currency_label)
#   .CL = local BVC Colombian stocks in COP
#   No suffix = ADR listed on NYSE in USD
TICKERS = [
    ("ECOPETROL.CL",  "Ecopetrol (Local)",      "COP"),
    ("ISA.CL",        "ISA (Local)",             "COP"),
    ("GRUPOAVAL.CL",  "Grupo Aval (Local)",      "COP"),
    ("NUTRESA.CL",    "Nutresa (Local)",          "COP"),
    ("CEMARGOS.CL",   "Cementos Argos (Local)",  "COP"),
    ("EC",            "Ecopetrol (ADR)",          "USD"),
    ("AVAL",          "Grupo Aval (ADR)",        "USD"),
    ("CIB",           "Bancolombia (ADR)",       "USD"),
]

LOOKBACK_DAYS = 120
RSI_PERIOD = 14
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
STOCH_K, STOCH_D = 14, 3
BB_PERIOD, BB_STD = 20, 2
ATR_PERIOD = 14
MFI_PERIOD = 14
ICHIMOKU_TENKAN = 9
ICHIMOKU_KIJUN = 26
ICHIMOKU_SPAN_B = 52


def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(span=period, adjust=False).mean()
    avg_loss = loss.ewm(span=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def calculate_macd(series, fast=12, slow=26, signal=9):
    ema_f = series.ewm(span=fast, adjust=False).mean()
    ema_s = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_f - ema_s
    sig_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, sig_line, macd_line - sig_line


def calculate_stochastic(df, k=14, d=3):
    low_k = df['Low'].rolling(window=k).min()
    high_k = df['High'].rolling(window=k).max()
    stoch_k = 100 * ((df['Close'] - low_k) / (high_k - low_k).replace(0, np.nan))
    stoch_d = stoch_k.rolling(window=d).mean()
    return stoch_k, stoch_d


def calculate_roc(series, period=12):
    return series.pct_change(periods=period) * 100


def calculate_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()


def calculate_atr(df, period=14):
    h, l, c = df['High'], df['Low'], df['Close']
    tr = pd.concat([
        h - l,
        (h - c.shift()).abs(),
        (l - c.shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()


def calculate_bollinger(series, period=20, std_dev=2):
    middle = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper = middle + std_dev * std
    lower = middle - std_dev * std
    bbp = (series - lower) / (upper - lower).replace(0, np.nan)
    bandwidth = (upper - lower) / middle
    return upper, lower, middle, bbp, bandwidth


def calculate_mfi(df, period=14):
    typical = (df['High'] + df['Low'] + df['Close']) / 3
    raw_mf = typical * df['Volume']
    flow = raw_mf.diff()
    pos = flow.where(flow > 0, 0).rolling(window=period).sum()
    neg = flow.where(flow < 0, 0).abs().rolling(window=period).sum()
    mf_ratio = pos / neg.replace(0, np.nan)
    return 100 - (100 / (1 + mf_ratio))


def calculate_ichimoku(df):
    tenkan = (
        df['High'].rolling(window=ICHIMOKU_TENKAN).max()
        + df['Low'].rolling(window=ICHIMOKU_TENKAN).min()
    ) / 2
    kijun = (
        df['High'].rolling(window=ICHIMOKU_KIJUN).max()
        + df['Low'].rolling(window=ICHIMOKU_KIJUN).min()
    ) / 2
    senkou_a = ((tenkan + kijun) / 2).shift(26)
    senkou_b = (
        df['High'].rolling(window=ICHIMOKU_SPAN_B).max()
        + df['Low'].rolling(window=ICHIMOKU_SPAN_B).min()
    ) / 2
    senkou_b = senkou_b.shift(26)
    chikou = df['Close'].shift(-26)
    cloud_thick = (senkou_a - senkou_b).abs()
    return tenkan, kijun, senkou_a, senkou_b, chikou, cloud_thick


def calculate_obv(df):
    return (df['Volume'] * (~df['Close'].diff().le(0) * 2 - 1)).cumsum()


def classify(val, kind):
    if kind == 'rsi':
        if val < 30: return f"oversold ({val:.1f})"
        if val > 70: return f"overbought ({val:.1f})"
        return f"neutral ({val:.1f})"
    if kind == 'stoch':
        if val < 20: return f"oversold ({val:.1f})"
        if val > 80: return f"overbought ({val:.1f})"
        return f"neutral ({val:.1f})"
    if kind == 'roc':
        if val > 5:  return f"strong up ({val:+.1f}%)"
        if val > 1:  return f"rising ({val:+.1f}%)"
        if val < -5: return f"strong down ({val:+.1f}%)"
        if val < -1: return f"falling ({val:+.1f}%)"
        return f"flat ({val:+.1f}%)"
    if kind == 'bbp':
        if val < 0:  return f"below lower band ({val:.2f})"
        if val > 1:  return f"above upper band ({val:.2f})"
        return f"within bands ({val:.2f})"
    if kind == 'bbw':
        if val < 0.05: return f"squeeze ({val:.2%})"
        if val < 0.10: return f"tight ({val:.2%})"
        return f"wide ({val:.2%})"
    if kind == 'mfi':
        if val < 20: return f"oversold ({val:.1f})"
        if val > 80: return f"overbought ({val:.1f})"
        return f"neutral ({val:.1f})"
    return f"{val}"


def build_report(ticker_symbol, name, df, currency="COP"):
    """Build a full technical report for one stock."""
    curr = currency
    pf = f"{curr} $"  # e.g. "COP $" or "USD $"
    close = df['Close']
    now = datetime.now()
    latest_date = df.index[-1]

    # ── Momentum ──
    rsi = calculate_rsi(close, RSI_PERIOD)
    macd_l, macd_s, macd_h = calculate_macd(close)
    stoch_k, stoch_d = calculate_stochastic(df)
    roc = calculate_roc(close)

    # ── Moving Averages ──
    ema9 = calculate_ema(close, 9)
    ema21 = calculate_ema(close, 21)
    ema50 = calculate_ema(close, 50)

    # ── Volume ──
    volume = df['Volume']
    obv = calculate_obv(df)

    # ── ATR ──
    atr = calculate_atr(df, ATR_PERIOD)

    # ── Bollinger ──
    bb_u, bb_l, bb_m, bbp, bbw = calculate_bollinger(close, BB_PERIOD, BB_STD)

    # ── MFI ──
    mfi = calculate_mfi(df, MFI_PERIOD)

    # ── Ichimoku ──
    tenkan, kijun, senkou_a, senkou_b, chikou, cloud_th = calculate_ichimoku(df)

    # ════════ Latest values ════════
    lc = close.iloc[-1]
    lh = df['High'].iloc[-1]
    ll = df['Low'].iloc[-1]
    lv = volume.iloc[-1]
    avg_vol = volume.rolling(20).mean().iloc[-1]
    vol_ratio = lv / avg_vol if pd.notna(avg_vol) and avg_vol > 0 else 1.0

    rsi_v = rsi.iloc[-1]
    macd_v = macd_l.iloc[-1]
    macd_sv = macd_s.iloc[-1]
    macd_hv = macd_h.iloc[-1]
    stoch_kv = stoch_k.iloc[-1]
    stoch_dv = stoch_d.iloc[-1]
    roc_v = roc.iloc[-1]

    e9v = ema9.iloc[-1]
    e21v = ema21.iloc[-1]
    e50v = ema50.iloc[-1]

    obv_v = obv.iloc[-1]
    obv_p = obv.iloc[-2] if len(obv) > 1 else obv_v

    atr_v = atr.iloc[-1]
    atr_pct = (atr_v / lc) * 100 if lc != 0 else 0

    bbp_v = bbp.iloc[-1]
    bbw_v = bbw.iloc[-1]
    bb_u_v = bb_u.iloc[-1]
    bb_l_v = bb_l.iloc[-1]
    bb_m_v = bb_m.iloc[-1]

    mfi_v = mfi.iloc[-1]

    tnk_v = tenkan.iloc[-1]
    kij_v = kijun.iloc[-1]
    ska_v = senkou_a.iloc[-1]
    skb_v = senkou_b.iloc[-1]
    cld_th = cloud_th.iloc[-1] if pd.notna(cloud_th.iloc[-1]) else np.nan

    # ── Interpretations ──

    # Ichimoku cloud position
    if pd.notna(ska_v) and pd.notna(skb_v):
        if lc > max(ska_v, skb_v):
            cloud_pos = "ABOVE the cloud (bullish)"
        elif lc < min(ska_v, skb_v):
            cloud_pos = "BELOW the cloud (bearish)"
        else:
            cloud_pos = "INSIDE the cloud (neutral/chop)"
    else:
        cloud_pos = "N/A (building)"

    # MACD signal
    if macd_v > macd_sv and macd_hv > 0:
        macd_txt = "BULLISH (MACD above signal + positive histo)"
    elif macd_v > macd_sv:
        macd_txt = "MILD BULLISH (MACD above signal)"
    elif macd_v < macd_sv and macd_hv < 0:
        macd_txt = "BEARISH (MACD below signal + negative histo)"
    else:
        macd_txt = "MILD BEARISH (MACD below signal)"

    # EMA crossover
    if e9v > e21v and lc > e9v:
        ema_txt = "BULLISH (EMA9 > EMA21, price above both)"
    elif e9v > e21v:
        ema_txt = "MILD BULLISH (EMA9 > EMA21)"
    elif e9v < e21v and lc < e9v:
        ema_txt = "BEARISH (EMA9 < EMA21, price below both)"
    else:
        ema_txt = "MILD BEARISH (EMA9 < EMA21)"

    trend_bias = "BULLISH BIAS (price above EMA 50)" if lc > e50v else "BEARISH BIAS (price below EMA 50)"

    obv_dir = "rising (accumulation)" if obv_v > obv_p else "falling (distribution)"

    if vol_ratio > 1.5:
        vol_note = "HIGH volume"
    elif vol_ratio > 1.2:
        vol_note = "above average volume"
    elif vol_ratio < 0.6:
        vol_note = "LOW volume"
    else:
        vol_note = "normal volume"

    tk_cross = ""
    if pd.notna(tnk_v) and pd.notna(kij_v):
        tk_cross = "BULLISH TK cross" if tnk_v > kij_v else "BEARISH TK cross"

    # Vol signal
    vol_chg = close.iloc[-1] - close.iloc[-2] if len(close) > 1 else 0
    if vol_ratio > 1.3 and vol_chg > 0:
        vol_sig = "PRICE UP + HIGH VOLUME = strong move (reliable)"
    elif vol_ratio > 1.3 and vol_chg < 0:
        vol_sig = "PRICE DOWN + HIGH VOLUME = strong selling pressure"
    elif vol_ratio < 0.7 and vol_chg > 0:
        vol_sig = "PRICE UP + LOW VOLUME = weak move (possible false breakout)"
    elif vol_ratio < 0.7 and vol_chg < 0:
        vol_sig = "PRICE DOWN + LOW VOLUME = weak selling"
    else:
        vol_sig = "Normal volume, normal price action"

    # OBV divergence
    obv_div = ""
    if len(obv) > 5:
        p_up = close.iloc[-1] > close.iloc[-5]
        p_dn = close.iloc[-1] < close.iloc[-5]
        o_up = obv_v > obv.iloc[-5]
        o_dn = obv_v < obv.iloc[-5]
        if p_up and o_dn:
            obv_div = "⚠ BEARISH DIVERGENCE: price up, OBV down (distribution)"
        elif p_dn and o_up:
            obv_div = "⚡ BULLISH DIVERGENCE: price down, OBV up (accumulation)"
        else:
            obv_div = "No divergence — price and OBV aligned"

    # ── Build report lines ──
    R = []
    def a(s):
        R.append(s)

    a("=" * 78)
    a(f"  {name} ({ticker_symbol}) — Technical Analysis Report")
    a(f"  Generated: {now.strftime('%Y-%b-%d %H:%M UTC')}  |  Price currency: {currency}")
    a(f"  Last Data: {latest_date.strftime('%Y-%b-%d')} ({now - latest_date} ago)")
    a("=" * 78)
    a("")

    a("  PRICE SNAPSHOT")
    a(f"  {'─' * 50}")
    a(f"    Close:        {pf}{lc:>10,.2f}")
    a(f"    High:         {pf}{lh:>10,.2f}")
    a(f"    Low:          {pf}{ll:>10,.2f}")
    a(f"    Range:        {pf}{ll:>,.2f} — {pf}{lh:>,.2f} ({pf}{lh-ll:>,.2f})")
    a(f"    Volume:       {lv:>12,.0f}  ({vol_note})")
    a(f"    Avg Vol(20):  {avg_vol:>12,.0f}")
    a(f"    Trend Bias:   {trend_bias}")
    a("")

    a("  1. MOMENTUM INDICATORS")
    a(f"  {'─' * 50}")
    a(f"    RSI(14):          {classify(rsi_v, 'rsi')}")
    a(f"    MACD:             {macd_txt}")
    a(f"    MACD Histogram:   {macd_hv:>+8.2f}")
    a(f"    Stoch %K(14):     {classify(stoch_kv, 'stoch')}")
    a(f"    Stoch %D(3):      {stoch_dv:.1f}")
    a(f"    ROC(12):          {classify(roc_v, 'roc')}")
    a("")

    a("  2. MOVING AVERAGES")
    a(f"  {'─' * 50}")
    a(f"    EMA 9:            {pf}{e9v:>10,.2f}")
    a(f"    EMA 21:           {pf}{e21v:>10,.2f}")
    a(f"    EMA 50:           {pf}{e50v:>10,.2f}")
    a(f"    EMA Crossover:    {ema_txt}")
    a(f"    Price vs EMA 50:  {(lc/e50v-1)*100 if pd.notna(e50v) and e50v!=0 else 0:+.2f}% from EMA 50")
    a("")

    a("  3. VOLUME")
    a(f"  {'─' * 50}")
    a(f"    Signal:           {vol_sig}")
    a("")

    a("  4. ON-BALANCE VOLUME (OBV)")
    a(f"  {'─' * 50}")
    a(f"    OBV Trend:        {obv_dir}")
    a(f"    Divergence:       {obv_div}")
    a("")

    a("  5. AVERAGE TRUE RANGE (Volatility)  ← NEW")
    a(f"  {'─' * 50}")
    a(f"    ATR(14):          {pf}{atr_v:>10,.2f} ({atr_pct:.2f}% of price)")
    a(f"    Stop-Loss (1.5x): {pf}{lc - 1.5 * atr_v:>10,.2f} ({pf}{1.5*atr_v:>,.2f} risk)")
    a(f"    Target (2x):      {pf}{lc + 2 * atr_v:>10,.2f}")
    a(f"    Risk per share:   {pf}{atr_v:>,.0f}")
    a(f"    Sizing hint:      For 1% risk, trade up to {lc*0.01/atr_v:,.0f} shares")
    a("")

    a(f"  6. BOLLINGER BANDS ({BB_PERIOD}, {BB_STD})  ← NEW")
    a(f"  {'─' * 50}")
    a(f"    Upper Band:       {pf}{bb_u_v:>10,.2f}")
    a(f"    Middle Band:      {pf}{bb_m_v:>10,.2f}")
    a(f"    Lower Band:       {pf}{bb_l_v:>10,.2f}")
    a(f"    %B:               {classify(bbp_v, 'bbp')}")
    a(f"    Bandwidth:        {classify(bbw_v, 'bbw')}")
    if bbw_v < 0.05:
        a("    ⚠ Squeeze detected — watch for imminent breakout!")
    a("")

    a(f"  7. MONEY FLOW INDEX (Volume-weighted RSI)  ← NEW")
    a(f"  {'─' * 50}")
    a(f"    MFI({MFI_PERIOD}):  {classify(mfi_v, 'mfi')}")
    if mfi_v < 20:
        a("    ⚡ Oversold WITH volume confirmation — strong buy setup")
    elif mfi_v > 80:
        a("    ⚠ Overbought WITH volume confirmation — take profits")
    elif rsi_v < 30 and mfi_v > 40:
        a("    ⚠ RSI says oversold but MFI disagrees — wait for volume confirmation")
    elif rsi_v > 70 and mfi_v < 60:
        a("    ⚠ RSI says overbought but MFI disagrees — weak signal, don't short")
    else:
        a("    RSI/MFI aligned — no contradiction")
    a("")

    a("  8. ICHIMOKU CLOUD  ← NEW")
    a(f"  {'─' * 50}")
    a(f"    Tenkan-sen (9):   {pf}{tnk_v:>10,.2f}" if pd.notna(tnk_v) else "    Tenkan-sen (9):   N/A")
    a(f"    Kijun-sen (26):   {pf}{kij_v:>10,.2f}" if pd.notna(kij_v) else "    Kijun-sen (26):   N/A")
    a(f"    Senkou A (lead):  {pf}{ska_v:>10,.2f}" if pd.notna(ska_v) else "    Senkou A (lead):  N/A")
    a(f"    Senkou B (lead):  {pf}{skb_v:>10,.2f}" if pd.notna(skb_v) else "    Senkou B (lead):  N/A")
    a(f"    Cloud Position:   {cloud_pos}")
    a(f"    TK Cross:         {tk_cross}")
    if pd.notna(cld_th):
        if cld_th / lc > 0.05:
            a("    Cloud is THICK (strong support/resistance zone)")
        else:
            a("    Cloud is THIN (breakout likely)")
    a("")

    # ── Signal Synthesis ──
    a("  SIGNAL SYNTHESIS")
    a(f"  {'─' * 50}")

    bullish = 0
    bearish = 0
    notes = []

    if rsi_v < 30:
        bullish += 1; notes.append("RSI oversold — potential reversal")
    elif rsi_v > 70:
        bearish += 1; notes.append("RSI overbought — potential exhaustion")

    if macd_v > macd_sv and macd_hv > 0:
        bullish += 1; notes.append("MACD bullish — momentum up")
    elif macd_v < macd_sv and macd_hv < 0:
        bearish += 1; notes.append("MACD bearish — momentum down")

    if e9v > e21v and lc > e9v:
        bullish += 1; notes.append("Bullish EMA alignment")
    elif e9v < e21v and lc < e9v:
        bearish += 1; notes.append("Bearish EMA alignment")

    if lc > e50v:
        bullish += 1; notes.append("Price above EMA 50 (bullish bias)")
    else:
        bearish += 1; notes.append("Price below EMA 50 (bearish bias)")

    if mfi_v < 20:
        bullish += 1; notes.append("MFI oversold — volume-confirmed bottom")
    elif mfi_v > 80:
        bearish += 1; notes.append("MFI overbought — volume-confirmed top")

    if "BULLISH DIVERGENCE" in obv_div:
        bullish += 2; notes.append("OBV bullish divergence — accumulation before price move")
    elif "BEARISH DIVERGENCE" in obv_div:
        bearish += 2; notes.append("OBV bearish divergence — distribution before price drop")

    if pd.notna(ska_v) and pd.notna(skb_v):
        if lc > max(ska_v, skb_v):
            bullish += 1; notes.append("Above Ichimoku cloud — trend up")
        elif lc < min(ska_v, skb_v):
            bearish += 1; notes.append("Below Ichimoku cloud — trend down")

    if pd.notna(tnk_v) and pd.notna(kij_v):
        if tnk_v > kij_v:
            bullish += 1; notes.append("TK cross bullish")
        else:
            bearish += 1; notes.append("TK cross bearish")

    total = bullish + bearish
    score = (bullish / total * 100) if total > 0 else 50

    if score >= 65:
        verdict = "\U0001f7e2 BULLISH"
    elif score >= 45:
        verdict = "\U0001f7e1 NEUTRAL / MIXED"
    else:
        verdict = "\U0001f534 BEARISH"

    a(f"    Bullish signals:  {bullish}")
    a(f"    Bearish signals:  {bearish}")
    a(f"    Bias score:       {score:.0f}% bullish")
    a(f"    Verdict:          {verdict}")
    a("")
    a("  Key Notes:")
    for n in notes[:6]:
        a(f"    \u2022 {n}")
    a("")
    a("=" * 78)
    a("")

    return "\n".join(R)


def build_telegram_report(symbol, name, df, currency):
    """Compact one-paragraph summary per stock for Telegram."""
    curr = currency
    pf = f"{curr} $"
    close = df['Close']
    volume = df['Volume']
    obv = calculate_obv(df)

    rsi = calculate_rsi(close, RSI_PERIOD).iloc[-1]
    macd_l, macd_s, macd_h = calculate_macd(close)
    macd_bull = macd_l.iloc[-1] > macd_s.iloc[-1] and macd_h.iloc[-1] > 0
    macd_bear = macd_l.iloc[-1] < macd_s.iloc[-1] and macd_h.iloc[-1] < 0
    ema9 = calculate_ema(close, 9).iloc[-1]
    ema21 = calculate_ema(close, 21).iloc[-1]
    ema50 = calculate_ema(close, 50).iloc[-1]
    lc = close.iloc[-1]
    atr = calculate_atr(df, ATR_PERIOD).iloc[-1]
    mfi = calculate_mfi(df, MFI_PERIOD).iloc[-1]
    tenkan, kijun, sk_a, sk_b, _, _ = calculate_ichimoku(df)
    avg_vol = volume.rolling(20).mean().iloc[-1]
    lv = volume.iloc[-1]
    vol_ratio = lv / avg_vol if pd.notna(avg_vol) and avg_vol > 0 else 1.0
    obv_v = obv.iloc[-1]
    obv_p = obv.iloc[-5] if len(obv) > 5 else obv_v

    obv_dir = "accumulation" if obv_v > obv_p else "distribution"

    # Volumen signal
    vol_chg = close.iloc[-1] - close.iloc[-2] if len(close) > 1 else 0
    if vol_ratio > 1.3 and vol_chg > 0:
        vol_sig = "+HIGH VOL"
    elif vol_ratio > 1.3 and vol_chg < 0:
        vol_sig = "-HIGH VOL"
    elif vol_ratio < 0.7 and vol_chg > 0:
        vol_sig = "+LOW VOL"
    elif vol_ratio < 0.7 and vol_chg < 0:
        vol_sig = "-LOW VOL"
    else:
        vol_sig = "norm vol"

    # RSI signal
    if rsi < 30: rsi_sig = "oversold"
    elif rsi > 70: rsi_sig = "overbought"
    else: rsi_sig = "neutral"

    # MACD
    macd_sig = "bull" if macd_bull else ("bear" if macd_bear else "neutral")

    # EMA alignment
    if ema9 > ema21 and lc > ema9:
        ema_sig = "bull"
    elif ema9 < ema21 and lc < ema9:
        ema_sig = "bear"
    else:
        ema_sig = "mixed"

    trend = "bull" if lc > ema50 else "bear"

    # MFI/RSI conflict
    if rsi > 70 and mfi < 60:
        mfi_note = "RSI overbought but MFI neutral"
    elif rsi < 30 and mfi > 40:
        mfi_note = "RSI oversold but MFI neutral"
    else:
        mfi_note = ""

    # OBV divergence
    obv_div = ""
    if len(obv) > 5:
        p_up = close.iloc[-1] > close.iloc[-5]
        p_dn = close.iloc[-1] < close.iloc[-5]
        o_up = obv_v > obv.iloc[-5]
        o_dn = obv_v < obv.iloc[-5]
        if p_up and o_dn:
            obv_div = "⚠️bear diver"
        elif p_dn and o_up:
            obv_div = "⚡bull diver"

    # Ichimoku cloud position
    tnk_v = tenkan.iloc[-1]
    kij_v = kijun.iloc[-1]
    tk = "bull" if (pd.notna(tnk_v) and pd.notna(kij_v) and tnk_v > kij_v) else "bear"

    cloud = ""
    if pd.notna(sk_a.iloc[-1]) and pd.notna(sk_b.iloc[-1]):
        if lc > max(sk_a.iloc[-1], sk_b.iloc[-1]):
            cloud = "above"
        elif lc < min(sk_a.iloc[-1], sk_b.iloc[-1]):
            cloud = "below"
        else:
            cloud = "inside"

    # Score
    b, b_count = 0, 0
    if rsi < 30: b += 1
    elif rsi > 70: b -= 1
    if macd_bull: b += 1
    elif macd_bear: b -= 1
    if ema_sig == "bull": b += 1
    elif ema_sig == "bear": b -= 1
    if trend == "bull": b += 1
    else: b -= 1
    if mfi < 20: b += 1
    elif mfi > 80: b -= 1
    if cloud == "above": b += 1
    elif cloud == "below": b -= 1
    if tk == "bull": b += 1
    else: b -= 1
    if "bull diver" in obv_div: b += 2
    elif "bear diver" in obv_div: b -= 2

    if b >= 3: verdict = "🟢BULLISH"
    elif b <= -3: verdict = "🔴BEARISH"
    elif b >= 1: verdict = "🟡MILD BULL"
    elif b <= -1: verdict = "🟡MILD BEAR"
    else: verdict = "⚪NEUTRAL"

    lines = []
    lines.append(f"{verdict}  **{name}** ({symbol})")
    lines.append(f"  Price: {pf}{lc:>,.2f}  |  RSI: {rsi:.0f} ({rsi_sig})  |  MACD: {macd_sig}  |  Vol: {vol_sig}")
    lines.append(f"  Trend: {trend} (EMA50)  |  EMA: {ema_sig}  |  TK: {tk}  |  Cloud: {cloud}  |  ATR: {atr:.0f} ({atr/lc*100:.1f}%)")
    if obv_div:
        lines.append(f"  OBV: {obv_dir} {obv_div}")
    if mfi_note:
        lines.append(f"  MFI: {mfi_note}")
    lines.append("")

    return "\n".join(lines)


def main():
    import sys
    telegram_mode = "--telegram" in sys.argv

    now = datetime.now()
    start_date = now - timedelta(days=LOOKBACK_DAYS)
    end_date = now

    if not telegram_mode:
        print("=" * 78)
        print("  COLOMBIAN STOCKS — TECHNICAL ANALYSIS REPORT")
        print(f"  Generated: {now.strftime('%Y-%b-%d %H:%M')} UTC")
        print(f"  Source: Yahoo Finance (.CL = BVC Local, ADR = NYSE)")
        print(f"  Analyzed: {', '.join(t[0] for t in TICKERS)}")
        print("=" * 78)
        print()

    results = []

    for symbol, name, currency in TICKERS:
        if not telegram_mode:
            print(f"  \u2b07  Fetching {symbol} ({name})… ", end="", flush=True)
        try:
            df = yf.download(symbol, start=start_date, end=end_date, progress=False,
                             auto_adjust=True)
            if df.empty or len(df) < 30:
                if not telegram_mode:
                    print(f"\u26a0  Insufficient data ({len(df)} rows)")
                continue

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            if telegram_mode:
                results.append(build_telegram_report(symbol, name, df, currency))
                if not telegram_mode:
                    print(f"OK ({len(df)} days)")
            else:
                print(f"OK ({len(df)} days)")
                report = build_report(symbol, name, df, currency)
                print(report)

        except Exception as e:
            if not telegram_mode:
                print(f"\u2717 Error: {e}")
            else:
                results.append(f"⚠️  **{name}** ({symbol}) — Error: {e}\n")

    if telegram_mode:
        # Print header
        date_str = now.strftime('%A, %b %d, %Y')
        print(f"\\ud83d\\udcca **COLOMBIAN STOCKS REPORT** — {date_str}")
        print(f"Source: Yahoo Finance (.CL = BVC, ADR = NYSE)")
        print(f"Generated: {now.strftime('%H:%M')} UTC")
        print("")
        print("\\u2501" * 40)
        print("")
        print("\n".join(results))
        print("\\u2501" * 40)
        print("\\ud83d\\udc49 Run with `--full` for full detailed report")
    else:
        print("  \u2713 Done. All reports generated.")
        print("=" * 78)


if __name__ == "__main__":
    main()