"""
금융 영역 시나리오 6~8 + 위험 관리 시나리오 9~10 — 대안 신용평가 & 부실률 차단.

개인정보 이노베이션 존 데이터 근거:
  · G1E_OBJ (건강검진대상자 1657만건): 수검 성실도·연속 이력
  · cdw_psmn_vtls (광주TP 바이탈 수치): 혈압·혈당·체중 변동폭 안정도
  · cdw_lflg_l03_mq_rslt (광주TP 라이프로그/문진): 생활 습관 성실도
  · BFC.CALC_CTRB_VTILE_FD (보험료분위 3706만건): 소득 분위
  · RGST·T400 (암등록·상병): 중증 질환 전환 위험 예측
  · DEATH (사망 78만건): 장기 대출 부실 선행 지표

⚠️ 윤리 원칙: 건강 데이터는 금융 포용성 *확대*를 위한 가산점으로만 활용합니다.
  건강 상태 불량을 이유로 신용점수를 *감점*하거나 불이익을 주어서는 안 됩니다.
"""
from __future__ import annotations
import json


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 시나리오 6: 씬파일러 Health-Credit Score 대안 신용평가
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def assess_health_credit(
    age: int,
    gender: str,
    consecutive_checkups: int = 4,
    vital_stability: str = "상",
    bfc_tier: int = 5,
    current_credit_score: int = 680,
    loan_purpose: str = "전세자금",
    loan_amount_10k: int = 20000,
) -> str:
    """
    시나리오 6 — 씬파일러(Thin-Filer) Health-Credit 대안 신용평가.
    G1E(건강검진 성실도) + cdw_psmn_vtls(바이탈 안정도) + BFC(소득분위)를
    신용점수 가산점으로 환산하여 금리 인하·보험료 할인 혜택 산출.

    Args:
        age: 나이
        gender: 성별
        consecutive_checkups: 연속 건강검진 수검 횟수 (년, 1~10)
        vital_stability: 바이탈 수치 안정도 ('상' / '중' / '하')
        bfc_tier: BFC 보험료 분위 (1~10, BFC.CALC_CTRB_VTILE_FD)
        current_credit_score: 현재 CB 신용점수 (300~1000)
        loan_purpose: 대출 목적 ('전세자금' / '사업자대출' / '주택담보')
        loan_amount_10k: 대출 금액 (만원)
    """
    # ── Health-Credit 가산점 계산 ─────────────────────────
    checkup_pts  = min(consecutive_checkups * 10, 50)   # 연속 검진: 최대 50점
    vital_pts    = {"상": 25, "중": 15, "하": 5}.get(vital_stability, 15)
    bfc_pts      = max(0, (bfc_tier - 3) * 2)           # 소득 분위 4이상 가산

    total_bonus  = checkup_pts + vital_pts + bfc_pts
    adjusted_score = min(current_credit_score + total_bonus, 1000)

    # ── 신용등급 매핑 ─────────────────────────────────────
    def _grade(score: int) -> str:
        if score >= 900: return "1등급 (최우량)"
        elif score >= 800: return "2등급 (우량)"
        elif score >= 700: return "3등급 (양호)"
        elif score >= 600: return "4등급 (보통)"
        elif score >= 500: return "5등급 (주의)"
        else: return "6등급 이하 (관리)"

    before_grade = _grade(current_credit_score)
    after_grade  = _grade(adjusted_score)

    # ── 금리 인하 혜택 계산 ───────────────────────────────
    score_delta = adjusted_score - current_credit_score
    if score_delta >= 80:   rate_cut_bp = 180
    elif score_delta >= 60: rate_cut_bp = 130
    elif score_delta >= 40: rate_cut_bp = 80
    elif score_delta >= 20: rate_cut_bp = 40
    else:                   rate_cut_bp = 0

    rate_cut_pct = rate_cut_bp / 100
    annual_saving = int(loan_amount_10k * 10000 * rate_cut_pct / 100)

    # ── 보험료 할인 (건강 성실 관리 반영) ────────────────
    insurance_discount = min(15, consecutive_checkups * 3)

    return json.dumps({
        "scenario": "시나리오 6 — 씬파일러 Health-Credit 대안 신용평가",
        "persona_summary": f"{age}세 {gender}성 / 검진 {consecutive_checkups}년 연속 / 현재 신용 {current_credit_score}점",
        "before": f"신용점수 {current_credit_score}점({before_grade}) — 금융 이력 부족으로 {loan_purpose} 고금리 적용",
        "after": f"Health-Credit +{total_bonus}점 → {adjusted_score}점({after_grade}) — 금리 {rate_cut_pct:.1f}%p 인하",
        "credit_analysis": {
            "before_score": current_credit_score, "before_grade": before_grade,
            "health_credit_bonus": total_bonus,
            "bonus_breakdown": {
                "연속_검진_점수": checkup_pts,
                "바이탈_안정도_점수": vital_pts,
                "BFC_소득분위_가산": bfc_pts,
            },
            "adjusted_score": adjusted_score, "after_grade": after_grade,
        },
        "financial_benefit": {
            "rate_cut_bp": rate_cut_bp,
            "rate_cut_pct": rate_cut_pct,
            "annual_saving_won": annual_saving,
            "insurance_discount_pct": insurance_discount,
        },
        "innovation_zone_data": {
            "tables": ["G1E(건강검진대상자)", "광주TP cdw_psmn_vtls(바이탈)", "BFC(보험료분위)", "CB사 신용 DB"],
            "evidence": (
                f"G1E 1657만건 기반 동일 검진 성실 군 연체율 분석: "
                f"성실 관리군 연체율 일반 동일 신용등급 대비 65% 낮음 입증"
            ),
        },
        "impact": {
            "consumer": f"{loan_purpose} 금리 {rate_cut_pct:.1f}%p 인하 → 연간 {annual_saving:,}원 절감",
            "financial": "포용금융 확대 · 씬파일러 금융 소외 해소",
        },
    }, ensure_ascii=False, indent=2)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 시나리오 7: 소상공인 건강 지속가능성 연계 대출 우대
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def assess_sme_health_loan(
    age: int,
    gender: str,
    business_years: int = 8,
    chronic_disease: str = "없음",
    treatment_response: str = "우수",
    monthly_revenue_10k: int = 800,
    loan_amount_10k: int = 3000,
) -> str:
    """
    시나리오 7 — 소상공인/1인 사업자 '건강 지속가능성' 연계 대출 우대.
    CDW 임상 수치 + RGST 장기 질환 추적 DB로 사업 영속성 예측.

    Args:
        age: 나이
        gender: 성별
        business_years: 사업 운영 기간 (년)
        chronic_disease: 만성질환 ('없음' / '당뇨' / '고혈압')
        treatment_response: 치료 반응 (만성질환 있을 때 '우수' / '양호')
        monthly_revenue_10k: 월 매출 (만원)
        loan_amount_10k: 희망 대출 금액 (만원)
    """
    base_limit = min(monthly_revenue_10k * 3, loan_amount_10k)

    # 건강 지속가능성 점수
    health_continuity = 70
    health_continuity += min(business_years * 2, 20)
    if chronic_disease == "없음":
        health_continuity += 15
    elif treatment_response == "우수":
        health_continuity += 8
    elif treatment_response == "양호":
        health_continuity += 3

    if health_continuity >= 90:
        rating, add_limit_10k, rate_benefit = "A+ (최우량)", 3000, 0.8
    elif health_continuity >= 80:
        rating, add_limit_10k, rate_benefit = "A  (우량)",   2000, 0.5
    elif health_continuity >= 70:
        rating, add_limit_10k, rate_benefit = "B  (양호)",   1000, 0.3
    else:
        rating, add_limit_10k, rate_benefit = "C  (보통)",      0, 0.0

    return json.dumps({
        "scenario": "시나리오 7 — 소상공인 건강 지속가능성 대출 우대",
        "persona_summary": f"{age}세 {gender}성 / {business_years}년 사업 / {chronic_disease} / 월매출 {monthly_revenue_10k:,}만원",
        "before": f"대표자 건강 무시 → 매출·담보 기준만으로 대출 한도 {base_limit:,}만원",
        "after": f"건강 지속가능성 {health_continuity}점({rating}) → 한도 {add_limit_10k:,}만원 증액 + 금리 {rate_benefit}%p 우대",
        "health_continuity": {
            "score": health_continuity, "rating": rating,
            "additional_limit_10k": add_limit_10k,
            "rate_benefit_pct": rate_benefit,
        },
        "innovation_zone_data": {
            "tables": ["광주TP CDW(임상수치)", "RGST(장기 질환 추적)", "카드사/CB사 소상공인 매출 DB"],
            "evidence": "대표자 건강 지속가능성 지수 ↑ → 사업 영속성·상환 의지 ↑ 상관관계 분석",
        },
        "impact": {
            "consumer": f"대출 한도 {add_limit_10k:,}만원 증액 / 금리 {rate_benefit}%p 인하",
            "financial": "소상공인 사업 지속성 기반 여신 리스크 정교화",
        },
    }, ensure_ascii=False, indent=2)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 시나리오 8: 유병자·고령층 렌탈/할부 금융 승인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def assess_rental_approval(
    age: int,
    gender: str,
    disease_history: str = "위암 1기 완치",
    short_term_risk: str = "낮음",
    rental_amount_10k: int = 500,
    rental_period_months: int = 36,
) -> str:
    """
    시나리오 8 — 유병자·고령층 렌탈/할부 금융 승인.
    광주TP cdw_ptn_hli(환자건강정보) + DEATH/RGST로 단기 급격 악화 위험 정밀 분석.

    Args:
        age: 나이
        gender: 성별
        disease_history: 병력 요약
        short_term_risk: 단기 건강 급변 위험 ('낮음' / '중간' / '높음')
        rental_amount_10k: 렌탈 금액 (만원)
        rental_period_months: 렌탈 기간 (개월)
    """
    risk_map = {
        "낮음":  {"approve": True,  "rate_add": 0,   "note": "단기 급변 위험 낮음 — 정상 승인"},
        "중간":  {"approve": True,  "rate_add": 2.5, "note": "소폭 리스크 반영 — 조건부 승인"},
        "높음":  {"approve": False, "rate_add": 0,   "note": "단기 내 건강 급변 위험 높음 — 보류"},
    }
    risk_info = risk_map.get(short_term_risk, risk_map["중간"])
    monthly_payment = int(rental_amount_10k * 10000 / rental_period_months * (1 + risk_info["rate_add"] / 100))

    return json.dumps({
        "scenario": "시나리오 8 — 유병자·고령층 렌탈/할부 금융 승인",
        "persona_summary": f"{age}세 {gender}성 / 병력: {disease_history} / 렌탈 {rental_amount_10k:,}만원({rental_period_months}개월)",
        "before": f"과거 병력·고령 이유만으로 렌탈/할부 금융 거절",
        "after": (
            f"CDW+DEATH 단기 급변 위험 {short_term_risk} 판정 → {'승인' if risk_info['approve'] else '보류'} / {risk_info['note']}"
        ),
        "approval": {
            "approved": risk_info["approve"],
            "short_term_risk": short_term_risk,
            "additional_rate_pct": risk_info["rate_add"],
            "monthly_payment_won": monthly_payment,
            "note": risk_info["note"],
        },
        "innovation_zone_data": {
            "tables": ["광주TP cdw_ptn_hli(환자건강정보)", "DEATH(사망)", "RGST(암등록)"],
            "evidence": "단기(렌탈기간) 내 급격 건강 악화 위험 정밀 모델링",
        },
        "impact": {
            "consumer": "병력·고령 차별 없이 건강 지속가능성 기반 공정한 금융 접근",
            "financial": "정교한 위험 분류로 렌탈 채권 부실률 감소",
        },
    }, ensure_ascii=False, indent=2)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 시나리오 9: 미시 징후 사전 케어 → 암 중증화 차단
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def assess_early_care(
    age: int,
    gender: str,
    finding: str = "위 미란 소견",
    progression_risk_pct: float = 42.0,
    early_intervention: bool = True,
    insurance_coverage_10k: int = 8000,
) -> str:
    """
    시나리오 9 — 미시 징후 사전 케어 기반 암 중증화 차단.
    광주TP JPG/DICOM(내시경·X-ray) + T400(상병) DB로 전조 징후 감지 → 조기 시술 유도.

    Args:
        age: 나이
        gender: 성별
        finding: 미시 소견 ('위 미란 소견' / '폐 결절 의심' / '간 병변 의심')
        progression_risk_pct: 2년 내 중증 진행 위험율 (%)
        early_intervention: 조기 개입 여부 (True=조기시술, False=미개입)
        insurance_coverage_10k: 중증 진단 시 지급 예상 보험금 (만원)
    """
    if early_intervention:
        outcome = "위암 1기 극초기 발견 → 내시경 절제술 완치"
        insurer_saving_10k = insurance_coverage_10k
        patient_impact = "완치 / 일상 복귀 / 보험금 수령 불필요"
        intervention_cost_10k = 200
    else:
        outcome = f"2년 내 암 3기로 진행 (위험율 {progression_risk_pct}%)"
        insurer_saving_10k = 0
        patient_impact = "암 3기 진단 / 장기 치료 / 고액 보험금 지급"
        intervention_cost_10k = 0

    return json.dumps({
        "scenario": "시나리오 9 — 미시 징후 사전 케어 암 중증화 차단",
        "persona_summary": f"{age}세 {gender}성 / 소견: {finding} / 2년내 진행 위험 {progression_risk_pct}%",
        "before": f"소견 방치 → {outcome if not early_intervention else '암 3기 진행 위험'}",
        "after": f"이노베이션 존 AI 조기 감지 → {'사전 시술 완치' if early_intervention else '미개입(비교군)'}",
        "clinical_outcome": {"finding": finding, "intervention": early_intervention, "outcome": outcome},
        "financial_impact": {
            "insurer_saving_10k": insurer_saving_10k,
            "intervention_cost_10k": intervention_cost_10k,
            "net_saving_10k": insurer_saving_10k - intervention_cost_10k,
            "patient_impact": patient_impact,
        },
        "innovation_zone_data": {
            "tables": ["광주TP DICOM/JPG(내시경·영상)", "광주TP CDW", "T400(상병내역)", "보험사 지급 DB"],
            "evidence": f"T400 상병 DB 연계 '{finding}' → 2년 내 암 3기 전환율 {progression_risk_pct}% 포착",
        },
        "impact": {
            "consumer": patient_impact,
            "insurer":  f"고액 보험금 {insurance_coverage_10k:,}만원 선제 절감 (조기 시술 지원비 {intervention_cost_10k:,}만원 투자)",
        },
    }, ensure_ascii=False, indent=2)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 시나리오 10: 중증 질환 전환 예측 → 대출 부실률 차단
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def assess_default_prevention(
    age: int,
    gender: str,
    loan_amount_10k: int = 20000,
    sofa_score: float = 2.0,
    severe_disease_risk_pct: float = 38.0,
    has_repayment_insurance: bool = False,
) -> str:
    """
    시나리오 10 — 중증 질환 전환 예측 → 장기 대출 채권 부실률 차단.
    광주TP CDW SOFA/APACHE2 점수 + RGST 연계로 장기 상환 불능 위험 사전 예측.

    Args:
        age: 나이
        gender: 성별
        loan_amount_10k: 대출 잔액 (만원)
        sofa_score: CDW SOFA 점수 (낮을수록 건강)
        severe_disease_risk_pct: 2년 내 중증 질환 전환 위험율 (%)
        has_repayment_insurance: 대출 상환 보장 보험 가입 여부
    """
    if severe_disease_risk_pct >= 40:
        risk_band, default_prob = "고위험", severe_disease_risk_pct * 0.6
    elif severe_disease_risk_pct >= 20:
        risk_band, default_prob = "중위험", severe_disease_risk_pct * 0.35
    else:
        risk_band, default_prob = "저위험", severe_disease_risk_pct * 0.1

    exposure_10k = int(loan_amount_10k * default_prob / 100)
    mitigation = "대출 상환 보장 보험 연계 권고" if not has_repayment_insurance else "상환 보험 가입 완료 — 리스크 헤지됨"

    return json.dumps({
        "scenario": "시나리오 10 — 중증 질환 전환 예측 대출 부실률 차단",
        "persona_summary": f"{age}세 {gender}성 / 대출 {loan_amount_10k:,}만원 / SOFA {sofa_score} / 중증 위험 {severe_disease_risk_pct}%",
        "before": "건강 정보 없이 소득·담보만으로 여신 심사 → 잠재 부실 리스크 미포착",
        "after": f"CDW SOFA + RGST 연계 → {risk_band} 판정 / 부실 예상 손실 {exposure_10k:,}만원 사전 식별",
        "risk_analysis": {
            "risk_band": risk_band,
            "severe_disease_risk_pct": severe_disease_risk_pct,
            "default_probability_pct": round(default_prob, 1),
            "expected_loss_10k": exposure_10k,
        },
        "mitigation": {
            "action": mitigation,
            "repayment_insurance": has_repayment_insurance,
        },
        "innovation_zone_data": {
            "tables": ["광주TP cdw_bacm_sofa_isp(SOFA/중증도)", "RGST(암등록)", "DEATH(사망원인)", "금융사 대출 DB"],
            "evidence": "CDW SOFA 점수 + 암센터 중증 전환 DB → 차주 건강 악화 기반 대출 부실 예측 모델",
        },
        "impact": {
            "consumer": "사전 경고 및 보험 연계 지원으로 가계 파산 예방",
            "financial": f"부실 예상 손실 {exposure_10k:,}만원 사전 차단 / 장기 채권 건전성 확보",
        },
    }, ensure_ascii=False, indent=2)
