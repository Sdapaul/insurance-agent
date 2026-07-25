"""건강검진.pdf -> 건강검진_테스트.pdf 가명처리 스크립트"""
import fitz

SRC = "건강검진.pdf"
DST = "건강검진_테스트.pdf"

REAL_NAME = "이종재"
FAKE_NAME = "홍길동"

# Windows 맑은 고딕 폰트 (한글 삽입용)
KO_FONT_PATH = "C:/Windows/Fonts/malgun.ttf"


def redact_rect(page, rect, replacement="", fontsize=8.5, ko_font=None):
    r = fitz.Rect(rect)
    page.add_redact_annot(r, fill=(1, 1, 1))
    # apply 후 별도 insert 방식 사용 → 호출자가 처리
    return r


def redact_text_ascii(page, old_text, new_text, fontsize=8.5):
    """ASCII/숫자 텍스트 치환 (내장 폰트로 충분)."""
    rects = page.search_for(old_text)
    for r in rects:
        page.add_redact_annot(r, text=new_text, fontsize=fontsize, fill=(1, 1, 1))
    return len(rects)


def redact_span_and_reinsert(page, span, new_text):
    """span 전체를 지우고 new_text 를 한국어 폰트로 재삽입."""
    bbox = span["bbox"]
    r = fitz.Rect(bbox)
    page.add_redact_annot(r, fill=(1, 1, 1))
    # apply_redactions 후에 삽입해야 하므로 (x0, y1) 좌표와 텍스트를 반환
    return (bbox[0], bbox[3] - 1, new_text, span["size"])


doc = fitz.open(SRC)

# ─────────────────────── Page 1 ───────────────────────────────
p0 = doc[0]

# 1) 숫자/날짜 치환
redact_text_ascii(p0, "780807", "900101")
redact_text_ascii(p0, "2026.05.11", "2025.01.15")

# 2) 이름 포함 span 수집 (헤더 + 본문)
pending_inserts = []  # (x, y, new_text, size)
name_header_done = False

blocks = p0.get_text("dict")["blocks"]
for b in blocks:
    if b.get("type") != 0:
        continue
    for line in b.get("lines", []):
        for span in line.get("spans", []):
            t = span["text"]
            if REAL_NAME not in t:
                continue
            new_t = t.replace(REAL_NAME, FAKE_NAME)
            info = redact_span_and_reinsert(p0, span, new_t)
            pending_inserts.append(info)

p0.apply_redactions()

# 이름 재삽입 (한국어 폰트)
for (x, y, text, size) in pending_inserts:
    p0.insert_text((x, y), text, fontsize=size, fontname="korea", color=(0, 0, 0))

# ─────────────────────── Page 2 ───────────────────────────────
p1 = doc[1]
redact_text_ascii(p1, "780807", "900101")
redact_text_ascii(p1, "2026.05.11", "2025.01.15")
p1.apply_redactions()

# ─────────────────────── Page 3 ───────────────────────────────
p2 = doc[2]
redact_text_ascii(p2, "20260521", "20250115")
redact_text_ascii(p2, "114151", "093000")
redact_text_ascii(p2, "13300083", "99900001")

# 발급일 (숫자 부분만 치환)
for old, new in [("2026", "2025"), ("07", "02"), ("11일", "10일")]:
    redact_text_ascii(p2, old, new)

# 검진기관명 (bbox 직접 지정)
p2.add_redact_annot(fitz.Rect(262.5, 135.0, 355.0, 148.0), fill=(1, 1, 1))

p2.apply_redactions()
p2.insert_text((262.5, 146.0), "테스트의원", fontsize=8.5, fontname="korea", color=(0, 0, 0))

doc.save(DST, garbage=4, deflate=True)
doc.close()
print(f"저장 완료: {DST}")
