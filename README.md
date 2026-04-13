# Stock Bot Pro

실행 가능한 주식 탐색/필터링 앱입니다.

## 핵심 기능

- 검색: 기업명/티커로 즉시 검색
- 기간 확장 차트: `6mo`, `1y`, `3y`, `5y`, `10y`, `max`
- 원클릭 우량기업 필터: 전략/신뢰도 기준으로 후보를 한 번에 나열
- 전략 프리셋 필터:
  - Buffett, Lynch, Graham, CANSLIM Lite, Minervini Lite, Quality Growth
- 전문가 의견/목표가 표시 + 출처 설명
- 신뢰도 기반 예상 주가 계산(애널리스트 목표가 + 내재가치 + 현재가 앵커)
- 관심종목 저장(`watchlist.json`) + Webhook 기반 모바일 알림 연동
- 투자 스타일/금액대별 가이드(스캘핑/스윙/장기, 투자금 구간)

## 정확도/신뢰성 원칙

- 데이터 출처 표시: yfinance(Yahoo Finance feed) 기반
- 전략 점수와 데이터 신뢰도 점수 분리 표기
- 데이터 결측 시 신뢰도 자동 하향
- 예측값은 단일 절대값이 아닌 구성요소 가중치 공개

## 실행 방법

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./run.sh
```

브라우저에서 Streamlit 주소를 열면 됩니다.
