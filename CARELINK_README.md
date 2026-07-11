# 케어링크(CareLink) — 건강검진 기반 위험예측 × 보험 추천 웹앱

건강검진 수치를 입력하면 **만성질환(당뇨·대사) 위험도**를 예측하고, 그 위험에 맞는 **보험 유형과 실제 보험다모아 상품**을 추천하는 웹 애플리케이션입니다. 기존 보험 상담 AI 에이전트(GPT-4o) 위에 "건강 위험 → 예방·보장" 흐름을 얹었습니다.

2026 가명정보 활용 경진대회 아이디어 "건강검진×보험 가명결합"의 실동작 데모.

---

## 주요 기능

- **건강 위험 예측**: 나이·성별·BMI·혈압·지질·간수치·흡연/음주로 당뇨 위험도 산출 (AUC ≈ 0.78)  
- **임상 플래그**: 비만·고혈압 의심·간수치 이상·이상지질혈증·흡연 자동 표시  
- **맞춤 보험 추천**: 위험 유형 → 질병/실손/간병·치매/종신 등 보험 유형 매핑  
- **실제 상품 연계**: 보험다모아 공시 데이터에서 연령·성별에 맞는 상품 조회  
- **AI 상담 연동**: 기존 GPT-4o 챗봇의 `assess_health_risk` 도구로도 호출 가능

---

## 빠른 시작

\# 1\) 의존성 설치

pip install \-r requirements.txt

\# 2\) 환경변수

echo OPENAI\_API\_KEY=sk-...  \> .env      \# 필수

\# echo FSS\_API\_KEY=...     \>\> .env      \# 선택(연금저축보험 조회)

\# 3\) 웹 서버 실행

python web\_app.py

\# 브라우저에서 http://localhost:5000/health-risk 접속

---

## 사용법

1. `/health-risk` 페이지에서 건강검진 값 입력 (나이·성별만 넣어도 동작, 값이 많을수록 정확)  
2. "위험 분석" 클릭 → 위험 점수·밴드(저/중/고), 임상 플래그, 추천 보험, 실제 상품 표시  
3. 또는 챗봇(`/`)에서 자연어로: *"48세 남자, 혈압 145/92, 중성지방 230, 흡연. 맞는 보험 추천해줘"*

### API 직접 호출

curl \-s \-X POST http://localhost:5000/api/health-risk \\

  \-H "Content-Type: application/json" \\

  \-d '{"age":48,"gender":"남","height":172,"weight":82,"sbp":145,"dbp":92,"triglyceride":230,"hdl":38,"ggt":85,"smoke":3,"drink":1}'

---

## 프로젝트 구조

insurance\_agent/

├── web\_app.py                     Flask 웹서버 (챗봇 \+ /health-risk)

├── main.py                        CLI 챗봇

├── agents/orchestrator.py         GPT-4o 오케스트레이터 (assess\_health\_risk 도구 등록)

├── tools/

│   ├── health\_risk\_tool.py        ★ 건강위험 예측 → 보험추천 로직

│   ├── excel\_search\_tool.py       보험다모아 엑셀 상품 검색

│   └── ...                        product/web/rag/credit 도구

├── data/

│   ├── risk\_model\_params.json     위험예측 모델 파라미터(순수 파이썬 추론)

│   └── \*.xls                      보험다모아 공시 데이터

├── health\_risk/

│   ├── train\_risk\_model.py        모델 학습 \+ AUC/ROC 산출

│   ├── roc\_curve.png              ROC 곡선 (AUC 0.78)

│   └── README.md                  모듈 상세

└── requirements.txt

---

## 모델 정보

- **타깃**: 공복혈당 ≥126(당뇨 위험). 혈당은 피처에서 제외해 정보 누출 방지  
- **입력 피처**: 나이·성별·BMI·허리둘레·수축기/이완기 혈압·TC·TG·HDL·LDL·AST·ALT·GGT·흡연·음주  
- **성능**: AUC ≈ 0.78 (당뇨 선별 모델로 타당)  
- **상위 위험요인**: BMI › 연령 › 흡연 › 중성지방 (임상적으로 타당)  
- **추론**: 표준화 \+ 로지스틱 계수로 순수 파이썬 계산 → 웹서버에 ML 라이브러리 불필요

### 실데이터로 재학습

현재 모델은 **NHIS 건강검진 공개데이터 스키마를 모사한 합성 데이터**로 학습돼 있습니다 (개발 환경 네트워크 제한 때문). 실제 데이터로 바꾸려면:

pip install scikit-learn pandas numpy matplotlib

\# health\_risk/train\_risk\_model.py 의 데이터 생성부를 실제 CSV 로드로 교체:

\#   df \= pd.read\_csv("국민건강보험공단\_건강검진정보\_2023.csv", encoding="cp949")

python health\_risk/train\_risk\_model.py     \# → data/risk\_model\_params.json 자동 갱신

공개데이터: **국민건강보험공단\_건강검진정보** — [https://www.data.go.kr/data/15007122/fileData.do](https://www.data.go.kr/data/15007122/fileData.do) (IRB·소속 없이 다운로드 가능)

---

## 윤리 및 주의

- 예측 결과는 **예방·보장 강화 목적**이며, **보험 가입 거절·불이익·차별의 근거로 사용하지 않습니다.**  
- 선별용 위험도이며 **의학적 진단이 아닙니다.** 정확한 진단은 의료기관에서 받으세요.  
- 보험료·상품 정보는 공시 기준이며 실제 조건은 보험사·설계사 확인이 필요합니다.

---

## 라이선스 / 크레딧

개인 학습·경진대회용 데모. 보험다모아(e-insmarket.or.kr) 공시자료, 국민건강보험공단 공개데이터 활용.  
