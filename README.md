# Stock Bot Pro KR

한국/미국 주식을 함께 지원하는 **실행 가능한** 투자 리서치 앱입니다.

## 프리미엄급 기능

- 한국주식 + 미국주식 검색 (`005930` 같은 6자리 코드도 지원)
- 장기 차트: `6mo`, `1y`, `3y`, `5y`, `10y`, `max`
- 원클릭 우량기업 스크리너 (전략점수 + 신뢰도 기준)
- 시가총액 필터(대형/중형/소형) + 필터 검증 요약
- 전략 프리셋(복수 선택): Buffett / Lynch / Graham / CANSLIM Lite / Minervini Lite / Quality Growth
- 통계 한글화 탭 (PER, PBR, ROE, 부채비율, 성장률 등)
- 리스크 통계(기간 수익률, 연환산 변동성, MDD)
- 전문가 의견/목표가 + 출처 안내
- 신뢰도 기반 예상 주가 (가중치 공개)
- 관심종목 저장 + Webhook 기반 모바일 알림
- 뉴스 탭
- 투자 스타일(스캘핑/스윙/장기) + 투자금 구간별 조언
- 스타일/투자금 적합성 필터 + 제외 사유 제공
- 리스크 기반 포지션 사이징 계산기(계좌 통화(KRW/USD) + 계좌금액/허용손실 기반)

## 디자인

- 전체 UI를 가독성 높은 밝은 테마로 구성
- 은은한 파스텔 보라 포인트 컬러 사용 (`#B79CFF`, `#6E4CCB`)

## 실행

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./run.sh
```


엔트리 파일: `stock.py`
