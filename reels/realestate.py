"""주간 부동산(토요일 12:00) 근거 숫자: 공공데이터포털 무료 API (일반 인증키 Decoding).
Secrets: DATA_GO_KR_TRADE_KEY(실거래가), DATA_GO_KR_APPLY_KEY(청약홈). 하나만 쓰면 DATA_GO_KR_KEY.
- 국토교통부 아파트 매매 실거래가: 최근 7일 신고된 서울 아파트 매매 건수·최고가 거래
- 한국부동산원 청약홈 분양정보: 앞으로 열흘 안에 청약 접수하는 아파트
키가 없거나 호출이 실패하면 None → 뉴스 기사만으로 만듦 (2026-11-24 사용자 결정: 주 1편으로 시작)."""
import datetime as dt
import re
import xml.etree.ElementTree as ET

import requests

from . import config

KST = dt.timezone(dt.timedelta(hours=9))
TRADE_API = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade"
APPLY_API = "https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/getAPTLttotPblancDetail"
SEOUL = {"11110": "종로구", "11140": "중구", "11170": "용산구", "11200": "성동구", "11215": "광진구",
         "11230": "동대문구", "11260": "중랑구", "11290": "성북구", "11305": "강북구", "11320": "도봉구",
         "11350": "노원구", "11380": "은평구", "11410": "서대문구", "11440": "마포구", "11470": "양천구",
         "11500": "강서구", "11530": "구로구", "11545": "금천구", "11560": "영등포구", "11590": "동작구",
         "11620": "관악구", "11650": "서초구", "11680": "강남구", "11710": "송파구", "11740": "강동구"}


def key(kind=""):
    """kind: trade(국토교통부 실거래가) | apply(청약홈). 서비스별 키가 없으면 공통 키(DATA_GO_KR_KEY)."""
    name = {"trade": "DATA_GO_KR_TRADE_KEY", "apply": "DATA_GO_KR_APPLY_KEY"}.get(kind)
    return ((config.env(name) if name else None) or config.env("DATA_GO_KR_KEY") or "").strip()


def _tag(el, *names):
    for n in names:
        c = el.find(n)
        if c is not None and (c.text or "").strip():
            return c.text.strip()
    return ""


def _trades(lawd, ymd):
    r = requests.get(TRADE_API, timeout=20, params={"serviceKey": key("trade"), "LAWD_CD": lawd, "DEAL_YMD": ymd,
                                                    "numOfRows": 1000, "pageNo": 1})
    r.raise_for_status()
    root = ET.fromstring(r.content)
    code = _tag(root, ".//resultCode")
    if code and code not in ("00", "000"):
        raise RuntimeError(f"실거래가 API 오류 {code}: {_tag(root, './/resultMsg')}")
    out = []
    for it in root.iter("item"):
        try:
            amt = int(re.sub(r"\D", "", _tag(it, "dealAmount", "거래금액")) or 0)   # 만원
            day = dt.date(int(_tag(it, "dealYear", "년")), int(_tag(it, "dealMonth", "월")), int(_tag(it, "dealDay", "일")))
        except (ValueError, TypeError):
            continue
        if _tag(it, "cdealType", "해제여부") in ("O", "o"):   # 계약 해제된 거래 제외
            continue
        out.append({"apt": _tag(it, "aptNm", "아파트"), "dong": _tag(it, "umdNm", "법정동"), "amt": amt, "day": day,
                    "area": _tag(it, "excluUseAr", "전용면적"), "gu": SEOUL.get(lawd, "")})
    return out


def _won(man):
    eok, rest = divmod(man, 10000)
    return (f"{eok}억" + (f" {rest:,}만" if rest else "") + "원") if eok else f"{man:,}만원"


def seoul_week():
    today = dt.datetime.now(KST).date()
    since = today - dt.timedelta(days=7)
    months = sorted({today.strftime("%Y%m"), since.strftime("%Y%m")})
    rows = []
    for lawd in SEOUL:
        for ym in months:
            rows += [t for t in _trades(lawd, ym) if since <= t["day"] <= today]
    if not rows:
        return None
    top = sorted(rows, key=lambda t: -t["amt"])[:3]
    by_gu = {}
    for t in rows:
        by_gu[t["gu"]] = by_gu.get(t["gu"], 0) + 1
    busiest = sorted(by_gu.items(), key=lambda x: -x[1])[:3]
    lines = [f"[서울 아파트 매매 실거래 (국토교통부, 계약일 {since}~{today}, 신고 기한이 30일이라 건수는 앞으로 늘어남)]",
             f"- 최근 7일 신고된 서울 아파트 매매: {len(rows):,}건",
             "- 거래가 많은 구: " + ", ".join(f"{g} {n}건" for g, n in busiest)]
    for t in top:
        area = f"전용 {float(t['area']):.0f}㎡" if t["area"] else ""
        lines.append(f"- 높은 거래가: {t['gu']} {t['dong']} {t['apt']} {area} {_won(t['amt'])} ({t['day']:%m월 %d일})")
    return "\n".join(lines)


def upcoming_subscriptions(days=10):
    today = dt.datetime.now(KST).date()
    r = requests.get(APPLY_API, timeout=20, params={
        "serviceKey": key("apply"), "page": 1, "perPage": 100,
        "cond[RCEPT_BGNDE::GTE]": today.isoformat(),
        "cond[RCEPT_BGNDE::LTE]": (today + dt.timedelta(days=days)).isoformat()})
    r.raise_for_status()
    items = r.json().get("data", [])
    if not items:
        return None
    items.sort(key=lambda x: (x.get("RCEPT_BGNDE") or "", -int(x.get("TOT_SUPLY_HSHLDCO") or 0)))
    lines = [f"[앞으로 {days}일 안에 청약 접수하는 아파트 (청약홈, {today} 기준, 총 {len(items)}곳)]"]
    for x in sorted(items, key=lambda x: -int(x.get("TOT_SUPLY_HSHLDCO") or 0))[:5]:
        lines.append(f"- {x.get('HOUSE_NM', '')} ({x.get('SUBSCRPT_AREA_CODE_NM') or ''}, {x.get('HSSPLY_ADRES', '')[:30]}): "
                     f"{int(x.get('TOT_SUPLY_HSHLDCO') or 0):,}가구, 접수 {x.get('RCEPT_BGNDE', '')}~{x.get('RCEPT_ENDDE', '')}")
    return "\n".join(lines)


def material():
    """주간 부동산 근거 자료(dict) 또는 None."""
    parts = []
    for name, kind, f in (("실거래가", "trade", seoul_week), ("청약 일정", "apply", upcoming_subscriptions)):
        if not key(kind):
            print(f"  [부동산] {name} 키 없음 → 건너뜀")
            continue
        try:
            t = f()
            if t:
                parts.append(t)
        except Exception as e:
            print(f"  [부동산] {name} 조회 실패(건너뜀): {e}")
    if not parts:
        return None
    body = "\n\n".join(parts)
    print("  " + body.replace("\n", "\n  "))
    return {"title": "부동산 공공데이터", "source": "국토교통부·청약홈", "link": "https://www.data.go.kr",
            "summary": "", "body": body}
