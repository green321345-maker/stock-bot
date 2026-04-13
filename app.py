import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import requests
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="Stock Bot Pro", page_icon="🟣", layout="wide")

ACCENT = "#8B5CF6"
st.markdown(
    f"""
    <style>
      .stApp {{ background: #F7F7FB; color: #1F2330; }}
      .block-container {{ padding-top: 1.2rem; padding-bottom: 2rem; max-width: 1200px; }}
      .hero {{ padding: 1rem 1.2rem; border-radius: 14px; background: linear-gradient(90deg, #ECE7FF 0%, #F7F7FB 70%); border: 1px solid #E3D9FF; }}
      .hero h1 {{ margin: 0; color: #2D1B69; }}
      .chip {{ display:inline-block; padding: 0.25rem 0.6rem; border-radius:999px; background:#EEE8FF; color:#5B37B7; margin-right:0.4rem; font-size:0.78rem; }}
      .card {{ background:white; border:1px solid #E7E7EF; border-radius:14px; padding:0.8rem 1rem; }}
      .purple {{ color: {ACCENT}; font-weight: 700; }}
    </style>
    """,
    unsafe_allow_html=True,
)

WATCHLIST_FILE = Path("watchlist.json")
CANDIDATE_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSM", "ASML", "JPM", "V", "MA", "COST", "KO", "PEP", "BRK-B",
    "JNJ", "PG", "HD", "UNH", "ADBE", "CRM", "ORCL", "ABBV", "MCD", "XOM", "AVGO", "LLY", "NFLX", "AMD", "INTU",
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
    "스캘핑": "체결속도/호가스프레드/수수료 관리가 핵심. 대형주·고유동성 위주, 손절 규칙 필수.",
    "스윙": "1일~수주 보유, 추세+실적 모멘텀 결합. 분할 매수/분할 매도 권장.",
    "장기투자": "3년+ 관점, 이익 성장과 재무건전성 중심. 리밸런싱 주기(월/분기) 유지.",
}

CAPITAL_HINTS = {
    "100만원 이하": "종목 수를 2~4개로 제한하고 과도한 분산을 피하세요. 거래비용 비중 관리가 중요합니다.",
    "100만~1,000만원": "핵심 5~10개 + 현금 비중 10~20%를 고려하세요. 전략별 바스켓 구성 추천.",
    "1,000만원 이상": "코어(장기) + 위성(스윙) 이중 구조가 유리하며, 최대낙폭(MDD) 관리 규칙을 설정하세요.",
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


@st.cache_data(ttl=300)
def search_tickers(query: str):
    return yf.Search(query, max_results=12).quotes


@st.cache_data(ttl=300)
def load_ticker(ticker: str, period: str):
    t = yf.Ticker(ticker)
    info = t.info
    hist = t.history(period=period)
    financials = t.financials
    recommendations = t.recommendations
    analyst_price_targets = t.analyst_price_targets
    return info, hist, financials, recommendations, analyst_price_targets


@st.cache_data(ttl=900)
def load_info(ticker: str):
    return yf.Ticker(ticker).info


def score_ticker(info: dict, strategy_name: str) -> Dict[str, float]:
    cfg = STRATEGY_PRESETS[strategy_name]
    checks = []

    trailing_pe = safe_num(info.get("trailingPE"))
    roe = safe_num(info.get("returnOnEquity"))
    debt = safe_num(info.get("debtToEquity"))
    margin = safe_num(info.get("profitMargins"))
    gross_margin = safe_num(info.get("grossMargins"))
    rev_growth = safe_num(info.get("revenueGrowth"))
    peg = safe_num(info.get("pegRatio"))
    pb = safe_num(info.get("priceToBook"))
    vol = safe_num(info.get("averageVolume"))
    beta = safe_num(info.get("beta"))
    eps_growth = safe_num(info.get("earningsGrowth"))

    def test(v, op, th):
        if v is None:
            return None
        return op(v, th)

    if "trailing_pe_max" in cfg:
        checks.append(test(trailing_pe, lambda a, b: a <= b, cfg["trailing_pe_max"]))
    if "roe_min" in cfg:
        checks.append(test(roe, lambda a, b: a >= b, cfg["roe_min"]))
    if "debt_to_equity_max" in cfg:
        checks.append(test(debt, lambda a, b: a <= b, cfg["debt_to_equity_max"]))
    if "profit_margin_min" in cfg:
        checks.append(test(margin, lambda a, b: a >= b, cfg["profit_margin_min"]))
    if "gross_margin_min" in cfg:
        checks.append(test(gross_margin, lambda a, b: a >= b, cfg["gross_margin_min"]))
    if "revenue_growth_min" in cfg:
        checks.append(test(rev_growth, lambda a, b: a >= b, cfg["revenue_growth_min"]))
    if "peg_ratio_max" in cfg:
        checks.append(test(peg, lambda a, b: a <= b, cfg["peg_ratio_max"]))
    if "price_to_book_max" in cfg:
        checks.append(test(pb, lambda a, b: a <= b, cfg["price_to_book_max"]))
    if "avg_volume_min" in cfg:
        checks.append(test(vol, lambda a, b: a >= b, cfg["avg_volume_min"]))
    if "beta_min" in cfg:
        checks.append(test(beta, lambda a, b: a >= b, cfg["beta_min"]))
    if "earnings_growth_min" in cfg:
        checks.append(test(eps_growth, lambda a, b: a >= b, cfg["earnings_growth_min"]))

    valid = [c for c in checks if c is not None]
    pass_rate = (sum(valid) / len(valid)) if valid else 0.0

    coverage = min(1.0, len(valid) / max(1, len(checks)))
    reliability = int((pass_rate * 0.7 + coverage * 0.3) * 100)
    score = int(pass_rate * 100)
    return {"score": score, "reliability": reliability, "coverage": coverage}


def reliability_estimated_price(info: dict, analyst_targets: dict):
    current = safe_num(info.get("currentPrice"))
    trailing_eps = safe_num(info.get("trailingEps"))
    forward_pe = safe_num(info.get("forwardPE"))
    roe = safe_num(info.get("returnOnEquity"))
    debt_to_equity = safe_num(info.get("debtToEquity"))
    analyst_mean = safe_num((analyst_targets or {}).get("mean"))
    analyst_count = safe_num((analyst_targets or {}).get("numberOfAnalystOpinions")) or 0

    parts = []
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
  <h1>Stock Bot Pro</h1>
  <div style='margin-top:0.4rem'>
    <span class='chip'>신뢰도 우선</span>
    <span class='chip'>원클릭 우량기업 필터</span>
    <span class='chip'>전략별 검색 (Buffett/Lynch/Graham/CANSLIM/Minervini)</span>
  </div>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### 검색/필터 옵션")
    period = st.selectbox("차트 기간", ["6mo", "1y", "3y", "5y", "10y", "max"], index=2)
    strategy = st.selectbox("전략 프리셋", list(STRATEGY_PRESETS.keys()))
    invest_style = st.selectbox("투자 스타일", ["스캘핑", "스윙", "장기투자"]) 
    capital_range = st.selectbox("투자 금액", list(CAPITAL_HINTS.keys()))
    min_score = st.slider("최소 전략 적합도", 40, 95, 65)
    min_reliability = st.slider("최소 신뢰도", 40, 95, 60)

st.info(f"{invest_style} 조언: {STYLE_HINTS[invest_style]}")
st.info(f"{capital_range} 조언: {CAPITAL_HINTS[capital_range]}")

# Quick screener
st.markdown("## 원클릭: 괜찮은 기업 필터링")
if st.button("전략 기준으로 후보 기업 바로 보기", type="primary"):
    rows = []
    progress = st.progress(0)
    for i, tk in enumerate(CANDIDATE_TICKERS):
        try:
            info = load_info(tk)
            scored = score_ticker(info, strategy)
            current_price = safe_num(info.get("currentPrice"))
            name = info.get("shortName") or tk
            if scored["score"] >= min_score and scored["reliability"] >= min_reliability:
                rows.append(
                    {
                        "ticker": tk,
                        "name": name,
                        "current_price": current_price,
                        "strategy_score": scored["score"],
                        "reliability": scored["reliability"],
                        "sector": info.get("sector"),
                    }
                )
        except Exception:
            pass
        progress.progress((i + 1) / len(CANDIDATE_TICKERS))

    df = pd.DataFrame(rows).sort_values(["reliability", "strategy_score"], ascending=False)
    if not df.empty:
        st.success(f"{len(df)}개 종목이 조건을 통과했습니다.")
        st.dataframe(df, use_container_width=True)
    else:
        st.warning("조건을 통과한 종목이 없습니다. 기준을 완화해보세요.")

st.markdown("## 기업 검색")
query = st.text_input("기업명 또는 티커", placeholder="예: Apple, AAPL, Tesla")
selected = None
if query:
    quotes = search_tickers(query)
    if quotes:
        options = []
        mapper = {}
        for q in quotes:
            symbol = q.get("symbol")
            shortname = q.get("shortname") or q.get("longname") or "Unknown"
            exchange = q.get("exchDisp") or ""
            label = f"{shortname} ({symbol}) {exchange}" if symbol else shortname
            options.append(label)
            mapper[label] = symbol
        picked = st.selectbox("검색 결과", options)
        selected = mapper.get(picked)
    else:
        st.warning("검색 결과가 없습니다.")

if selected:
    info, hist, financials, recommendations, targets = load_ticker(selected, period)
    st.markdown(f"### 선택 종목: <span class='purple'>{selected}</span>", unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("현재가", f"{safe_num(info.get('currentPrice')) or '-'}")
    c2.metric("시가총액", f"{safe_num(info.get('marketCap')) or '-'}")
    c3.metric("전략 적합도", f"{score_ticker(info, strategy)['score']}")
    c4.metric("데이터 신뢰도", f"{score_ticker(info, strategy)['reliability']}")

    tab1, tab2, tab3, tab4 = st.tabs(["차트/재무", "전문가 의견", "예상 주가", "관심종목/알림"])

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
                st.dataframe(financials.head(12), use_container_width=True)
            else:
                st.info("재무 데이터 없음")

    with tab2:
        st.markdown("#### 전문가 목표가")
        if isinstance(targets, dict) and targets:
            tdf = pd.DataFrame([targets]).T
            tdf.columns = ["value"]
            st.dataframe(tdf, use_container_width=True)
        else:
            st.info("목표가 데이터 없음")

        st.markdown("#### 어떤 전문가의 의견인가?")
        if recommendations is not None and not recommendations.empty:
            rec = recommendations.reset_index().copy()
            st.dataframe(rec.head(20), use_container_width=True)
            st.caption("출처: Yahoo Finance recommendation feed (증권사/리서치 기관 컨센서스 집계)")
        else:
            st.info("전문가 의견 데이터 없음")

    with tab3:
        model = reliability_estimated_price(info, targets if isinstance(targets, dict) else {})
        if model:
            st.success(f"신뢰도 기반 예상 주가: {model['estimated_price']:.2f} | 신뢰도 {model['confidence']}/100")
            st.dataframe(pd.DataFrame(model["components"], columns=["value", "weight", "method"]))
        else:
            st.warning("예상 주가 계산 데이터 부족")
        st.caption("중요: 투자 판단 책임은 본인에게 있으며, 본 도구는 의사결정 보조 도구입니다.")

    with tab4:
        watch = load_watchlist()
        st.write("현재 관심종목:", watch if watch else "없음")
        c_add, c_rm = st.columns(2)
        with c_add:
            if st.button("관심종목 추가"):
                watch.append(selected)
                save_watchlist(watch)
                st.success("추가되었습니다.")
        with c_rm:
            if st.button("관심종목 제거"):
                watch = [w for w in watch if w != selected]
                save_watchlist(watch)
                st.success("제거되었습니다.")

        st.markdown("#### 모바일 알림(Webhook)")
        webhook_url = st.text_input("Webhook URL (예: Slack/Telegram/IFTTT)", key="webhook")
        buy_below = st.number_input("매수 알림 가격 이하", min_value=0.0, value=0.0, step=1.0)
        sell_above = st.number_input("매도 알림 가격 이상", min_value=0.0, value=0.0, step=1.0)

        if st.button("지금 조건 확인 후 알림 보내기"):
            current = safe_num(info.get("currentPrice")) or 0
            alerts = []
            if buy_below > 0 and current <= buy_below:
                alerts.append(f"[매수신호] {selected} 현재가 {current} <= {buy_below}")
            if sell_above > 0 and current >= sell_above:
                alerts.append(f"[매도신호] {selected} 현재가 {current} >= {sell_above}")

            if not alerts:
                st.info("현재 조건에 맞는 알림이 없습니다.")
            elif webhook_url:
                code, body = trigger_webhook(
                    webhook_url,
                    {
                        "ticker": selected,
                        "price": current,
                        "alerts": alerts,
                        "time": datetime.now(timezone.utc).isoformat(),
                        "source": "Stock Bot Pro",
                    },
                )
                if code and 200 <= code < 300:
                    st.success("모바일/외부 알림 전송 성공")
                else:
                    st.error(f"전송 실패: {code} / {body}")
            else:
                st.warning("Webhook URL을 입력하면 폰 알림 채널과 연동할 수 있습니다.")

st.markdown("---")
st.caption(f"Data source: Yahoo Finance API wrapper(yfinance) | updated_at={datetime.now(timezone.utc).isoformat()}")
