"""
API 크레딧 없이 로컬 기능 테스트
- 상품 검색/비교/견적
- RAG 지식 검색 (ChromaDB 또는 키워드)
- FSS 데이터 연동
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()


def separator(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def run_tests():
    # ── 1. 상품 검색 ──────────────────────────────────────────
    separator("TEST 1: 생명보험 검색")
    from tools.product_tools import search_products
    result = search_products(insurance_type="생명보험")
    print(result[:800])

    separator("TEST 2: 덴탈보험 검색 (임플란트 필요)")
    result = search_products(insurance_type="덴탈보험", needs=["임플란트"])
    print(result[:800])

    separator("TEST 3: 암보험 검색")
    result = search_products(insurance_type="실손의료보험", subtype="암보험")
    print(result[:800])

    # ── 2. 상품 비교 ──────────────────────────────────────────
    separator("TEST 4: 덴탈보험 비교 (dental_001 vs dental_002)")
    from tools.product_tools import compare_products
    result = compare_products(["dental_001", "dental_002"])
    print(result[:1000])

    # ── 3. 보험료 견적 ────────────────────────────────────────
    separator("TEST 5: 삼성화재 실손보험 45세 남성 보험료")
    from tools.product_tools import get_premium_estimate
    result = get_premium_estimate("health_001", 45, "남")
    print(result)

    separator("TEST 6: 라이나생명 암보험 40세 여성 보험료")
    result = get_premium_estimate("cancer_001", 40, "여")
    print(result)

    # ── 4. RAG 지식 검색 ──────────────────────────────────────
    separator("TEST 7: RAG - '임플란트 치과보험 대기기간'")
    from tools.rag_tools import retrieve_insurance_knowledge
    result = retrieve_insurance_knowledge("임플란트 치과보험 대기기간", top_k=2)
    print(result[:1000])

    separator("TEST 8: RAG - '암보험 면역항암 보장'")
    result = retrieve_insurance_knowledge("암보험 면역항암치료 보장", top_k=2)
    print(result[:1000])

    separator("TEST 9: RAG - '실손보험 3세대 4세대 차이'")
    result = retrieve_insurance_knowledge("실손보험 3세대 4세대 차이", top_k=2)
    print(result[:800])

    # ── 5. FSS 데이터 ─────────────────────────────────────────
    separator("TEST 10: FSS 실시간 조회 (API 없으면 로컬 fallback)")
    from tools.product_tools import fetch_fss_realtime
    result = fetch_fss_realtime("annuity")
    print(result[:600])

    separator("모든 테스트 완료!")
    print("Claude API 크레딧 충전 후 python main.py 로 전체 챗봇 실행 가능합니다.")


if __name__ == "__main__":
    run_tests()
