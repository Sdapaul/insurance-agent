"""건강검진.pdf -> 건강검진_테스트.pdf 가명처리 스크립트
PyMuPDF redact API 사용 -> 텍스트 스트림에서도 원본 완전 제거
"""
import fitz

SRC = "건강검진.pdf"
DST = "건강검진_테스트.pdf"


def redact_rect(page, rect, replacement="", fontsize=8.5):
    """rect 영역의 텍스트를 PDF 스트림에서 완전 삭제 후 replacement 삽입."""
    r = fitz.Rect(rect)
    page.add_redact_annot(r, text=replacement, fontsize=fontsize, fill=(1, 1, 1))


def redact_text(page, search_text, replacement="", fontsize=8.5):
    """search_text 를 찾아 모두 redact. 반환: 처리 건수."""
    rects = page.search_for(search_text)
    for r in rects:
        page.add_redact_annot(r, text=replacement, fontsize=fontsize, fill=(1, 1, 1))
    return len(rects)


doc = fitz.open(SRC)

# ── Page 1 ────────────────────────────────────────────────────
p0 = doc[0]

# 이름 (bbox 직접 지정 — 한글 인코딩으로 search_for 불가)
redact_rect(p0, (125.3, 129.0, 165.0, 141.5), "홍길동")

# 주민등록번호 앞 6자리
redact_text(p0, "780807", "900101")

# 검진일
redact_text(p0, "2026.05.11", "2025.01.15")

p0.apply_redactions()

# ── Page 2 ────────────────────────────────────────────────────
p1 = doc[1]
redact_text(p1, "780807", "900101")
redact_text(p1, "2026.05.11", "2025.01.15")
p1.apply_redactions()

# ── Page 3 ────────────────────────────────────────────────────
p2 = doc[2]

# 발급일 - 각 토큰 개별 처리 (PDF가 연,월,일 단어별로 분리 저장)
redact_text(p2, "2026년07월11일", "2025년02월10일")
# 위가 안 될 경우 개별 처리
for old, new in [("2026년", "2025년"), ("07월", "02월"), ("11일", "10일")]:
    redact_text(p2, old, new)

# 검진 처리 코드
redact_text(p2, "20260521", "20250115")

# 검진 시간 코드
redact_text(p2, "114151", "093000")

# 검진기관명 (bbox 직접 지정)
redact_rect(p2, (262.5, 135.0, 355.0, 148.0), "테스트의원")

# 기관 코드
redact_text(p2, "13300083", "99900001")

p2.apply_redactions()

doc.save(DST, garbage=4, deflate=True)
doc.close()
print(f"저장 완료: {DST}")
