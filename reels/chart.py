"""시세 차트 이미지 생성 (무료 Yahoo Finance 데이터).
- 뉴스: 최근 1개월 일봉
- '그때 그 결정': start_year부터 현재까지 월봉 + '그때' 표시, 그때 대비 몇 배인지"""
import datetime as dt

import requests

from . import config
from . import fonts

UP, DOWN = "#FF4D4F", "#3B82F6"   # 한국식: 상승 빨강, 하락 파랑
MARK = "#FFD400"


def get_series(ticker, start_year=None):
    long = bool(start_year)
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        h = t.history(start=f"{start_year}-01-01", interval="1mo") if long else t.history(period="1mo", interval="1d")
        s = h["Close"].dropna()
        closes = [float(x) for x in s.tolist()]
        dates = [d.to_pydatetime().replace(tzinfo=None) for d in s.index]
        if len(closes) >= 5:
            return dates, closes
    except Exception as e:
        print(f"  [차트] yfinance 실패: {e}")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    params = {"range": "max", "interval": "1mo"} if long else {"range": "1mo", "interval": "1d"}
    r = requests.get(url, params=params, headers=config.UA, timeout=15)
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    pts = [(dt.datetime.fromtimestamp(t), c) for t, c in
           zip(res["timestamp"], res["indicators"]["quote"][0]["close"]) if c is not None]
    if long:
        pts = [p for p in pts if p[0].year >= start_year]
    if len(pts) < 5:
        raise ValueError("데이터 부족")
    return [p[0] for p in pts], [float(p[1]) for p in pts]


def _fmt(v):
    if v >= 10000:
        return f"{v:,.0f}"
    if v >= 100:
        return f"{v:,.2f}"
    return f"{v:,.3f}"


def draw(dates, closes, label, out, w=960, h=580, mark_year=None, upto=1.0):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties
    from matplotlib.patches import FancyBboxPatch

    ff = fonts.path("Bold")
    fp = (lambda s: FontProperties(fname=ff, size=s)) if ff else (lambda s: FontProperties(size=s))
    mi = None
    if mark_year and dates[0].year <= mark_year:      # 데이터가 그 해를 포함할 때만 '그때' 표시
        mi = next((i for i, d in enumerate(dates) if d.year >= mark_year), None)
    base = closes[mi] if mi is not None else closes[0]
    ratio = closes[-1] / base
    chg = (ratio - 1) * 100
    col = UP if chg >= 0 else DOWN

    fig = plt.figure(figsize=(w / 100, h / 100), dpi=100)
    fig.patch.set_alpha(0)
    bg = FancyBboxPatch((0.01, 0.01), 0.98, 0.98, boxstyle="round,pad=0,rounding_size=0.04",
                        transform=fig.transFigure, facecolor="#0B1220", alpha=0.9,
                        edgecolor="#2A3550", linewidth=2, zorder=-10)
    fig.patches.append(bg)
    fig.text(0.06, 0.88, label, color="#CBD5E1", fontproperties=fp(26))
    fig.text(0.06, 0.76, _fmt(closes[max(2, int(round(len(closes) * upto))) - 1]), color="white", fontproperties=fp(46))
    if mi is not None and ratio >= 2:
        badge = f"그때 대비 ×{ratio:,.0f}배" if ratio >= 10 else f"그때 대비 ×{ratio:.1f}배"
    elif mi is not None:
        badge = f"그때 대비 {'▲' if chg >= 0 else '▼'} {abs(chg):.0f}%"
    else:
        badge = f"{'▲' if chg >= 0 else '▼'} {abs(chg):.2f}%"
    if upto >= 1.0:
        fig.text(0.94, 0.78, badge, color=col, ha="right", fontproperties=fp(36 if mi is not None else 40))

    ax = fig.add_axes([0.07, 0.12, 0.86, 0.58])
    ax.set_facecolor("none")
    x = list(range(len(closes)))
    n = max(2, int(round(len(closes) * upto)))
    log = min(closes) > 0 and max(closes) / min(closes) > 20
    if log:
        ax.set_yscale("log")
    ax.plot(x[:n], closes[:n], color=col, linewidth=4 if len(x) < 60 else 3, solid_capstyle="round")
    lo, hi = min(closes), max(closes)
    floor = lo * 0.8 if log else lo - ((hi - lo) * 0.12 or 1)
    ax.fill_between(x[:n], closes[:n], floor, color=col, alpha=0.18)
    ax.set_ylim(floor, hi * 1.25 if log else hi + ((hi - lo) * 0.12 or 1))
    ax.set_xlim(0, len(x) - 1)
    ax.scatter([x[n - 1]], [closes[n - 1]], color=col, s=120, zorder=5)
    if mi is not None and n > mi:
        ax.axvline(mi, color=MARK, linewidth=2.5, linestyle=(0, (4, 4)), zorder=4)
        ax.scatter([mi], [closes[mi]], color=MARK, s=140, zorder=6)
        ax.annotate(f"그때 ({dates[mi].year})", (mi, closes[mi]), xytext=(12, 18), textcoords="offset points",
                    color=MARK, fontproperties=fp(24))
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(colors="#94A3B8", length=0)
    ax.set_yticks([])
    ax.minorticks_off()
    ax.set_xticks([0, len(x) - 1])
    fmt = "%Y" if (dates[-1] - dates[0]).days > 400 else "%m/%d"
    ax.set_xticklabels([dates[0].strftime(fmt), dates[-1].strftime(fmt)], fontproperties=fp(22))
    fig.savefig(out, transparent=True)
    plt.close(fig)
    return chg


def _data(chart, offline, start_year):
    import math
    if offline:
        if start_year:
            dates = [dt.datetime(start_year + i // 12, i % 12 + 1, 1) for i in range((2026 - start_year) * 12)]
            closes = [0.3 * math.exp(i / 45) * (1 + 0.15 * math.sin(i / 7)) for i in range(len(dates))]
        else:
            base = dt.datetime(2026, 10, 13)
            dates = [base + dt.timedelta(days=i) for i in range(22)]
            closes = [6000 + 80 * math.sin(i / 3) + i * 12 for i in range(22)]
        return dates, closes
    return get_series(chart["ticker"], start_year)


def make_chart_frames(chart, out_dir, offline=False, start_year=None, mark_year=None, frames=24, w=960, h=580):
    """선이 왼쪽부터 그려지는 애니메이션 프레임. 반환: (파일 패턴, 프레임 수, 폭, 높이) 또는 None"""
    if not chart or not chart.get("ticker"):
        return None
    try:
        dates, closes = _data(chart, offline, start_year)
        out_dir.mkdir(parents=True, exist_ok=True)
        label = chart.get("label") or chart["ticker"]
        for i in range(frames):
            k = 1 - (1 - (i + 1) / frames) ** 2
            draw(dates, closes, label, out_dir / f"{i:04d}.png", w=w, h=h, mark_year=mark_year, upto=k)
        print(f"  [차트] {chart['ticker']} 애니메이션 {frames}프레임")
        return str(out_dir / "%04d.png"), frames, w, h
    except Exception as e:
        print(f"  [차트] 생략 ({chart.get('ticker')}): {e}")
        return None


def make_chart(chart, out, offline=False, start_year=None, mark_year=None):
    if not chart or not chart.get("ticker"):
        return None
    try:
        if offline:
            import math
            if start_year:
                dates = [dt.datetime(start_year + i // 12, i % 12 + 1, 1) for i in range((2026 - start_year) * 12)]
                closes = [0.3 * math.exp(i / 45) * (1 + 0.15 * math.sin(i / 7)) for i in range(len(dates))]
            else:
                base = dt.datetime(2026, 10, 13)
                dates = [base + dt.timedelta(days=i) for i in range(22)]
                closes = [6000 + 80 * math.sin(i / 3) + i * 12 for i in range(22)]
        else:
            dates, closes = get_series(chart["ticker"], start_year)
        chg = draw(dates, closes, chart.get("label") or chart["ticker"], out, mark_year=mark_year)
        print(f"  [차트] {chart['ticker']} {chg:+.2f}%")
        return out
    except Exception as e:
        print(f"  [차트] 생략 ({chart.get('ticker')}): {e}")
        return None
