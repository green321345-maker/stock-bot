import json
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="Stock Bot", page_icon="📈", layout="wide")

ACCENT = "#7C4DFF"
st.markdown(
    f"""
    <style>
      .stApp {{ background: linear-gradient(180deg, #0F1115 0%, #131826 100%); color: #f5f7ff; }}
      .block-container {{ padding-top: 1.5rem; }}
      .pill {{ display:inline-block;padding:4px 10px;border-radius:999px;background:{ACCENT};color:white;font-size:12px; }}
    </style>
    """,
    unsafe_allow_html=True,
)

@st.cache_data(ttl=3600)
def load_expert_opinions() -> dict:
    path = Path("data/expert_opinions.json")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


@st.cache_data(ttl=900)
def search_tickers(query: str) -> list[str]:
    # yfinance built-in search API
    if not query.strip():
        return []
    results = yf.Search(query, max_results=8).quotes
    symbols = []
    for r in results:
        symbol = r.get("symbol")
        short = r.get("shortname") or r.get("longname") or ""
        exch = r.get("exchange") or ""
        if symbol:
            symbols.append(f"{symbol} | {short} | {exch}")
    return symbols


@st.cache_data(ttl=900)
def load_stock_bundle(ticker: str):
    tk = yf.Ticker(ticker)
    info = tk.info
    price = tk.history(period="1y", auto_adjust=True)
    fin = tk.financials
    bal = tk.balance_sheet
    cash = tk.cashflow
    rec = tk.recommendations
    return info, price, fin, bal, cash, rec


def safe_float(v, default=np.nan):
    try:
        return float(v)
    except Exception:
        return default


def intrinsic_price_model(info: dict) -> dict:
    """신뢰도 중심 간이 모델: Graham + P/E anchor + margin of safety."""
    eps = safe_float(info.get("trailingEps"))
    growth = safe_float(info.get("earningsQuarterlyGrowth"), 0.08)
    growth = np.clip(growth if not np.isnan(growth) else 0.08, 0.00, 0.20)
    current_pe = safe_float(info.get("trailingPE"), 15.0)
    current_pe = np.clip(current_pe if not np.isnan(current_pe) else 15.0, 6.0, 25.0)

    # Graham-like (simplified): V = EPS * (8.5 + 2g*100)
    graham = eps * (8.5 + 2 * growth * 100) if not np.isnan(eps) else np.nan
    pe_anchor = eps * min(18.0, current_pe) if not np.isnan(eps) else np.nan

    if np.isnan(graham) and np.isnan(pe_anchor):
        return {
            "fair_value": np.nan,
            "buy_price": np.nan,
            "confidence": "D",
            "method": "데이터 부족",
        }

    fair = np.nanmean([graham, pe_anchor])
    buy = fair * 0.8  # 20% margin of safety

    coverage = int(not np.isnan(eps)) + int(not np.isnan(current_pe)) + int(not np.isnan(growth))
    confidence = "A" if coverage == 3 else "B" if coverage == 2 else "C"

    return {
        "fair_value": fair,
        "buy_price": buy,
        "confidence": confidence,
        "method": "Graham+PE 앵커 블렌드 (보수적 안전마진 20%)",
    }


def render_expert_table(ticker: str, opinions: dict):
    rows = opinions.get(ticker.upper(), [])
    if not rows:
        st.info("등록된 전문가 의견 데이터가 없습니다. (샘플은 일부 티커만 포함)")
        return
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)


def fmt(v):
    if pd.isna(v):
        return "N/A"
    return f"${v:,.2f}"


st.title("📈 Stock Bot — 검색/재무/전문가의견/예상주가")
st.markdown('<span class="pill">실시간 검색 + 근거 기반 예상주가 + 전문가 출처 표시</span>', unsafe_allow_html=True)

query = st.text_input("기업명 또는 티커 검색", placeholder="예: Apple, AAPL, Tesla, TSLA")
results = search_tickers(query) if query else []
selected = st.selectbox("검색 결과", options=results, index=0 if results else None, placeholder="검색어를 입력하세요")

if selected:
    ticker = selected.split(" | ")[0].strip().upper()
    with st.spinner("데이터 불러오는 중..."):
        info, price, fin, bal, cash, rec = load_stock_bundle(ticker)
        opinions = load_expert_opinions()
        model = intrinsic_price_model(info)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("현재가", fmt(safe_float(info.get("currentPrice"))))
    c2.metric("시가총액", f"${safe_float(info.get('marketCap')):,.0f}" if info.get("marketCap") else "N/A")
    c3.metric("모델 적정가", fmt(model["fair_value"]))
    c4.metric("보수적 매수가", fmt(model["buy_price"]))

    st.subheader("1년 가격 추이")
    if not price.empty:
        st.line_chart(price["Close"])
    else:
        st.warning("가격 데이터가 없습니다.")

    st.subheader("재무제표")
    t1, t2, t3 = st.tabs(["손익계산서", "대차대조표", "현금흐름표"])
    with t1:
        st.dataframe(fin.T.head(8), use_container_width=True)
    with t2:
        st.dataframe(bal.T.head(8), use_container_width=True)
    with t3:
        st.dataframe(cash.T.head(8), use_container_width=True)

    st.subheader("전문가 의견 & 목표주가 (출처 포함)")
    render_expert_table(ticker, opinions)

    st.subheader("신뢰도 있는 예상 주가")
    st.write(f"- 방법: **{model['method']}**")
    st.write(f"- 모델 신뢰도: **{model['confidence']}**")
    st.write("- 해석: 적정가보다 현재가가 충분히 낮을 때만 매수 후보로 분류")

    st.subheader("애널리스트 추천(원천: Yahoo Finance 제공 값)")
    if rec is not None and not rec.empty:
        display_cols = [c for c in ["period", "strongBuy", "buy", "hold", "sell", "strongSell"] if c in rec.columns]
        st.dataframe(rec[display_cols].tail(6), use_container_width=True)
    else:
        st.info("제공 가능한 추천 데이터가 없습니다.")

st.caption(f"Last updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
