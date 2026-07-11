# CLAUDE.md — 건강위험 예측 × 보험 추천 웹앱

이 파일은 Claude Code(claude.ai/code)가 이 저장소에서 작업할 때 참고하는 지침입니다.

---

## 프로젝트 목표

기존 **보험 상담 AI 에이전트**(`insurance_agent`)에, **건강검진 기반 만성질환 위험 예측 → 맞춤 보험 보장 연계** 기능을 **웹페이지**로 제공한다. 사용자가 브라우저에서 건강검진 수치(혈압·혈당·BMI·간수치 등)를 입력하면 → 당뇨/대사 위험도를 예측하고 → 위험에 맞는 보험 유형과 **보험다모아 실제 상품**을 추천한다.

배경: 2026 가명정보 활용 경진대회 아이디어 "케어링크(건강검진×보험 결합)"의 실동작 데모.

---

## 지금 만들 것 (이번 작업 범위)

1. **웹 입력 폼 페이지** `/health-risk` — 건강검진 값 입력 UI  
2. **API 엔드포인트** `POST /api/health-risk` — 입력 → `assess_health_risk()` 호출 → JSON 반환  
3. **결과 화면** — 위험 점수(게이지/밴드), 임상 플래그, 추천 보험 유형, 보험다모아 상품 카드  
4. (선택) 기존 챗봇 화면에서 "건강검진으로 추천받기" 버튼으로 연결

---

## 실행 명령어

\# 의존성

pip install \-r requirements.txt          \# flask, openai, python-dotenv, pandas, xlrd 등

pip install scikit-learn matplotlib numpy \# 모델 재학습용(선택)

\# 웹 서버 (메인) — http://localhost:5000

python web\_app.py

\# 위험예측 모델 재학습(실데이터 반영 시)

python health\_risk/train\_risk\_model.py   \# → data/risk\_model\_params.json 갱신

\# CLI 챗봇

python main.py

`.env` 필요: `OPENAI_API_KEY=sk-...` (FSS\_API\_KEY는 선택)

---

## 아키텍처

web\_app.py (Flask \+ SSE)

  ├── GET  /                     기존 챗봇 UI (render\_template\_string)

  ├── POST /api/chat/stream      GPT-4o 오케스트레이터 스트리밍

  ├── POST /api/credit-portfolio 신용점수 포트폴리오

  ├── GET  /health-risk          ★ 신규: 건강위험 입력 폼 페이지

  └── POST /api/health-risk      ★ 신규: 위험예측 \+ 상품추천 JSON

agents/orchestrator.py

  └── InsuranceChatbot (GPT-4o Tool Calling)

      TOOLS \= \[ search\_insurance\_products, search\_insmarket\_products,

                assess\_health\_risk, get\_personalized\_recommendation, ... \]

      execute\_tool() 로 각 도구 디스패치

tools/health\_risk\_tool.py         ★ 핵심 로직 (이미 구현됨, 재사용)

  └── assess\_health\_risk(age, gender, height, weight, waist, sbp, dbp,

        total\_cholesterol, triglyceride, hdl, ldl, ast, alt, ggt, smoke, drink,

        include\_products=True) \-\> JSON 문자열

      · data/risk\_model\_params.json 로드 → 순수 파이썬 로지스틱 추론(외부 ML 의존 없음)

      · 위험밴드(저/중/고) \+ 임상 플래그 \+ 추천 보험유형

      · include\_products=True면 tools/excel\_search\_tool.search\_insmarket\_products로

        보험다모아 실제 상품(연령·성별 필터) 조회

data/risk\_model\_params.json        모델 파라미터(표준화 mean/scale, 계수, intercept, AUC)

health\_risk/train\_risk\_model.py    학습 스크립트 (AUC/ROC 산출, params JSON export)

health\_risk/roc\_curve.png          ROC 곡선 (Logistic AUC 0.777 / GBoost 0.773)

---

## 구현 가이드 (신규 웹페이지)

### 1\) API 엔드포인트 — `web_app.py`에 추가

from tools.health\_risk\_tool import assess\_health\_risk

@app.route('/api/health-risk', methods=\['POST'\])

def api\_health\_risk():

    d \= request.get\_json(force=True) or {}

    \# 숫자 필드는 빈 값이면 None으로 (모델이 결측을 평균 대체)

    def num(k):

        v \= d.get(k)

        return float(v) if v not in (None, "", "null") else None

    out \= assess\_health\_risk(

        age=int(d\["age"\]), gender=d.get("gender", "남"),

        height=num("height"), weight=num("weight"), waist=num("waist"),

        sbp=num("sbp"), dbp=num("dbp"),

        total\_cholesterol=num("total\_cholesterol"), triglyceride=num("triglyceride"),

        hdl=num("hdl"), ldl=num("ldl"),

        ast=num("ast"), alt=num("alt"), ggt=num("ggt"),

        smoke=int(d\["smoke"\]) if d.get("smoke") else None,

        drink=int(d\["drink"\]) if d.get("drink") not in (None, "") else None,

        include\_products=True,

    )

    return app.response\_class(out, mimetype='application/json')

`assess_health_risk`는 **JSON 문자열**을 반환하므로 그대로 응답에 실으면 됨.

### 2\) 입력 폼 페이지 — `/health-risk`

- 필수: 나이, 성별. 선택: 키/몸무게(→BMI 자동), 허리둘레, 혈압, 지질, 간수치, 흡연/음주  
- 제출 시 `fetch('/api/health-risk', {method:'POST', body: JSON})` → 결과 렌더  
- 결과 표시: `risk_assessment.risk_score`(0\~1)를 게이지/색상 밴드로, `input_summary.flags` 칩, `recommended_insurance_types` 목록, `insmarket_products[type].results[]` 상품 카드

### 3\) 응답 JSON 형태(참고)

{

  "input\_summary": {"age": 48, "gender": "남", "bmi": 27.7, "flags": \["비만(BMI≥25)","고혈압 의심","현재 흡연"\]},

  "risk\_assessment": {"target":"당뇨(대사질환) 위험","risk\_score":0.881,"risk\_band":"고위험",

                       "model":"NHIS 건강검진 스키마 로지스틱 (AUC 0.7771)"},

  "recommended\_insurance\_types": \["질병보험","실손의료보험"\],

  "insmarket\_products": {"질병보험": {"results":\[...\], "total\_found": N}, "실손의료보험": {...}},

  "guidance": "...", "disclaimer": "..."

}

---

## 코딩 규칙 / 주의사항

- **한국어 UI/주석**. 인코딩은 UTF-8(단, `run.bat`은 예외로 ANSI/CP949 유지).  
- `assess_health_risk`는 표준 라이브러리만 사용 → 웹서버에 별도 ML 의존성 추가 금지.  
- 결측 검진값은 반드시 `None`으로 전달(빈 문자열 금지) → 모델이 학습 평균으로 대체.  
- 위험도 밴드 기준: `>=0.30 고위험`, `>=0.15 중간위험`, 그 외 저위험(도구 내부 로직과 일치).  
- `search_insmarket_products`의 `insurance_type` enum: 실손의료보험·간병·치매보험·치아보험· 종신보험·질병보험·상해보험·저축보험 (오타 주의: 정확히 일치해야 조회됨).  
- **윤리 필수**: 결과 화면에 "예방·보장 강화 목적, 가입 거절·불이익 근거 아님 / 의학적 진단 아님" 고지를 반드시 노출. 위험도로 가입 거절·차별을 유도하는 UI 금지.

### 데이터 주의 (모델)

현재 `risk_model_params.json`은 **NHIS 건강검진 스키마를 모사한 합성 데이터**로 학습됨 (개발 환경에서 data.go.kr 접근 불가). 실데이터로 재학습하려면 `health_risk/train_risk_model.py`의 데이터 생성부를 실제 CSV 로드로 교체 후 재실행 → params JSON이 갱신되면 도구가 자동 반영. 공개데이터: 국민건강보험공단\_건강검진정보 (data.go.kr/data/15007122/fileData.do).

---

## 테스트

\# 도구 단독

python tools/health\_risk\_tool.py           \# 48세 남성 샘플 출력

\# API (서버 실행 후)

curl \-s \-X POST http://localhost:5000/api/health-risk \\

  \-H "Content-Type: application/json" \\

  \-d '{"age":52,"gender":"여","height":160,"weight":70,"sbp":150,"dbp":95,"triglyceride":210,"hdl":42,"ggt":60,"smoke":1}'

기대: `risk_band` "고위험", `recommended_insurance_types`에 질병보험·실손의료보험, `insmarket_products`에 실제 상품 배열.  
