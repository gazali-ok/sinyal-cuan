from concurrent.futures import ThreadPoolExecutor
from operator import itemgetter
import re
import time
import xml.etree.ElementTree as ET
import requests
import urllib3
import streamlit as st

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(page_title="Preferensi Sinyal Kehidupan", layout="wide")

DAFTAR_KOIN = (
    ("BTC", "Bitcoin"),
    ("ETH", "Ethereum"),
    ("SOL", "Solana"),
    ("BNB", "BNB"),
    ("XRP", "XRP"),
    ("ICP", "ICP"),
    ("NOT", "Not Coin"),
    ("SATS", "Sats"),
)

PROTO = "https://"
OKX_HOSTS = ("www." + "okx.com", "www." + "okx.me")

HEADERS_JSON = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/xml, application/xml, text/html;q=0.9, */*;q=0.8",
}


def fetch_okx(endpoint, params):
    last_err = ""
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
        for item in res.get("data", list()):
            inst_id = item.get("instId", "")
            if inst_id.endswith("-USDT-SWAP"):
                koin = inst_id.replace("-USDT-SWAP", "")
                prices[koin] = float(item.get("last", 0))
    return prices


def _raw_usd_to_idr():
    sumber_list = (
        ("FloatRates", "www." + "floatrates.com", "/daily/usd.json", ("idr", "rate")),
        ("Frankfurter", "api." + "frankfurter.dev", "/v1/latest?base=USD&symbols=IDR", ("rates", "IDR")),
        ("OpenER-API", "open." + "er-api.com", "/v6/latest/USD", ("rates", "IDR")),
        ("Currency-CDN", "cdn." + "jsdelivr.net", "/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.min.json", ("usd", "idr")),
    )
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
    if res.get("code") == "0" and len(res.get("data", list())) > 0:
        row = itemgetter(0)(res["data"])
        return float(itemgetter(1)(row)), None
    return None, f"Gagal ambil rasio: {res}"


def get_okx_whale_volume(coin, period):
    res, err = fetch_okx("/api/v5/rubik/stat/taker-volume", {"ccy": coin, "instType": "CONTRACTS", "period": period})
    if err or not res:
        return None, None, None, err
    if res.get("code") == "0" and len(res.get("data", list())) > 0:
        row = itemgetter(0)(res["data"])
        sell_vol = float(itemgetter(1)(row))
        buy_vol = float(itemgetter(2)(row))
        ratio_vol = buy_vol / sell_vol if sell_vol > 0 else 1.0
        total = buy_vol + sell_vol
        buy_pct = (buy_vol / total * 100) if total > 0 else 50.0
        sell_pct = (sell_vol / total * 100) if total > 0 else 50.0
        return ratio_vol, buy_pct, sell_pct, None
    return None, None, None, f"Gagal ambil volume: {res}"


def get_okx_funding_rate(coin):
    inst_id = f"{coin}-USDT-SWAP"
    res, err = fetch_okx("/api/v5/public/funding-rate", {"instId": inst_id})
    if err or not res:
        return None, err
    if res.get("code") == "0" and len(res.get("data", list())) > 0:
        row = itemgetter(0)(res["data"])
        rate = float(row.get("fundingRate", 0)) * 100
        return rate, None
    return None, f"Gagal ambil funding rate: {res}"


def get_okx_price_and_rsi(coin, period, length=14):
    inst_id = f"{coin}-USDT-SWAP"
    res, err = fetch_okx("/api/v5/market/candles", {"instId": inst_id, "bar": period, "limit": 100})
    if err or not res:
        return None, None, err
    if res.get("code") != "0" or len(res.get("data", list())) <= length:
        return None, None, f"Data harga kosong: {res}"

    candles = list(reversed(res["data"]))
    get_close = itemgetter(4)
    closes = list(float(get_close(c)) for c in candles)
    current_price = itemgetter(-1)(closes)

    gains = list(max(closes[i] - closes[i - 1], 0) for i in range(1, len(closes)))
    losses = list(max(closes[i - 1] - closes[i], 0) for i in range(1, len(closes)))

    avg_gain = sum(gains[:length]) / length
    avg_loss = sum(losses[:length]) / length

    for i in range(length, len(gains)):
        avg_gain = (avg_gain * (length - 1) + gains[i]) / length
        avg_loss = (avg_loss * (length - 1) + losses[i]) / length

    rsi = 100.0 if avg_loss == 0 else 100 - (100 / (1 + (avg_gain / avg_loss)))
    return current_price, rsi, None







@st.cache_data(ttl=300, show_spinner=False)
def get_sentimen_global():
    # 1. Crypto Fear & Greed Index (API JSON + Cadangan Halaman Web)
    fng_val, fng_class = None, "Tidak Tersedia"
    fng_sources = (
        ("api." + "alternative.me", "/fng/?limit=1"),
        ("api." + "alternative.me", "/fng/"),
    )
    for host_fng, path_fng in fng_sources:
        try:
            r = requests.get(PROTO + host_fng + path_fng, headers=HEADERS_JSON, timeout=6, verify=False)
            if r.status_code == 200:
                data_list = r.json().get("data", list())
                if len(data_list) > 0:
                    item = itemgetter(0)(data_list)
                    fng_val = int(item.get("value", 50))
                    fng_class = item.get("value_classification", "Neutral")
                    break
        except Exception:
            continue

    # Cadangan jika endpoint JSON Alternative.me gagal
    if fng_val is None:
        try:
            url_web = PROTO + "alternative." + "me/crypto/fear-and-greed-index/"
            r = requests.get(url_web, headers=HEADERS_JSON, timeout=6, verify=False)
            if r.status_code == 200:
                match = re.search(r'fng-circle">\s*(\d+)\s*<', r.text)
                if match:
                    fng_val = int(match.group(1))
                    if fng_val <= 24:
                        fng_class = "Extreme Fear"
                    elif fng_val <= 49:
                        fng_class = "Fear"
                    elif fng_val == 50:
                        fng_class = "Neutral"
                    elif fng_val <= 74:
                        fng_class = "Greed"
                    else:
                        fng_class = "Extreme Greed"
        except Exception:
            pass

    # 2. Sentimen Berita Kripto (Multi-Sumber RSS dengan Fallback)
    kata_bullish = {
        "surge", "soar", "rally", "bull", "bullish", "inflow", "adopt", "adoption",
        "approve", "approved", "ath", "gain", "gains", "buy", "accumulate", "cut rate",
        "rise", "rises", "jump", "jumps", "rebound", "recovery", "high", "etf", "boost"
    }
    kata_bearish = {
        "crash", "plunge", "drop", "drops", "bear", "bearish", "outflow", "hack", "exploit",
        "sec", "lawsuit", "ban", "dump", "liquidation", "inflation", "hawkish", "fall",
        "falls", "slump", "fear", "risk", "sell-off", "selloff", "decline", "low", "warning"
    }

    sumber_rss = (
        ("Cointelegraph", "cointelegraph." + "com", "/rss"),
        ("CoinDesk", "www." + "coindesk.com", "/arc/outboundfeeds/rss/"),
        ("Decrypt", "decrypt." + "co", "/feed"),
    )

    skor_berita_mentah = 0
    judul_berita = list()
    sumber_berita_aktif = ""

    for nama_rss, host_rss, path_rss in sumber_rss:
        try:
            r = requests.get(PROTO + host_rss + path_rss, headers=HEADERS_JSON, timeout=5, verify=False)
            if r.status_code == 200 and len(r.content) > 200:
                root = ET.fromstring(r.content)
                items = root.findall(".//item")[:15]
                if len(items) > 0:
                    sumber_berita_aktif = nama_rss
                    for item in items:
                        title_el = item.find("title")
                        judul = title_el.text.strip() if (title_el is not None and title_el.text) else ""
                        if judul:
                            judul_berita.append(judul)
                            j_low = judul.lower()
                            skor_berita_mentah += sum(1 for k in kata_bullish if k in j_low)
                            skor_berita_mentah -= sum(1 for k in kata_bearish if k in j_low)
                    break
        except Exception:
            continue

    if skor_berita_mentah >= 2:
        label_berita = "Bullish"
    elif skor_berita_mentah <= -2:
        label_berita = "Bearish"
    else:
        label_berita = "Netral"

    # 3. Indeks Dolar AS / DXY (Multi-Sumber dengan Fallback)
    dxy_val, dxy_chg = None, 0.0
    sumber_dxy = (
        ("query1.finance." + "yahoo.com", "/v8/finance/chart/DX-Y.NYB?interval=1d&range=5d"),
        ("query2.finance." + "yahoo.com", "/v8/finance/chart/DX-Y.NYB?interval=1d&range=5d"),
        ("query1.finance." + "yahoo.com", "/v8/finance/chart/UUP?interval=1d&range=5d"),
    )
    for host_dxy, path_dxy in sumber_dxy:
        try:
            r = requests.get(PROTO + host_dxy + path_dxy, headers=HEADERS_JSON, timeout=5, verify=False)
            if r.status_code == 200:
                result_list = r.json().get("chart", {}).get("result", list())
                if len(result_list) > 0:
                    res0 = itemgetter(0)(result_list)
                    quote_list = res0.get("indicators", {}).get("quote", list())
                    if len(quote_list) > 0:
                        raw_closes = itemgetter(0)(quote_list).get("close", list())
                        closes = list(float(c) for c in raw_closes if c is not None)
                        if len(closes) >= 2:
                            dxy_val = itemgetter(-1)(closes)
                            prev_val = itemgetter(-2)(closes)
                            dxy_chg = ((dxy_val - prev_val) / prev_val) * 100
                            break
        except Exception:
            continue

    if dxy_chg <= -0.25:
        label_dxy = "Bullish Kripto"
    elif dxy_chg >= 0.25:
        label_dxy = "Bearish Kripto"
    else:
        label_dxy = "Netral"

    # Normalisasi skor global ke skala -1.0 s/d +1.0
    s_fng = 0.0
    if fng_val is not None:
        s_fng = 0.8 if fng_val <= 25 else (-0.8 if fng_val >= 75 else (0.3 if fng_val < 45 else (-0.3 if fng_val > 55 else 0.0)))

    s_news = max(-1.0, min(1.0, skor_berita_mentah / 5.0))
    s_dxy = 0.7 if dxy_chg <= -0.25 else (-0.7 if dxy_chg >= 0.25 else 0.0)

    skor_global_gabungan = (s_fng * 0.4) + (s_news * 0.3) + (s_dxy * 0.3)
    return {
        "skor_global": skor_global_gabungan,
        "fng_val": fng_val,
        "fng_class": fng_class,
        "skor_berita": skor_berita_mentah,
        "label_berita": label_berita,
        "sumber_berita": sumber_berita_aktif,
        "judul_berita": judul_berita[:5],
        "dxy_val": dxy_val,
        "dxy_chg": dxy_chg,
        "label_dxy": label_dxy,
    }







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


def cek_funding_rate(rate):
    if rate is None:
        return "⚪ Data Funding Rate tidak tersedia saat ini.", "info"
    if rate > 0.03:
        return f"🔴 Biaya Long Terlalu Mahal ({rate:+.4f}%) — Terlalu banyak posisi beli ber-leverage, rawan terbanting turun (Long Squeeze).", "warning"
    elif rate < -0.01:
        return f"🟢 Penjual Mendominasi ({rate:+.4f}%) — Banyak posisi jual menumpuk, berpotensi memicu pantulan tajam (Short Squeeze).", "success"
    return f"⚖️ Biaya Pendanaan Normal ({rate:+.4f}%) — Leverage pasar futures masih dalam batas sehat.", "info"


def cek_fear_greed(val, kelas):
    if val is None:
        return "⚪ Data indeks ketakutan & keserakahan sedang tidak tersedia.", "info"
    if val <= 25:
        return f"💎 Pasar Ketakutan Ekstrem ({val} - {kelas}) — Secara kontrarian, area ini sering menjadi titik akumulasi murah.", "success"
    elif val >= 75:
        return f"🚨 Pasar Terlalu Euforia ({val} - {kelas}) — Investor terlalu serakah, waspada koreksi mendadak.", "warning"
    return f"⚖️ Psikologi Pasar Stabil ({val} - {kelas}) — Emosi pelaku pasar global masih terjaga.", "info"


def cek_berita_dan_makro(skor_berita, label_berita, dxy_chg, label_dxy):
    if label_berita == "Bullish" or "Bullish" in label_dxy:
        return f"🟢 Sentimen Eksternal Bullish (Berita: {label_berita} / {skor_berita:+d} poin | DXY: {label_dxy}) — Narasi berita dan/atau pergerakan Dolar AS mendukung kenaikan kripto.", "success"
    elif label_berita == "Bearish" or "Bearish" in label_dxy:
        return f"🔴 Sentimen Eksternal Bearish (Berita: {label_berita} / {skor_berita:+d} poin | DXY: {label_dxy}) — Tekanan berita negatif dan/atau penguatan Dolar AS membebani kripto.", "warning"
    return f"⚖️ Sentimen Eksternal Netral (Berita: {label_berita} / {skor_berita:+d} poin | DXY: {label_dxy}) — Belum ada katalis berita ekstrem atau gejolak Dolar AS yang signifikan.", "info"


def buat_kesimpulan(rasio_akun, rasio_volume, rsi=50.0, funding_rate=0.0, skor_global=0.0):
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

    if funding_rate is None:
        skor_funding = 0.0
    elif funding_rate < -0.01:
        skor_funding = 0.8
    elif funding_rate > 0.03:
        skor_funding = -0.8
    else:
        skor_funding = 0.0

    # Total Bobot = 100% (Whale 35%, L/S 20%, RSI 15%, Funding 10%, Sentimen Global 20%)
    skor_total = (
        (skor_whale * 0.35)
        + (skor_ls * 0.20)
        + (skor_rsi * 0.15)
        + (skor_funding * 0.10)
        + (skor_global * 0.20)
    )

    persen_beli = max(0.0, min(100.0, ((skor_total + 1) / 2) * 100))
    persen_jual = 100.0 - persen_beli

    if persen_beli >= 65:
        return "Beli", f"{persen_beli:.0f}%", "🟢 KESIMPULAN: SEBAIKNYA BELI (LONG)", f"Seluruh indikator (Whale, Teknikal, & Sentimen Global) selaras mengarah naik dengan kekuatan **{persen_beli:.1f}%**.", persen_beli, persen_jual, "success"
    elif persen_jual >= 65:
        return "Jual", f"{persen_jual:.0f}%", "🔴 KESIMPULAN: SEBAIKNYA JUAL (SHORT)", f"Seluruh indikator (Whale, Teknikal, & Sentimen Global) selaras mengarah turun dengan kekuatan **{persen_jual:.1f}%**.", persen_beli, persen_jual, "error"
    return "Tahan", f"{max(persen_beli, persen_jual):.0f}%", "🟡 KESIMPULAN: TAHAN / TUNGGU DULU (WAIT & SEE)", "Sinyal antar indikator teknikal, derivatif, dan sentimen pasar masih terbelah (belum mencapai ambang 65%).", persen_beli, persen_jual, "warning"







@st.cache_data(ttl=20, show_spinner=False)
def muat_semua_data_utama(period):
    def _ambil_satu_koin(kode):
        ls, _ = get_okx_long_short(kode, period)
        vol, _, _, _ = get_okx_whale_volume(kode, period)
        fund, _ = get_okx_funding_rate(kode)
        return kode, ls, vol, fund

    hasil_koin = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        fut_prices = pool.submit(_raw_all_prices)
        fut_idr = pool.submit(_raw_usd_to_idr)
        fut_global = pool.submit(get_sentimen_global)

        kode_list = list(k for k, _ in DAFTAR_KOIN)
        for i in range(0, len(kode_list), 2):
            batch = kode_list[i:i + 2]
            futs = list(pool.submit(_ambil_satu_koin, k) for k in batch)
            for f in futs:
                k, ls, vol, fund = f.result()
                hasil_koin[k] = (ls, vol, fund)
            if i + 2 < len(kode_list):
                time.sleep(0.9)

        prices = fut_prices.result()
        kurs_idr, sumber_kurs = fut_idr.result()
        data_global = fut_global.result()

    return prices, kurs_idr, sumber_kurs, hasil_koin, data_global


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
    st.markdown("<p style='text-align: center; font-size: 0.85rem; opacity: 0.75; margin-bottom: 1rem;'>Pantauan Sinyal Kripto & Sentimen Pasar Real-Time</p>", unsafe_allow_html=True)

    col_tf, col_ref = st.columns(2, vertical_alignment="bottom")
    with col_tf:
        tf_options = ("5m", "1H", "1D")
        idx_tf = tf_options.index(st.session_state["timeframe"]) if st.session_state["timeframe"] in tf_options else 0
        period = st.selectbox("⏱️ Pilih Time Frame", tf_options, index=idx_tf)
        st.session_state["timeframe"] = period
    with col_ref:
        if st.button("🔄 Refresh", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    with st.spinner("Memuat data seluruh koin & sentimen pasar..."):
        all_prices, kurs_idr, sumber_kurs, hasil_koin, data_global = muat_semua_data_utama(period)

    # Ringkasan Sentimen Pasar Global
    with st.container(border=True):
        st.markdown("**🌐 Kondisi Sentimen Global Saat Ini**")
        g1, g2, g3 = st.columns(3)

        # 1. Fear & Greed
        if data_global["fng_val"] is not None:
            fng_v = data_global["fng_val"]
            ikon_fng = "🟢" if fng_v <= 40 else ("🔴" if fng_v >= 65 else "🟡")
            g1.markdown(
                f"""
                <div style="font-size:0.85rem; opacity:0.8;">Fear & Greed</div>
                <div style="font-size:1.55rem; font-weight:700; line-height:1.2;">{fng_v} / 100</div>
                <div style="font-size:0.82rem; margin-top:2px;">{ikon_fng} {data_global['fng_class']}</div>
                """,
                unsafe_allow_html=True,
            )
        else:
            g1.markdown(
                """
                <div style="font-size:0.85rem; opacity:0.8;">Fear & Greed</div>
                <div style="font-size:1.55rem; font-weight:700; line-height:1.2;">-</div>
                <div style="font-size:0.82rem; margin-top:2px;">⚪ Tidak Tersedia</div>
                """,
                unsafe_allow_html=True,
            )

        # 2. Dolar (DXY)
        if data_global["dxy_val"] is not None:
            lbl_dxy = data_global["label_dxy"]
            ikon_dxy = "🟢" if "Bullish" in lbl_dxy else ("🔴" if "Bearish" in lbl_dxy else "🟡")
            g2.markdown(
                f"""
                <div style="font-size:0.85rem; opacity:0.8;">Dolar (DXY)</div>
                <div style="font-size:1.55rem; font-weight:700; line-height:1.2;">{data_global['dxy_val']:.2f}</div>
                <div style="font-size:0.82rem; margin-top:2px;">{ikon_dxy} {lbl_dxy} ({data_global['dxy_chg']:+.2f}%)</div>
                """,
                unsafe_allow_html=True,
            )
        else:
            g2.markdown(
                """
                <div style="font-size:0.85rem; opacity:0.8;">Dolar (DXY)</div>
                <div style="font-size:1.55rem; font-weight:700; line-height:1.2;">-</div>
                <div style="font-size:0.82rem; margin-top:2px;">⚪ Tidak Tersedia</div>
                """,
                unsafe_allow_html=True,
            )

        # 3. Skor Berita
        lbl_brt = data_global["label_berita"]
        ikon_brt = "🟢" if lbl_brt == "Bullish" else ("🔴" if lbl_brt == "Bearish" else "🟡")
        g3.markdown(
            f"""
            <div style="font-size:0.85rem; opacity:0.8;">Skor Berita</div>
            <div style="font-size:1.55rem; font-weight:700; line-height:1.2;">{data_global['skor_berita']:+d} Poin</div>
            <div style="font-size:0.82rem; margin-top:2px;">{ikon_brt} {lbl_brt}</div>
            """,
            unsafe_allow_html=True,
        )

    for kode, nama in DAFTAR_KOIN:
        rasio_akun, rasio_volume, funding_rate = hasil_koin.get(kode, (None, None, None))
        harga = all_prices.get(kode)

        with st.container(border=True):
            if rasio_akun is not None and rasio_volume is not None and harga:
                teks_harga = format_harga_koin(kode, harga, kurs_idr)
                sinyal_singkat, persen_str, _, _, _, _, _ = buat_kesimpulan(
                    rasio_akun, rasio_volume, 50.0, funding_rate, data_global["skor_global"]
                )

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
    col_back, col_tf_det = st.columns((1.2, 1.8), vertical_alignment="bottom")
    with col_back:
        if st.button("⬅️ Kembali", use_container_width=True):
            st.session_state["halaman"] = "utama"
            st.rerun()

    with col_tf_det:
        tf_options = ("5m", "1H", "1D")
        idx_tf = tf_options.index(st.session_state["timeframe"]) if st.session_state["timeframe"] in tf_options else 0
        period = st.selectbox("⏱️ Time Frame", tf_options, index=idx_tf, key="tf_detail")
        st.session_state["timeframe"] = period

    kode_aktif = st.session_state["koin_terpilih"]
    nama_aktif = dict(DAFTAR_KOIN).get(kode_aktif, kode_aktif)

    st.markdown(f"### 📊 Detail {nama_aktif} ({kode_aktif})")

    with st.spinner(f"Memuat rincian indikator & sentimen {nama_aktif}..."):
        with ThreadPoolExecutor(max_workers=6) as pool_det:
            f1 = pool_det.submit(get_okx_long_short, kode_aktif, period)
            f2 = pool_det.submit(get_okx_whale_volume, kode_aktif, period)
            f3 = pool_det.submit(get_okx_price_and_rsi, kode_aktif, period)
            f4 = pool_det.submit(_raw_usd_to_idr)
            f5 = pool_det.submit(get_okx_funding_rate, kode_aktif)
            f6 = pool_det.submit(get_sentimen_global)

            rasio_akun, err1 = f1.result()
            rasio_volume, whale_long, whale_short, err2 = f2.result()
            harga, nilai_rsi, err3 = f3.result()
            kurs_idr, sumber_kurs = f4.result()
            funding_rate, _ = f5.result()
            data_global = f6.result()

    if rasio_akun is not None and rasio_volume is not None and harga is not None:
        long_pct = (rasio_akun / (1 + rasio_akun)) * 100
        short_pct = 100 - long_pct

        teks_harga = format_harga_koin(kode_aktif, harga, kurs_idr)
        label_harga = f"Harga {kode_aktif}-USDT Saat Ini" if (kode_aktif == "BTC" or kurs_idr is None) else f"Harga {kode_aktif}-IDR (Kurs Rp{kurs_idr:,.0f} via {sumber_kurs})"

        with st.container(border=True):
            st.metric(label=label_harga, value=teks_harga)

        st.subheader("🎯 Kesimpulan Sinyal")
        _, _, rek_judul, rek_ket, p_beli, p_jual, rek_warna = buat_kesimpulan(
            rasio_akun, rasio_volume, nilai_rsi, funding_rate, data_global["skor_global"]
        )
        getattr(st, rek_warna)(f"**{rek_judul}**\n\n{rek_ket}")

        with st.container(border=True):
            k1, k2 = st.columns(2)
            k1.metric("Sinyal Beli (Long)", f"{p_beli:.1f}%")
            k2.metric("Sinyal Jual (Short)", f"{p_jual:.1f}%")

        st.subheader("🔍 Rincian 6 Indikator")

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

        with st.container(border=True):
            st.markdown("**4. Biaya Pendanaan Futures (Funding Rate)**")
            st.metric("Funding Rate", f"{funding_rate:+.4f}%" if funding_rate is not None else "-")
            pesan_fr, warna_fr = cek_funding_rate(funding_rate)
            getattr(st, warna_fr)(pesan_fr)

        with st.container(border=True):
            st.markdown("**5. Psikologi Pasar Global (Fear & Greed Index)**")
            if data_global["fng_val"] is not None:
                fng_v = data_global["fng_val"]
                ikon_fng = "🟢" if fng_v <= 40 else ("🔴" if fng_v >= 65 else "🟡")
                st.markdown(
                    f"""
                    <div style="font-size:0.85rem; opacity:0.8;">Skor Psikologi</div>
                    <div style="font-size:1.6rem; font-weight:700; line-height:1.2;">{fng_v} / 100</div>
                    <div style="font-size:0.85rem; margin-top:2px; margin-bottom:8px;">{ikon_fng} {data_global['fng_class']}</div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                st.metric("Skor Psikologi", "-")
            pesan_fng, warna_fng = cek_fear_greed(data_global["fng_val"], data_global["fng_class"])
            getattr(st, warna_fng)(pesan_fng)

        with st.container(border=True):
            st.markdown("**6. Narasi Berita & Makroekonomi (DXY)**")
            m1, m2 = st.columns(2)
            lbl_brt_det = data_global["label_berita"]
            ikon_b_det = "🟢" if lbl_brt_det == "Bullish" else ("🔴" if lbl_brt_det == "Bearish" else "🟡")
            m1.markdown(
                f"""
                <div style="font-size:0.85rem; opacity:0.8;">Skor Berita</div>
                <div style="font-size:1.55rem; font-weight:700; line-height:1.2;">{data_global['skor_berita']:+d} Poin</div>
                <div style="font-size:0.82rem; margin-top:2px; margin-bottom:8px;">{ikon_b_det} {lbl_brt_det}</div>
                """,
                unsafe_allow_html=True,
            )
            if data_global["dxy_val"] is not None:
                lbl_dxy_det = data_global["label_dxy"]
                ikon_dxy_det = "🟢" if "Bullish" in lbl_dxy_det else ("🔴" if "Bearish" in lbl_dxy_det else "🟡")
                m2.markdown(
                    f"""
                    <div style="font-size:0.85rem; opacity:0.8;">Indeks Dolar (DXY)</div>
                    <div style="font-size:1.55rem; font-weight:700; line-height:1.2;">{data_global['dxy_val']:.2f}</div>
                    <div style="font-size:0.82rem; margin-top:2px; margin-bottom:8px;">{ikon_dxy_det} {lbl_dxy_det} ({data_global['dxy_chg']:+.2f}%)</div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                m2.metric("Indeks Dolar (DXY)", "-")

            pesan_bm, warna_bm = cek_berita_dan_makro(
                data_global["skor_berita"],
                data_global["label_berita"],
                data_global["dxy_chg"],
                data_global["label_dxy"],
            )
            getattr(st, warna_bm)(pesan_bm)
            if len(data_global["judul_berita"]) > 0:
                sumber_label = f" ({data_global['sumber_berita']})" if data_global["sumber_berita"] else ""
                with st.expander(f"📰 Lihat 5 Judul Berita Kripto Terbaru{sumber_label}"):
                    for j in data_global["judul_berita"]:
                        st.markdown(f"- {j}")
    else:
        st.error("Gagal mengambil data dari API OKX. Silakan muat ulang halaman.")
        for err in (err1, err2, err3):
            if err:
                st.caption(err)


