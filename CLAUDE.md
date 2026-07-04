# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## 보험 상담 AI 에이전트

GPT-4o + ChromaDB RAG + 보험다모아 엑셀/실시간 스크래핑 + FSS API + 실시간 웹 검색 기반 보험 상담 챗봇.

---

## 실행 명령어

```bash
# 웹 서버 (메인)
python web_app.py          # http://localhost:5000

# CLI
python main.py

# Windows 원클릭
run.bat                    # ANSI(CP949) 인코딩 필수 — UTF-8 저장 시 한글 깨짐

# ChromaDB 최초 구축
python scripts/build_vectorstore.py [--reset]

# 엑셀 → 지식베이스 반영 + ChromaDB 재구축
python scripts/build_knowledge_from_excel.py --apply --rebuild

# 보험다모아 실시간 데이터 수집 (CDP 모드)
python scripts/fetch_live_data.py --cdp [--type 종신보험] [--debug]
```

### 보험다모아 CDP 스크래핑 사전 작업
```cmd
"C:\Program Files\Google\Chrome\Application\chrome.exe" ^
    --remote-debugging-port=9222 ^
    --user-data-dir="%TEMP%\ChromeDebug" ^
    --remote-allow-origins=* ^
    "https://www.e-insmarket.or.kr"
```

---

## 아키텍처

```
사용자 입력
    │
    ▼
InsuranceChatbot (agents/orchestrator.py)
    │  GPT-4o Tool Calling 루프 + SSE 스트리밍
    │  _build_system_prompt(): 오늘 날짜 동적 주입
    │
    ├── search_insmarket_products    → tools/excel_search_tool.py  ← 1순위
    ├── search_web / fetch_webpage   → tools/web_search_tool.py    ← 2순위
    ├── search_insurance_products    → tools/product_tools.py      ← 3순위
    ├── retrieve_insurance_knowledge → tools/rag_tools.py (ChromaDB) ← fallback
    ├── fetch_fss_realtime_products  → api/fss_client.py
    ├── get_credit_score             → tools/credit_score_tool.py (CDP)
    └── get_personalized_recommendation → Sub-agent (GPT-4o)
```

**데이터 소스 우선순위** (GPT-4o 지시 순서):
1. 보험다모아 엑셀 공시 데이터 (`*.xls` 프로젝트 루트 스캔)
2. 실시간 웹 검색 (DuckDuckGo, API 키 불필요)
3. 로컬 정적 DB (`data/products.py`, `data/dental_products.py`)
4. ChromaDB RAG fallback (`data/knowledge.py` 기반)
5. FSS API (연금저축보험 전용, `FSS_API_KEY` 필요)

---

## 핵심 설계 결정 사항

### 엑셀 로더 (`data/excel_loader.py`)
- 프로젝트 루트 `*.xls` 자동 스캔 및 파싱
- 파일명에서 연령대/성별 컨텍스트 추출 (예: `40대_남성_실손보험.xls`)
- Type 1: 단일 보험료 컬럼 / Type 2: 남/여 별도 컬럼
- `file_context.age_group` 없는 상품 = 연령 무관 → 모든 조회에 포함
- 캐시: `data/insmarket_excel_cache.json` (파일 수정 시 자동 갱신)

### ChromaDB 벡터 스토어 (`rag/vectorstore.py`)
- 싱글톤 패턴, `get_instance()` 사용
- `add_documents(docs)` 로 upsert, `reset()` 후 재구축
- `build_from_knowledge()` 메서드는 **존재하지 않음** — 항상 `get_all_knowledge()` + `add_documents()` 패턴 사용

### 임베딩 (`rag/embeddings.py`)
- 모델: `jhgan/ko-sroberta-multitask` (최초 실행 시 ~443MB 다운로드)
- ChromaDB 미설치 시 `rag_tools.py`가 키워드 검색으로 자동 fallback

### 웹 서버 (`web_app.py`)
- Flask + SSE 스트리밍 (`/api/chat/stream`)
- Live Mode: GPT-4o 오케스트레이터 / Mock Mode: 로컬 도구만 사용
- Auto Mode: API 크레딧 확인 후 자동 선택

### 신용점수 포트폴리오
- `/api/credit-portfolio` → GPT-4o 서브에이전트 생성
- 5등급 모델 (`data/credit_model.py`): 최우량(900+) / 우량(750~) / 보통(600~) / 주의(450~) / 불량(~449)
- NICE + KCB 점수 평균 자동 계산

---

## 주의 사항

- `data/dental_products.py`는 함수 없음 — `DENTAL_INSURANCE_PRODUCTS` 리스트 직접 참조
- `run.bat`은 반드시 **ANSI(CP949)** 인코딩 저장
- FSS API는 **연금저축보험만** 지원
- `scripts/build_knowledge_from_excel.py`의 `update_knowledge_py()`:
  - `re.sub` 교체값은 반드시 `'\n'` (빈 문자열이면 `]` 탐지 실패)
  - AUTO-GENERATED 블록은 `data/knowledge.py`의 `KNOWLEDGE_BASE` 리스트 닫는 `]` 바로 앞에 삽입됨

---

## 환경 변수 (`.env`)

```
OPENAI_API_KEY=sk-...   # 필수
FSS_API_KEY=...         # 선택 (연금저축보험 조회 시)
```
