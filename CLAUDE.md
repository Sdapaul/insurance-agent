# 보험 상담 AI 에이전트

생명보험·실손의료보험·암보험·치아보험·간병·치매보험·연금보험 전문 상담 챗봇.
OpenAI GPT-4o + ChromaDB RAG + 보험다모아 엑셀/실시간 스크래핑 + FSS API + 실시간 웹 검색 + 신용점수 포트폴리오 구조.

---

## 환경 설정

### 1. 패키지 설치

```bash
pip install -r requirements.txt

# ChromaDB RAG 사용 시 추가 설치
pip install chromadb sentence-transformers
# PyTorch (Windows CPU)
pip install torch --index-url https://download.pytorch.org/whl/cpu

# 보험다모아 실시간 스크래핑 사용 시 추가 설치
pip install playwright
playwright install chromium

# 웹 검색 (DuckDuckGo, API 키 불필요)
pip install ddgs
```

### 2. 환경 변수 (.env)

`.env.example`을 복사해 `.env`로 저장 후 키 입력:

```
OPENAI_API_KEY=sk-...       # 필수 — platform.openai.com/api-keys
FSS_API_KEY=...              # 선택 — finlife.fss.or.kr (아래 참고)
```

#### FSS API 키 발급 (무료, 당일~익일 승인)

1. <https://finlife.fss.or.kr> 접속
2. 우측 상단 **[회원가입]** → 개인/법인 선택
3. 로그인 후 **[마이페이지] → [API 활용 신청]**
4. 활용 목적 작성 후 신청 (심사 당일~익일)
5. 승인 후 **[마이페이지] → [API 키 관리]** 에서 키 확인

> FSS API는 **연금저축보험**만 공식 지원.
> 종신·실손·암·치아보험 실시간 데이터는 보험다모아 스크래핑으로 수집.

---

## 실행

```bash
# 원클릭 실행 (Windows)
run.bat 더블클릭

# 또는 터미널에서
python web_app.py          # http://localhost:5000

# CLI
python main.py
```

### 보험다모아 실시간 데이터 수집

보험다모아는 **mbuster 봇 차단 시스템**을 사용하므로 실제 Chrome 브라우저에 연결하는 CDP 모드를 사용합니다.

**1단계: Chrome을 원격 디버깅 모드로 실행**
```cmd
"C:\Program Files\Google\Chrome\Application\chrome.exe" ^
    --remote-debugging-port=9222 ^
    --user-data-dir="%TEMP%\ChromeDebug" ^
    --remote-allow-origins=* ^
    "https://www.e-insmarket.or.kr"
```

**2단계: 열린 Chrome에서 보험다모아 접속**
```
https://www.e-insmarket.or.kr
```

**3단계: 별도 터미널에서 수집 스크립트 실행**
```bash
python scripts/fetch_live_data.py --cdp

# 특정 보험 종류만 수집
python scripts/fetch_live_data.py --cdp --type 종신보험

# 선택자 디버깅 (HTML 저장)
python scripts/fetch_live_data.py --cdp --debug
```

---

## 아키텍처

```
사용자 입력 (채팅 탭 또는 신용점수 포트폴리오 탭)
    │
    ▼
InsuranceChatbot (agents/orchestrator.py)
    │  GPT-4o + Tool Calling 루프 (SSE 스트리밍)
    │  _build_system_prompt(): 오늘 날짜 동적 주입
    │
    ├── search_insmarket_products    → tools/excel_search_tool.py  ← 1순위
    ├── search_web / fetch_webpage   → tools/web_search_tool.py    ← 2순위
    ├── search_insurance_products    → tools/product_tools.py      ← 3순위
    ├── compare_insurance_products   → tools/product_tools.py
    ├── get_premium_estimate         → tools/product_tools.py
    ├── retrieve_insurance_knowledge → tools/rag_tools.py (ChromaDB)  ← fallback
    ├── fetch_fss_realtime_products  → api/fss_client.py
    ├── get_credit_score             → tools/credit_score_tool.py (CDP)
    └── get_personalized_recommendation → Sub-agent (GPT-4o)
             └── _run_recommendation_subagent()
                   ├── 보험다모아 엑셀 필터링 (연령/성별)
                   ├── 로컬 DB 상품
                   ├── 신용점수 반영 (credit_model.py)
                   ├── 연령대별 포트폴리오 가이드
                   └── 뉴스 자동 검색 (search_web)
```

---

## 데이터 소스 우선순위

| 순위 | 소스 | 대상 보험 | 조건 |
|------|------|-----------|------|
| 1 | **보험다모아 엑셀** 공시 데이터 | 실손·간병·치아·종신 등 | XLS 파일 존재 |
| 2 | **실시간 웹 검색** (DuckDuckGo) | 전체 | ddgs 설치 |
| 3 | **보험다모아** 실시간 스크래핑 | 종신·정기·실손·암·치아 | Playwright + CDP |
| 4 | **FSS API** 실시간 | 연금저축보험 전용 | FSS_API_KEY 설정 |
| 5 | FSS 로컬 캐시 | 연금저축보험 | `data/fss_cache.json` (24h TTL) |
| 6 | **로컬 정적 데이터** | 전체 (기본값) | 항상 사용 가능 |

### 도구 호출 우선순위 (GPT-4o 지시)
1. `search_insmarket_products` (보험다모아 엑셀) — 가장 먼저 시도
2. `search_web` + `fetch_webpage` — 최신 뉴스·비교 정보
3. `search_insurance_products` / `get_premium_estimate` — 로컬 DB
4. `retrieve_insurance_knowledge` — fallback (지식베이스)

---

## 파일 구조

```
insurance_agent/
├── main.py                  # CLI 진입점
├── web_app.py               # Flask 웹 서버 + 탭 UI (채팅 + 신용점수 포트폴리오)
├── run.bat                  # Windows 원클릭 실행 스크립트 (ANSI 인코딩)
├── requirements.txt
├── .env                     # API 키 (git 제외)
├── .env.example             # 키 템플릿
│
├── agents/
│   └── orchestrator.py      # GPT-4o 오케스트레이터 + Tool 정의
│                            # _build_system_prompt(): 날짜 동적 주입
│                            # _run_recommendation_subagent(): 연령별 포트폴리오
│
├── tools/
│   ├── product_tools.py     # 상품 검색/비교/보험료 견적
│   ├── rag_tools.py         # ChromaDB 벡터 검색 (fallback: 키워드)
│   ├── web_search_tool.py   # DuckDuckGo 실시간 웹 검색
│   ├── web_fetch_tool.py    # URL 본문 크롤링
│   ├── excel_search_tool.py # 보험다모아 엑셀 데이터 검색 (연령/성별 필터)
│   └── credit_score_tool.py # NICE/KCB 신용점수 CDP 스크래핑
│
├── api/
│   ├── fss_client.py        # FSS API 클라이언트 (연금저축보험)
│   └── insmarket_scraper.py # 보험다모아 Playwright 스크래퍼
│
├── data/
│   ├── products.py          # 로컬 보험 상품 정적 데이터 (fallback)
│   ├── dental_products.py   # 치아보험 상품 데이터 (DENTAL_INSURANCE_PRODUCTS 리스트)
│   ├── knowledge.py         # 보험 지식 베이스 (RAG 원본, 엑셀에서 자동 생성 가능)
│   ├── excel_loader.py      # XLS 파싱 + 캐시 (insmarket_excel_cache.json)
│   ├── credit_model.py      # 신용점수 5등급 모델 + 보험 추천 로직
│   ├── insmarket_cache.json # 보험다모아 스크래핑 캐시 (자동 생성)
│   ├── insmarket_excel_cache.json  # 엑셀 파싱 캐시 (자동 생성)
│   ├── fss_cache.json       # FSS API 캐시 (자동 생성)
│   └── debug/               # 스크래핑 디버그 HTML (--debug 옵션)
│
├── rag/
│   └── vectorstore.py       # ChromaDB 래퍼
│
├── scripts/
│   ├── fetch_live_data.py   # 보험다모아 수동 갱신 CLI
│   └── build_knowledge_from_excel.py  # 엑셀→지식베이스 자동 생성
│
└── chroma_db/               # ChromaDB 저장소 (자동 생성)
```

---

## 주요 모델 / 라이브러리

| 항목 | 값 |
|------|----|
| LLM | `gpt-4o` (오케스트레이터 + 추천 서브에이전트) |
| API 상태 체크 | `gpt-4o-mini` (1토큰, 60초 캐싱) |
| 실시간 스크래핑 | Playwright (Chromium CDP 모드) |
| 웹 검색 | DuckDuckGo (`ddgs` 라이브러리, API 키 불필요) |
| 엑셀 파싱 | `xlrd` (XLS 형식) |
| 임베딩 | `jhgan/ko-sroberta-multitask` (최초 실행 시 ~443MB 다운로드) |
| 벡터 DB | ChromaDB (로컬, `chroma_db/` 디렉터리) |
| 웹 프레임워크 | Flask + SSE 스트리밍 |

---

## 웹 UI 기능

### 탭 구성
1. **💬 보험 상담 탭** — GPT-4o 스트리밍 채팅
   - 빠른 버튼: 암보험/치아보험/실손비교/간병·치매/포트폴리오/4세대vs5세대
   - SSE(Server-Sent Events) 스트리밍으로 토큰 단위 실시간 출력
   - 도구 호출 단계 표시 (🔍 엑셀 검색 중, 🌐 웹 검색 중 등)

2. **💳 신용점수 포트폴리오 탭** — 신용점수 기반 맞춤 포트폴리오
   - 신용점수 확인 방법 안내 (토스/카카오페이/NICE지키미/올크레딧)
   - NICE + KCB 점수 중 하나 또는 둘 다 입력 가능 → 평균 자동 계산
   - 입력 즉시 등급 뱃지 표시 (최우량/우량/보통/주의/불량)
   - `/api/credit-portfolio` 엔드포인트 → GPT-4o 포트폴리오 생성

### 답변 구성
모든 보험 상품 답변에 자동으로 포함:
1. 상품 추천/비교 본문
2. **📰 관련 최신 뉴스** — 웹 검색 후 2~3개 자동 첨부
3. **📋 이 답변의 근거** — 데이터 출처·신뢰도 표

---

## 신용점수 모델 (data/credit_model.py)

| 등급 | 점수 | 특성 | 추천 방향 |
|------|------|------|-----------|
| 최우량 | 900+ | 금융 신용 최상위 | 프리미엄 종신·변액·저축보험 |
| 우량 | 750~899 | 일반 직장인 | 모든 보험 표준 추천 |
| 보통 | 600~749 | 부채 있음 | 보장성 보험 집중 |
| 주의 | 450~599 | 연체 경험 | 무심사/간편심사형 우선 |
| 불량 | ~449 | 신용 위험 | 무심사 상품 + 신용 관리 병행 |

### NICE/KCB 신용점수 CDP 조회 (tools/credit_score_tool.py)
- Chrome 디버깅 모드로 NICE지키미(credit.co.kr) 또는 올크레딧(allcredit.co.kr) 로그인 후 조회
- 6가지 CSS 선택자 후보 + 정규식 fallback으로 점수 추출
- CDP 포트: 9222 (보험다모아 스크래핑과 동일)

---

## 엑셀 데이터 연동 (data/excel_loader.py)

- 프로젝트 루트의 `*.xls` 파일 자동 스캔·파싱
- 파일명에서 성별/연령대 컨텍스트 자동 추출 (예: `40대_남성_실손보험.xls`)
- 두 가지 형식 지원:
  - Type 1: 단일 보험료 컬럼 (종신·암·간병보험 등)
  - Type 2: 남/여 별도 컬럼 (실손보험)
- `file_context.age_group` 없는 상품(간병보험 등) = 연령 무관 → 모든 연령 조회에 포함
- 캐시: `data/insmarket_excel_cache.json` (파일 수정 시 자동 갱신)

### 지식베이스 자동 생성
```bash
python scripts/build_knowledge_from_excel.py          # 미리보기
python scripts/build_knowledge_from_excel.py --apply  # data/knowledge.py 적용
python scripts/build_knowledge_from_excel.py --apply --rebuild  # + ChromaDB 재구축
```

---

## 시스템 프롬프트 동적 주입 (agents/orchestrator.py)

```python
def _build_system_prompt() -> str:
    today = date.today().strftime("%Y년 %m월 %d일")
    # 오늘 날짜 + 2025/2026 웹 검색 지시 + SYSTEM_PROMPT 조합
```

- 모든 채팅 요청마다 오늘 날짜가 시스템 프롬프트에 주입됨
- 웹 검색 쿼리에 반드시 2025/2026 연도 포함 지시
- 2024년 이전 자료 재해석 지시

---

## CLI 명령어

| 명령 | 동작 |
|------|------|
| `/reset` | 대화 초기화 |
| `/help` | 도움말 |
| `/refresh` | 보험다모아 실시간 데이터 즉시 갱신 (Playwright 필요) |
| `/rebuild` | ChromaDB 벡터 DB 재구축 |
| `/quit` | 종료 |

---

## 스크래핑 문제 해결

### 봇 차단(mbuster) 우회
```cmd
# 1. Chrome 디버깅 모드 실행
"C:\Program Files\Google\Chrome\Application\chrome.exe" ^
    --remote-debugging-port=9222 ^
    --user-data-dir="%TEMP%\ChromeDebug"

# 2. Chrome에서 보험다모아 접속 확인
# 3. 스크립트 실행
python scripts/fetch_live_data.py --cdp
```

### 선택자 디버깅
```bash
python scripts/fetch_live_data.py --cdp --debug
# data/debug/ HTML 파일로 구조 확인 후 api/insmarket_scraper.py _extract() 수정
```

---

## 특이 사항

- `data/dental_products.py`에는 함수가 없고 `DENTAL_INSURANCE_PRODUCTS` 리스트만 존재 — import 시 직접 리스트 참조
- 블록체인 덴탈보험 질문 시 **라이나생명 블록체인치아보험 스마트 (dental_005)** 1순위 추천
- ChromaDB 미설치 시 키워드 검색으로 자동 fallback
- FSS API는 연금저축보험만 지원
- `run.bat`은 반드시 ANSI(CP949) 인코딩으로 저장 — UTF-8 저장 시 한글 깨짐
- 보험다모아 공시 기준 상품만 표시 — 비공시 특약 등은 보험사 직접 확인 필요
- Windows 작업 스케줄러로 `fetch_live_data.py`를 매일 실행하면 항상 최신 엑셀 데이터 유지
