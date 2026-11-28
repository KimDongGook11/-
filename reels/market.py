"""시세 스냅샷 (무료 Yahoo Finance).
증시 브리핑의 지수·환율·종목 숫자는 기사 대신 여기서 직접 가져와 대본 근거 자료 맨 앞에 넣습니다
(AI가 기사 숫자를 옮기다 틀리는 일을 줄이기 위해, 2026-11-21 운영 개편)."""
import datetime as dt

from . import config

US = [("^GSPC", "S&P 500"), ("^IXIC", "나스닥"), ("^DJI", "다우"), ("^SOX", "필라델피아 반도체지수"),
      ("^TNX", "미국 10년물 국채 금리"), ("KRW=X", "원/달러 환율"), ("CL=F", "WTI 유가"), ("BTC-USD", "비트코인"),
      ("NVDA", "엔비디아"), ("TSLA", "테슬라"), ("AAPL", "애플")]
KR = [("^KS11", "코스피"), ("^KQ11", "코스닥"), ("KRW=X", "원/달러 환율"), ("005930.KS", "삼성전자"),
      ("000660.KS", "SK하이닉스"), ("005380.KS", "현대차"), ("035420.KS", "네이버")]


def _bars(ticker):
    """최근 일봉 [(날짜, 종가)]. 실패하면 []."""
    try:
        import yfinance as yf
        h = yf.Ticker(ticker).history(period="10d", interval="1d")
        s = h["Close"].dropna()
        return [(d.date(), float(c)) for d, c in zip(s.index, s.tolist())]
    except Exception as e:
        print(f"  [시세] {ticker} 실패: {e}")
    try:
        import requests
        r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
                         params={"range": "10d", "interval": "1d"}, headers=config.UA, timeout=15)
        res = r.json()["chart"]["result"][0]
        tz = dt.timezone(dt.timedelta(seconds=res["meta"].get("gmtoffset", 0)))
        return [(dt.datetime.fromtimestamp(t, tz).date(), float(c)) for t, c in
                zip(res["timestamp"], res["indicators"]["quote"][0]["close"]) if c is not None]
    except Exception as e:
        print(f"  [시세] {ticker} 대체 조회도 실패: {e}")
        return []


def last_session(ticker):
    """가장 최근 거래일 날짜 (휴장 판단용). 모르면 None."""
    b = _bars(ticker)
    return b[-1][0] if b else None


def snapshot(items):
    out = []
    for ticker, name in items:
        b = _bars(ticker)
        if len(b) < 2:
            continue
        (d, c), (_, p) = b[-1], b[-2]
        row = {"ticker": ticker, "name": name, "date": d.isoformat(), "close": c, "prev": p,
               "chg_pct": round((c - p) / p * 100, 2) if p else 0.0}
        if ticker == "^TNX":                      # 금리는 %가 아니라 bp(0.01%p)로 변화 표시
            row["chg_bp"] = round((c - p) * 100, 1)
        out.append(row)
    return out


def _num(v):
    if v >= 1000:
        return f"{v:,.2f}"
    return f"{v:,.2f}" if v >= 10 else f"{v:,.3f}"


def as_text(snap, title):
    """대본 근거 자료용 텍스트."""
    lines = [f"[{title}] (Yahoo Finance 종가 기준, 숫자는 이 표의 값만 그대로 사용)"]
    for r in snap:
        if r["ticker"] == "^TNX":
            lines.append(f"- {r['name']}: {r['close']:.2f}% (전일 대비 {r['chg_bp']:+.1f}bp) · 기준일 {r['date']}")
        elif r["ticker"] == "KRW=X":
            lines.append(f"- {r['name']}: {r['close']:,.1f}원 (전일 대비 {r['close'] - r['prev']:+,.1f}원, "
                         f"{r['chg_pct']:+.2f}%) · 기준일 {r['date']}")
        else:
            lines.append(f"- {r['name']}: {_num(r['close'])} (전일 대비 {r['chg_pct']:+.2f}%) · 기준일 {r['date']}")
    return "\n".join(lines)


def material(focus):
    """브리핑 시리즈의 시세 근거 자료 1개 (dict) 또는 None."""
    items, title = (US, "미국 증시 마감 시세") if focus == "us" else (KR, "국내 증시 마감 시세")
    snap = snapshot(items)
    if not snap:
        print("  [시세] 데이터를 못 가져와 기사 숫자만으로 진행")
        return None
    text = as_text(snap, title)
    print("  " + text.replace("\n", "\n  "))
    return {"title": title, "source": "Yahoo Finance", "link": "https://finance.yahoo.com", "summary": "",
            "body": text, "market": snap}


WEEK = [("^KS11", "코스피"), ("^KQ11", "코스닥"), ("KRW=X", "원/달러 환율"), ("005930.KS", "삼성전자"),
        ("000660.KS", "SK하이닉스"), ("^GSPC", "S&P 500"), ("^IXIC", "나스닥"), ("^SOX", "필라델피아 반도체지수"),
        ("^TNX", "미국 10년물 국채 금리"), ("CL=F", "WTI 유가")]


def weekly_material(sessions=5):
    """이슈 뒷담화(수·일)용: 최근 n거래일 등락 (마지막 종가 vs n거래일 전 종가)."""
    lines = [f"[최근 시세] (Yahoo Finance 종가 기준, 최근 {sessions}거래일 대비. 숫자는 이 표의 값만 그대로 사용)"]
    for ticker, name in WEEK:
        b = _bars(ticker)
        if len(b) < sessions + 1:
            continue
        (d1, c1), (d0, c0) = b[-1], b[-1 - sessions]
        if ticker == "^TNX":
            lines.append(f"- {name}: {c1:.2f}% ({d0}→{d1} {(c1 - c0) * 100:+.1f}bp)")
        elif ticker == "KRW=X":
            lines.append(f"- {name}: {c1:,.1f}원 ({d0}→{d1} {c1 - c0:+,.1f}원)")
        else:
            lines.append(f"- {name}: {_num(c1)} ({d0}→{d1} {(c1 - c0) / c0 * 100:+.2f}%)")
    if len(lines) < 3:
        return None
    text = "\n".join(lines)
    print("  " + text.replace("\n", "\n  "))
    return {"title": "최근 시세", "source": "Yahoo Finance", "link": "https://finance.yahoo.com",
            "summary": "", "body": text}


def _won(v):
    """원 → '약 1억 2,340만 원' (만 원 단위 반올림)."""
    man = int(round(v / 10000))
    eok, rest = divmod(man, 10000)
    if eok:
        return f"약 {eok}억" + (f" {rest:,}만 원" if rest else " 원")
    return f"약 {man:,}만 원"


def what_if(ticker, year, amount=1_000_000):
    """'그때 샀다면' (그때 그 결정 쇼츠용, 2026-11-28 사용자 결정).
    그해 첫 달(상장이 늦으면 상장 첫 달) 종가에 amount원어치 샀다면 지금 가치. 분할 반영·배당 제외 주가 기준.
    반환: {"sentence", "number", "fact"} 또는 None(티커 없음·데이터 부족)."""
    if not ticker or not year:
        return None
    try:
        import yfinance as yf
        h = yf.Ticker(ticker).history(start=f"{int(year)}-01-01", interval="1mo", auto_adjust=False)
        s = h["Close"].dropna()
        if len(s) < 6:
            return None
        d0, p0, d1, p1 = s.index[0], float(s.iloc[0]), s.index[-1], float(s.iloc[-1])
    except Exception as e:
        print(f"  [그때 샀다면] {ticker} 시세 실패: {e}")
        return None
    if p0 <= 0:
        return None
    mult = p1 / p0
    now_v = amount * mult
    since = f"{d0.year}년" + ("" if d0.year == int(year) else "(상장 첫해)")
    kr = ticker.endswith((".KS", ".KQ"))
    note = "" if kr else " 달러 주가 기준이라 환율 변화는 빼고 계산했어요."
    if mult >= 1:
        change = f"{mult:,.1f}배" if mult >= 2 else f"{(mult - 1) * 100:,.0f}% 늘어난"
        sentence = f"{since}에 이 회사 주식을 100만 원어치 샀다면, 지금은 {_won(now_v)}이에요. {change} 셈이죠.{note}"
        number = {"value": f"{mult:,.1f}배" if mult >= 2 else f"{(mult - 1) * 100:,.0f}%",   # 멘트에 나오는 숫자 그대로 (RULES 8)
                  "label": f"{since[:5]} 100만 원 →", "dir": "up"}
    else:
        sentence = (f"{since}에 이 회사 주식을 100만 원어치 샀다면, 지금은 {_won(now_v)}으로 "
                    f"{(1 - mult) * 100:,.0f}% 줄었어요.{note}")
        number = {"value": f"{(1 - mult) * 100:,.0f}%", "label": f"{since[:5]} 100만 원 →", "dir": "down"}
    fact = (f"그때 샀다면: {ticker} {d0:%Y-%m} 월말 종가 {p0:,.2f} → {d1:%Y-%m} {p1:,.2f} "
            f"({mult:,.2f}배, Yahoo Finance, 분할 반영·배당 제외)")
    print(f"  [그때 샀다면] {fact}")
    return {"sentence": sentence, "number": number, "fact": fact, "won": _won(now_v)}
