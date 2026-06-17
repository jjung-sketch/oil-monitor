"""
유가 모니터 — index.html 생성 (GitHub Pages 배포용)
데이터 소스:
  - WTI, 브렌트유, 싱가포르 가스오일: Yahoo Finance (yfinance)
  - 두바이유: 브렌트유 기준 추정 (역사적 스프레드 -$1.5/배럴)
  - 국내 평균 유가: 오피넷 avgAllPrice API
  - 남태령 주유소 + 주변: 오피넷 detailById + aroundAll API
"""
import os
import yfinance as yf
import plotly.graph_objects as go
import pandas as pd
import urllib.request
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, date

# ── 설정 ─────────────────────────────────────────────────
DUBAI_SPREAD  = -1.5
LOOKBACK_DAYS = 45
OPINET_KEY    = os.environ.get("OPINET_KEY", "F250618500")
TARGET_ID     = "A0000928"
TARGET_X      = "310659.3"
TARGET_Y      = "541009.5"
AROUND_RADIUS = "3000"

PRODCD_MAP = {"B027": "휘발유", "B034": "고급휘발유", "D047": "경유", "C004": "실내등유", "E012": "자동차용부탄"}

# ────────────────────────────────────────────────────────
# 1. 국제 유가 (yfinance)
# ────────────────────────────────────────────────────────
end   = datetime.today()
start = end - timedelta(days=LOOKBACK_DAYS)
yf_tickers = {"WTI": "CL=F", "브렌트유": "BZ=F", "싱가포르 가스오일": "SGB=F"}
prices = {}

for name, symbol in yf_tickers.items():
    df = yf.download(symbol, start=start, end=end, auto_adjust=True, progress=False)
    if df.empty:
        print(f"[경고] {name}({symbol}) 데이터 없음")
        continue
    close = df["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.squeeze()
    prices[name] = close.dropna().tail(30)

if "브렌트유" in prices:
    prices["두바이유(추정)"] = prices["브렌트유"] + DUBAI_SPREAD

intl_summary = {}
for name, series in prices.items():
    tp = float(series.iloc[-1]); pp = float(series.iloc[-2]) if len(series) >= 2 else tp
    chg = tp - pp
    intl_summary[name] = {"price": tp, "change": chg, "pct": chg/pp*100,
                          "date": series.index[-1].strftime("%Y-%m-%d"), "estimated": "추정" in name}

# ────────────────────────────────────────────────────────
# 2. 국내 평균 유가 (오피넷)
# ────────────────────────────────────────────────────────
SHOW_PRODUCTS = {"휘발유", "자동차용경유", "자동차용부탄"}
domestic = {}
try:
    url = f"http://www.opinet.co.kr/api/avgAllPrice.do?out=xml&code={OPINET_KEY}"
    with urllib.request.urlopen(url, timeout=10) as r:
        root = ET.fromstring(r.read())
    for item in root.iter("OIL"):
        nm    = item.findtext("PRODNM", "").strip()
        price = item.findtext("PRICE",  "0").strip()
        diff  = item.findtext("DIFF",   "0").strip()
        dt    = item.findtext("TRADE_DT", "").strip()
        if nm in SHOW_PRODUCTS:
            fp = float(price); fd = float(diff)
            domestic[nm] = {"price": fp, "change": fd,
                            "pct": fd/(fp-fd)*100 if fp != fd else 0,
                            "date": f"{dt[:4]}-{dt[4:6]}-{dt[6:]}"}
    print(f"✅ 국내 평균: {list(domestic.keys())}")
except Exception as e:
    print(f"⚠️  국내 평균 수집 실패: {e}")

# ────────────────────────────────────────────────────────
# 3. 남태령 주유소 상세 + 주변 주유소
# ────────────────────────────────────────────────────────
target_station = {}
around_stations = []

try:
    url = f"http://www.opinet.co.kr/api/detailById.do?out=json&code={OPINET_KEY}&id={TARGET_ID}"
    with urllib.request.urlopen(url, timeout=10) as r:
        d = json.loads(r.read().decode("utf-8", errors="replace"))
    st = d["RESULT"]["OIL"][0]
    target_station = {
        "name": st["OS_NM"], "addr": st["NEW_ADR"],
        "prices": {PRODCD_MAP.get(p["PRODCD"], p["PRODCD"]): p["PRICE"]
                   for p in st.get("OIL_PRICE", [])},
    }
    print(f"✅ 대상 주유소: {target_station['name']}")

    url2 = (f"http://www.opinet.co.kr/api/aroundAll.do?"
            f"out=json&code={OPINET_KEY}&x={TARGET_X}&y={TARGET_Y}"
            f"&radius={AROUND_RADIUS}&prodcd=B027&sort=2")
    with urllib.request.urlopen(url2, timeout=10) as r:
        d2 = json.loads(r.read().decode("utf-8", errors="replace"))
    for s in d2.get("RESULT", {}).get("OIL", []):
        if s.get("UNI_ID") == TARGET_ID:
            continue
        around_stations.append({
            "name": s.get("OS_NM", ""),
            "addr": s.get("NEW_ADR", s.get("VAN_ADR", ""))[:25],
            "price_gas": s.get("PRICE", "-"),
        })
        if len(around_stations) >= 10:
            break
    print(f"✅ 주변 주유소: {len(around_stations)}개")
except Exception as e:
    print(f"⚠️  주유소 데이터 수집 실패: {e}")

# ────────────────────────────────────────────────────────
# 4. 차트
# ────────────────────────────────────────────────────────
colors   = {"WTI": "#E07B54", "브렌트유": "#5B9BD5", "두바이유(추정)": "#7DC98F", "싱가포르 가스오일": "#A569BD"}
dash_map = {"두바이유(추정)": "dot"}

fig = go.Figure()
for name, series in prices.items():
    fig.add_trace(go.Scatter(
        x=series.index, y=series.values, name=name, mode="lines+markers",
        line=dict(width=2, color=colors.get(name, "#888"), dash=dash_map.get(name, "solid")),
        marker=dict(size=4),
        hovertemplate=f"<b>{name}</b><br>%{{x|%Y-%m-%d}}<br>$%{{y:.2f}}<extra></extra>",
    ))
fig.update_layout(
    title=dict(text="국제 유가 추이 (최근 30거래일)", font=dict(size=16)),
    xaxis_title="날짜", yaxis_title="USD/배럴",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    hovermode="x unified", plot_bgcolor="#f9f9f9", paper_bgcolor="#fff",
    margin=dict(t=50, b=40, l=60, r=20),
)

# ────────────────────────────────────────────────────────
# 5. HTML 생성
# ────────────────────────────────────────────────────────
def intl_card(name, s):
    arrow = "▲" if s["change"] >= 0 else "▼"
    c = "#c0392b" if s["change"] >= 0 else "#2980b9"
    sign = "+" if s["change"] >= 0 else ""
    note = ('<div style="font-size:11px;color:#e67e22;margin-top:4px;">* 브렌트 기준 추정</div>'
            if s["estimated"] else
            '<div style="font-size:11px;color:#888;margin-top:4px;">NYMEX SGB=F</div>'
            if name == "싱가포르 가스오일" else "")
    return f"""<div style="background:#fff;border-radius:12px;padding:16px 22px;
        box-shadow:0 2px 8px rgba(0,0,0,.07);min-width:170px;text-align:center;">
      <div style="font-size:12px;color:#888;margin-bottom:2px;">{name}</div>
      <div style="font-size:26px;font-weight:700;color:#222;">${s['price']:.2f}</div>
      <div style="font-size:13px;color:{c};margin-top:2px;">{arrow} {sign}{s['change']:.2f} ({sign}{s['pct']:.2f}%)</div>
      <div style="font-size:11px;color:#bbb;margin-top:3px;">{s['date']} · USD/BBL</div>{note}
    </div>"""

def dom_card(name, s):
    arrow = "▲" if s["change"] >= 0 else "▼"
    c = "#c0392b" if s["change"] >= 0 else "#2980b9"
    sign = "+" if s["change"] >= 0 else ""
    label = name.replace("자동차용경유","경유").replace("자동차용부탄","LPG(부탄)")
    return f"""<div style="background:#fff;border-radius:12px;padding:16px 22px;
        box-shadow:0 2px 8px rgba(0,0,0,.07);min-width:150px;text-align:center;">
      <div style="font-size:12px;color:#888;margin-bottom:2px;">국내 {label}</div>
      <div style="font-size:26px;font-weight:700;color:#222;">{s['price']:,.0f}</div>
      <div style="font-size:13px;color:{c};margin-top:2px;">{arrow} {sign}{s['change']:.2f}원</div>
      <div style="font-size:11px;color:#bbb;margin-top:3px;">{s['date']} · 원/L · 전국평균</div>
    </div>"""

def price_rows(prices_dict):
    rows = ""
    for fuel, price in prices_dict.items():
        rows += f'<tr><td style="padding:6px 12px;color:#555;">{fuel}</td><td style="padding:6px 12px;font-weight:600;text-align:right;">{price:,}원/L</td></tr>'
    return rows

around_rows = ""
for s in around_stations:
    around_rows += f"""<tr>
      <td style="padding:7px 12px;">{s['name']}</td>
      <td style="padding:7px 12px;color:#666;font-size:12px;">{s['addr']}</td>
      <td style="padding:7px 12px;font-weight:600;text-align:right;">{s['price_gas']:,}원/L</td>
    </tr>"""

intl_cards_html = "".join(intl_card(n, s) for n, s in intl_summary.items())
dom_cards_html  = "".join(dom_card(n, s)  for n, s in domestic.items()) if domestic else ""
chart_html = fig.to_html(full_html=False, include_plotlyjs="cdn")
now_str    = datetime.now().strftime("%Y-%m-%d %H:%M")
target_nm  = target_station.get("name", "(주)대농석유 남태령주유소")
target_addr= target_station.get("addr", "서울 서초구 과천대로 838")
pr_rows    = price_rows(target_station.get("prices", {}))

html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>유가 모니터</title>
  <style>
    * {{ box-sizing:border-box; }}
    body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
           background:#f4f6f9;margin:0;padding:24px;color:#333; }}
    h2 {{ font-size:15px;font-weight:700;margin:0 0 12px;color:#444;
          border-left:4px solid #5B9BD5;padding-left:8px; }}
    .sub {{ font-size:12px;color:#aaa;margin-bottom:20px; }}
    .cards {{ display:flex;gap:12px;flex-wrap:wrap;margin-bottom:18px; }}
    .box {{ background:#fff;border-radius:12px;padding:20px;
            box-shadow:0 2px 8px rgba(0,0,0,.07);margin-bottom:18px; }}
    hr {{ border:none;border-top:1px solid #eee;margin:18px 0; }}
    table {{ width:100%;border-collapse:collapse;font-size:14px; }}
    th {{ background:#f8f8f8;padding:8px 12px;text-align:left;font-size:12px;color:#888;border-bottom:1px solid #eee; }}
    tr:hover {{ background:#fafafa; }}
    .station-card {{
      background:#fff;border-radius:12px;padding:18px 22px;
      box-shadow:0 2px 8px rgba(0,0,0,.07);cursor:pointer;
      border:2px solid transparent;transition:border-color .2s;
    }}
    .station-card:hover {{ border-color:#5B9BD5; }}
    .station-card h3 {{ margin:0 0 4px;font-size:15px;color:#222; }}
    .station-card .addr {{ font-size:12px;color:#999;margin-bottom:10px; }}
    .toggle-hint {{ font-size:12px;color:#5B9BD5;margin-top:8px; }}
    #around-panel {{ display:none;margin-top:14px; }}
  </style>
</head>
<body>
  <h1 style="font-size:21px;font-weight:700;margin:0 0 4px;">🛢 유가 모니터</h1>
  <div class="sub">업데이트: {now_str} (KST) &nbsp;|&nbsp; 국제: Yahoo Finance &nbsp;|&nbsp; 국내: 오피넷</div>

  <h2>🌐 국제 유가 (USD/배럴)</h2>
  <div class="cards">{intl_cards_html}</div>
  <div class="box">{chart_html}</div>
  <hr>

  <h2>⛽ 국내 주유소 평균 (원/리터)</h2>
  <div class="cards">{dom_cards_html}</div>
  <hr>

  <h2>📍 특정 주유소</h2>
  <div class="station-card" onclick="toggleAround()">
    <h3>{target_nm}</h3>
    <div class="addr">{target_addr}</div>
    <table>
      <tr><th>유종</th><th style="text-align:right;">가격</th></tr>
      {pr_rows}
    </table>
    <div class="toggle-hint" id="hint">▼ 클릭하면 주변 주유소 보기</div>
  </div>

  <div id="around-panel">
    <div class="box">
      <h2 style="margin-top:0;">🗺 주변 주유소 3km 이내 — 휘발유 거리순</h2>
      <table>
        <tr>
          <th>주유소명</th><th>주소</th><th style="text-align:right;">휘발유</th>
        </tr>
        {around_rows}
      </table>
    </div>
  </div>

  <script>
    var open = false;
    function toggleAround() {{
      open = !open;
      document.getElementById('around-panel').style.display = open ? 'block' : 'none';
      document.getElementById('hint').textContent = open ? '▲ 클릭하면 접기' : '▼ 클릭하면 주변 주유소 보기';
    }}
  </script>
</body>
</html>"""

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html)

print(f"✅ index.html 저장 완료 ({now_str})")
