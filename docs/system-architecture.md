# 시스템 아키텍처 (신뢰도 우선)

## 1) 계층

1. Data Ingestion
   - 시세, 재무제표, 뉴스/공시, 금리/거시 데이터
2. Data Quality Layer
   - 스키마 검증, 결측 보정, 소스 간 교차검증
3. Feature Store
   - 팩터/지표 계산 결과 저장
4. Strategy Engine
   - Buffett/Lynch/기타 전략 점수 계산
5. Alert Engine
   - 룰 + 우선순위 + 사용자 선호도 반영
6. API Layer
   - 종목조회, 스크리너, 점수설명, 알림
7. Frontend
   - 대시보드, 스코어카드, 시나리오 차트

## 2) 권장 기술 스택

- Backend: Python (FastAPI)
- Data Jobs: Airflow or Prefect + pandas/polars
- DB: PostgreSQL + Redis
- Search: OpenSearch/Elasticsearch (티커/뉴스)
- Frontend: Next.js + TypeScript + Tailwind
- Charts: ECharts or TradingView widget

## 3) 신뢰성 설계

- 모든 지표에 `source`, `as_of_date`, `version` 저장
- 배치 실패 시 재시도 + 부분 롤백
- 전략 버전 관리 (`strategy_version`)
- 감사 로그: 점수 산출 입력값/결과 추적

## 4) API 예시

- `GET /stocks/{ticker}`: 기본 정보 + 최신 지표
- `POST /screen`: 필터 조건 검색
- `GET /scores/{ticker}`: 전략별 점수 및 근거
- `POST /alerts`: 알림 규칙 생성
- `GET /valuation/{ticker}`: 시나리오별 예상 가격


## 5) 데이터 소스 맵

- **Primary Filings Adapter**: EDGAR/DART 원문 수집, XBRL 파싱
- **Market Data Adapter**: 가격/거래량/기업행위 수집
- **Secondary Vendor Adapter**: 정규화된 재무/추정치 수집
- **Reconciliation Job**: 동일 필드 교차검증(우선순위: 1차 > 2차)

우선순위 룰 예시:
1. 공시 원문 값 존재 시 원문 채택
2. 원문 결측 시 보조 벤더 값 채택 + confidence 하향
3. 상충 시 최신 공시일/주석 근거가 있는 값 채택


## 6) 실시간 알림 아키텍처

- Price Stream: WebSocket/벤더 스트림 수신 (초/틱 단위)
- Rule Evaluator: 사용자별 매수/매도 조건 실시간 평가
- Signal Dedup: 동일 원인 신호 묶음 처리
- Notifier: Push/Email/Webhook 발송

지연 목표(SLO):
- 가격 이벤트 수신 후 알림 발송까지 p95 5초 이내
- 장중 장애 시 재시도 + 대체 채널 발송
