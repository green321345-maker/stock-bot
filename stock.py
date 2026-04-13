import json
import math
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
st.markdown(
    f"""
    <style>
      .stApp {{ background: #FCFAFF; color: #2B2B3A; }}
      .block-container {{ padding-top: 1.2rem; padding-bottom: 2rem; max-width: 1260px; }}
      .hero {{ padding: 1rem 1.2rem; border-radius: 16px; background: linear-gradient(90deg, #F3EDFF 0%, #FCFAFF 75%); border: 1px solid #E5D9FF; }}
      .hero h1 {{ margin: 0; color: {ACCENT_DARK}; }}
      .chip {{ display:inline-block; padding: 0.26rem 0.65rem; border-radius:999px; background:#EFE6FF; color:{ACCENT_DARK}; margin-right:0.4rem; font-size:0.78rem; }}
      .soft-card {{ background:white; border:1px solid #EEE7FF; border-radius:14px; padding:0.85rem 1rem; }}
      .purple {{ color: {ACCENT_DARK}; font-weight: 700; }}
    </style>
    """,
    unsafe_allow_html=True,
)

WATCHLIST_FILE = Path("watchlist.json")
CANDIDATE_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSM", "ASML", "JPM", "V", "MA", "COST", "KO", "PEP", "BRK-B",
    "005930.KS", "000660.KS", "035420.KS", "051910.KS", "005380.KS", "068270.KS", "035720.KQ", "207940.KS",
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


def save_watchlist(items: List[str]):
    WATCHLIST_FILE.write_text(json.dumps(sorted(set(items)), ensure_ascii=False, indent=2))


def trigger_webhook(url: str, payload: dict):
    try:
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
    min_score = st.slider("최소 전략 적합도", 40, 95, 65)
    min_reliability = st.slider("최소 신뢰도", 40, 95, 60)

st.info(f"{invest_style} 조언: {STYLE_HINTS[invest_style]}")
st.info(f"{capital_range} 조언: {CAPITAL_HINTS[capital_range]}")

st.markdown("## 원클릭: 괜찮은 기업 필터링")
if st.button("전략 기준으로 후보 기업 바로 보기", type="primary"):
    rows = []
    progress = st.progress(0)
    for i, tk in enumerate(CANDIDATE_TICKERS):
        try:
            info = load_info(tk)
            agg = aggregate_strategy_scores(info, selected_strategies, strategy_mode)
            pass_checks = agg["score"] >= min_score and agg["reliability"] >= min_reliability
            if strategy_mode.startswith("ALL"):
                pass_checks = pass_checks and all(v["score"] >= min_score for v in agg["by_strategy"].values())
            elif strategy_mode.startswith("ANY"):
                pass_checks = pass_checks and any(v["score"] >= min_score for v in agg["by_strategy"].values())

            if pass_checks:
                rows.append(
                    {
                        "티커": tk,
                        "기업명": info.get("shortName") or tk,
                        "현재가": safe_num(info.get("currentPrice")),
                        "전략점수(평균)": agg["score"],
                        "신뢰도(평균)": agg["reliability"],
                        "전략개수": len(selected_strategies),
                        "섹터": info.get("sector") or "-",
                    }
                )
        except Exception:
            pass
        progress.progress((i + 1) / len(CANDIDATE_TICKERS))

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["신뢰도(평균)", "전략점수(평균)"], ascending=False)
        st.success(f"{len(df)}개 종목이 조건을 통과했습니다.")
        st.dataframe(df, use_container_width=True)
    else:
        st.warning("조건 통과 종목이 없습니다. 기준을 완화해 보세요.")

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

    st.markdown(f"### 선택 종목: <span class='purple'>{selected}</span>", unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("현재가", format_value(safe_num(info.get("currentPrice"))))
    c2.metric("시가총액", format_value(safe_num(info.get("marketCap"))))
    c3.metric("전략 적합도(평균)", str(agg_scored["score"]))
    c4.metric("데이터 신뢰도(평균)", str(agg_scored["reliability"]))
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
        webhook_url = st.text_input("Webhook URL (Slack/Telegram/IFTTT)", key="webhook")
        buy_below = st.number_input("매수 알림 가격 이하", min_value=0.0, value=0.0, step=1.0)
        sell_above = st.number_input("매도 알림 가격 이상", min_value=0.0, value=0.0, step=1.0)

        if st.button("조건 확인 후 알림 보내기"):
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
