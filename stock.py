import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="Stock Bot Pro KR", page_icon="🟣", layout="wide")

ACCENT = "#B79CFF"
ACCENT_DARK = "#6E4CCB"
CSS_THEME = """
<style>
  .stApp { background: radial-gradient(circle at 12% 12%, #FFE8FB 0%, #FFE8FB 10%, transparent 40%), radial-gradient(circle at 88% 18%, #EDE2FF 0%, #EDE2FF 12%, transparent 45%), linear-gradient(180deg, #FFF9FE 0%, #FCFAFF 100%); color: #2B2B3A; }
  .block-container { padding-top: 1.2rem; padding-bottom: 2rem; max-width: 1260px; }
  .hero { padding: 1rem 1.2rem; border-radius: 18px; background: linear-gradient(90deg, #F7ECFF 0%, #FFF7FD 75%); border: 1px solid #EBD8FF; box-shadow: 0 6px 18px rgba(178,150,255,0.15); }
  .hero h1 { margin: 0; color: __ACCENT_DARK__; }
  .chip { display:inline-block; padding: 0.26rem 0.65rem; border-radius:999px; background:#EFE6FF; color:__ACCENT_DARK__; margin-right:0.4rem; font-size:0.78rem; }
  .soft-card { background:white; border:1px solid #EEE7FF; border-radius:14px; padding:0.85rem 1rem; }
  .purple { color: __ACCENT_DARK__; font-weight: 700; }
</style>
"""
st.markdown(CSS_THEME.replace("__ACCENT_DARK__", ACCENT_DARK), unsafe_allow_html=True)

WATCHLIST_FILE = Path("watchlist.json")
ALERT_RULES_FILE = Path("alert_rules.json")
ALERT_STATE_FILE = Path("alert_state.json")
CANDIDATE_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSM", "ASML", "JPM", "V", "MA", "COST", "KO", "PEP", "BRK-B",
    "SMCI", "SOFI", "PLTR", "HOOD", "RIVN", "RKLB", "IONQ", "U", "AAOI", "HIMS",
    "005930.KS", "000660.KS", "035420.KS", "051910.KS", "005380.KS", "068270.KS", "035720.KQ", "207940.KS",
    "263750.KS", "214150.KQ", "091990.KQ", "102120.KQ", "195940.KQ"
]

STRATEGY_PRESETS = {
    "Buffett (가치+품질)": {"roe_min": 0.12, "debt_to_equity_max": 140, "trailing_pe_max": 28, "profit_margin_min": 0.1},
    "Lynch (성장+PEG)": {"revenue_growth_min": 0.08, "trailing_pe_max": 35, "peg_ratio_max": 1.8},
    "Graham (안전마진)": {"trailing_pe_max": 20, "price_to_book_max": 3.0, "debt_to_equity_max": 100},
    "CANSLIM Lite": {"revenue_growth_min": 0.15, "earnings_growth_min": 0.15, "avg_volume_min": 2_000_000},
    "Minervini Lite": {"revenue_growth_min": 0.12, "trailing_pe_max": 60, "beta_min": 1.0},
    "Quality Growth": {"roe_min": 0.15, "gross_margin_min": 0.45, "revenue_growth_min": 0.1},
}

STYLE_HINTS = {
    "스캘핑": "체결속도/호가스프레드/수수료 관리가 핵심. 고유동성 위주, 손절 규칙 필수.",
    "스윙": "1일~수주 보유, 추세+실적 모멘텀 결합. 분할 매수/분할 매도 권장.",
    "장기투자": "3년+ 관점, 이익 성장과 재무건전성 중심. 리밸런싱 주기 유지.",
}

CAPITAL_HINTS = {
    "100만원 이하": "2~4개 종목 중심, 과도한 분산 지양. 거래비용 비중 관리.",
    "100만~1,000만원": "핵심 5~10개 + 현금 10~20% 고려.",
    "1,000만원 이상": "코어(장기)+위성(스윙) 구조와 MDD 제한 규칙 권장.",
}

ISSUE_SECTOR_MAP = {
    "금리 상승": {
        "good": ["에너지", "보험", "방산", "현금흐름 우량주"],
        "bad": ["고PER 성장주", "부채비율 높은 부동산", "장기채 민감주"],
    },
    "금리 인하": {
        "good": ["성장주", "소프트웨어", "반도체", "리츠"],
        "bad": ["원자재 단기 과열주"],
    },
    "인플레이션 재상승": {
        "good": ["원자재", "에너지", "필수소비재"],
        "bad": ["마진 취약 소비재", "고정가격 계약 비중 높은 업종"],
    },
    "경기 침체 우려": {
        "good": ["헬스케어", "유틸리티", "필수소비재", "배당주"],
        "bad": ["경기민감 소비재", "고레버리지 산업재"],
    },
    "AI/반도체 사이클 강세": {
        "good": ["반도체", "데이터센터 인프라", "전력기기", "클라우드"],
        "bad": ["수요 둔화 구간의 범용 하드웨어"],
    },
}

METRIC_LABELS_KR = {
    "currentPrice": "현재가",
    "marketCap": "시가총액",
    "trailingPE": "PER(최근)",
    "forwardPE": "PER(선행)",
    "priceToBook": "PBR",
    "returnOnEquity": "ROE",
    "debtToEquity": "부채비율",
    "revenueGrowth": "매출성장률",
    "earningsGrowth": "이익성장률",
    "profitMargins": "순이익률",
    "grossMargins": "매출총이익률",
    "beta": "베타",
    "averageVolume": "평균거래량",
}


def safe_num(value) -> Optional[float]:
    try:
        if value is None:
            return None
        v = float(value)
        if math.isnan(v):
            return None
        return v
    except Exception:
        return None


def format_value(v: Optional[float]) -> str:
    if v is None:
        return "-"
    if abs(v) >= 1_000_000_000:
        return f"{v/1_000_000_000:.2f}B"
    if abs(v) >= 1_000_000:
        return f"{v/1_000_000:.2f}M"
    return f"{v:.4g}"


def normalize_symbol_input(raw: str) -> List[str]:
    q = raw.strip().upper()
    if q.isdigit() and len(q) == 6:
        return [f"{q}.KS", f"{q}.KQ", q]
    return [q]


@st.cache_data(ttl=300)
def search_tickers(query: str):
    search_results = yf.Search(query, max_results=14).quotes
    candidates = []
    for x in search_results:
        symbol = x.get("symbol")
        if symbol:
            candidates.append(x)
    for sym in normalize_symbol_input(query):
        if not any(c.get("symbol") == sym for c in candidates):
            candidates.append({"symbol": sym, "shortname": sym, "exchDisp": "직접입력"})
    return candidates


@st.cache_data(ttl=300)
def load_ticker(ticker: str, period: str):
    t = yf.Ticker(ticker)
    info = t.info
    hist = t.history(period=period)
    financials = t.financials
    recommendations = t.recommendations
    analyst_price_targets = t.analyst_price_targets
    news = t.news
    return info, hist, financials, recommendations, analyst_price_targets, news


@st.cache_data(ttl=900)
def load_info(ticker: str):
    return yf.Ticker(ticker).info


def score_ticker(info: dict, strategy_name: str) -> Dict[str, float]:
    cfg = STRATEGY_PRESETS[strategy_name]
    checks = []

    values = {
        "trailing_pe": safe_num(info.get("trailingPE")),
        "roe": safe_num(info.get("returnOnEquity")),
        "debt": safe_num(info.get("debtToEquity")),
        "margin": safe_num(info.get("profitMargins")),
        "gross_margin": safe_num(info.get("grossMargins")),
        "rev_growth": safe_num(info.get("revenueGrowth")),
        "peg": safe_num(info.get("pegRatio")),
        "pb": safe_num(info.get("priceToBook")),
        "vol": safe_num(info.get("averageVolume")),
        "beta": safe_num(info.get("beta")),
        "eps_growth": safe_num(info.get("earningsGrowth")),
    }

    def test(v, op, th):
        if v is None:
            return None
        return op(v, th)

    if "trailing_pe_max" in cfg:
        checks.append(test(values["trailing_pe"], lambda a, b: a <= b, cfg["trailing_pe_max"]))
    if "roe_min" in cfg:
        checks.append(test(values["roe"], lambda a, b: a >= b, cfg["roe_min"]))
    if "debt_to_equity_max" in cfg:
        checks.append(test(values["debt"], lambda a, b: a <= b, cfg["debt_to_equity_max"]))
    if "profit_margin_min" in cfg:
        checks.append(test(values["margin"], lambda a, b: a >= b, cfg["profit_margin_min"]))
    if "gross_margin_min" in cfg:
        checks.append(test(values["gross_margin"], lambda a, b: a >= b, cfg["gross_margin_min"]))
    if "revenue_growth_min" in cfg:
        checks.append(test(values["rev_growth"], lambda a, b: a >= b, cfg["revenue_growth_min"]))
    if "peg_ratio_max" in cfg:
        checks.append(test(values["peg"], lambda a, b: a <= b, cfg["peg_ratio_max"]))
    if "price_to_book_max" in cfg:
        checks.append(test(values["pb"], lambda a, b: a <= b, cfg["price_to_book_max"]))
    if "avg_volume_min" in cfg:
        checks.append(test(values["vol"], lambda a, b: a >= b, cfg["avg_volume_min"]))
    if "beta_min" in cfg:
        checks.append(test(values["beta"], lambda a, b: a >= b, cfg["beta_min"]))
    if "earnings_growth_min" in cfg:
        checks.append(test(values["eps_growth"], lambda a, b: a >= b, cfg["earnings_growth_min"]))

    valid = [c for c in checks if c is not None]
    pass_rate = (sum(valid) / len(valid)) if valid else 0.0
    coverage = min(1.0, len(valid) / max(1, len(checks)))
    reliability = int((pass_rate * 0.7 + coverage * 0.3) * 100)
    score = int(pass_rate * 100)
    return {"score": score, "reliability": reliability, "coverage": coverage}


def aggregate_strategy_scores(info: dict, strategies: List[str], mode: str) -> Dict[str, object]:
    if not strategies:
        return {"score": 0, "reliability": 0, "by_strategy": {}, "passed": False}

    by_strategy = {s: score_ticker(info, s) for s in strategies}
    scores = [x["score"] for x in by_strategy.values()]
    reliabilities = [x["reliability"] for x in by_strategy.values()]

    if mode.startswith("ALL"):
        passed = all((by_strategy[s]["score"] >= 0) for s in strategies)
    else:
        passed = any((by_strategy[s]["score"] >= 0) for s in strategies)

    return {
        "score": int(sum(scores) / len(scores)),
        "reliability": int(sum(reliabilities) / len(reliabilities)),
        "by_strategy": by_strategy,
        "passed": passed,
    }


def summarize_strategy_hits(by_strategy: Dict[str, Dict[str, float]], min_score: int) -> Tuple[List[str], List[str]]:
    matched = [name for name, v in by_strategy.items() if v.get("score", 0) >= min_score]
    missed = [name for name, v in by_strategy.items() if v.get("score", 0) < min_score]
    return matched, missed


def risk_stats(hist: pd.DataFrame) -> Dict[str, Optional[float]]:
    if hist is None or hist.empty or "Close" not in hist:
        return {"수익률(기간)": None, "연환산 변동성": None, "최대낙폭(MDD)": None}

    close = hist["Close"].dropna()
    if close.empty:
        return {"수익률(기간)": None, "연환산 변동성": None, "최대낙폭(MDD)": None}

    ret = close.pct_change().dropna()
    total_return = (close.iloc[-1] / close.iloc[0]) - 1 if len(close) > 1 else None
    vol = (ret.std() * (252**0.5)) if not ret.empty else None
    cummax = close.cummax()
    dd = (close / cummax - 1).min() if not close.empty else None
    return {"수익률(기간)": total_return, "연환산 변동성": vol, "최대낙폭(MDD)": dd}


def market_cap_bucket(mcap: Optional[float]) -> str:
    if mcap is None:
        return "미상"
    if mcap >= 10_000_000_000:
        return "대형주"
    if mcap >= 2_000_000_000:
        return "중형주"
    return "소형주"


def market_cap_filter_ok(mcap: Optional[float], cap_filter: str) -> bool:
    if cap_filter == "전체":
        return True
    return market_cap_bucket(mcap) == cap_filter


def style_capital_match(info: dict, invest_style: str, capital_range: str, cap_filter: str) -> Tuple[bool, List[str]]:
    reasons: List[str] = []
    ok = True

    price = safe_num(info.get("currentPrice"))
    currency = (info.get("currency") or "").upper()
    mcap = safe_num(info.get("marketCap"))
    avg_vol = safe_num(info.get("averageVolume"))
    if not market_cap_filter_ok(mcap, cap_filter):
        ok = False
        reasons.append(f"시총 필터 미충족({cap_filter})")
    beta = safe_num(info.get("beta"))
    debt = safe_num(info.get("debtToEquity"))

    # style filters
    if invest_style == "스캘핑":
        if avg_vol is None or avg_vol < 5_000_000:
            ok = False
            reasons.append("거래량 부족(스캘핑)")
        if beta is None or beta < 0.8:
            ok = False
            reasons.append("변동성 부족(스캘핑)")
    elif invest_style == "스윙":
        if avg_vol is None or avg_vol < 1_000_000:
            ok = False
            reasons.append("거래량 부족(스윙)")
    elif invest_style == "장기투자":
        if mcap is not None and mcap < 2_000_000_000:
            ok = False
            reasons.append("시총 너무 작음(장기)")
        if debt is not None and debt > 250:
            ok = False
            reasons.append("부채비율 과다(장기)")

    # capital filters
    if price is not None:
        if capital_range == "100만원 이하":
            if currency == "KRW" and price > 150000:
                ok = False
                reasons.append("주당 가격 높음(소액자금)")
            if currency in {"USD", ""} and price > 300:
                ok = False
                reasons.append("주당 가격 높음(소액자금)")
        elif capital_range == "100만~1,000만원":
            if currency == "KRW" and price > 500000:
                ok = False
                reasons.append("주당 가격 높음(중간자금)")
            if currency in {"USD", ""} and price > 1000:
                ok = False
                reasons.append("주당 가격 높음(중간자금)")

    return ok, reasons


def suggest_position_size(hist: pd.DataFrame, account_size: float, risk_pct: float, current_price: Optional[float]) -> Dict[str, Optional[float]]:
    if hist is None or hist.empty or current_price is None or current_price <= 0:
        return {"shares": None, "position_value": None, "stop_distance": None}

    rets = hist["Close"].pct_change().dropna()
    if rets.empty:
        return {"shares": None, "position_value": None, "stop_distance": None}

    daily_vol = rets.std()
    stop_distance = max(current_price * daily_vol * 2, current_price * 0.02)
    risk_budget = account_size * (risk_pct / 100)
    shares = int(risk_budget / stop_distance) if stop_distance > 0 else 0
    position_value = shares * current_price
    return {"shares": shares, "position_value": position_value, "stop_distance": stop_distance}


def reliability_estimated_price(info: dict, analyst_targets: dict):
    current = safe_num(info.get("currentPrice"))
    trailing_eps = safe_num(info.get("trailingEps"))
    forward_pe = safe_num(info.get("forwardPE"))
    roe = safe_num(info.get("returnOnEquity"))
    debt_to_equity = safe_num(info.get("debtToEquity"))
    analyst_mean = safe_num((analyst_targets or {}).get("mean"))
    analyst_count = safe_num((analyst_targets or {}).get("numberOfAnalystOpinions")) or 0

    parts: List[Tuple[float, float, str]] = []
    if analyst_mean:
        analyst_weight = 0.55 if analyst_count >= 15 else 0.40
        parts.append((analyst_mean, analyst_weight, "애널리스트 평균 목표가"))
    if trailing_eps and forward_pe:
        pe_based = trailing_eps * forward_pe
        quality_bonus = 0.10 if roe and roe > 0.12 else 0.0
        risk_penalty = -0.05 if debt_to_equity and debt_to_equity > 180 else 0.0
        parts.append((pe_based, max(0.25, 0.45 + quality_bonus + risk_penalty), "EPS×Forward P/E 내재가치"))
    if current:
        parts.append((current, 0.20, "현재가 앵커"))

    if not parts:
        return None

    weight_sum = sum(w for _, w, _ in parts)
    fair = sum(v * w for v, w, _ in parts) / weight_sum
    confidence = 40 + (20 if analyst_count >= 10 else 0) + (15 if roe and roe > 0.1 else 0) + (10 if debt_to_equity and debt_to_equity < 150 else 0) + (10 if current else 0)
    return {"estimated_price": fair, "confidence": min(95, confidence), "components": parts}


def load_watchlist() -> List[str]:
    if WATCHLIST_FILE.exists():
        try:
            return json.loads(WATCHLIST_FILE.read_text())
        except Exception:
            return []
    return []


def render_issue_sector_reco(issue: str):
    data = ISSUE_SECTOR_MAP.get(issue)
    if not data:
        return
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### ✅ 추천 섹터")
        for s in data.get("good", []):
            st.markdown(f"- {s}")
    with c2:
        st.markdown("#### ⚠️ 주의 섹터")
        for s in data.get("bad", []):
            st.markdown(f"- {s}")


def save_watchlist(items: List[str]):
    WATCHLIST_FILE.write_text(json.dumps(sorted(set(items)), ensure_ascii=False, indent=2))


def load_alert_rules() -> Dict[str, dict]:
    if ALERT_RULES_FILE.exists():
        try:
            return json.loads(ALERT_RULES_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_alert_rule(ticker: str, rule: dict):
    rules = load_alert_rules()
    rules[ticker] = rule
    ALERT_RULES_FILE.write_text(json.dumps(rules, ensure_ascii=False, indent=2))


def load_alert_state() -> Dict[str, float]:
    if ALERT_STATE_FILE.exists():
        try:
            return json.loads(ALERT_STATE_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_alert_state(state: Dict[str, float]):
    ALERT_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def run_auto_alert_scan(cooldown_min: int = 10) -> List[str]:
    sent_messages: List[str] = []
    rules = load_alert_rules()
    state = load_alert_state()
    now_ts = time.time()

    for ticker, rule in rules.items():
        webhook_url = rule.get("webhook_url")
        if not webhook_url:
            continue
        provider = rule.get("provider", "discord")
        buy_below = float(rule.get("buy_below", 0) or 0)
        sell_above = float(rule.get("sell_above", 0) or 0)

        try:
            info = load_info(ticker)
            current = safe_num(info.get("currentPrice")) or 0
        except Exception:
            continue

        alerts = []
        if buy_below > 0 and current <= buy_below:
            alerts.append(f"[매수신호] {ticker} 현재가 {current} <= {buy_below}")
        if sell_above > 0 and current >= sell_above:
            alerts.append(f"[매도신호] {ticker} 현재가 {current} >= {sell_above}")
        if not alerts:
            continue

        event_key = f"{ticker}|{'|'.join(alerts)}"
        last_sent = float(state.get(event_key, 0))
        if now_ts - last_sent < cooldown_min * 60:
            continue

        code, _ = trigger_webhook(
            webhook_url,
            {
                "ticker": ticker,
                "alerts": alerts,
                "price": current,
                "time": datetime.now(timezone.utc).isoformat(),
                "source": "Stock Bot Pro KR AutoScan",
            },
            provider=provider,
        )
        if code and 200 <= code < 300:
            state[event_key] = now_ts
            sent_messages.append(f"{ticker}: {', '.join(alerts)}")

    save_alert_state(state)
    return sent_messages


def trigger_webhook(url: str, payload: dict, provider: str = "generic"):
    try:
        if provider == "discord":
            text_lines = [f"📢 {payload.get('ticker', '-')}"]
            for a in payload.get("alerts", []):
                text_lines.append(f"- {a}")
            text_lines.append(f"price: {payload.get('price', '-')}")
            text_lines.append(f"time: {payload.get('time', '-')}")
            body = {"content": "\n".join(text_lines)}
            r = requests.post(url, json=body, timeout=8)
        else:
            r = requests.post(url, json=payload, timeout=8)
        return r.status_code, r.text[:200]
    except Exception as e:
        return None, str(e)


st.markdown("""
<div class='hero'>
  <h1>Stock Bot Pro KR</h1>
  <div style='margin-top:0.4rem'>
    <span class='chip'>한국주식 + 미국주식</span>
    <span class='chip'>통계 한글화</span>
    <span class='chip'>프리미엄급 다기능 스크리닝</span>
  </div>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### 검색/필터 옵션")
    period = st.selectbox("차트 기간", ["6mo", "1y", "3y", "5y", "10y", "max"], index=3)
    selected_strategies = st.multiselect(
        "전략 프리셋(복수 선택 가능)",
        list(STRATEGY_PRESETS.keys()),
        default=["Buffett (가치+품질)"]
    )
    strategy_mode = st.selectbox("전략 결합 방식", ["ALL(모두 충족)", "ANY(하나 이상 충족)"])
    invest_style = st.selectbox("투자 스타일", ["스캘핑", "스윙", "장기투자"])
    capital_range = st.selectbox("투자 금액", list(CAPITAL_HINTS.keys()))
    cap_filter = st.selectbox("시가총액 필터", ["전체", "대형주", "중형주", "소형주"])
    macro_issue = st.selectbox("현재 이슈/국면", list(ISSUE_SECTOR_MAP.keys()))
    min_score = st.slider("최소 전략 적합도", 40, 95, 65)
    min_reliability = st.slider("최소 신뢰도", 40, 95, 60)
    st.markdown("---")
    st.markdown("### 자동 알림 감시")
    auto_monitor = st.checkbox("자동 감시 모드", value=False)
    refresh_sec = st.slider("자동 새로고침(초)", 15, 300, 60, 15)
    cooldown_min = st.slider("동일 신호 재전송 쿨다운(분)", 1, 60, 10, 1)

st.info(f"{invest_style} 조언: {STYLE_HINTS[invest_style]}")
st.info(f"{capital_range} 조언: {CAPITAL_HINTS[capital_range]}")

if auto_monitor:
    st.markdown(f"<meta http-equiv='refresh' content='{refresh_sec}'>", unsafe_allow_html=True)
    sent = run_auto_alert_scan(cooldown_min=cooldown_min)
    if sent:
        st.success(f"자동 감시 알림 발송: {len(sent)}건")
        with st.expander("자동 발송 내역"):
            for msg in sent:
                st.write(msg)
    else:
        st.caption("자동 감시 실행됨: 현재 새로 보낼 알림 없음")

st.markdown(f"## 이슈 기반 섹터 가이드: {macro_issue}")
render_issue_sector_reco(macro_issue)

st.markdown("## 원클릭: 괜찮은 기업 필터링")
if st.button("전략 기준으로 후보 기업 바로 보기", type="primary"):
    rows = []
    progress = st.progress(0)
    for i, tk in enumerate(CANDIDATE_TICKERS):
        try:
            info = load_info(tk)
            agg = aggregate_strategy_scores(info, selected_strategies, strategy_mode)
            style_ok, style_reasons = style_capital_match(info, invest_style, capital_range, cap_filter)
            pass_checks = agg["score"] >= min_score and agg["reliability"] >= min_reliability and style_ok
            if strategy_mode.startswith("ALL"):
                pass_checks = pass_checks and all(v["score"] >= min_score for v in agg["by_strategy"].values())
            elif strategy_mode.startswith("ANY"):
                pass_checks = pass_checks and any(v["score"] >= min_score for v in agg["by_strategy"].values())

            matched, missed = summarize_strategy_hits(agg["by_strategy"], min_score)
            strategy_hit_text = ", ".join(matched) if matched else "없음"
            strategy_miss_text = ", ".join(missed) if missed else "없음"

            if pass_checks:
                rows.append(
                    {
                        "티커": tk,
                        "기업명": info.get("shortName") or tk,
                        "현재가": safe_num(info.get("currentPrice")),
                        "전략점수(평균)": agg["score"],
                        "신뢰도(평균)": agg["reliability"],
                        "전략개수": len(selected_strategies),
                        "통과전략": strategy_hit_text,
                        "미통과전략": strategy_miss_text,
                        "스타일/금액 적합": "적합",
                        "제외사유": "",
                        "시총구분": market_cap_bucket(safe_num(info.get("marketCap"))),
                        "섹터": info.get("sector") or "-",
                    }
                )
            else:
                fail_reason = []
                if style_reasons:
                    fail_reason.extend(style_reasons)
                if missed:
                    fail_reason.append("전략 미통과: " + ", ".join(missed))
                rows.append(
                    {
                        "티커": tk,
                        "기업명": info.get("shortName") or tk,
                        "현재가": safe_num(info.get("currentPrice")),
                        "전략점수(평균)": agg["score"],
                        "신뢰도(평균)": agg["reliability"],
                        "전략개수": len(selected_strategies),
                        "통과전략": strategy_hit_text,
                        "미통과전략": strategy_miss_text,
                        "스타일/금액 적합": "부적합",
                        "제외사유": ", ".join(fail_reason) if fail_reason else "전략 점수 미달",
                        "시총구분": market_cap_bucket(safe_num(info.get("marketCap"))),
                        "섹터": info.get("sector") or "-",
                    }
                )
        except Exception:
            pass
        progress.progress((i + 1) / len(CANDIDATE_TICKERS))

    df = pd.DataFrame(rows)
    if not df.empty:
        passed_df = df[df["스타일/금액 적합"] == "적합"].copy()
        failed_df = df[df["스타일/금액 적합"] != "적합"].copy()
        if not passed_df.empty:
            passed_df = passed_df.sort_values(["신뢰도(평균)", "전략점수(평균)"], ascending=False)
            st.success(f"{len(passed_df)}개 종목이 조건을 통과했습니다.")
            st.dataframe(passed_df, use_container_width=True)
        else:
            st.warning("조건 통과 종목이 없습니다. 기준을 완화해 보세요.")

        with st.expander("제외된 종목 및 사유 보기"):
            if not failed_df.empty:
                st.dataframe(failed_df[["티커", "기업명", "시총구분", "통과전략", "미통과전략", "전략점수(평균)", "신뢰도(평균)", "제외사유"]], use_container_width=True)
            else:
                st.caption("제외 종목 없음")

        with st.expander("필터링 검증 요약"):
            cap_counts = df["시총구분"].value_counts(dropna=False).to_dict()
            st.write({"전체후보수": len(df), "통과수": len(passed_df), "제외수": len(failed_df), "시총분포": cap_counts})
    else:
        st.warning("스크리너 결과가 없습니다.")

st.markdown("## 기업 검색")
query = st.text_input("기업명 / 티커 / 한국 6자리 코드(예: 005930)", placeholder="예: 삼성전자, 005930, AAPL")
selected = None
if query:
    quotes = search_tickers(query) or []
    if quotes:
        options = []
        mapper = {}
        for q in quotes:
            symbol = q.get("symbol")
            shortname = q.get("shortname") or q.get("longname") or symbol
            exchange = q.get("exchDisp") or ""
            label = f"{shortname} ({symbol}) {exchange}" if symbol else shortname
            options.append(label)
            mapper[label] = symbol
        picked = st.selectbox("검색 결과", options)
        selected = mapper.get(picked)
    else:
        st.warning("검색 결과가 없습니다.")

if selected:
    info, hist, financials, recommendations, targets, news = load_ticker(selected, period)
    agg_scored = aggregate_strategy_scores(info, selected_strategies, strategy_mode)

    style_ok, style_reasons = style_capital_match(info, invest_style, capital_range, cap_filter)
    st.markdown(f"### 선택 종목: <span class='purple'>{selected}</span>", unsafe_allow_html=True)
    if style_ok:
        st.success("현재 투자 스타일/금액 기준에 적합한 종목입니다.")
    else:
        st.warning("현재 투자 스타일/금액 기준에서 주의 필요: " + ", ".join(style_reasons))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("현재가", format_value(safe_num(info.get("currentPrice"))))
    c2.metric("시가총액", format_value(safe_num(info.get("marketCap"))))
    c3.metric("전략 적합도(평균)", str(agg_scored["score"]))
    c4.metric("데이터 신뢰도(평균)", str(agg_scored["reliability"]))
    hit, miss = summarize_strategy_hits(agg_scored["by_strategy"], min_score)
    st.markdown(f"**통과 전략:** {', '.join(hit) if hit else '없음'}")
    st.markdown(f"**미통과 전략:** {', '.join(miss) if miss else '없음'}")
    st.json({"전략별점수": agg_scored["by_strategy"]})

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["차트/재무", "통계(한글)", "전문가 의견", "예상 주가", "관심종목/알림", "뉴스"])

    with tab1:
        left, right = st.columns([1.2, 1])
        with left:
            st.markdown(f"#### 가격 추이 ({period})")
            if hist is not None and not hist.empty:
                st.line_chart(hist["Close"])
            else:
                st.info("가격 데이터 없음")
        with right:
            st.markdown("#### 재무제표(연간)")
            if financials is not None and not financials.empty:
                st.dataframe(financials.head(14), use_container_width=True)
            else:
                st.info("재무 데이터 없음")

    with tab2:
        st.markdown("#### 핵심 통계 (한글)")
        rows = []
        for k, label in METRIC_LABELS_KR.items():
            rows.append({"지표": label, "값": format_value(safe_num(info.get(k)))})
        st.dataframe(pd.DataFrame(rows), use_container_width=True)

        stats = risk_stats(hist)
        risk_df = pd.DataFrame(
            [{"항목": k, "값": f"{v*100:.2f}%" if v is not None else "-"} for k, v in stats.items()]
        )
        st.markdown("#### 리스크 통계")
        st.dataframe(risk_df, use_container_width=True)

    with tab3:
        st.markdown("#### 전문가 목표가")
        if isinstance(targets, dict) and targets:
            tdf = pd.DataFrame([targets]).T
            tdf.columns = ["값"]
            st.dataframe(tdf, use_container_width=True)
        else:
            st.info("목표가 데이터 없음")

        st.markdown("#### 어떤 전문가 의견인가?")
        if recommendations is not None and not recommendations.empty:
            rec = recommendations.reset_index().copy()
            st.dataframe(rec.head(25), use_container_width=True)
            st.caption("출처: Yahoo Finance recommendation feed (증권사/리서치 기관 컨센서스 집계)")
        else:
            st.info("전문가 의견 데이터 없음")

    with tab4:
        model = reliability_estimated_price(info, targets if isinstance(targets, dict) else {})
        if model:
            st.success(f"신뢰도 기반 예상 주가: {model['estimated_price']:.2f} | 신뢰도 {model['confidence']}/100")
            comp_df = pd.DataFrame(model["components"], columns=["값", "가중치", "방법"])
            st.dataframe(comp_df, use_container_width=True)
        else:
            st.warning("예상 주가 계산 데이터 부족")

        st.markdown("#### 추가 기능: 리스크 기반 포지션 사이징")
        account_currency = st.selectbox("계좌 통화", ["KRW", "USD"], index=0)
        default_amount = 5000000.0 if account_currency == "KRW" else 5000.0
        step_amount = 100000.0 if account_currency == "KRW" else 100.0
        account_size = st.number_input("계좌 총액", min_value=1.0, value=default_amount, step=step_amount)
        risk_pct = st.slider("1회 거래 허용 손실(%)", 0.1, 5.0, 1.0, 0.1)
        pos = suggest_position_size(hist, account_size, risk_pct, safe_num(info.get("currentPrice")))
        if pos["shares"] is not None:
            st.info(
                f"권장 수량: {pos['shares']}주 | 권장 진입금액: {pos['position_value']:.0f} {account_currency} | 추정 손절폭: {pos['stop_distance']:.2f}"
            )

    with tab5:
        watch = load_watchlist()
        st.write("현재 관심종목:", watch if watch else "없음")
        a1, a2 = st.columns(2)
        with a1:
            if st.button("관심종목 추가"):
                watch.append(selected)
                save_watchlist(watch)
                st.success("추가되었습니다")
        with a2:
            if st.button("관심종목 제거"):
                watch = [w for w in watch if w != selected]
                save_watchlist(watch)
                st.success("제거되었습니다")

        st.markdown("#### 모바일 알림(Webhook)")
        st.caption("알림은 앱 내부 푸시가 아니라, 입력한 Webhook 채널(예: 디스코드/텔레그램/슬랙/IFTTT)로 전달됩니다.")
        st.markdown("- 디스코드: 서버 설정 → Integrations → Webhooks 생성\n- 텔레그램: BotFather로 봇 생성 후 webhook 브리지 사용\n- 슬랙: Incoming Webhook URL 발급\n- IFTTT: Webhooks + 모바일 알림 앱 연동")

        saved_rule = load_alert_rules().get(selected, {})
        provider_default = saved_rule.get("provider", "discord")
        provider_idx = 0 if provider_default == "discord" else 1
        webhook_provider = st.selectbox(
            "웹훅 채널",
            ["discord", "generic"],
            index=provider_idx,
            format_func=lambda x: "Discord" if x == "discord" else "Generic(JSON)",
            key=f"provider_{selected}",
        )
        webhook_url = st.text_input(
            "Webhook URL (Discord/Slack/Telegram/IFTTT)",
            value=saved_rule.get("webhook_url", ""),
            key=f"webhook_{selected}",
        )
        buy_below = st.number_input(
            "매수 알림 가격 이하",
            min_value=0.0,
            value=float(saved_rule.get("buy_below", 0.0)),
            step=1.0,
            key=f"buy_{selected}",
        )
        sell_above = st.number_input(
            "매도 알림 가격 이상",
            min_value=0.0,
            value=float(saved_rule.get("sell_above", 0.0)),
            step=1.0,
            key=f"sell_{selected}",
        )

        if st.button("이 종목 알림 조건 저장", key=f"save_alert_{selected}"):
            save_alert_rule(
                selected,
                {
                    "provider": webhook_provider,
                    "webhook_url": webhook_url,
                    "buy_below": buy_below,
                    "sell_above": sell_above,
                },
            )
            st.success(f"{selected} 알림 조건이 저장되었습니다. ({ALERT_RULES_FILE})")

        if st.button("조건 확인 후 알림 보내기", key=f"send_alert_{selected}"):
            current = safe_num(info.get("currentPrice")) or 0
            alerts = []
            if buy_below > 0 and current <= buy_below:
                alerts.append(f"[매수신호] {selected} 현재가 {current} <= {buy_below}")
            if sell_above > 0 and current >= sell_above:
                alerts.append(f"[매도신호] {selected} 현재가 {current} >= {sell_above}")

            if not alerts:
                st.info("조건에 맞는 알림 없음")
            elif webhook_url:
                code, body = trigger_webhook(
                    webhook_url,
                    {
                        "ticker": selected,
                        "alerts": alerts,
                        "price": current,
                        "time": datetime.now(timezone.utc).isoformat(),
                        "source": "Stock Bot Pro KR",
                    },
                    provider=webhook_provider,
                )
                if code and 200 <= code < 300:
                    st.success("알림 전송 성공")
                else:
                    st.error(f"알림 전송 실패: {code} / {body}")
            else:
                st.warning("Webhook URL을 입력하면 폰 알림 채널 연동 가능")

    with tab6:
        st.markdown("#### 최신 뉴스")
        if news:
            for n in news[:12]:
                title = n.get("title") or "제목 없음"
                publisher = n.get("publisher") or "-"
                link = n.get("link") or ""
                st.markdown(f"- **{title}** | {publisher}  ")
                if link:
                    st.markdown(f"  [기사 보기]({link})")
        else:
            st.info("뉴스 데이터 없음")

st.markdown("---")
st.caption(f"Data source: yfinance(Yahoo Finance) | updated_at={datetime.now(timezone.utc).isoformat()}")
