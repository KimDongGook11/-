"""관련 시세 차트 이미지 생성 (최근 1개월, 무료 Yahoo Finance 데이터)."""
import datetime as dt

import requests

from . import config
from .utils import font_file

UP, DOWN = "#FF4D4F", "#3B82F6"   # 한국식: 상승 빨강, 하락 파랑


def get_series(ticker):
    try:
        import yfinance as yf
        h = yf.Ticker(ticker).history(period="1mo", interval="1d")
        closes = [float(x) for x in h["Close"].dropna().tolist()]
        dates = [d.to_pydatetime() for d in h["Close"].dropna().index]
        if len(closes) >= 5:
            return dates, closes
    except Exception as e:
        print(f"  [차트] yfinance 실패: {e}")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    r = requests.get(url, params={"range": "1mo", "interval": "1d"}, headers=config.UA, timeout=15)
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    pts = [(dt.datetime.fromtimestamp(t), c) for t, c in
           zip(res["timestamp"], res["indicators"]["quote"][0]["close"]) if c is not None]
    if len(pts) < 5:
        raise ValueError("데이터 부족")
    return [p[0] for p in pts], [float(p[1]) for p in pts]


def _fmt(v):
    if v >= 10000:
        return f"{v:,.0f}"
    if v >= 100:
        return f"{v:,.2f}"
    return f"{v:,.3f}"


def draw(dates, closes, label, out, w=960, h=700):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties
    from matplotlib.patches import FancyBboxPatch

    ff = font_file(True)
    fp = (lambda s: FontProperties(fname=ff, size=s)) if ff else (lambda s: FontProperties(size=s))
    chg = (closes[-1] / closes[0] - 1) * 100
    col = UP if chg >= 0 else DOWN

    fig = plt.figure(figsize=(w / 100, h / 100), dpi=100)
    fig.patch.set_alpha(0)
    bg = FancyBboxPatch((0.01, 0.01), 0.98, 0.98, boxstyle="round,pad=0,rounding_size=0.04",
                        transform=fig.transFigure, facecolor="#0B1220", alpha=0.9,
                        edgecolor="#2A3550", linewidth=2, zorder=-10)
    fig.patches.append(bg)
    fig.text(0.06, 0.88, label, color="#CBD5E1", fontproperties=fp(26))
    fig.text(0.06, 0.76, _fmt(closes[-1]), color="white", fontproperties=fp(46))
    arrow = "▲" if chg >= 0 else "▼"
    fig.text(0.94, 0.78, f"{arrow} {abs(chg):.2f}%", color=col, ha="right", fontproperties=fp(40))

    ax = fig.add_axes([0.07, 0.12, 0.86, 0.58])
    ax.set_facecolor("none")
    x = list(range(len(closes)))
    ax.plot(x, closes, color=col, linewidth=4, solid_capstyle="round")
    lo = min(closes)
    pad = (max(closes) - lo) * 0.12 or 1
    ax.fill_between(x, closes, lo - pad, color=col, alpha=0.18)
    ax.set_ylim(lo - pad, max(closes) + pad)
    ax.set_xlim(0, len(x) - 1)
    ax.scatter([x[-1]], [closes[-1]], color=col, s=120, zorder=5)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(colors="#94A3B8", length=0)
    ax.set_yticks([])
    ax.set_xticks([0, len(x) - 1])
    ax.set_xticklabels([dates[0].strftime("%m/%d"), dates[-1].strftime("%m/%d")], fontproperties=fp(22))
    ax.grid(axis="y", color="#1E293B", linewidth=1)
    fig.savefig(out, transparent=True)
    plt.close(fig)
    return chg


def make_chart(chart, out, offline=False):
    if not chart:
        return None
    try:
        if offline:
            import math
            base = dt.datetime(2026, 10, 13)
            dates = [base + dt.timedelta(days=i) for i in range(22)]
            closes = [6000 + 80 * math.sin(i / 3) + i * 12 for i in range(22)]
        else:
            dates, closes = get_series(chart["ticker"])
        chg = draw(dates, closes, chart.get("label") or chart["ticker"], out)
        print(f"  [차트] {chart['ticker']} {chg:+.2f}%")
        return out
    except Exception as e:
        print(f"  [차트] 생략 ({chart.get('ticker')}): {e}")
        return None
