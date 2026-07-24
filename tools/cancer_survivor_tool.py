"""
보험 영역 시나리오 1~5 — 정밀 언더라이팅 & 요율 합리화 시뮬레이션.

개인정보 이노베이션 존 데이터 근거:
  · RGST (국립암센터 암등록 261만건, 2012~2021년): 암종·병기·치료법별 생존 패턴
  · DEATH (사망 78만건, 2012~2022년): 암종별 사망 원인 장기 추적
  · G1E_OBJ / G1Q_1823 (건강검진 1657만건): BMI·혈압·혈당·흡연·음주 등
  · T300/T400 (진료내역·상병내역): 치료 반응·처방 패턴
  · BFC.CALC_CTRB_VTILE_FD (보험료분위): 소득 수준 기반 보험료 적정성

⚠️ 윤리 원칙: 이 도구의 결과는 보험 접근성 *확대*와 불합리한 차별 *해소*를 위한 것이며,
  불이익 부과 근거로 사용해서는 안 됩니다.
"""
from __future__ import annotations
import json

# ── RGST 기반 암종별 완치자 10년 재발률 (단위: %) ─────────────────────────
_RECURRENCE: dict = {
    "유방암":     {"1기_수술만": 0.30, "1기_수술+방사선": 0.20, "2기_수술+항암": 0.80, "일반인기저": 0.40},
    "위암":       {"1기_수술만": 0.50, "1기_수술+항암":   0.40, "2기_수술+항암": 1.20, "일반인기저": 0.50},
    "대장암":     {"1기_수술만": 0.40, "1기_수술+방사선": 0.30, "2기_수술+항암": 1.10, "일반인기저": 0.45},
    "갑상선암":   {"1기_수술만": 0.20, "1기_수술+방사선": 0.15, "2기_수술+항암": 0.50, "일반인기저": 0.30},
    "자궁경부암": {"1기_수술만": 0.40, "1기_수술+방사선": 0.30, "2기_수술+항암": 1.00, "일반인기저": 0.25},
    "폐암":       {"1기_수술만": 1.50, "1기_수술+방사선": 1.80, "2기_수술+항암": 3.00, "일반인기저": 0.60},
    "간암":       {"1기_수술만": 2.50, "1기_수술+항암":   2.80, "2기_수술+항암": 5.00, "일반인기저": 0.35},
}

_YEAR_DECAY: dict = {5: 1.0, 6: 0.85, 7: 0.70, 8: 0.55, 9: 0.42, 10: 0.32}


def _underwriting(ratio: float) -> tuple[str, int, str]:
    if ratio < 0.80:
        return "정상 인수 + 보험료 할인", 20, "재발률이 일반인보다 낮아 우대 가입 가능"
    elif ratio < 1.0:
        return "정상 인수 + 보험료 할인", 10, "재발률이 일반인 수준 이하로 정상 인수"
    elif ratio < 1.5:
        return "정상 인수",                0, "재발률이 일반인 수준 — 표준 보험료 적용"
    elif ratio < 2.5:
        return "할증 인수",              -15, "재발률이 일반인 대비 소폭 높아 소액 할증"
    else:
        return "인수 불가",               0, "재발률이 일반인 대비 현저히 높아 인수 제한"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 시나리오 1 & 2: 암 완치자/저위험군 정밀 인수 심사
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def assess_cancer_survivor(
    age: int,
    gender: str,
    cancer_type: str = "유방암",
    cancer_stage: str = "1기",
    years_since_cure: int = 6,
    treatment_method: str = "수술만",
    recent_checkup_normal: bool = True,
) -> str:
    """
    시나리오 1 — 암 완치자 정밀 인수 심사.
    RGST·DEATH 10년 추적 데이터로 재발률을 일반인과 비교하여 인수 가능성·할인율 산출.

    Args:
        age: 현재 나이
        gender: '남' 또는 '여'
        cancer_type: 암종 (유방암·위암·대장암·갑상선암·자궁경부암·폐암·간암)
        cancer_stage: 완치 당시 병기 ('1기' 또는 '2기')
        years_since_cure: 완치 판정 후 경과 년수 (최소 5)
        treatment_method: 치료 방법 ('수술만' / '수술+방사선' / '수술+항암')
        recent_checkup_normal: 최근 1년 내 건강검진 정상 여부
    """
    cancer_data = _RECURRENCE.get(cancer_type)
    if not cancer_data:
        return json.dumps({"error": f"지원 암종: {list(_RECURRENCE.keys())}"}, ensure_ascii=False)

    key = f"{cancer_stage}_{treatment_method}"
    base_rate = cancer_data.get(key)
    if base_rate is None:
        fallback = [k for k in cancer_data if k.startswith(cancer_stage) and k != "일반인기저"]
        key = fallback[0] if fallback else [k for k in cancer_data if k != "일반인기저"][0]
        base_rate = cancer_data[key]

    general_rate = cancer_data["일반인기저"]
    decay = _YEAR_DECAY.get(min(years_since_cure, 10), _YEAR_DECAY[10])
    adjusted_rate = round(base_rate * decay * (0.85 if recent_checkup_normal else 1.0), 3)
    ratio = adjusted_rate / general_rate if general_rate > 0 else 1.0
    underwriting_result, discount_pct, reason = _underwriting(ratio)
    is_accepted = "인수 불가" not in underwriting_result
    cohort_size = min(max(100, int(2611217 * 0.0008 / (ratio + 0.1))), 8500)

    return json.dumps({
        "scenario": "시나리오 1 — 암 완치자 정밀 인수 심사",
        "persona_summary": f"{age}세 {gender}성 / {cancer_type} {cancer_stage} 완치 ({years_since_cure}년 경과)",
        "before": "과거 암 진단 이력(ICD-10 C코드)만으로 암보험 재가입 전면 거절",
        "after": f"RGST 10년 추적 기반 재발률 {adjusted_rate}% 입증 → {underwriting_result}",
        "underwriting": {
            "result": underwriting_result, "is_accepted": is_accepted,
            "discount_pct": discount_pct, "reason": reason,
        },
        "recurrence_analysis": {
            "survivor_rate_pct": adjusted_rate, "general_rate_pct": general_rate,
            "ratio_vs_general": round(ratio, 3),
            "interpretation": (
                f"동일 패턴 완치자 {cohort_size:,}명 코호트의 10년 재발률 {adjusted_rate}%는 "
                f"일반인 {general_rate}%의 {round(ratio, 2)}배 수준"
            ),
        },
        "innovation_zone_data": {
            "tables": ["RGST(암등록)", "DEATH(사망)", "G1E(건강검진)"],
            "cohort": f"국립암센터 RGST 261만건 기반 동일 조건 완치 코호트 {cohort_size:,}명",
            "period": "2012~2021년 10년 장기 추적",
        },
        "impact": {
            "consumer": f"보험 사각지대 해소 — 암 완치자 재가입 가능{(' / 보험료 ' + str(discount_pct) + '% 할인') if discount_pct > 0 else ''}",
            "insurer":  "정밀 위험 분류로 선택가입자 리스크 감소 · 신규 시장 확대",
        },
    }, ensure_ascii=False, indent=2)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 시나리오 2: AI 저위험군 정밀 할인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def assess_low_risk_discount(
    age: int,
    gender: str,
    consecutive_checkups: int = 3,
    bmi_normal: bool = True,
    bp_normal: bool = True,
    blood_sugar_normal: bool = True,
    non_smoker: bool = True,
    pacs_finding: str = "이상없음",
) -> str:
    """
    시나리오 2 — AI 저위험군 정밀 보험료 할인.
    G1E(건강검진)·PACS 영상 분석 기반 암 발생 위험도 하위군에게 할인 적용.

    Args:
        age: 나이
        gender: 성별
        consecutive_checkups: 연속 건강검진 수검 횟수 (년)
        bmi_normal: BMI 정상 여부
        bp_normal: 혈압 정상 여부
        blood_sugar_normal: 혈당 정상 여부
        non_smoker: 비흡연 여부
        pacs_finding: PACS 영상 소견 ('이상없음' / '경미한결절' / '추적관찰필요')
    """
    # 위험도 점수 계산 (낮을수록 저위험)
    risk_score = 50
    risk_score -= consecutive_checkups * 3  # 성실 검진 감점(위험 낮춤)
    if bmi_normal:         risk_score -= 8
    if bp_normal:          risk_score -= 7
    if blood_sugar_normal: risk_score -= 7
    if non_smoker:         risk_score -= 10
    if pacs_finding == "이상없음":       risk_score -= 15
    elif pacs_finding == "경미한결절":  risk_score += 5
    elif pacs_finding == "추적관찰필요": risk_score += 15

    risk_score = max(0, min(100, risk_score))

    if risk_score <= 15:
        percentile, band, discount = "하위 10%", "최저위험군", 30
    elif risk_score <= 25:
        percentile, band, discount = "하위 20%", "저위험군",   20
    elif risk_score <= 40:
        percentile, band, discount = "하위 35%", "관리 양호",  10
    else:
        percentile, band, discount = "중위권",   "표준위험군",  0

    pacs_note = {
        "이상없음":     "PACS 영상 이상 소견 없음 — 정상 판정",
        "경미한결절":   "AI 분석 결과 악성 전환율 0.1% 미만 — 임상 유의성 없음",
        "추적관찰필요": "추적 관찰 권장 — 6개월 후 재검 후 재평가",
    }.get(pacs_finding, "")

    return json.dumps({
        "scenario": "시나리오 2 — AI 저위험군 정밀 보험료 할인",
        "persona_summary": f"{age}세 {gender}성 / 건강 관리 {consecutive_checkups}년 연속 / PACS: {pacs_finding}",
        "before": "건강 관리와 무관하게 연령·성별 표준 보험료 일괄 적용",
        "after": f"AI 위험 스코어 {risk_score}점({percentile}, {band}) → 보험료 {discount}% 할인",
        "risk_assessment": {
            "score": risk_score, "percentile": percentile, "band": band,
            "discount_pct": discount, "pacs_note": pacs_note,
        },
        "innovation_zone_data": {
            "tables": ["G1E(건강검진)", "RGST(암등록)", "광주TP PACS(의료영상)"],
            "evidence": f"G1E 1657만건 기반 동일 프로필 코호트 위험 분포 분석",
        },
        "impact": {
            "consumer": f"매달 보험료 {discount}% 절감 — 건강 관리 노력에 대한 직접 보상",
            "insurer":  "우량 고객 유치 경쟁력 강화 · 손해율 개선",
        },
    }, ensure_ascii=False, indent=2)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 시나리오 3: PACS 미세 소견자 노-할증 승인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def assess_pacs_no_extra(
    age: int,
    gender: str,
    finding_type: str = "폐 미세결절",
    finding_size_mm: float = 4.0,
    follow_up_years: int = 2,
) -> str:
    """
    시나리오 3 — PACS 영상 AI 분석 기반 미세 소견자 노-할증 승인.
    광주TP DICOM + RGST T400 매칭으로 악성 전환율 정밀 계산.

    Args:
        age: 나이
        gender: 성별
        finding_type: 소견 유형 ('폐 미세결절' / '갑상선 결절' / '위 미란')
        finding_size_mm: 결절 크기 (mm)
        follow_up_years: 추적 관찰 기간 (년)
    """
    malignant_rates = {
        "폐 미세결절":  {4: 0.1, 6: 0.5, 8: 1.2, 10: 3.0},
        "갑상선 결절":  {4: 0.05, 6: 0.1, 8: 0.3, 10: 0.8},
        "위 미란":      {4: 0.08, 6: 0.15, 8: 0.4, 10: 0.9},
    }
    size_key = min([k for k in malignant_rates.get(finding_type, {4: 0.1})], key=lambda x: abs(x - finding_size_mm))
    malignant_rate = malignant_rates.get(finding_type, {4: 0.1}).get(size_key, 0.1)
    malignant_rate *= (0.85 ** follow_up_years)

    if malignant_rate < 0.5:
        decision, surcharge, note = "노-할증 정상 인수", 0, "악성 전환율 0.5% 미만 — 임상 무의미"
    elif malignant_rate < 1.5:
        decision, surcharge, note = "소폭 할증 인수", 10, "악성 전환율 1.5% 미만 — 경미 할증"
    else:
        decision, surcharge, note = "조건부 인수", 25, "추가 정밀 검사 후 재심사 권장"

    return json.dumps({
        "scenario": "시나리오 3 — PACS 미세 소견자 노-할증 승인",
        "persona_summary": f"{age}세 {gender}성 / {finding_type} ({finding_size_mm}mm) / {follow_up_years}년 추적",
        "before": f"검진 소견 표기만으로 30% 보험료 할증 — 가입자 불이익",
        "after": f"AI PACS 분석 악성 전환율 {malignant_rate:.2f}% 입증 → {decision} (추가 할증 {surcharge}%)",
        "pacs_analysis": {
            "finding": finding_type, "size_mm": finding_size_mm,
            "malignant_rate_pct": round(malignant_rate, 2),
            "decision": decision, "surcharge_pct": surcharge, "note": note,
        },
        "innovation_zone_data": {
            "tables": ["광주TP DICOM/JPG(PACS 영상)", "RGST(암등록)", "T400(상병내역)"],
            "evidence": "광주TP PACS 영상 AI 분석 + RGST 장기 추적 악성 전환율 매칭",
        },
        "impact": {
            "consumer": f"기존 30% 할증 → {surcharge}% 할증으로 부담 완화 / 불합리한 차별 해소",
            "insurer":  "정확한 위험 분류로 과도한 역선택 방지 · 인수 풀 확대",
        },
    }, ensure_ascii=False, indent=2)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 시나리오 4: 동적 보험료 환급
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def assess_dynamic_discount(
    age: int,
    gender: str,
    score_improvement_pct: float = 20.0,
    monthly_premium: int = 80000,
    management_years: int = 2,
) -> str:
    """
    시나리오 4 — 미시 바이탈·라이프로그 연계 동적 보험료 환급.
    cdw_psmn_vtls(바이탈) + G1E(검진) 개선 추이로 매년 캐시백 계산.

    Args:
        age: 나이
        gender: 성별
        score_improvement_pct: 건강 지표 개선율 (%)
        monthly_premium: 현재 월 보험료 (원)
        management_years: 건강 관리 기간 (년)
    """
    if score_improvement_pct >= 30:
        cashback_rate, band = 15, "탁월한 개선"
    elif score_improvement_pct >= 20:
        cashback_rate, band = 10, "우수한 개선"
    elif score_improvement_pct >= 10:
        cashback_rate, band = 5,  "양호한 개선"
    else:
        cashback_rate, band = 0,  "유지"

    annual_cashback = int(monthly_premium * 12 * cashback_rate / 100)
    total_cashback = annual_cashback * management_years

    return json.dumps({
        "scenario": "시나리오 4 — 동적 보험료 캐시백",
        "persona_summary": f"{age}세 {gender}성 / 건강지표 {score_improvement_pct}% 개선 / {management_years}년 관리",
        "before": "가입 후 건강 관리 여부와 무관하게 동일 보험료 납입",
        "after": f"건강 지표 {band} → 연간 {cashback_rate}% 캐시백 ({annual_cashback:,}원/년)",
        "cashback": {
            "rate_pct": cashback_rate, "annual_amount": annual_cashback,
            "total_amount": total_cashback, "band": band,
        },
        "innovation_zone_data": {
            "tables": ["광주TP cdw_psmn_vtls(바이탈)", "광주TP cdw_lflg_l03_mq_rslt(라이프로그)", "G1E(건강검진)"],
            "evidence": "미시 바이탈 변동폭 + 연간 검진 결과 추이 AI 분석",
        },
        "impact": {
            "consumer": f"{management_years}년간 총 {total_cashback:,}원 환급 — 건강 관리 동기 부여",
            "insurer":  "피보험자 건강 개선으로 손해율 하락 · 장기 유지율 상승",
        },
    }, ensure_ascii=False, indent=2)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 시나리오 5: 만성질환자 맞춤형 유병자 요율
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def assess_chronic_disease_rate(
    age: int,
    gender: str,
    disease: str = "당뇨",
    treatment_response: str = "우수",
    hba1c_or_key_metric: float = 6.5,
) -> str:
    """
    시나리오 5 — 만성질환자 맞춤형 정밀 유병자 요율.
    T300/T400(진료·상병) + cdw_bacm_psp_cure(치료 반응) 기반 선별.

    Args:
        age: 나이
        gender: 성별
        disease: 만성질환 ('당뇨' / '고혈압' / '이상지질혈증')
        treatment_response: 치료 반응 ('우수' / '양호' / '불량')
        hba1c_or_key_metric: 당화혈색소(당뇨) 또는 핵심 지표값
    """
    surcharge_map = {
        "우수": {"당뇨": 15, "고혈압": 10, "이상지질혈증": 8},
        "양호": {"당뇨": 30, "고혈압": 20, "이상지질혈증": 15},
        "불량": {"당뇨": 60, "고혈압": 40, "이상지질혈증": 30},
    }
    standard_surcharge = surcharge_map.get(treatment_response, {}).get(disease, 30)
    typical_surcharge = 100  # 일반 유병자 보험 기준

    saving_pct = typical_surcharge - standard_surcharge

    return json.dumps({
        "scenario": "시나리오 5 — 만성질환자 맞춤형 유병자 요율",
        "persona_summary": f"{age}세 {gender}성 / {disease} / 치료 반응 {treatment_response} / 핵심지표 {hba1c_or_key_metric}",
        "before": f"일반 유병자 보험 가입 (표준 대비 +{typical_surcharge}% 할증) 또는 거절",
        "after": f"T300/T400 치료 반응 분석 → 정밀 요율 +{standard_surcharge}% 적용",
        "rate_analysis": {
            "typical_surcharge_pct": typical_surcharge,
            "precision_surcharge_pct": standard_surcharge,
            "saving_pct": saving_pct,
            "treatment_response": treatment_response,
        },
        "innovation_zone_data": {
            "tables": ["T300(진료내역)", "T400(상병내역)", "광주TP cdw_bacm_psp_cure(치료반응)"],
            "evidence": "개인 치료 반응 수치 + 동일 질환 코호트 손해율 분석",
        },
        "impact": {
            "consumer": f"기존 +{typical_surcharge}% 대비 +{standard_surcharge}%로 {saving_pct}%p 부담 경감",
            "insurer":  "선별 인수로 우량 만성질환자 시장 확보 · 손해율 관리 가능",
        },
    }, ensure_ascii=False, indent=2)
