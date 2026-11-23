import requests
import urllib3
import streamlit as st

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(page_title="Asisten Sinyal Trading Kripto", layout="centered")
st.title("📊 Asisten Sinyal Trading Kripto")
st.caption("Alat bantu cek arah pasar secara real-time berdasarkan data OKX Futures")

# Pilihan koin dan timeframe (khusus yang didukung OKX)
col_in1, col_in2 = st.columns(2)
with col_in1:
    coin = st.selectbox("Pilih Koin:", ["BTC", "ETH", "SOL", "BNB", "XRP"])
with col_in2:
    period = st.selectbox("Pilih Timeframe:", ["5m", "1H", "1D"], index=0)

st.divider()

HEADERS = {"User-Agent": "Mozilla/5.0"}
BASE_OKX = "https://okx.com"

# ==========================================
# 1. FUNGSI AMBIL DATA REAL-TIME OKX
# ==========================================
def get_okx_long_short(coin, period):
    url = f"{BASE_OKX}/api/v5/rubik/stat/contracts/long-short-account-ratio"
    params = {"ccy": coin, "period": period}
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=10, verify=False)
        res = r.json()
        if res.get("code") == "0" and len(res.get("data", [])) > 0:
            ratio = float(res["data"][0][1])
            return ratio, None
        return None, f"Gagal ambil rasio: {res}"
    except Exception as e:
        return None, str(e)

def get_okx_whale_volume(coin, period):
    url = f"{BASE_OKX}/api/v5/rubik/stat/taker-volume"
    params = {"ccy": coin, "instType": "CONTRACTS", "period": period}
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=10, verify=False)
        res = r.json()
        if res.get("code") == "0" and len(res.get("data", [])) > 0:
            sell_vol = float(res["data"][0][1])
            buy_vol = float(res["data"][0][2])
            ratio_vol = buy_vol / sell_vol if sell_vol > 0 else 1.0
            total = buy_vol + sell_vol
            buy_pct = (buy_vol / total * 100) if total > 0 else 50.0
            sell_pct = (sell_vol / total * 100) if total > 0 else 50.0
            return ratio_vol, buy_pct, sell_pct, None
        return None, None, None, f"Gagal ambil volume: {res}"
    except Exception as e:
        return None, None, None, str(e)

def get_okx_price_and_rsi(coin, period, length=14):
    inst_id = f"{coin}-USDT-SWAP"
    url = f"{BASE_OKX}/api/v5/market/candles"
    params = {"instId": inst_id, "bar": period, "limit": 100}
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=10, verify=False)
        res = r.json()
        if res.get("code") != "0" or len(res.get("data", [])) <= length:
            return None, None, f"Data harga kosong: {res}"
        
        candles = list(reversed(res["data"]))
        closes = [float(c[4]) for c in candles]
        current_price = closes[-1]

        gains = []
        losses = []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i - 1]
            gains.append(max(diff, 0))
            losses.append(max(-diff, 0))

        avg_gain = sum(gains[:length]) / length
        avg_loss = sum(losses[:length]) / length

        for i in range(length, len(gains)):
            avg_gain = (avg_gain * (length - 1) + gains[i]) / length
            avg_loss = (avg_loss * (length - 1) + losses[i]) / length

        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))

        return current_price, rsi, None
    except Exception as e:
        return None, None, str(e)

# ==========================================
# 2. LOGIKA EVALUASI (BAHASA SIMPEL)
# ==========================================
def cek_long_short(rasio):
    if rasio >= 2.50:
        return "⚠️ Terlalu Banyak yang Beli (Waspada Long Squeeze) — Hati-hati harga bisa dibanting turun mendadak.", "error"
    elif 1.20 <= rasio <= 2.49:
        return "📈 Mayoritas Optimis Naik — Kecenderungan harga bergerak naik.", "success"
    elif 0.85 <= rasio <= 1.19:
        return "⚖️ Pasar Seimbang (Sideways) — Pembeli dan penjual sama kuat, harga cenderung datar.", "info"
    elif 0.41 <= rasio <= 0.84:
        return "📉 Mayoritas Pesimis Turun — Kecenderungan harga bergerak turun.", "warning"
    else:
        return "⚠️ Terlalu Banyak yang Jual (Waspada Short Squeeze) — Hati-hati harga bisa ditarik naik mendadak.", "error"

def cek_ritel_vs_whale(akun, volume):
    if akun > 2.0 and volume < 0.9:
        return (
            "🚨 JEBAKAN NAIK (Ritel Beli, Modal Besar Jualan)",
            "Trader kecil ramai-ramai beli, tapi volume jual agresif justru mendominasi. Waspada koreksi turun (Cari peluang Jual / Short).",
            "error"
        )
    elif akun < 0.6 and volume > 1.2:
        return (
            "💎 JEBAKAN TURUN (Ritel Panik Jual, Modal Besar Borong)",
            "Trader kecil ketakutan jual rugi, tapi volume beli agresif justru memborong. Waspada pantulan naik (Cari peluang Beli / Long).",
            "success"
        )
    elif akun > 1.5 and volume > 1.2:
        return (
            "🚀 NAIK KOMPAK (Ritel & Volume Besar Satu Suara)",
            "Jumlah pembeli dan volume uang masuk sama-sama mendorong harga naik. Tren naik sangat kuat (Fokus cari posisi Beli / Long).",
            "success"
        )
    elif akun < 0.7 and volume < 0.8:
        return (
            "🐻 TURUN KOMPAK (Ritel & Volume Besar Satu Suara)",
            "Jumlah penjual dan tekanan jual uang besar sama-sama menekan harga turun. Tren turun kuat (Fokus cari posisi Jual / Short).",
            "warning"
        )
    else:
        return (
            "⚖️ BELUM ADA PERGERAKAN UANG BESAR YANG MENCOLOK",
            "Perbandingan jumlah akun dan volume uang masuk masih normal. Tunggu sinyal yang lebih jelas sebelum masuk pasar.",
            "info"
        )

def cek_rsi(rsi):
    if rsi >= 70:
        return "🔥 Harga Sudah Kemahalan (Overbought) — Rawan koreksi turun, jangan asal kejar beli di pucuk.", "warning"
    elif rsi <= 30:
        return "❄️ Harga Sudah Kemurahan (Oversold) — Rawan memantul naik, hati-hati jika mau buka posisi jual.", "success"
    elif 50 < rsi < 70:
        return "🟢 Tenaga Naik Masih Sehat — Momentum harga sedang mengarah ke atas dan belum jenuh.", "info"
    else:
        return "🟠 Tenaga Turun Masih Dominan — Momentum harga sedang mengarah ke bawah dan belum jenuh.", "info"

# ==========================================
# 3. TAMPILAN DASHBOARD
# ==========================================
rasio_akun, err1 = get_okx_long_short(coin, period)
rasio_volume, whale_long, whale_short, err2 = get_okx_whale_volume(coin, period)
harga, nilai_rsi, err3 = get_okx_price_and_rsi(coin, period)

if rasio_akun is not None and rasio_volume is not None and harga is not None:
    long_pct = (rasio_akun / (1 + rasio_akun)) * 100
    short_pct = 100 - long_pct

    st.metric(label=f"Harga {coin}-USDT Saat Ini", value=f"${harga:,.2f}")
    st.divider()

    st.subheader("1️⃣ Keramaian Pasar (Rasio Akun Long vs Short)")
    c1, c2, c3 = st.columns(3)
    c1.metric("Angka Rasio", f"{rasio_akun:.2f}")
    c2.metric("Yang Pilih Naik (Long)", f"{long_pct:.1f}%")
    c3.metric("Yang Pilih Turun (Short)", f"{short_pct:.1f}%")

    pesan_ls, warna_ls = cek_long_short(rasio_akun)
    getattr(st, warna_ls)(pesan_ls)

    st.divider()

    st.subheader("2️⃣ Jejak Tekanan Uang (Akun vs Volume)")
    w1, w2, w3 = st.columns(3)
    w1.metric("Rasio Akun (Ritel)", f"{rasio_akun:.2f}")
    w2.metric("Rasio Volume Beli/Jual", f"{rasio_volume:.2f}")
    w3.metric("Volume (Beli / Jual)", f"{whale_long:.0f}% / {whale_short:.0f}%")

    judul_w, ket_w, warna_w = cek_ritel_vs_whale(rasio_akun, rasio_volume)
    getattr(st, warna_w)(f"**{judul_w}**\n\n{ket_w}")

    st.divider()

    st.subheader("3️⃣ Filter Harga Murah/Mahal (RSI 14)")
    st.metric("Nilai RSI Saat Ini", f"{nilai_rsi:.1f} / 100")

    pesan_rsi, warna_rsi = cek_rsi(nilai_rsi)
    getattr(st, warna_rsi)(pesan_rsi)

else:
    st.error("Gagal mengambil data dari server OKX.")
    st.caption(f"Detail teknis: {err1 or err2 or err3}")

st.write("")
if st.button("🔄 Perbarui Data Terbaru"):
    st.rerun()
