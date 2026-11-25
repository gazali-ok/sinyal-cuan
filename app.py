from concurrent.futures import ThreadPoolExecutor
from operator import itemgetter
import time
import requests
import urllib3
import streamlit as st

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(page_title="Preferensi Sinyal Kehidupan", layout="wide")

DAFTAR_KOIN = [
    ("BTC", "Bitcoin"),
    ("ETH", "Ethereum"),
    ("SOL", "Solana"),
    ("BNB", "BNB"),
    ("XRP", "XRP"),
    ("ICP", "ICP"),
    ("NOT", "Not Coin"),
    ("SATS", "Sats"),
]

PROTO = "https://"
OKX_HOSTS = ["www." + "okx.com", "www." + "okx.me"]

HEADERS_JSON = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}


def fetch_okx(endpoint, params):
    last_err = ""
    # Coba hingga 2 kali jika terkena batas kecepatan (HTTP 429 / kode 50011)
    for percobaan in range(2):
        for host in OKX_HOSTS:
            try:
                r = requests.get(PROTO + host + endpoint, params=params, headers=HEADERS_JSON, timeout=5, verify=False)
                if r.status_code == 200:
                    data = r.json()
                    if data.get("code") == "50011":
                        last_err = "Rate limit OKX"
                        time.sleep(1.2)
                        break
                    return data, None
                elif r.status_code == 429:
                    last_err = "HTTP 429 Too Many Requests"
                    time.sleep(1.2)
                    break
                last_err = f"HTTP {r.status_code}"
            except Exception as e:
                last_err = str(e)
    return None, last_err


def _raw_all_prices():
    res, _ = fetch_okx("/api/v5/market/tickers", {"instType": "SWAP"})
    prices = {}
    if res and res.get("code") == "0":
        for item in res.get("data", []):
            inst_id = item.get("instId", "")
            if inst_id.endswith("-USDT-SWAP"):
                koin = inst_id.replace("-USDT-SWAP", "")
                prices[koin] = float(item.get("last", 0))
    return prices


def _raw_usd_to_idr():
    sumber_list = [
        ("FloatRates", "www." + "floatrates.com", "/daily/usd.json", ("idr", "rate")),
        ("Frankfurter", "api." + "frankfurter.dev", "/v1/latest?base=USD&symbols=IDR", ("rates", "IDR")),
        ("OpenER-API", "open." + "er-api.com", "/v6/latest/USD", ("rates", "IDR")),
        ("Currency-CDN", "cdn." + "jsdelivr.net", "/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.min.json", ("usd", "idr")),
    ]
    for nama, host, path, jalur in sumber_list:
        try:
            r = requests.get(PROTO + host + path, headers=HEADERS_JSON, timeout=3, verify=False)
            if r.status_code == 200:
                data = r.json()
                for kunci in jalur:
                    data = data[kunci]
                kurs = float(data)
                if kurs > 1000:
                    return kurs, nama
        except Exception:
            continue
    return None, None






def get_okx_long_short(coin, period):
    res, err = fetch_okx("/api/v5/rubik/stat/contracts/long-short-account-ratio", {"ccy": coin, "period": period})
    if err or not res:
        return None, err
    if res.get("code") == "0" and len(res.get("data", [])) > 0:
        row = itemgetter(0)(res["data"])
        return float(itemgetter(1)(row)), None
    return None, f"Gagal ambil rasio: {res}"


def get_okx_whale_volume(coin, period):
    res, err = fetch_okx("/api/v5/rubik/stat/taker-volume", {"ccy": coin, "instType": "CONTRACTS", "period": period})
    if err or not res:
        return None, None, None, err
    if res.get("code") == "0" and len(res.get("data", [])) > 0:
        row = itemgetter(0)(res["data"])
        sell_vol = float(itemgetter(1)(row))
        buy_vol = float(itemgetter(2)(row))
        ratio_vol = buy_vol / sell_vol if sell_vol > 0 else 1.0
        total = buy_vol + sell_vol
        buy_pct = (buy_vol / total * 100) if total > 0 else 50.0
        sell_pct = (sell_vol / total * 100) if total > 0 else 50.0
        return ratio_vol, buy_pct, sell_pct, None
    return None, None, None, f"Gagal ambil volume: {res}"


def get_okx_price_and_rsi(coin, period, length=14):
    inst_id = f"{coin}-USDT-SWAP"
    res, err = fetch_okx("/api/v5/market/candles", {"instId": inst_id, "bar": period, "limit": 100})
    if err or not res:
        return None, None, err
    if res.get("code") != "0" or len(res.get("data", [])) <= length:
        return None, None, f"Data harga kosong: {res}"

    candles = list(reversed(res["data"]))
    get_close = itemgetter(4)
    closes = [float(get_close(c)) for c in candles]
    current_price = itemgetter(-1)(closes)

    gains = [max(closes[i] - closes[i - 1], 0) for i in range(1, len(closes))]
    losses = [max(closes[i - 1] - closes[i], 0) for i in range(1, len(closes))]

    avg_gain = sum(gains[:length]) / length
    avg_loss = sum(losses[:length]) / length

    for i in range(length, len(gains)):
        avg_gain = (avg_gain * (length - 1) + gains[i]) / length
        avg_loss = (avg_loss * (length - 1) + losses[i]) / length

    rsi = 100.0 if avg_loss == 0 else 100 - (100 / (1 + (avg_gain / avg_loss)))
    return current_price, rsi, None


def format_harga_koin(coin, harga, kurs_idr):
    def fmt_usd(val):
        if val < 0.0001:
            return f"$ {val:,.10f}"
        elif val < 0.01:
            return f"$ {val:,.6f}"
        elif val < 1:
            return f"$ {val:,.4f}"
        return f"$ {val:,.2f}"

    if coin == "BTC" or kurs_idr is None:
        return fmt_usd(harga)

    harga_idr = harga * kurs_idr
    if harga_idr < 0.01:
        return f"Rp. {harga_idr:,.6f}"
    elif harga_idr < 1:
        return f"Rp. {harga_idr:,.4f}"
    elif harga_idr < 1000:
        return f"Rp. {harga_idr:,.3f}"
    return f"Rp. {harga_idr:,.2f}"


def cek_long_short(rasio):
    if rasio >= 2.50:
        return "⚠️ Terlalu Banyak yang Beli (Waspada Long Squeeze) — Hati-hati harga bisa dibanting turun mendadak.", "error"
    elif 1.20 <= rasio <= 2.49:
        return "📈 Mayoritas Optimis Naik — Kecenderungan harga bergerak naik.", "success"
    elif 0.85 <= rasio <= 1.19:
        return "⚖️ Pasar Seimbang (Sideways) — Pembeli dan penjual sama kuat, harga cenderung datar.", "info"
    elif 0.41 <= rasio <= 0.84:
        return "📉 Mayoritas Pesimis Turun — Kecenderungan harga bergerak turun.", "warning"
    return "⚠️ Terlalu Banyak yang Jual (Waspada Short Squeeze) — Hati-hati harga bisa ditarik naik mendadak.", "error"


def cek_ritel_vs_whale(akun, volume):
    if akun > 2.0 and volume < 0.9:
        return "🚨 JEBAKAN NAIK (Ritel Beli, Modal Besar Jualan)", "Trader kecil ramai-ramai beli, tapi volume jual agresif justru mendominasi. Waspada koreksi turun (Cari peluang Jual / Short).", "error"
    elif akun < 0.6 and volume > 1.2:
        return "💎 JEBAKAN TURUN (Ritel Panik Jual, Modal Besar Borong)", "Trader kecil ketakutan jual rugi, tapi volume beli agresif justru memborong. Waspada pantulan naik (Cari peluang Beli / Long).", "success"
    elif akun > 1.5 and volume > 1.2:
        return "🚀 NAIK KOMPAK (Ritel & Volume Besar Satu Suara)", "Jumlah pembeli dan volume uang masuk sama-sama mendorong harga naik. Tren naik sangat kuat (Fokus cari posisi Beli / Long).", "success"
    elif akun < 0.7 and volume < 0.8:
        return "🐻 TURUN KOMPAK (Ritel & Volume Besar Satu Suara)", "Jumlah penjual dan tekanan jual uang besar sama-sama menekan harga turun. Tren turun kuat (Fokus cari posisi Jual / Short).", "warning"
    return "⚖️ BELUM ADA PERGERAKAN UANG BESAR YANG MENCOLOK", "Perbandingan jumlah akun dan volume uang masuk masih normal. Tunggu sinyal yang lebih jelas sebelum masuk pasar.", "info"


def cek_rsi(rsi):
    if rsi >= 70:
        return "🔥 Harga Sudah Kemahalan (Overbought) — Rawan koreksi turun, jangan asal kejar beli di pucuk.", "warning"
    elif rsi <= 30:
        return "❄️ Harga Sudah Kemurahan (Oversold) — Rawan memantul naik, hati-hati jika mau buka posisi jual.", "success"
    elif 50 < rsi < 70:
        return "🟢 Tenaga Naik Masih Sehat — Momentum harga sedang mengarah ke atas dan belum jenuh.", "info"
    return "🟠 Tenaga Turun Masih Dominan — Momentum harga sedang mengarah ke bawah dan belum jenuh.", "info"


def buat_kesimpulan(rasio_akun, rasio_volume, rsi):
    skor_ls = -0.8 if rasio_akun >= 2.50 else (0.6 if rasio_akun >= 1.20 else (0.0 if rasio_akun >= 0.85 else (-0.6 if rasio_akun >= 0.41 else 0.8)))

    if rasio_akun > 2.0 and rasio_volume < 0.9:
        skor_whale = -1.0
    elif rasio_akun < 0.6 and rasio_volume > 1.2:
        skor_whale = 1.0
    elif rasio_akun > 1.5 and rasio_volume > 1.2:
        skor_whale = 1.0
    elif rasio_akun < 0.7 and rasio_volume < 0.8:
        skor_whale = -1.0
    else:
        skor_whale = 0.3 if rasio_volume > 1.05 else (-0.3 if rasio_volume < 0.95 else 0.0)

    skor_rsi = 1.0 if rsi <= 30 else (-1.0 if rsi >= 70 else (0.5 if 50 < rsi < 70 else -0.5))
    skor_total = (skor_ls * 0.30) + (skor_whale * 0.45) + (skor_rsi * 0.25)
    persen_beli = ((skor_total + 1) / 2) * 100
    persen_jual = 100 - persen_beli

    if persen_beli >= 65:
        return "Beli", f"{persen_beli:.0f}%", "🟢 KESIMPULAN: SEBAIKNYA BELI (LONG)", f"Ketiga indikator cenderung selaras mengarah naik dengan kekuatan sinyal **{persen_beli:.1f}%**.", persen_beli, persen_jual, "success"
    elif persen_jual >= 65:
        return "Jual", f"{persen_jual:.0f}%", "🔴 KESIMPULAN: SEBAIKNYA JUAL (SHORT)", f"Ketiga indikator cenderung selaras mengarah turun dengan kekuatan sinyal **{persen_jual:.1f}%**.", persen_beli, persen_jual, "error"
    return "Tahan", f"{max(persen_beli, persen_jual):.0f}%", "🟡 KESIMPULAN: TAHAN / TUNGGU DULU (WAIT & SEE)", "Sinyal antar indikator masih terbelah (belum mencapai ambang keyakinan minimal 65%).", persen_beli, persen_jual, "warning"





@st.cache_data(ttl=20, show_spinner=False)
def muat_semua_data_utama(period):
    def _ambil_satu_koin(kode):
        ls, _ = get_okx_long_short(kode, period)
        vol, _, _, _ = get_okx_whale_volume(kode, period)
        return kode, ls, vol

    hasil_koin = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        fut_prices = pool.submit(_raw_all_prices)
        fut_idr = pool.submit(_raw_usd_to_idr)

        # Kirim per 2 koin (4 request) agar tetap di bawah batas 5 request/2 detik OKX
        kode_list = [k for k, _ in DAFTAR_KOIN]
        for i in range(0, len(kode_list), 2):
            batch = kode_list[i:i + 2]
            futs = [pool.submit(_ambil_satu_koin, k) for k in batch]
            for f in futs:
                k, ls, vol = f.result()
                hasil_koin[k] = (ls, vol)
            if i + 2 < len(kode_list):
                time.sleep(0.9)

        prices = fut_prices.result()
        kurs_idr, sumber_kurs = fut_idr.result()

    return prices, kurs_idr, sumber_kurs, hasil_koin


if "halaman" not in st.session_state:
    st.session_state["halaman"] = "utama"
if "koin_terpilih" not in st.session_state:
    st.session_state["koin_terpilih"] = "BTC"
if "timeframe" not in st.session_state:
    st.session_state["timeframe"] = "5m"

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
        max-width: 850px;
    }
    div.stButton > button[kind="primary"] {
        background-color: #10893E;
        border-color: #10893E;
        color: white;
        width: 100%;
        border-radius: 8px;
        font-weight: 600;
        padding: 0.45rem 0.75rem;
    }
    div.stButton > button[kind="primary"]:hover {
        background-color: #0b6b2f;
        border-color: #0b6b2f;
    }
    .coin-card {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 4px 2px 8px 2px;
    }
    .coin-name {
        font-size: 1.05rem;
        font-weight: 700;
        margin: 0;
    }
    .coin-price {
        font-size: 0.92rem;
        opacity: 0.85;
        margin-top: 2px;
    }
    .badge-beli {
        background-color: rgba(16, 137, 62, 0.16);
        color: #16a34a;
        border: 1px solid rgba(22, 163, 74, 0.4);
        padding: 4px 10px;
        border-radius: 999px;
        font-weight: 700;
        font-size: 0.85rem;
        white-space: nowrap;
    }
    .badge-jual {
        background-color: rgba(220, 38, 38, 0.16);
        color: #ef4444;
        border: 1px solid rgba(239, 68, 68, 0.4);
        padding: 4px 10px;
        border-radius: 999px;
        font-weight: 700;
        font-size: 0.85rem;
        white-space: nowrap;
    }
    .badge-tahan {
        background-color: rgba(217, 119, 6, 0.16);
        color: #f59e0b;
        border: 1px solid rgba(245, 158, 11, 0.4);
        padding: 4px 10px;
        border-radius: 999px;
        font-weight: 700;
        font-size: 0.85rem;
        white-space: nowrap;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ==========================================
# HALAMAN 1: TAMPILAN UTAMA (RESPONSIF HP)
# ==========================================
if st.session_state["halaman"] == "utama":
    st.markdown("<h3 style='text-align: center; margin-bottom: 0.2rem;'>📊 PREFERENSI SINYAL KEHIDUPAN</h3>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; font-size: 0.85rem; opacity: 0.75; margin-bottom: 1rem;'>Pantauan Sinyal Kripto Real-Time (OKX Futures)</p>", unsafe_allow_html=True)

    col_tf, col_ref = st.columns(2, vertical_alignment="bottom")
    with col_tf:
        tf_options = ["5m", "1H", "1D"]
        idx_tf = tf_options.index(st.session_state["timeframe"]) if st.session_state["timeframe"] in tf_options else 0
        period = st.selectbox("⏱️ Pilih Time Frame", tf_options, index=idx_tf)
        st.session_state["timeframe"] = period
    with col_ref:
        if st.button("🔄 Refresh", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    with st.spinner("Memuat data seluruh koin..."):
        all_prices, kurs_idr, sumber_kurs, hasil_koin = muat_semua_data_utama(period)

    for kode, nama in DAFTAR_KOIN:
        rasio_akun, rasio_volume = hasil_koin.get(kode, (None, None))
        harga = all_prices.get(kode)

        with st.container(border=True):
            if rasio_akun is not None and rasio_volume is not None and harga:
                teks_harga = format_harga_koin(kode, harga, kurs_idr)
                sinyal_singkat, persen_str, _, _, _, _, _ = buat_kesimpulan(rasio_akun, rasio_volume, 50.0)

                if sinyal_singkat == "Beli":
                    kelas_badge = "badge-beli"
                    ikon = "🟢"
                elif sinyal_singkat == "Jual":
                    kelas_badge = "badge-jual"
                    ikon = "🔴"
                else:
                    kelas_badge = "badge-tahan"
                    ikon = "🟡"

                st.markdown(
                    f"""
                    <div class="coin-card">
                        <div>
                            <div class="coin-name">{nama} <span style="font-size:0.8rem; opacity:0.6;">({kode})</span></div>
                            <div class="coin-price">{teks_harga}</div>
                        </div>
                        <div class="{kelas_badge}">{ikon} {sinyal_singkat} • {persen_str}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"""
                    <div class="coin-card">
                        <div>
                            <div class="coin-name">{nama} ({kode})</div>
                            <div class="coin-price">-</div>
                        </div>
                        <div class="badge-tahan">Gagal Memuat</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            if st.button(f"Lihat Detail {nama}", key=f"btn_{kode}", type="primary"):
                st.session_state["koin_terpilih"] = kode
                st.session_state["halaman"] = "detail"
                st.rerun()

    if kurs_idr is not None:
        st.caption(f"💱 Kurs aktif: 1 USD = Rp {kurs_idr:,.0f} (via {sumber_kurs})")
    else:
        st.caption("💱 Kurs Rupiah tidak tersedia, harga ditampilkan dalam USD.")






# ==========================================
# HALAMAN 2: TAMPILAN DETAIL INDIKATOR
# ==========================================
else:
    col_back, col_tf_det = st.columns([1.2, 1.8], vertical_alignment="bottom")
    with col_back:
        if st.button("⬅️ Kembali", use_container_width=True):
            st.session_state["halaman"] = "utama"
            st.rerun()

    with col_tf_det:
        tf_options = ["5m", "1H", "1D"]
        idx_tf = tf_options.index(st.session_state["timeframe"]) if st.session_state["timeframe"] in tf_options else 0
        period = st.selectbox("⏱️ Time Frame", tf_options, index=idx_tf, key="tf_detail")
        st.session_state["timeframe"] = period

    kode_aktif = st.session_state["koin_terpilih"]
    nama_aktif = dict(DAFTAR_KOIN).get(kode_aktif, kode_aktif)

    st.markdown(f"### 📊 Detail {nama_aktif} ({kode_aktif})")

    with st.spinner(f"Memuat rincian indikator {nama_aktif}..."):
        with ThreadPoolExecutor(max_workers=4) as pool_det:
            f1 = pool_det.submit(get_okx_long_short, kode_aktif, period)
            f2 = pool_det.submit(get_okx_whale_volume, kode_aktif, period)
            f3 = pool_det.submit(get_okx_price_and_rsi, kode_aktif, period)
            f4 = pool_det.submit(_raw_usd_to_idr)

            rasio_akun, err1 = f1.result()
            rasio_volume, whale_long, whale_short, err2 = f2.result()
            harga, nilai_rsi, err3 = f3.result()
            kurs_idr, sumber_kurs = f4.result()

    if rasio_akun is not None and rasio_volume is not None and harga is not None:
        long_pct = (rasio_akun / (1 + rasio_akun)) * 100
        short_pct = 100 - long_pct

        teks_harga = format_harga_koin(kode_aktif, harga, kurs_idr)
        label_harga = f"Harga {kode_aktif}-USDT Saat Ini" if (kode_aktif == "BTC" or kurs_idr is None) else f"Harga {kode_aktif}-IDR (Kurs Rp{kurs_idr:,.0f} via {sumber_kurs})"

        with st.container(border=True):
            st.metric(label=label_harga, value=teks_harga)

        st.subheader("🎯 Kesimpulan Sinyal")
        _, _, rek_judul, rek_ket, p_beli, p_jual, rek_warna = buat_kesimpulan(rasio_akun, rasio_volume, nilai_rsi)
        getattr(st, rek_warna)(f"**{rek_judul}**\n\n{rek_ket}")

        with st.container(border=True):
            k1, k2 = st.columns(2)
            k1.metric("Sinyal Beli (Long)", f"{p_beli:.1f}%")
            k2.metric("Sinyal Jual (Short)", f"{p_jual:.1f}%")

        st.subheader("🔍 Rincian 3 Indikator")

        with st.container(border=True):
            st.markdown("**1. Sentimen Mayoritas (Long/Short Ratio)**")
            c1, c2, c3 = st.columns(3)
            c1.metric("Rasio L/S", f"{rasio_akun:.2f}")
            c2.metric("Long", f"{long_pct:.1f}%")
            c3.metric("Short", f"{short_pct:.1f}%")
            pesan_ls, warna_ls = cek_long_short(rasio_akun)
            getattr(st, warna_ls)(pesan_ls)

        with st.container(border=True):
            st.markdown("**2. Pergerakan Modal Besar (Taker Volume)**")
            w1, w2, w3 = st.columns(3)
            w1.metric("Rasio Vol", f"{rasio_volume:.2f}")
            w2.metric("Beli", f"{whale_long:.1f}%")
            w3.metric("Jual", f"{whale_short:.1f}%")
            judul_whale, pesan_whale, warna_whale = cek_ritel_vs_whale(rasio_akun, rasio_volume)
            getattr(st, warna_whale)(f"**{judul_whale}**\n\n{pesan_whale}")

        with st.container(border=True):
            st.markdown("**3. Momentum Harga (RSI 14)**")
            st.metric("Nilai RSI (14)", f"{nilai_rsi:.2f}")
            pesan_rsi, warna_rsi = cek_rsi(nilai_rsi)
            getattr(st, warna_rsi)(pesan_rsi)
    else:
        st.error("Gagal mengambil data dari API OKX. Silakan muat ulang halaman.")
        for err in [err1, err2, err3]:
            if err:
                st.caption(err)
