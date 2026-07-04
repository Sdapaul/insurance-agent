"""
보험 상담 챗봇 웹 인터페이스
- API 크레딧 있을 때: Claude 오케스트레이터 사용 (Live Mode)
- 크레딧 없을 때: 로컬 도구 + 스마트 응답 (Mock Mode)

실행: python web_app.py
접속: http://localhost:5000
"""

import sys
import os
import re
import json
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, jsonify, render_template_string, Response, stream_with_context

app = Flask(__name__)

# ── 세션 저장소 ───────────────────────────────────────────
sessions = {}  # session_id -> {chatbot, context, mode}


# ── Mock 컨텍스트 ──────────────────────────────────────────
class MockContext:
    def __init__(self):
        self.age = None
        self.gender = "남"
        self.budget = None
        self.last_products = []
        self.last_type = None


def extract_info(text, ctx):
    m = re.search(r'(\d{2,3})\s*세', text)
    if m:
        ctx.age = int(m.group(1))
    else:
        m = re.search(r'(\d+)0\s*대', text)
        if m:
            ctx.age = int(m.group(1)) * 10 + 5

    if any(k in text for k in ['남성', '남자', '남 ', '아빠', '아버지']):
        ctx.gender = '남'
    elif any(k in text for k in ['여성', '여자', '여 ', '엄마', '어머니']):
        ctx.gender = '여'

    m = re.search(r'(\d+)\s*만\s*원', text)
    if m:
        ctx.budget = int(m.group(1)) * 10000


def detect_intent(text, ctx):
    if '비교' in text and ctx.last_products:
        return 'compare'
    if any(k in text for k in ['암보험', '암 보험', '암진단', '면역항암', '항암']):
        return 'cancer'
    if any(k in text for k in ['블록체인', 'blockchain']) and any(k in text for k in ['덴탈', '치과', '임플란트', '치아', '보험']):
        return 'dental_blockchain'
    if any(k in text for k in ['덴탈', '치과', '임플란트', '스케일링', '충치', '잇몸', '치아']):
        return 'dental'
    if any(k in text for k in ['실손', '실비', '의료비', '병원비', '의료보험']):
        return 'health'
    if any(k in text for k in ['생명보험', '종신보험', '정기보험', '사망보험', '사망보장']):
        return 'life'
    if any(k in text for k in ['추천', '포트폴리오', '어떤 보험', '뭐가 좋', '어디가 좋']):
        return 'recommend'
    if any(k in text for k in ['보험료', '얼마', '가격', '월납']):
        return 'premium'
    if any(k in text for k in ['안녕', '처음', '시작']):
        return 'greeting'
    return 'knowledge'


def mock_response(message, ctx):
    from tools.product_tools import search_products, compare_products, get_premium_estimate
    from tools.rag_tools import retrieve_insurance_knowledge

    extract_info(message, ctx)
    intent = detect_intent(message, ctx)
    age = ctx.age or 40
    gender = ctx.gender or '남'

    # ── 인사 ──────────────────────────────────────────────
    if intent == 'greeting':
        return (
            "안녕하세요! **보험 상담 AI 어시스턴트**입니다.\n\n"
            "생명보험, 실손의료보험, 암보험, 덴탈(치과)보험 상담을 도와드립니다.\n\n"
            "나이, 성별, 예산을 알려주시면 더 정확한 추천이 가능해요!\n\n"
            "> 예시: *\"45세 남성, 월 20만원 예산으로 암보험 추천해줘\"*"
        )

    # ── 암보험 ────────────────────────────────────────────
    elif intent == 'cancer':
        raw = json.loads(search_products(insurance_type='실손의료보험', subtype='암보험', age=age))
        results = raw.get('results', [])
        ctx.last_products = [r['id'] for r in results[:3]]
        ctx.last_type = '암보험'

        lines = [f"## 암보험 추천 ({age}세 {gender}성 기준)\n"]
        for i, p in enumerate(results[:3], 1):
            try:
                pr = json.loads(get_premium_estimate(p['id'], age, gender))
                pstr = pr.get('premium_formatted', f"{p['monthly_premium_reference']:,}원/월")
            except Exception:
                pstr = f"{p['monthly_premium_reference']:,}원/월"

            lines += [
                f"### {i}. {p['name']}",
                f"| 항목 | 내용 |",
                f"|------|------|",
                f"| 회사 | {p['company']} |",
                f"| 월 보험료 | **{pstr}** |",
                f"| 주요 보장 | {', '.join(p.get('key_coverage', [])[:3])} |",
                f"| 특징 | {p.get('key_features', ['-'])[0]} |",
                f"| 장점 | {p.get('pros', ['-'])[0]} |",
                "",
            ]
        lines.append("> 💡 **체크포인트**: 면책기간 90일 / 비갱신형은 보험료 고정 / 진단금 2,000만원 이상 권장")
        lines.append("\n\"두 상품 비교해줘\" 또는 특정 상품 보험료 문의도 가능합니다!")
        return '\n'.join(lines)

    # ── 블록체인 덴탈보험 ─────────────────────────────────
    elif intent == 'dental_blockchain':
        raw = json.loads(search_products(insurance_type='덴탈보험', needs=['블록체인'], age=age))
        results = raw.get('results', [])
        # 라이나생명(dental_005) 1순위 보장
        lina = [r for r in results if r['id'] == 'dental_005']
        others = [r for r in results if r['id'] != 'dental_005']
        results = lina + others
        if not lina:
            # 전체 검색에서라도 가져오기
            all_raw = json.loads(search_products(insurance_type='덴탈보험'))
            all_results = all_raw.get('results', [])
            lina = [r for r in all_results if r['id'] == 'dental_005']
            results = lina + [r for r in results if r['id'] != 'dental_005']
        ctx.last_products = [r['id'] for r in results[:3]]
        ctx.last_type = '덴탈보험'

        lines = [
            f"## 블록체인 덴탈(치과)보험 추천 ({age}세 {gender}성 기준)\n",
            "> 블록체인 기반 보험은 **라이나생명 블록체인치아보험 스마트**를 강력 추천드립니다!\n",
        ]
        for i, p in enumerate(results[:3], 1):
            try:
                pr = json.loads(get_premium_estimate(p['id'], age, gender))
                pstr = pr.get('premium_formatted', f"{p['monthly_premium_reference']:,}원/월")
            except Exception:
                pstr = f"{p['monthly_premium_reference']:,}원/월"

            badge = " ⭐ **블록체인 추천**" if p['id'] == 'dental_005' else ""
            lines += [
                f"### {i}. {p['name']}{badge}",
                f"| 항목 | 내용 |",
                f"|------|------|",
                f"| 회사 | {p['company']} |",
                f"| 월 보험료 | **{pstr}** |",
                f"| 주요 보장 | {', '.join(p.get('key_coverage', [])[:3])} |",
                f"| 특징 | {p.get('key_features', ['-'])[0]} |",
                "",
            ]
        lines.append("> 💡 **블록체인 장점**: 스마트 계약 자동 청구 / 서류 불필요 / 보험금 이력 투명 공개")
        lines.append("> ⚠️ **필수 확인**: 임플란트 대기기간 **180일** — 가입 즉시 보장 안 됩니다!")
        return '\n'.join(lines)

    # ── 덴탈보험 ──────────────────────────────────────────
    elif intent == 'dental':
        needs = []
        if '임플란트' in message:
            needs.append('임플란트')
        raw = json.loads(search_products(insurance_type='덴탈보험', needs=needs or None, age=age))
        results = raw.get('results', [])
        ctx.last_products = [r['id'] for r in results[:3]]
        ctx.last_type = '덴탈보험'

        lines = [f"## 덴탈(치과)보험 추천 ({age}세 {gender}성 기준)\n"]
        for i, p in enumerate(results[:3], 1):
            try:
                pr = json.loads(get_premium_estimate(p['id'], age, gender))
                pstr = pr.get('premium_formatted', f"{p['monthly_premium_reference']:,}원/월")
            except Exception:
                pstr = f"{p['monthly_premium_reference']:,}원/월"

            lines += [
                f"### {i}. {p['name']}",
                f"| 항목 | 내용 |",
                f"|------|------|",
                f"| 회사 | {p['company']} |",
                f"| 월 보험료 | **{pstr}** |",
                f"| 주요 보장 | {', '.join(p.get('key_coverage', [])[:3])} |",
                f"| 특징 | {p.get('key_features', ['-'])[0]} |",
                "",
            ]
        lines.append("> 💡 **필수 확인**: 임플란트 대기기간 **180일** / 충치치료 **90일** — 가입 즉시 보장 안 됩니다!")
        return '\n'.join(lines)

    # ── 실손보험 ──────────────────────────────────────────
    elif intent == 'health':
        raw = json.loads(search_products(insurance_type='실손의료보험', age=age))
        results = [r for r in raw.get('results', []) if r.get('subtype') != '암보험'][:3]
        ctx.last_products = [r['id'] for r in results]
        ctx.last_type = '실손의료보험'

        lines = [f"## 실손의료보험 추천 ({age}세 {gender}성 기준)\n"]
        for i, p in enumerate(results, 1):
            try:
                pr = json.loads(get_premium_estimate(p['id'], age, gender))
                pstr = pr.get('premium_formatted', f"{p['monthly_premium_reference']:,}원/월")
            except Exception:
                pstr = f"{p['monthly_premium_reference']:,}원/월"

            lines += [
                f"### {i}. {p['name']}",
                f"| 항목 | 내용 |",
                f"|------|------|",
                f"| 회사 | {p['company']} |",
                f"| 유형 | {p.get('subtype', '-')} |",
                f"| 월 보험료 | **{pstr}** |",
                f"| 장점 | {p.get('pros', ['-'])[0]} |",
                f"| 단점 | {p.get('cons', ['-'])[0]} |",
                "",
            ]
        lines.append("> 💡 신규 가입은 **4세대 실손**만 가능합니다. 비급여 본인부담 30% 적용.")
        return '\n'.join(lines)

    # ── 생명보험 ──────────────────────────────────────────
    elif intent == 'life':
        raw = json.loads(search_products(insurance_type='생명보험', age=age))
        results = raw.get('results', [])[:3]
        ctx.last_products = [r['id'] for r in results]
        ctx.last_type = '생명보험'

        lines = [f"## 생명보험 추천 ({age}세 {gender}성 기준)\n"]
        for i, p in enumerate(results, 1):
            try:
                pr = json.loads(get_premium_estimate(p['id'], age, gender))
                pstr = pr.get('premium_formatted', f"{p['monthly_premium_reference']:,}원/월")
            except Exception:
                pstr = f"{p['monthly_premium_reference']:,}원/월"

            cov_amount = p.get('coverage_amount', 0)
            lines += [
                f"### {i}. {p['name']}",
                f"| 항목 | 내용 |",
                f"|------|------|",
                f"| 회사 | {p['company']} |",
                f"| 유형 | {p.get('subtype', '-')} |",
                f"| 보장금액 | {cov_amount // 10000:,}만원 |" if cov_amount else f"| 특징 | {p.get('key_features', ['-'])[0]} |",
                f"| 월 보험료 | **{pstr}** |",
                f"| 장점 | {p.get('pros', ['-'])[0]} |",
                "",
            ]
        lines.append("> 💡 부양가족 있다면 **종신보험** / 일정 기간만 보장 원하면 **정기보험**이 유리합니다.")
        return '\n'.join(lines)

    # ── 비교 ──────────────────────────────────────────────
    elif intent == 'compare' and ctx.last_products:
        ids = ctx.last_products[:2]
        raw = json.loads(compare_products(ids))
        products = raw.get('products', [])
        if len(products) < 2:
            return "비교할 상품이 부족합니다. 먼저 상품을 검색해 주세요."

        p0, p1 = products[0], products[1]
        pm0 = p0.get('monthly_premiums', {})
        pm1 = p1.get('monthly_premiums', {})
        v0 = next((v for k, v in pm0.items() if gender in k), next(iter(pm0.values()), 0))
        v1 = next((v for k, v in pm1.items() if gender in k), next(iter(pm1.values()), 0))

        lines = [f"## {p0['name']} vs {p1['name']}\n"]
        lines += [
            f"| 구분 | {p0['company']} | {p1['company']} |",
            f"|------|------|------|",
            f"| 월 보험료 | **{v0:,}원** | **{v1:,}원** |",
        ]

        cov0 = p0.get('coverage', {})
        cov1 = p1.get('coverage', {})
        all_keys = list(dict.fromkeys(list(cov0.keys())[:3] + list(cov1.keys())[:3]))
        for ck in all_keys[:4]:
            c0 = str(cov0.get(ck, '-'))[:25]
            c1 = str(cov1.get(ck, '-'))[:25]
            lines.append(f"| {ck} | {c0} | {c1} |")

        pros0 = ', '.join(p0.get('pros', ['-'])[:2])
        pros1 = ', '.join(p1.get('pros', ['-'])[:2])
        lines.append(f"| 장점 | {pros0} | {pros1} |")
        cons0 = p0.get('cons', ['-'])[0]
        cons1 = p1.get('cons', ['-'])[0]
        lines.append(f"| 단점 | {cons0} | {cons1} |")
        lines.append("")

        cheaper = p0['name'] if v0 <= v1 else p1['name']
        lines.append(f"**결론**: 보험료 절약 → **{cheaper}** / 보장 범위는 세부 특약 비교 후 결정 권장")
        return '\n'.join(lines)

    # ── 포트폴리오 추천 ────────────────────────────────────
    elif intent == 'recommend':
        budget_str = f"월 {ctx.budget // 10000:,}만원" if ctx.budget else "예산 미정"
        lines = [f"## {age}세 {gender}성 맞춤 보험 포트폴리오\n",
                 f"**기준**: {age}세 / {gender}성 / {budget_str}\n"]

        cats = [
            ('실손의료보험', None),
            ('실손의료보험', '암보험'),
            ('덴탈보험', None),
        ]
        total = 0
        for i, (ins_type, subtype) in enumerate(cats, 1):
            kwargs = {'insurance_type': ins_type, 'age': age}
            if subtype:
                kwargs['subtype'] = subtype
            raw = json.loads(search_products(**kwargs))
            results = raw.get('results', [])
            if not results:
                continue
            p = results[0]
            label = subtype or ins_type
            try:
                pr = json.loads(get_premium_estimate(p['id'], age, gender))
                prem = pr.get('estimated_monthly_premium', p['monthly_premium_reference'])
                pstr = pr.get('premium_formatted', f"{prem:,}원/월")
            except Exception:
                prem = p['monthly_premium_reference']
                pstr = f"{prem:,}원/월"
            total += prem
            lines += [
                f"### {i}순위 · {label}",
                f"**{p['name']}** ({p['company']})",
                f"- 월 보험료: **{pstr}**",
                f"- 주요 보장: {', '.join(p.get('key_coverage', [])[:3])}",
                f"- 추천 이유: {p.get('pros', ['기본 보장 충실'])[0]}",
                "",
            ]

        lines += [
            "---",
            f"**예상 총 월 보험료: {total:,}원**\n",
            "> 실제 보험료는 건강상태, 직업, 특약 구성에 따라 달라질 수 있습니다.",
        ]
        return '\n'.join(lines)

    # ── 보험료 조회 ────────────────────────────────────────
    elif intent == 'premium':
        if not ctx.last_products:
            return "어떤 상품의 보험료를 알고 싶으신가요?\n먼저 상품을 검색해 주세요.\n예) *\"실손보험 추천해줘\"*"

        lines = [f"## 보험료 조회 ({age}세 / {gender}성)\n"]
        for pid in ctx.last_products[:3]:
            try:
                pr = json.loads(get_premium_estimate(pid, age, gender))
                lines += [
                    f"**{pr['product_name']}** ({pr['company']})",
                    f"- 월 보험료: **{pr['premium_formatted']}**",
                    f"- 연간 보험료: {pr['annual_premium']}",
                    f"- 참고: {pr.get('note', '')}",
                    "",
                ]
            except Exception:
                pass
        return '\n'.join(lines)

    # ── 지식 검색 (RAG) ────────────────────────────────────
    else:
        raw = json.loads(retrieve_insurance_knowledge(message, top_k=2))
        results = raw.get('results', [])
        if not results:
            return (
                "죄송합니다, 관련 정보를 찾지 못했습니다.\n\n"
                "다음과 같이 질문해 보세요:\n"
                "- \"암보험 추천해줘\"\n"
                "- \"임플란트 치과보험 대기기간\"\n"
                "- \"실손보험 3세대 4세대 차이\"\n"
                "- \"40대 남성 보험 포트폴리오 추천\""
            )

        lines = []
        for r in results:
            lines.append(f"## {r['title']}\n")
            content = r['content']
            if len(content) > 700:
                content = content[:700] + "..."
            lines.append(content)
            lines.append("")
        score = results[0].get('relevance_score')
        if score:
            lines.append(f"\n*관련도: {score:.0%}*")
        return '\n'.join(lines)


# ── HTML 템플릿 ───────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>보험 상담 AI</title>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', sans-serif; background: #f0f4f8; height: 100vh; display: flex; flex-direction: column; }

  /* Header */
  .header {
    background: linear-gradient(135deg, #1d4ed8, #2563eb);
    color: white;
    padding: 14px 20px;
    display: flex;
    align-items: center;
    gap: 12px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.2);
  }
  .header-icon { font-size: 28px; }
  .header-title { font-size: 18px; font-weight: 700; }
  .header-sub { font-size: 12px; opacity: 0.85; margin-top: 2px; }
  .mode-selector {
    margin-left: auto;
    position: relative;
  }
  .mode-badge {
    background: rgba(255,255,255,0.2);
    border: 1px solid rgba(255,255,255,0.4);
    border-radius: 20px;
    padding: 4px 12px;
    font-size: 11px;
    font-weight: 600;
    cursor: pointer;
    user-select: none;
    white-space: nowrap;
  }
  .mode-badge:hover { background: rgba(255,255,255,0.3); }
  .mode-badge.live { background: rgba(34,197,94,0.3); border-color: rgba(34,197,94,0.6); }
  .mode-badge.mock { background: rgba(251,191,36,0.3); border-color: rgba(251,191,36,0.6); }
  .mode-dropdown {
    display: none;
    position: absolute;
    right: 0;
    top: calc(100% + 6px);
    background: white;
    border-radius: 10px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.2);
    overflow: hidden;
    z-index: 100;
    min-width: 150px;
  }
  .mode-dropdown.open { display: block; }
  .mode-option {
    padding: 10px 16px;
    font-size: 13px;
    color: #1e293b;
    cursor: pointer;
    white-space: nowrap;
  }
  .mode-option:hover { background: #f1f5f9; }

  /* Chat area */
  #chat {
    flex: 1;
    overflow-y: auto;
    padding: 20px 16px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  /* Message bubbles */
  .msg { display: flex; gap: 10px; max-width: 85%; }
  .msg.user { margin-left: auto; flex-direction: row-reverse; }
  .msg.bot { margin-right: auto; }

  .avatar {
    width: 36px; height: 36px;
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 16px; flex-shrink: 0;
  }
  .msg.user .avatar { background: #2563eb; color: white; }
  .msg.bot .avatar { background: #e2e8f0; }

  .bubble {
    padding: 12px 16px;
    border-radius: 16px;
    line-height: 1.6;
    font-size: 14px;
    max-width: 100%;
    word-break: break-word;
  }
  .msg.user .bubble {
    background: #2563eb;
    color: white;
    border-bottom-right-radius: 4px;
  }
  .msg.bot .bubble {
    background: white;
    color: #1e293b;
    border-bottom-left-radius: 4px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.1);
  }

  /* Markdown styles inside bot bubble */
  .bubble h2 { font-size: 15px; color: #1d4ed8; margin: 0 0 10px; padding-bottom: 6px; border-bottom: 2px solid #dbeafe; }
  .bubble h3 { font-size: 14px; color: #374151; margin: 12px 0 6px; }
  .bubble table { width: 100%; border-collapse: collapse; margin: 8px 0; font-size: 13px; }
  .bubble th, .bubble td { border: 1px solid #e2e8f0; padding: 6px 10px; text-align: left; }
  .bubble th { background: #f1f5f9; font-weight: 600; }
  .bubble tr:nth-child(even) td { background: #f8fafc; }
  .bubble strong { color: #1d4ed8; }
  .bubble ul, .bubble ol { padding-left: 18px; margin: 6px 0; }
  .bubble li { margin: 3px 0; }
  .bubble blockquote { border-left: 3px solid #2563eb; padding-left: 10px; color: #64748b; margin: 8px 0; font-size: 13px; }
  .bubble em { color: #64748b; font-style: normal; }
  .bubble p { margin: 6px 0; }
  .bubble code { background: #f1f5f9; padding: 2px 5px; border-radius: 4px; font-size: 12px; }

  /* Typing indicator */
  .typing { display: flex; gap: 5px; align-items: center; padding: 12px 16px; }
  .typing span {
    width: 8px; height: 8px; background: #94a3b8;
    border-radius: 50%; animation: bounce 1.2s infinite;
  }
  .typing span:nth-child(2) { animation-delay: 0.2s; }
  .typing span:nth-child(3) { animation-delay: 0.4s; }
  @keyframes bounce {
    0%, 60%, 100% { transform: translateY(0); }
    30% { transform: translateY(-6px); }
  }

  /* Quick buttons */
  .quick-buttons {
    display: flex; gap: 8px; flex-wrap: wrap; padding: 0 16px 12px;
  }
  .qbtn {
    background: white; border: 1px solid #d1d5db;
    border-radius: 20px; padding: 6px 14px;
    font-size: 12px; cursor: pointer; color: #374151;
    transition: all 0.2s;
  }
  .qbtn:hover { background: #dbeafe; border-color: #2563eb; color: #1d4ed8; }

  /* Input area */
  .input-area {
    background: white;
    padding: 12px 16px;
    border-top: 1px solid #e2e8f0;
    display: flex;
    gap: 10px;
    align-items: flex-end;
  }
  #input {
    flex: 1;
    border: 1px solid #d1d5db;
    border-radius: 24px;
    padding: 10px 16px;
    font-size: 14px;
    outline: none;
    resize: none;
    max-height: 120px;
    min-height: 42px;
    line-height: 1.5;
    font-family: inherit;
    transition: border-color 0.2s;
  }
  #input:focus { border-color: #2563eb; }
  #send {
    background: #2563eb; color: white;
    border: none; border-radius: 50%;
    width: 42px; height: 42px;
    cursor: pointer; font-size: 18px;
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0;
    transition: background 0.2s;
  }
  #send:hover { background: #1d4ed8; }
  #send:disabled { background: #94a3b8; cursor: not-allowed; }

  .reset-btn {
    background: none; border: none; color: #94a3b8;
    cursor: pointer; font-size: 20px; padding: 4px;
    flex-shrink: 0;
  }
  .reset-btn:hover { color: #ef4444; }

  /* Streaming tool status */
  .tool-status {
    display: none;
    font-size: 12px;
    color: #2563eb;
    background: #dbeafe;
    border-radius: 12px;
    padding: 4px 10px;
    margin-bottom: 6px;
    width: fit-content;
    animation: pulse 1.5s infinite;
  }
  @keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:0.5; } }

  /* Streaming cursor blink */
  .stream-cursor {
    display: inline-block;
    width: 2px;
    height: 14px;
    background: #2563eb;
    margin-left: 2px;
    vertical-align: middle;
    animation: blink 0.8s step-end infinite;
  }
  @keyframes blink { 0%,100% { opacity:1; } 50% { opacity:0; } }

  /* ── Tab Navigation ── */
  .tab-nav {
    display: flex;
    background: #1e40af;
    padding: 0 16px;
    gap: 4px;
  }
  .tab-btn {
    padding: 10px 18px;
    font-size: 13px;
    font-weight: 600;
    color: rgba(255,255,255,0.65);
    border: none;
    background: transparent;
    cursor: pointer;
    border-bottom: 3px solid transparent;
    transition: all 0.2s;
    white-space: nowrap;
  }
  .tab-btn:hover { color: white; }
  .tab-btn.active { color: white; border-bottom-color: #60a5fa; }
  .tab-panel { display: none; flex: 1; overflow: hidden; flex-direction: column; }
  .tab-panel.active { display: flex; }

  /* ── Credit Portfolio Panel ── */
  .credit-panel {
    flex: 1;
    overflow-y: auto;
    padding: 20px;
    background: #f0f4f8;
  }
  .credit-guide {
    background: white;
    border-radius: 12px;
    padding: 18px 20px;
    margin-bottom: 16px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08);
  }
  .credit-guide h3 { font-size: 14px; color: #1e40af; margin-bottom: 10px; }
  .score-sources {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    margin-top: 8px;
  }
  .score-source-card {
    flex: 1;
    min-width: 140px;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 12px 14px;
    background: #f8fafc;
    cursor: pointer;
    transition: all 0.15s;
  }
  .score-source-card:hover { border-color: #3b82f6; background: #eff6ff; }
  .score-source-card .source-logo { font-size: 22px; margin-bottom: 4px; }
  .score-source-card .source-name { font-size: 13px; font-weight: 700; color: #1e293b; }
  .score-source-card .source-desc { font-size: 11px; color: #64748b; margin-top: 3px; }
  .score-source-card .source-link {
    font-size: 11px; color: #2563eb; margin-top: 6px;
    text-decoration: none; display: inline-block;
  }
  .credit-form {
    background: white;
    border-radius: 12px;
    padding: 20px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08);
    margin-bottom: 16px;
  }
  .credit-form h3 { font-size: 14px; color: #1e293b; font-weight: 700; margin-bottom: 14px; }
  .form-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
  }
  .form-group { display: flex; flex-direction: column; gap: 5px; }
  .form-group.full { grid-column: 1 / -1; }
  .form-group label { font-size: 12px; font-weight: 600; color: #475569; }
  .form-group input, .form-group select {
    padding: 9px 12px;
    border: 1.5px solid #e2e8f0;
    border-radius: 8px;
    font-size: 13px;
    outline: none;
    transition: border-color 0.15s;
    background: white;
  }
  .form-group input:focus, .form-group select:focus { border-color: #3b82f6; }
  .score-input-wrap { position: relative; }
  .score-input-wrap input { padding-right: 40px; width: 100%; }
  .score-badge {
    position: absolute; right: 10px; top: 50%; transform: translateY(-50%);
    font-size: 10px; font-weight: 700; padding: 2px 6px; border-radius: 10px;
  }
  .score-badge.tier1 { background: #dcfce7; color: #16a34a; }
  .score-badge.tier2 { background: #dbeafe; color: #1d4ed8; }
  .score-badge.tier3 { background: #fef3c7; color: #d97706; }
  .score-badge.tier4 { background: #fee2e2; color: #dc2626; }
  .score-badge.tier5 { background: #f1f5f9; color: #64748b; }
  .score-avg-note { font-size: 11px; color: #64748b; margin-top: 4px; }
  .gen-btn {
    width: 100%;
    margin-top: 16px;
    padding: 13px;
    background: linear-gradient(135deg, #2563eb, #1d4ed8);
    color: white;
    border: none;
    border-radius: 10px;
    font-size: 14px;
    font-weight: 700;
    cursor: pointer;
    transition: opacity 0.2s;
  }
  .gen-btn:hover { opacity: 0.92; }
  .gen-btn:disabled { opacity: 0.55; cursor: not-allowed; }
  .credit-result {
    background: white;
    border-radius: 12px;
    padding: 20px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08);
  }
  .credit-result-header {
    display: flex; align-items: center; gap: 10px;
    padding-bottom: 12px;
    border-bottom: 1px solid #f1f5f9;
    margin-bottom: 14px;
  }
  .credit-result-header .score-pill {
    background: #eff6ff; border: 1.5px solid #bfdbfe;
    color: #1d4ed8; font-weight: 700; font-size: 13px;
    padding: 4px 12px; border-radius: 20px;
  }
  .credit-result-body { line-height: 1.7; font-size: 13.5px; color: #1e293b; }
  .credit-result-body table { width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 12.5px; }
  .credit-result-body th { background: #f8fafc; padding: 7px 10px; border: 1px solid #e2e8f0; text-align: left; font-weight: 600; }
  .credit-result-body td { padding: 7px 10px; border: 1px solid #e2e8f0; }
  .credit-result-body h3 { font-size: 14px; margin: 14px 0 6px; color: #1e40af; }
  .credit-result-body h4 { font-size: 13px; margin: 10px 0 5px; color: #374151; }
  .credit-result-body ul, .credit-result-body ol { padding-left: 18px; margin: 5px 0; }
  .credit-result-body blockquote { border-left: 3px solid #3b82f6; padding-left: 12px; color: #475569; margin: 8px 0; }
  .credit-loading {
    display: flex; align-items: center; gap: 10px;
    padding: 30px; justify-content: center; color: #64748b; font-size: 14px;
  }
  .credit-loading .spin {
    width: 22px; height: 22px; border: 3px solid #e2e8f0;
    border-top-color: #3b82f6; border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .extra-section {
    border: 1.5px dashed #e2e8f0;
    border-radius: 10px;
    margin-top: 16px;
    overflow: hidden;
  }
  .extra-section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 11px 14px;
    background: #f8fafc;
    cursor: pointer;
    user-select: none;
    font-size: 13px;
    font-weight: 600;
    color: #374151;
  }
  .extra-section-header:hover { background: #f1f5f9; }
  .extra-section-toggle { transition: transform 0.2s; font-size: 12px; color: #94a3b8; }
  .extra-section-toggle.open { transform: rotate(180deg); }
  .extra-section-body {
    padding: 14px;
    display: none;
    border-top: 1.5px dashed #e2e8f0;
  }
  .extra-section-body.open { display: block; }
  .financial-summary {
    background: #f0f9ff;
    border: 1px solid #bae6fd;
    border-radius: 8px;
    padding: 10px 14px;
    margin-top: 12px;
    font-size: 12px;
    color: #0c4a6e;
    display: none;
  }
  .financial-summary.visible { display: block; }
  .financial-summary-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 3px 0;
    border-bottom: 1px solid #e0f2fe;
  }
  .financial-summary-row:last-child { border-bottom: none; }
  .risk-badge {
    display: inline-block;
    padding: 1px 7px;
    border-radius: 10px;
    font-size: 10px;
    font-weight: 700;
  }
  .risk-low  { background: #dcfce7; color: #16a34a; }
  .risk-med  { background: #fef3c7; color: #d97706; }
  .risk-high { background: #fee2e2; color: #dc2626; }
  /* 종합 적합도 점수 카드 */
  .composite-score-card {
    background: linear-gradient(135deg, #1e40af 0%, #1d4ed8 100%);
    border-radius: 12px;
    padding: 18px 20px;
    color: white;
    margin-bottom: 16px;
  }
  .composite-score-card .cs-title {
    font-size: 12px; font-weight: 600; opacity: 0.8; margin-bottom: 4px;
  }
  .composite-score-card .cs-score {
    font-size: 32px; font-weight: 800; letter-spacing: -1px;
  }
  .composite-score-card .cs-grade {
    display: inline-block; background: rgba(255,255,255,0.2);
    border-radius: 20px; padding: 3px 12px; font-size: 12px;
    font-weight: 700; margin-left: 10px; vertical-align: middle;
  }
  .composite-score-card .cs-base {
    font-size: 11px; opacity: 0.75; margin-top: 4px;
  }
  .composite-score-card .cs-risk {
    display: inline-block; margin-top: 8px;
    padding: 4px 10px; border-radius: 8px; font-size: 11px; font-weight: 700;
  }
  .cs-risk-normal { background: #dcfce7; color: #15803d; }
  .cs-risk-caution { background: #fef3c7; color: #b45309; }
  .cs-risk-mid    { background: #fed7aa; color: #c2410c; }
  .cs-risk-high   { background: #fee2e2; color: #dc2626; }
  .adj-list {
    margin-top: 10px; display: flex; flex-direction: column; gap: 4px;
  }
  .adj-item {
    display: flex; justify-content: space-between; align-items: center;
    background: rgba(255,255,255,0.1); border-radius: 6px;
    padding: 5px 10px; font-size: 11px;
  }
  .adj-delta-pos { color: #86efac; font-weight: 700; }
  .adj-delta-neg { color: #fca5a5; font-weight: 700; }
  .adj-delta-zer { color: rgba(255,255,255,0.5); }
  /* 의료이력 체크박스 */
  .medical-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 7px;
    margin-bottom: 10px;
  }
  .medical-check {
    display: flex; align-items: center; gap: 7px;
    padding: 7px 10px;
    border: 1.5px solid #e2e8f0; border-radius: 8px;
    cursor: pointer; font-size: 12px; color: #374151;
    transition: all 0.15s; user-select: none;
  }
  .medical-check:hover { border-color: #93c5fd; background: #eff6ff; }
  .medical-check input[type=checkbox] { accent-color: #2563eb; width: 14px; height: 14px; }
  .medical-check.checked { border-color: #2563eb; background: #eff6ff; font-weight: 600; }
  /* 점수 분해 카드 (결과 영역 상단) */
  .score-breakdown-card {
    background: #f8fafc; border: 1.5px solid #e2e8f0;
    border-radius: 10px; padding: 14px 16px; margin-bottom: 14px;
    font-size: 12.5px;
  }
  .score-breakdown-card h4 {
    font-size: 12px; font-weight: 700; color: #1e40af;
    margin: 0 0 10px; display: flex; align-items: center; gap: 6px;
  }
  .sbc-row {
    display: flex; justify-content: space-between;
    padding: 4px 0; border-bottom: 1px solid #f1f5f9; color: #374151;
  }
  .sbc-row:last-child { border-bottom: none; }
  .sbc-pos { color: #16a34a; font-weight: 700; }
  .sbc-neg { color: #dc2626; font-weight: 700; }
  .sbc-zer { color: #94a3b8; }

  /* 약관대출 카드 */
  .policy-loan-card {
    background: #f0f9ff; border: 1px solid #bae6fd;
    border-radius: 10px; padding: 16px; margin-bottom: 16px; font-size: 13px;
  }
  .policy-loan-card h4 { margin: 0 0 4px; color: #0369a1; font-size: 14px; font-weight: 700; }
  .loan-subtitle { color: #64748b; font-size: 11.5px; margin: 0 0 12px; }
  .loan-table-wrap { overflow-x: auto; }
  .loan-table { width: 100%; border-collapse: collapse; font-size: 12px; min-width: 520px; }
  .loan-table th, .loan-table td {
    border: 1px solid #bae6fd; padding: 6px 10px; text-align: right; white-space: nowrap;
  }
  .loan-table th:first-child, .loan-table td:first-child,
  .loan-table th:nth-child(2), .loan-table td:nth-child(2) { text-align: left; }
  .loan-table thead th { background: #e0f2fe; font-weight: 700; color: #0369a1; }
  .loan-table .loan-total-row td { background: #dbeafe; font-weight: 700; border-top: 2px solid #93c5fd; }
  .inelig-section { margin-top: 10px; font-size: 11.5px; color: #64748b; }
  .inelig-badge {
    display: inline-block; background: #f1f5f9; border: 1px solid #e2e8f0;
    border-radius: 4px; padding: 1px 7px; margin: 2px 2px; font-size: 11px; color: #64748b;
  }
  .loan-disclaimer { color: #94a3b8; font-size: 10.5px; margin: 10px 0 0; line-height: 1.5; }
  .loan-basis { margin-top: 10px; }
  .loan-basis summary {
    cursor: pointer; font-size: 11.5px; color: #0369a1; font-weight: 600;
    user-select: none; outline: none; list-style: none; padding: 4px 0;
  }
  .loan-basis summary::-webkit-details-marker { display: none; }
  .loan-basis-body { margin-top: 8px; }
  .loan-basis-formula { font-size: 11.5px; color: #334155; margin: 0 0 8px; }
  .loan-basis-table td, .loan-basis-table th { font-size: 11px; padding: 4px 8px; }
  .loan-basis-table td { color: #475569; }

  /* 보험 가입 링크 버튼 */
  .ins-link-btn {
    display: inline-block; padding: 3px 9px; border-radius: 4px;
    background: #1d4ed8; color: #fff !important; font-size: 11px; font-weight: 600;
    text-decoration: none !important; white-space: nowrap;
    transition: background 0.15s;
  }
  .ins-link-btn:hover { background: #1e40af; }
  .ins-link-damoah { background: #0369a1; }
  .ins-link-damoah:hover { background: #075985; }
  /* 채팅 버블 내 테이블 가입 링크 열 */
  .bubble table th:last-child,
  .bubble table td:last-child,
  #credit-result-body table th:last-child,
  #credit-result-body table td:last-child { white-space: nowrap; text-align: center; }
</style>
</head>
<body>

<div class="header">
  <div class="header-icon">🛡️</div>
  <div>
    <div class="header-title">보험 상담 AI 어시스턴트</div>
    <div class="header-sub">종신 · 실손 · 암 · 치아 · 간병·치매 · 연금보험</div>
  </div>
  <div class="mode-selector" id="modeSelector">
    <div class="mode-badge" id="modeBadge" onclick="toggleModeDropdown()">확인 중... ▾</div>
    <div class="mode-dropdown" id="modeDropdown">
      <div class="mode-option" onclick="setMode('auto')">🔄 Auto (자동)</div>
      <div class="mode-option" onclick="setMode('live')">🟢 Live Mode</div>
      <div class="mode-option" onclick="setMode('mock')">🔧 Mock Mode</div>
    </div>
  </div>
</div>

<!-- Tab Navigation -->
<div class="tab-nav">
  <button class="tab-btn active" onclick="switchTab('chat')">💬 보험 상담</button>
  <button class="tab-btn" onclick="switchTab('credit')">💳 신용점수 포트폴리오</button>
</div>

<!-- Tab: 보험 상담 -->
<div class="tab-panel active" id="tab-chat">
  <div id="chat"></div>
  <div class="quick-buttons">
    <button class="qbtn" onclick="quickSend('40대 남성 암보험 추천해줘')">암보험 추천</button>
    <button class="qbtn" onclick="quickSend('40대 남성 치아보험 추천해줘')">치아보험</button>
    <button class="qbtn" onclick="quickSend('실손보험 보험사별 비교해줘')">실손보험 비교</button>
    <button class="qbtn" onclick="quickSend('간병보험·치매보험 추천해줘')">간병·치매보험</button>
    <button class="qbtn" onclick="quickSend('45세 남성 보험 포트폴리오 추천해줘')">포트폴리오 추천</button>
    <button class="qbtn" onclick="quickSend('실손보험 4세대 5세대 차이 알려줘')">4세대 vs 5세대</button>
  </div>
  <div class="input-area">
    <button class="reset-btn" onclick="resetChat()" title="대화 초기화">🔄</button>
    <textarea id="input" placeholder="보험에 대해 무엇이든 물어보세요..." rows="1"
      onkeydown="handleKey(event)" oninput="autoResize(this)"></textarea>
    <button id="send" onclick="sendMessage()">➤</button>
  </div>
</div>

<!-- Tab: 신용점수 포트폴리오 -->
<div class="tab-panel" id="tab-credit">
  <div class="credit-panel">

    <!-- 신용점수 확인 안내 -->
    <div class="credit-guide">
      <h3>📊 신용점수 확인 방법 (무료)</h3>
      <p style="font-size:12.5px;color:#475569;margin-bottom:8px;">아래 앱·사이트에서 신용점수를 무료로 확인 후 입력하세요. NICE·KCB 중 하나만 입력해도 됩니다.</p>
      <div class="score-sources">
        <div class="score-source-card" onclick="openUrl('https://toss.im')">
          <div class="source-logo">💚</div>
          <div class="source-name">토스</div>
          <div class="source-desc">KCB 점수 무료 조회<br>(앱 → 신용점수)</div>
          <span class="source-link">toss.im →</span>
        </div>
        <div class="score-source-card" onclick="openUrl('https://www.kakaopay.com')">
          <div class="source-logo">💛</div>
          <div class="source-name">카카오페이</div>
          <div class="source-desc">NICE 점수 무료 조회<br>(앱 → 신용점수 조회)</div>
          <span class="source-link">kakaopay.com →</span>
        </div>
        <div class="score-source-card" onclick="openUrl('https://credit.co.kr')">
          <div class="source-logo">🏛️</div>
          <div class="source-name">NICE 지키미</div>
          <div class="source-desc">NICE 공식 조회<br>(1회/월 무료)</div>
          <span class="source-link">credit.co.kr →</span>
        </div>
        <div class="score-source-card" onclick="openUrl('https://www.allcredit.co.kr')">
          <div class="source-logo">📋</div>
          <div class="source-name">올크레딧(KCB)</div>
          <div class="source-desc">KCB 공식 조회<br>(1회/월 무료)</div>
          <span class="source-link">allcredit.co.kr →</span>
        </div>
      </div>
    </div>

    <!-- 입력 폼 -->
    <div class="credit-form">
      <h3>✏️ 정보 입력</h3>
      <div class="form-grid">
        <div class="form-group">
          <label>나이</label>
          <input type="number" id="cf-age" placeholder="예: 42" min="20" max="70" value="">
        </div>
        <div class="form-group">
          <label>성별</label>
          <select id="cf-gender">
            <option value="남">남성</option>
            <option value="여">여성</option>
          </select>
        </div>
        <div class="form-group">
          <label>월 보험료 예산 (만원)</label>
          <input type="number" id="cf-budget" placeholder="예: 20" min="5" max="100" value="">
        </div>
        <div class="form-group">
          <label>기혼/미혼</label>
          <select id="cf-married">
            <option value="">선택 안함</option>
            <option value="기혼">기혼</option>
            <option value="미혼">미혼</option>
          </select>
        </div>
        <div class="form-group">
          <label>NICE 신용점수 <span style="font-weight:400;color:#94a3b8">(토스·카카오페이·NICE 지키미)</span></label>
          <div class="score-input-wrap">
            <input type="number" id="cf-nice" placeholder="없으면 비워두세요 (300~1000)"
              min="300" max="1000" oninput="updateScoreBadge('nice')">
            <span class="score-badge" id="badge-nice"></span>
          </div>
        </div>
        <div class="form-group">
          <label>KCB 신용점수 <span style="font-weight:400;color:#94a3b8">(토스·올크레딧)</span></label>
          <div class="score-input-wrap">
            <input type="number" id="cf-kcb" placeholder="없으면 비워두세요 (300~1000)"
              min="300" max="1000" oninput="updateScoreBadge('kcb')">
            <span class="score-badge" id="badge-kcb"></span>
          </div>
        </div>
        <div class="form-group full">
          <div class="score-avg-note" id="score-avg-note"></div>
        </div>
        <div class="form-group full">
          <label>현재 가입 보험 (선택)</label>
          <input type="text" id="cf-existing" placeholder="예: 실손보험 가입, 암보험 없음">
        </div>
        <div class="form-group full">
          <label>건강 특이사항 (선택)</label>
          <input type="text" id="cf-health" placeholder="예: 고혈압 약 복용 중, 특이사항 없음">
        </div>
      </div>
      <!-- 금융데이터 입력 -->
      <div class="extra-section">
        <div class="extra-section-header" onclick="toggleSection('financial')">
          <span>💰 금융데이터 <span style="font-weight:400;color:#94a3b8;font-size:11px">— 선택 입력 (더 정확한 추천)</span></span>
          <span class="extra-section-toggle" id="toggle-financial">▼</span>
        </div>
        <div class="extra-section-body" id="body-financial">
          <div class="form-grid">
            <div class="form-group">
              <label>연소득 (만원/년)</label>
              <input type="number" id="cf-income" placeholder="예: 4500" min="0" oninput="updateFinancialSummary()">
            </div>
            <div class="form-group">
              <label>금융자산 (만원)</label>
              <input type="number" id="cf-assets" placeholder="예: 3000 (예금·적금·주식 등)" min="0" oninput="updateFinancialSummary()">
            </div>
            <div class="form-group">
              <label>부채·대출 잔액 (만원)</label>
              <input type="number" id="cf-debt" placeholder="예: 5000" min="0" oninput="updateFinancialSummary()">
            </div>
            <div class="form-group">
              <label>현재 납입 보험료 (만원/월)</label>
              <input type="number" id="cf-current-premium" placeholder="예: 10" min="0" oninput="updateFinancialSummary()">
            </div>
          </div>
          <div class="financial-summary" id="financial-summary"></div>
        </div>
      </div>

      <!-- 대안데이터 입력 -->
      <div class="extra-section">
        <div class="extra-section-header" onclick="toggleSection('alt')">
          <span>📊 대안데이터 <span style="font-weight:400;color:#94a3b8;font-size:11px">— 선택 입력 (신용평가 보완)</span></span>
          <span class="extra-section-toggle" id="toggle-alt">▼</span>
        </div>
        <div class="extra-section-body" id="body-alt">
          <div class="form-grid">
            <div class="form-group">
              <label>직업 유형</label>
              <select id="cf-employment">
                <option value="">선택 안함</option>
                <option value="정규직">정규직 (직장인)</option>
                <option value="비정규직">비정규직 (계약직·파견)</option>
                <option value="자영업">자영업·사업자</option>
                <option value="프리랜서">프리랜서·독립계약</option>
                <option value="공무원">공무원·교직원</option>
                <option value="무직">무직·구직 중</option>
              </select>
            </div>
            <div class="form-group">
              <label>거주 형태</label>
              <select id="cf-housing">
                <option value="">선택 안함</option>
                <option value="자가">자가 (본인 소유)</option>
                <option value="전세">전세</option>
                <option value="월세">월세·반전세</option>
                <option value="가족거주">가족 소유 (무상거주)</option>
                <option value="기타">기타</option>
              </select>
            </div>
            <div class="form-group">
              <label>통신비 납부 이력</label>
              <select id="cf-telecom">
                <option value="">선택 안함</option>
                <option value="정상납부">정상납부 (지연 없음)</option>
                <option value="지연경험">지연 경험 있음</option>
                <option value="연체경험">연체 경험 있음</option>
              </select>
            </div>
            <div class="form-group">
              <label>공과금 납부 이력</label>
              <select id="cf-utility">
                <option value="">선택 안함</option>
                <option value="정상납부">정상납부 (지연 없음)</option>
                <option value="지연경험">지연 경험 있음</option>
                <option value="연체경험">연체 경험 있음</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      <!-- 최근 5년 치료 내역 -->
      <div class="extra-section">
        <div class="extra-section-header" onclick="toggleSection('medical')">
          <span>🏥 최근 5년 치료 내역 <span style="font-weight:400;color:#94a3b8;font-size:11px">— 선택 입력 (심사 유형 최적화)</span></span>
          <span class="extra-section-toggle" id="toggle-medical">▼</span>
        </div>
        <div class="extra-section-body" id="body-medical">
          <p style="font-size:11.5px;color:#64748b;margin:0 0 10px">최근 5년 내 진단·치료 이력이 있는 항목을 선택하세요. 심사 유형(일반/간편/무심사) 결정에 활용됩니다.</p>
          <div class="medical-grid" id="medical-grid">
            <label class="medical-check" onclick="toggleMedical(this)">
              <input type="checkbox" value="암·종양 치료"> 암·종양 치료
            </label>
            <label class="medical-check" onclick="toggleMedical(this)">
              <input type="checkbox" value="심장질환"> 심장질환 (협심증·심근경색)
            </label>
            <label class="medical-check" onclick="toggleMedical(this)">
              <input type="checkbox" value="뇌질환"> 뇌질환 (뇌졸중·뇌경색)
            </label>
            <label class="medical-check" onclick="toggleMedical(this)">
              <input type="checkbox" value="당뇨병"> 당뇨병
            </label>
            <label class="medical-check" onclick="toggleMedical(this)">
              <input type="checkbox" value="고혈압"> 고혈압
            </label>
            <label class="medical-check" onclick="toggleMedical(this)">
              <input type="checkbox" value="간질환"> 간질환 (간경화·간염)
            </label>
            <label class="medical-check" onclick="toggleMedical(this)">
              <input type="checkbox" value="신장질환"> 신장질환
            </label>
            <label class="medical-check" onclick="toggleMedical(this)">
              <input type="checkbox" value="척추·관절질환"> 척추·관절질환
            </label>
            <label class="medical-check" onclick="toggleMedical(this)">
              <input type="checkbox" value="정신건강 질환"> 정신건강 질환
            </label>
            <label class="medical-check" onclick="toggleMedical(this)">
              <input type="checkbox" value="기타 질환"> 기타 질환
            </label>
          </div>
          <div class="form-grid" style="margin-top:4px">
            <div class="form-group">
              <label>최근 5년 입원 횟수</label>
              <select id="cf-hospitalization">
                <option value="">없음</option>
                <option value="1회">1회</option>
                <option value="2회">2회</option>
                <option value="3회 이상">3회 이상</option>
              </select>
            </div>
            <div class="form-group">
              <label>현재 복용 약물 (선택)</label>
              <input type="text" id="cf-medications" placeholder="예: 혈압약, 당뇨약">
            </div>
          </div>
        </div>
      </div>

      <button class="gen-btn" id="gen-btn" onclick="generatePortfolio()">
        💳 신용점수 반영 포트폴리오 생성
      </button>
    </div>

    <!-- 결과 -->
    <div class="credit-result" id="credit-result" style="display:none">
      <div class="credit-result-header">
        <span style="font-size:16px">📋</span>
        <span style="font-weight:700;font-size:14px">맞춤형 보험 포트폴리오</span>
        <span class="score-pill" id="result-score-pill"></span>
        <button onclick="document.getElementById('credit-result').style.display='none'"
          style="margin-left:auto;background:none;border:none;cursor:pointer;color:#94a3b8;font-size:18px">✕</button>
      </div>
      <!-- 종합 적합도 점수 카드 (JS로 채움) -->
      <div id="composite-score-card-area"></div>
      <div id="policy-loan-card-area"></div>
      <div class="credit-result-body" id="credit-result-body"></div>
    </div>

  </div>
</div>

<script>
const SESSION_ID = crypto.randomUUID();
let isLoading = false;

// 모든 링크를 새 탭으로 열기 (marked v4/v5 호환)
const renderer = new marked.Renderer();
renderer.link = function(token, legacyTitle, legacyText) {
  let href, title, text;
  if (token && typeof token === 'object' && 'href' in token) {
    // marked v5+: 첫 번째 인자가 토큰 객체
    href = token.href; title = token.title; text = token.text;
  } else {
    // marked v4: 위치 인자
    href = token; title = legacyTitle; text = legacyText;
  }
  const titleAttr = title ? ` title="${title}"` : '';
  return `<a href="${href}"${titleAttr} target="_blank" rel="noopener noreferrer">${text}</a>`;
};
marked.setOptions({ breaks: true, gfm: true, renderer });

async function checkMode() {
  try {
    const r = await fetch('/api/status');
    const d = await r.json();
    updateBadge(d.effective_mode, d.forced_mode);
  } catch(e) {}
}

function updateBadge(effectiveMode, forcedMode) {
  const badge = document.getElementById('modeBadge');
  badge.classList.remove('live', 'mock');
  if (forcedMode === 'auto' || !forcedMode) {
    if (effectiveMode === 'live') {
      badge.textContent = '🟢 Live Mode (자동) ▾';
      badge.classList.add('live');
    } else {
      badge.textContent = '🔧 Mock Mode (자동) ▾';
      badge.classList.add('mock');
    }
  } else if (forcedMode === 'live') {
    badge.textContent = '🟢 Live Mode ▾';
    badge.classList.add('live');
  } else {
    badge.textContent = '🔧 Mock Mode ▾';
    badge.classList.add('mock');
  }
}

function toggleModeDropdown() {
  document.getElementById('modeDropdown').classList.toggle('open');
}

async function setMode(mode) {
  document.getElementById('modeDropdown').classList.remove('open');
  await fetch('/api/set-mode', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode })
  });
  await checkMode();
}

document.addEventListener('click', (e) => {
  if (!document.getElementById('modeSelector').contains(e.target)) {
    document.getElementById('modeDropdown').classList.remove('open');
  }
});

const TOOL_LABELS = {
  search_insurance_products:       '🔍 보험 상품 검색 중...',
  compare_insurance_products:      '📊 상품 비교 중...',
  get_premium_estimate:            '💰 보험료 계산 중...',
  retrieve_insurance_knowledge:    '📚 지식 베이스 검색 중...',
  fetch_fss_realtime_products:     '🏛️ FSS 실시간 조회 중...',
  get_personalized_recommendation: '🤖 맞춤 추천 생성 중...',
  search_insmarket_products:       '📊 보험다모아 공시 조회 중...',
  search_web:                      '🌐 웹 검색 중...',
  fetch_webpage:                   '📄 페이지 읽는 중...',
  get_credit_score:                '💳 신용점수 조회 중...',
  _news_search:                    '📰 관련 뉴스 검색 중...',
};

function scrollToBottom() {
  const chat = document.getElementById('chat');
  chat.scrollTop = chat.scrollHeight;
}

function addMessage(role, text) {
  const chat = document.getElementById('chat');
  const isUser = role === 'user';

  const div = document.createElement('div');
  div.className = `msg ${role}`;

  const avatar = document.createElement('div');
  avatar.className = 'avatar';
  avatar.textContent = isUser ? '👤' : '🛡️';

  const bubble = document.createElement('div');
  bubble.className = 'bubble';

  if (isUser) {
    bubble.textContent = text;
  } else {
    bubble.innerHTML = addLinksToTables(marked.parse(preprocessMd(text)));
  }

  div.appendChild(avatar);
  div.appendChild(bubble);
  chat.appendChild(div);
  scrollToBottom();
}

function createStreamingBubble() {
  const chat = document.getElementById('chat');

  const msgDiv = document.createElement('div');
  msgDiv.className = 'msg bot';

  const avatar = document.createElement('div');
  avatar.className = 'avatar';
  avatar.textContent = '🛡️';

  const right = document.createElement('div');
  right.style.display = 'flex';
  right.style.flexDirection = 'column';
  right.style.maxWidth = '100%';

  const toolStatus = document.createElement('div');
  toolStatus.className = 'tool-status';

  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  // initial typing indicator
  bubble.innerHTML = '<span class="typing"><span></span><span></span><span></span></span>';

  right.appendChild(toolStatus);
  right.appendChild(bubble);
  msgDiv.appendChild(avatar);
  msgDiv.appendChild(right);
  chat.appendChild(msgDiv);
  scrollToBottom();

  return { msgDiv, bubble, toolStatus };
}

async function sendMessage() {
  if (isLoading) return;
  const input = document.getElementById('input');
  const text = input.value.trim();
  if (!text) return;

  input.value = '';
  autoResize(input);
  addMessage('user', text);
  isLoading = true;
  document.getElementById('send').disabled = true;

  const { bubble, toolStatus } = createStreamingBubble();
  let fullText = '';
  let cursor = null;

  function startCursor() {
    if (!cursor) {
      cursor = document.createElement('span');
      cursor.className = 'stream-cursor';
      bubble.appendChild(cursor);
    }
  }
  function removeCursor() {
    if (cursor) { cursor.remove(); cursor = null; }
  }

  try {
    const r = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, session_id: SESSION_ID })
    });

    if (!r.ok) {
      bubble.innerHTML = '⚠️ 서버 오류가 발생했습니다.';
    } else {
      const reader = r.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          let event;
          try { event = JSON.parse(line.slice(6)); } catch { continue; }

          if (event.type === 'token') {
            fullText += event.text;
            bubble.innerHTML = marked.parse(preprocessMd(fullText));
            startCursor();
            scrollToBottom();

          } else if (event.type === 'tool_start') {
            toolStatus.textContent = TOOL_LABELS[event.tool] || '⚙️ 처리 중...';
            toolStatus.style.display = 'block';

          } else if (event.type === 'tool_done') {
            toolStatus.style.display = 'none';

          } else if (event.type === 'done') {
            fullText = event.full_text || fullText;
            bubble.innerHTML = addLinksToTables(marked.parse(preprocessMd(fullText)));
            toolStatus.style.display = 'none';
            removeCursor();
            scrollToBottom();

          } else if (event.type === 'error') {
            bubble.innerHTML = '⚠️ 오류: ' + event.message;
            toolStatus.style.display = 'none';
            removeCursor();
          }
        }
      }
      removeCursor();
    }
  } catch(e) {
    bubble.innerHTML = '⚠️ 서버 연결 오류가 발생했습니다.';
  }

  isLoading = false;
  document.getElementById('send').disabled = false;
  input.focus();
}

async function resetChat() {
  await fetch('/api/reset', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: SESSION_ID })
  });
  document.getElementById('chat').innerHTML = '';
  addMessage('bot', '대화가 초기화되었습니다. 무엇을 도와드릴까요?');
}

function quickSend(text) {
  document.getElementById('input').value = text;
  sendMessage();
}

function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}

function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 120) + 'px';
}

// ── Tab switching ──────────────────────────────────────────
function switchTab(name) {
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  event.currentTarget.classList.add('active');
}

function openUrl(url) { window.open(url, '_blank'); }

// ── Credit score tier helper ───────────────────────────────
function scoreTier(v) {
  if (v >= 900) return { cls:'tier1', label:'최우량' };
  if (v >= 750) return { cls:'tier2', label:'우량' };
  if (v >= 600) return { cls:'tier3', label:'보통' };
  if (v >= 450) return { cls:'tier4', label:'주의' };
  return { cls:'tier5', label:'불량' };
}

function updateScoreBadge(type) {
  const input = document.getElementById('cf-' + type);
  const badge = document.getElementById('badge-' + type);
  const v = parseInt(input.value);
  if (isNaN(v) || v < 300 || v > 1000) { badge.textContent = ''; badge.className = 'score-badge'; }
  else {
    const t = scoreTier(v);
    badge.textContent = t.label;
    badge.className = 'score-badge ' + t.cls;
  }
  updateAvgNote();
}

function updateAvgNote() {
  const nice = parseInt(document.getElementById('cf-nice').value);
  const kcb  = parseInt(document.getElementById('cf-kcb').value);
  const note = document.getElementById('score-avg-note');
  const both = !isNaN(nice) && !isNaN(kcb);
  const oneNice = !isNaN(nice) && isNaN(kcb);
  const oneKcb  = isNaN(nice) && !isNaN(kcb);
  if (both) {
    const avg = Math.round((nice + kcb) / 2);
    const t = scoreTier(avg);
    note.innerHTML = `📊 NICE+KCB 평균 점수: <strong>${avg}점</strong> — <strong>${t.label}</strong> 등급으로 포트폴리오를 구성합니다.`;
  } else if (oneNice) {
    const t = scoreTier(nice);
    note.innerHTML = `📊 NICE 점수 ${nice}점 (${t.label}) 기준으로 포트폴리오를 구성합니다.`;
  } else if (oneKcb) {
    const t = scoreTier(kcb);
    note.innerHTML = `📊 KCB 점수 ${kcb}점 (${t.label}) 기준으로 포트폴리오를 구성합니다.`;
  } else {
    note.innerHTML = '';
  }
}

function toggleMedical(label) {
  const cb = label.querySelector('input[type=checkbox]');
  cb.checked = !cb.checked;
  label.classList.toggle('checked', cb.checked);
}

function getCheckedConditions() {
  return Array.from(document.querySelectorAll('#medical-grid input[type=checkbox]:checked'))
    .map(cb => cb.value);
}

// ── 마크다운 전처리: 숫자 범위 ~ 를 취소선 오해 방지 ───────────────
function preprocessMd(text) {
  // 숫자·한글 사이의 ~ 를 \~ 로 이스케이프하여 marked.js 취소선 오렌더링 방지
  // 예: "300만~500만" → "300만\~500만"
  return text.replace(/([\d가-힣원,]+)\s*~\s*([\d가-힣원,])/g, '$1\\~$2');
}

// ── 보험사 가입 링크 매핑 ─────────────────────────────────────
const INSURER_URLS = {
  // 생명보험사
  '삼성생명':       'https://www.samsunglife.com',
  '한화생명':       'https://www.hanwhalife.com',
  '교보생명':       'https://www.kyobo.com',
  '교보라이프플래닛': 'https://www.lifeplanet.co.kr',
  '신한라이프':     'https://www.shinhanlife.co.kr',
  'NH농협생명':     'https://www.nhlife.co.kr',
  '농협생명':       'https://www.nhlife.co.kr',
  '라이나생명':     'https://www.lina.co.kr',
  'AIA생명':        'https://www.aia.co.kr',
  'KB라이프':       'https://www.kblife.co.kr',
  'KB라이프생명':   'https://www.kblife.co.kr',
  '동양생명':       'https://www.myangel.co.kr',
  '흥국생명':       'https://www.heungkuklife.co.kr',
  '미래에셋생명':   'https://life.miraeasset.com',
  'ABL생명':        'https://www.abllife.co.kr',
  'DB생명':         'https://direct.idblife.com',
  '메트라이프':     'https://www.metlife.co.kr',
  '푸르덴셜생명':   'https://www.kblife.co.kr',
  '처브라이프':     'https://www.chubblife.co.kr',
  // 손해보험사
  '삼성화재':  'https://direct.samsungfire.com',
  '현대해상':      'https://direct.hi.co.kr',
  '현대해상화재':  'https://direct.hi.co.kr',
  'DB손해보험':    'https://www.idbins.com',
  'DB손보':        'https://www.idbins.com',
  'KB손보':        'https://www.kbinsure.co.kr',
  'KB손해보험':    'https://www.kbinsure.co.kr',
  '메리츠화재':    'https://direct.meritzfire.com',
  '메리츠손해보험': 'https://direct.meritzfire.com',
  '한화손보':      'https://www.hwgeneralins.com',
  '한화손해보험':  'https://www.hwgeneralins.com',
  '롯데손보':      'https://www.lotteins.co.kr',
  '롯데손해보험':  'https://www.lotteins.co.kr',
  '흥국화재':      'https://www.heungkukfire.co.kr',
  '하나손보':      'https://www.hanainsure.co.kr',
  '하나손해보험':  'https://www.hanainsure.co.kr',
  '신한EZ손해보험': 'https://www.shinhanez.co.kr',
  '신한EZ':        'https://www.shinhanez.co.kr',
  '농협손보':      'https://www.nhfire.co.kr',
  'NH손해보험':    'https://www.nhfire.co.kr',
};
const DAMOAH_URL = 'https://www.e-insmarket.or.kr';

function findInsurerUrl(text) {
  for (const [name, url] of Object.entries(INSURER_URLS)) {
    if (text.includes(name)) return { name, url };
  }
  return null;
}

function addLinksToTables(htmlStr) {
  const wrap = document.createElement('div');
  wrap.innerHTML = htmlStr;

  wrap.querySelectorAll('table').forEach(tbl => {
    const thead = tbl.querySelector('thead tr');
    const tbody = tbl.querySelector('tbody');
    if (!thead || !tbody) return;

    // "이 답변의 근거" 테이블(신뢰도 컬럼 존재) 제외
    const thTexts = Array.from(thead.querySelectorAll('th')).map(t => t.textContent.trim());
    if (thTexts.includes('신뢰도') || thTexts.includes('출처')) return;

    // 헤더에 "가입 안내" 열 추가
    const th = document.createElement('th');
    th.textContent = '가입 안내';
    thead.appendChild(th);

    tbody.querySelectorAll('tr').forEach(row => {
      const rowText = row.textContent;
      const insurer = findInsurerUrl(rowText);
      const td = document.createElement('td');

      const a = document.createElement('a');
      a.target = '_blank';
      a.rel = 'noopener noreferrer';

      if (insurer) {
        a.href = insurer.url;
        a.className = 'ins-link-btn';
        a.textContent = '가입하기 →';
      } else {
        a.href = DAMOAH_URL;
        a.className = 'ins-link-btn ins-link-damoah';
        a.textContent = '비교하기 →';
      }
      td.appendChild(a);
      row.appendChild(td);
    });
  });

  return wrap.innerHTML;
}

function renderCompositeCard(cs) {
  if (!cs) return '';
  const deltaStr = cs.total_delta >= 0 ? `+${cs.total_delta}` : `${cs.total_delta}`;
  const riskCls = {
    '일반': 'cs-risk-normal', '주의': 'cs-risk-caution',
    '중위험': 'cs-risk-mid', '고위험': 'cs-risk-high'
  }[cs.underwriting_risk] || 'cs-risk-normal';

  const adjRows = (cs.adjustments || []).map(a => {
    const cls = a.delta > 0 ? 'adj-delta-pos' : a.delta < 0 ? 'adj-delta-neg' : 'adj-delta-zer';
    const sign = a.delta > 0 ? '+' : '';
    return `<div class="adj-item">
      <span>${a.factor} <span style="opacity:0.7;font-size:10px">— ${a.reason}</span></span>
      <span class="${cls}">${sign}${a.delta}</span>
    </div>`;
  }).join('');

  const sbcRows = (cs.adjustments || []).map(a => {
    const cls = a.delta > 0 ? 'sbc-pos' : a.delta < 0 ? 'sbc-neg' : 'sbc-zer';
    const sign = a.delta > 0 ? '+' : '';
    return `<div class="sbc-row"><span>${a.factor}</span><span class="${cls}">${sign}${a.delta}점</span></div>`;
  }).join('');

  return `<div class="score-breakdown-card">
    <h4>📊 종합 보험 가입 적합도 분석</h4>
    <div class="sbc-row"><span>기본 신용점수 (NICE/KCB 평균)</span><span style="font-weight:700">${cs.base_score}점</span></div>
    ${sbcRows}
    <div class="sbc-row" style="font-weight:700;border-top:2px solid #e2e8f0;margin-top:6px;padding-top:6px">
      <span>종합 적합도 지수</span>
      <span style="color:#1d4ed8;font-size:15px">${cs.composite_score}점 (${cs.grade})</span>
    </div>
    <div style="margin-top:10px;font-size:11.5px;color:#475569">
      <strong>보험 심사 위험도:</strong>
      <span class="risk-badge ${riskCls === 'cs-risk-normal' ? 'risk-low' : riskCls === 'cs-risk-caution' ? 'risk-med' : 'risk-high'}">${cs.underwriting_risk}</span>
      ${cs.underwriting_risk !== '일반' ? `<span style="margin-left:6px;color:#64748b">— 간편심사·무심사형 상품 우선 검토</span>` : ''}
    </div>
    ${cs.preferred_products && cs.preferred_products.length ? `<div style="margin-top:8px;font-size:11.5px;color:#475569"><strong>적합 상품군:</strong> ${cs.preferred_products.slice(0,4).join(' · ')}</div>` : ''}
    ${cs.avoid_products && cs.avoid_products.length ? `<div style="margin-top:4px;font-size:11.5px;color:#475569"><strong>신중 검토 상품:</strong> <span style="color:#dc2626">${cs.avoid_products.slice(0,3).join(' · ')}</span></div>` : ''}
  </div>`;
}

function renderPolicyLoanCard(ld) {
  if (!ld) return '';
  const years = ['1','3','5','10'];
  const stripMd = s => (s || '').replace(/\*\*/g, '').replace(/\*/g, '').trim();
  // 대출 한도 포맷 (만원 단위)
  const fmt = n => {
    if (n >= 100000000) return `${(n/100000000).toFixed(1)}억원`;
    if (n >= 10000)     return `${Math.round(n/10000).toLocaleString()}만원`;
    return n > 0 ? `${n.toLocaleString()}원` : '—';
  };
  // 보험료 포맷 (원 단위 그대로 표시)
  const fmtPrem = n => {
    if (n >= 10000) return `${(n/10000).toFixed(n % 10000 === 0 ? 0 : 1)}만원`;
    return `${n.toLocaleString()}원`;
  };

  let eligRows = '';
  for (const p of (ld.eligible || [])) {
    const loanCells = years.map(y => `<td>${fmt(p.loans[y] || 0)}</td>`).join('');
    eligRows += `<tr>
      <td>${p.type}</td>
      <td style="max-width:180px;overflow:hidden;text-overflow:ellipsis">${p.name}</td>
      <td>${fmtPrem(p.monthly_premium)}</td>
      ${loanCells}
    </tr>`;
  }

  const totalCells = years.map(y => `<td>${fmt(ld.totals && ld.totals[y] || 0)}</td>`).join('');
  const totalRow = ld.has_eligible ? `<tr class="loan-total-row">
    <td colspan="3">합계 (저축성 상품 기준)</td>${totalCells}
  </tr>` : '';

  const ineligBadges = (ld.ineligible || []).map(p =>
    `<span class="inelig-badge">${stripMd(p.type)} (${fmtPrem(p.monthly_premium)})</span>`
  ).join('');

  if (!ld.has_eligible && !(ld.ineligible || []).length) return '';

  return `<div class="policy-loan-card">
    <h4>💰 약관대출 예상 한도</h4>
    <p class="loan-subtitle">저축성 보험의 해지환급금을 담보로 보험사에서 대출받을 수 있는 예상 한도입니다.</p>
    ${ld.has_eligible ? `
    <div class="loan-table-wrap">
      <table class="loan-table">
        <thead><tr>
          <th>보험 종류</th><th>상품명</th><th>월 보험료</th>
          ${years.map(y => `<th>${y}년 후</th>`).join('')}
        </tr></thead>
        <tbody>${eligRows}${totalRow}</tbody>
      </table>
    </div>` : '<p style="color:#64748b;font-size:12px">추천된 상품 중 약관대출 가능한 저축성 보험이 없습니다.</p>'}
    ${ineligBadges ? `<div class="inelig-section">
      <strong>순수보장형 (약관대출 불가):</strong> ${ineligBadges}
    </div>` : ''}
    <p class="loan-disclaimer">※ 실제 대출 한도·이자율은 보험사·상품·납입 완료 여부에 따라 다릅니다. 일반적으로 해지환급금의 80~95% 이내. 대출 중 이자 미납 시 보험 계약 실효 가능.</p>
    ${ld.has_eligible ? `
    <details class="loan-basis">
      <summary>📐 산출 기준 보기</summary>
      <div class="loan-basis-body">
        <p class="loan-basis-formula">약관대출 한도 = <strong>월 보험료 × 12 × 납입기간(년) × 해지환급금률 × 약관대출비율</strong></p>
        <div class="loan-table-wrap">
          <table class="loan-table loan-basis-table">
            <thead><tr>
              <th>보험 종류</th><th>기준</th>
              <th>1년 후</th><th>3년 후</th><th>5년 후</th><th>10년 후</th>
              <th>약관대출 비율</th>
            </tr></thead>
            <tbody>
              <tr><td>종신보험</td><td style="font-size:10px;color:#64748b">비갱신형</td><td>30%</td><td>55%</td><td>70%</td><td>85%</td><td>85%</td></tr>
              <tr><td>연금보험</td><td style="font-size:10px;color:#64748b">공시이율형</td><td>75%</td><td>88%</td><td>92%</td><td>96%</td><td>90%</td></tr>
              <tr><td>변액보험</td><td style="font-size:10px;color:#64748b">수익률 변동</td><td>50%</td><td>70%</td><td>80%</td><td>88%</td><td>80%</td></tr>
              <tr><td>저축보험</td><td style="font-size:10px;color:#64748b">저축성</td><td>80%</td><td>90%</td><td>94%</td><td>97%</td><td>90%</td></tr>
              <tr><td>유니버셜</td><td style="font-size:10px;color:#64748b">유니버셜형</td><td>60%</td><td>75%</td><td>83%</td><td>90%</td><td>85%</td></tr>
            </tbody>
          </table>
        </div>
        <p style="color:#94a3b8;font-size:10px;margin:6px 0 0">해지환급금률은 업계 평균 추정치입니다. 실제 해지환급금은 공시이율·특약·저해약환급금형 여부에 따라 다릅니다.</p>
      </div>
    </details>` : ''}
  </div>`;
}

function toggleSection(name) {
  const body   = document.getElementById('body-' + name);
  const toggle = document.getElementById('toggle-' + name);
  const opening = !body.classList.contains('open');
  body.classList.toggle('open', opening);
  toggle.classList.toggle('open', opening);
}

function updateFinancialSummary() {
  const income  = parseFloat(document.getElementById('cf-income').value) || 0;
  const assets  = parseFloat(document.getElementById('cf-assets').value) || 0;
  const debt    = parseFloat(document.getElementById('cf-debt').value) || 0;
  const cprem   = parseFloat(document.getElementById('cf-current-premium').value) || 0;
  const summaryEl = document.getElementById('financial-summary');

  if (!income && !assets && !debt) {
    summaryEl.classList.remove('visible');
    return;
  }

  const monthlyIncome = income / 12;
  let rows = '';

  if (income)
    rows += `<div class="financial-summary-row"><span>월 환산 소득</span><span><strong>${Math.round(monthlyIncome).toLocaleString()}만원</strong>/월</span></div>`;

  if (debt && income) {
    const ratio = (debt / income * 100).toFixed(0);
    const [cls, lbl] = ratio < 100 ? ['risk-low','양호'] : ratio < 300 ? ['risk-med','보통'] : ['risk-high','과다'];
    rows += `<div class="financial-summary-row"><span>부채비율 (부채÷연소득)</span><span><strong>${ratio}%</strong> <span class="risk-badge ${cls}">${lbl}</span></span></div>`;
  }

  if (cprem && income) {
    const avail = Math.max(0, monthlyIncome * 0.15 - cprem);
    rows += `<div class="financial-summary-row"><span>추가 가입 여력 (소득 15% 기준)</span><span><strong>≈ ${avail.toFixed(0)}만원</strong>/월</span></div>`;
  }

  if (assets)
    rows += `<div class="financial-summary-row"><span>금융자산</span><span><strong>${assets.toLocaleString()}만원</strong></span></div>`;

  summaryEl.innerHTML = `<div style="font-weight:700;margin-bottom:6px;color:#0369a1">📊 재무 현황 분석</div>${rows}`;
  summaryEl.classList.add('visible');
}

// ── Portfolio generation ───────────────────────────────────
async function generatePortfolio() {
  const age    = parseInt(document.getElementById('cf-age').value);
  const gender = document.getElementById('cf-gender').value;
  const budget = parseInt(document.getElementById('cf-budget').value);
  const nice   = parseInt(document.getElementById('cf-nice').value);
  const kcb    = parseInt(document.getElementById('cf-kcb').value);
  const married  = document.getElementById('cf-married').value;
  const existing = document.getElementById('cf-existing').value.trim();
  const health   = document.getElementById('cf-health').value.trim();

  // 금융데이터
  const income     = parseFloat(document.getElementById('cf-income').value) || null;
  const assets     = parseFloat(document.getElementById('cf-assets').value) || null;
  const debt       = parseFloat(document.getElementById('cf-debt').value) || null;
  const curPremium = parseFloat(document.getElementById('cf-current-premium').value) || null;

  // 대안데이터
  const employment = document.getElementById('cf-employment').value;
  const housing    = document.getElementById('cf-housing').value;
  const telecom    = document.getElementById('cf-telecom').value;
  const utility    = document.getElementById('cf-utility').value;

  // 의료이력
  const medConditions     = getCheckedConditions();
  const hospitalization   = document.getElementById('cf-hospitalization').value;
  const currentMedications = document.getElementById('cf-medications').value.trim();

  if (!age || age < 20 || age > 70) { alert('나이를 20~70세 사이로 입력해주세요.'); return; }
  if (!budget || budget < 5)        { alert('월 예산을 입력해주세요 (최소 5만원).'); return; }

  const hasNice = !isNaN(nice) && nice >= 300 && nice <= 1000;
  const hasKcb  = !isNaN(kcb)  && kcb  >= 300 && kcb  <= 1000;
  if (!hasNice && !hasKcb) { alert('NICE 또는 KCB 신용점수 중 하나 이상을 입력해주세요.'); return; }

  const scores = [];
  if (hasNice) scores.push({ source: 'NICE', score: nice });
  if (hasKcb)  scores.push({ source: 'KCB',  score: kcb  });
  const avgScore = Math.round(scores.reduce((s,x) => s + x.score, 0) / scores.length);
  const tier = scoreTier(avgScore);

  // Show result area with loading
  const resultEl = document.getElementById('credit-result');
  const bodyEl   = document.getElementById('credit-result-body');
  const pillEl   = document.getElementById('result-score-pill');
  resultEl.style.display = 'block';
  resultEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
  pillEl.textContent = `${avgScore}점 (${tier.label})`;
  bodyEl.innerHTML = '<div class="credit-loading"><div class="spin"></div>포트폴리오 생성 중... (30~60초 소요)</div>';

  const btn = document.getElementById('gen-btn');
  btn.disabled = true;
  btn.textContent = '⏳ 생성 중...';

  try {
    const resp = await fetch('/api/credit-portfolio', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        age, gender, budget_man: budget, scores, avg_score: avgScore,
        married, existing_insurance: existing, health_notes: health,
        financial_data: { income, assets, debt, current_premium: curPremium },
        alt_data: { employment, housing, telecom, utility },
        medical_data: { conditions: medConditions, hospitalization, current_medications: currentMedications }
      })
    });
    const data = await resp.json();
    if (data.error) {
      bodyEl.innerHTML = `<p style="color:#dc2626">⚠️ ${data.error}</p>`;
    } else {
      // 종합 적합도 카드 렌더링
      const cardArea = document.getElementById('composite-score-card-area');
      if (data.composite_score_data) {
        cardArea.innerHTML = renderCompositeCard(data.composite_score_data);
        const cs = data.composite_score_data;
        pillEl.textContent = `종합 ${cs.composite_score}점 (${cs.grade})`;
      } else {
        cardArea.innerHTML = '';
      }
      // 약관대출 카드 렌더링
      const loanArea = document.getElementById('policy-loan-card-area');
      if (loanArea) {
        loanArea.innerHTML = renderPolicyLoanCard(data.policy_loan_data);
      }
      bodyEl.innerHTML = addLinksToTables(marked.parse(preprocessMd(data.result || '결과가 없습니다.')));
    }
  } catch(e) {
    bodyEl.innerHTML = '<p style="color:#dc2626">⚠️ 서버 연결 오류가 발생했습니다.</p>';
  } finally {
    btn.disabled = false;
    btn.textContent = '💳 신용점수 반영 포트폴리오 생성';
  }
}

// 초기화
checkMode();
addMessage('bot',
  '안녕하세요! **보험 상담 AI 어시스턴트**입니다. 🛡️\n\n' +
  '**종신보험, 실손의료보험, 암보험, 치아보험, 간병·치매보험, 연금보험** 상담을 도와드립니다.\n\n' +
  '보험다모아 공시 데이터 + 실시간 웹 검색을 통해 최신 정보로 답변드립니다.\n\n' +
  '나이, 성별, 예산을 알려주시면 더 정확한 추천이 가능합니다!\n\n' +
  '> 예시: *"50대 남성, 간병보험 보험사별로 비교해줘"*'
);
</script>
</body>
</html>"""


# ── Routes ────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template_string(HTML)


def _check_api_live():
    """실제 API 호출로 키 유효 여부 확인 (결과를 60초 캐싱)"""
    now = __import__('time').time()
    cached = _check_api_live._cache
    if cached['ts'] and now - cached['ts'] < 60:
        return cached['result']

    api_key = os.getenv('OPENAI_API_KEY', '')
    if not api_key:
        result = False
    else:
        try:
            import openai as _oai
            _oai.OpenAI(api_key=api_key).chat.completions.create(
                model='gpt-4o-mini',
                max_tokens=1,
                messages=[{'role': 'user', 'content': 'hi'}],
            )
            result = True
        except Exception:
            result = False

    _check_api_live._cache = {'ts': now, 'result': result}
    return result

_check_api_live._cache = {'ts': None, 'result': False}

# 사용자가 수동으로 선택한 모드: 'auto', 'live', 'mock'
forced_mode = 'auto'


@app.route('/api/set-mode', methods=['POST'])
def set_mode():
    global forced_mode
    mode = request.json.get('mode', 'auto')
    if mode not in ('auto', 'live', 'mock'):
        return jsonify({'error': '유효하지 않은 모드'}), 400
    forced_mode = mode
    # 캐시 무효화해서 다음 요청에서 재확인
    _check_api_live._cache = {'ts': None, 'result': False}
    live = _check_api_live()
    effective = _get_effective_mode(live)
    return jsonify({'forced_mode': forced_mode, 'effective_mode': effective})


def _get_effective_mode(api_live: bool) -> str:
    if forced_mode == 'live':
        return 'live'
    if forced_mode == 'mock':
        return 'mock'
    return 'live' if api_live else 'mock'


@app.route('/api/status')
def status():
    live = _check_api_live()
    effective = _get_effective_mode(live)
    return jsonify({'mode': effective, 'effective_mode': effective, 'forced_mode': forced_mode})


@app.route('/api/credit-portfolio', methods=['POST'])
def credit_portfolio():
    """신용점수 입력 기반 보험 포트폴리오 생성"""
    data = request.json or {}
    age           = data.get('age')
    gender        = data.get('gender', '남')
    budget_man    = data.get('budget_man')        # 만원 단위
    scores        = data.get('scores', [])        # [{'source':'NICE','score':820}, ...]
    avg_score     = data.get('avg_score')
    married       = data.get('married', '')
    existing      = data.get('existing_insurance', '')
    health        = data.get('health_notes', '')
    financial_data = data.get('financial_data', {}) or {}
    alt_data      = data.get('alt_data', {}) or {}
    medical_data  = data.get('medical_data', {}) or {}

    if not age or not budget_man or not scores:
        return jsonify({'error': '나이, 예산, 신용점수를 모두 입력해주세요.'}), 400

    # 종합 적합도 점수 산출 (항상 계산)
    from data.credit_model import (
        calculate_composite_score, get_financial_profile_summary, get_credit_summary_for_prompt
    )
    cs = calculate_composite_score(avg_score, financial_data, alt_data, medical_data)

    api_live = _check_api_live()
    effective = _get_effective_mode(api_live)

    if effective == 'live':
        try:
            from agents.orchestrator import InsuranceChatbot
            bot = InsuranceChatbot()

            score_parts = [f"{s['source']} {s['score']}점" for s in scores]
            score_str = ' / '.join(score_parts)
            married_str = f", {married}" if married else ""
            existing_str = f"\n- 현재 가입 보험: {existing}" if existing else ""
            health_str = f"\n- 건강 특이사항: {health}" if health else ""

            # 의료이력 요약
            conditions = medical_data.get("conditions", [])
            hosp = medical_data.get("hospitalization", "")
            meds = medical_data.get("current_medications", "")
            med_lines = []
            if conditions:
                med_lines.append(f"- 최근 5년 치료 이력: {', '.join(conditions)}")
            if hosp:
                med_lines.append(f"- 최근 5년 입원: {hosp}")
            if meds:
                med_lines.append(f"- 현재 복용 약물: {meds}")
            med_section = ("\n" + "\n".join(med_lines)) if med_lines else ""

            # 금융·대안데이터 분석
            fin_profile = get_financial_profile_summary(financial_data, alt_data)
            fin_section = f"\n\n{fin_profile}" if fin_profile.strip() else ""

            # 종합 점수 분석 블록
            adj_str = "\n".join(
                f"  • {a['factor']}: {'+' if a['delta']>=0 else ''}{a['delta']}점 ({a['reason']})"
                for a in cs['adjustments']
            )
            cs_section = (
                f"\n\n## 종합 보험 가입 적합도 분석 결과\n"
                f"- 기본 신용점수: {cs['base_score']}점\n"
                f"- 조정 항목:\n{adj_str}\n"
                f"- **종합 적합도 지수: {cs['composite_score']}점 ({cs['grade']})**\n"
                f"- 보험 심사 위험도: {cs['underwriting_risk']}\n"
                f"- 권장 상품군: {', '.join(cs['preferred_products'][:4])}\n"
                f"- 신중 검토: {', '.join(cs['avoid_products'][:3]) if cs['avoid_products'] else '없음'}"
            )

            msg = (
                f"{age}세 {gender}성{married_str}, 월 예산 {budget_man}만원으로 "
                f"보험 포트폴리오 추천해줘.\n"
                f"신용점수: {score_str} (평균 {avg_score}점)"
                f"{existing_str}{health_str}{med_section}"
                f"{fin_section}{cs_section}\n\n"
                f"위 종합 적합도 분석을 바탕으로 각 상품 추천 이유를 구체적으로 설명하고, "
                f"보험 심사 위험도({cs['underwriting_risk']})와 신용등급({cs['grade']})이 "
                f"추천에 어떻게 반영됐는지 반드시 포함해줘."
            )
            result = bot.chat(msg)
            from data.credit_model import parse_recommended_products, calculate_policy_loans
            loan_data = calculate_policy_loans(parse_recommended_products(result))
            return jsonify({'result': result, 'avg_score': avg_score, 'composite_score_data': cs, 'policy_loan_data': loan_data})
        except Exception as e:
            return jsonify({'error': f'포트폴리오 생성 실패: {str(e)}'}), 500
    else:
        # Mock fallback
        tier_info = get_credit_summary_for_prompt(avg_score)
        fin_profile = get_financial_profile_summary(financial_data, alt_data)
        fin_section = f"\n{fin_profile}" if fin_profile.strip() else ""

        conditions = medical_data.get("conditions", [])
        med_rows = []
        if conditions: med_rows.append(f"치료 이력: {', '.join(conditions)}")
        if medical_data.get("hospitalization"): med_rows.append(f"입원: {medical_data['hospitalization']}")
        if medical_data.get("current_medications"): med_rows.append(f"복용 약물: {medical_data['current_medications']}")
        alt_rows = []
        if alt_data.get("employment"): alt_rows.append(f"직업: {alt_data['employment']}")
        if alt_data.get("housing"):    alt_rows.append(f"거주: {alt_data['housing']}")
        all_extra = med_rows + alt_rows
        extra_section = ("\n- " + "\n- ".join(all_extra)) if all_extra else ""

        mock_result = f"""## 💳 신용점수 반영 보험 포트폴리오 (Mock 모드)

> ⚠️ **Mock 모드**: OpenAI API 키가 없어 샘플 결과를 표시합니다.

### 입력 정보
- 나이: {age}세 {gender}성 / 월 예산: {budget_man}만원
- 신용점수: {', '.join(f"{s['source']} {s['score']}점" for s in scores)} → 평균 **{avg_score}점**
- **종합 적합도 지수: {cs['composite_score']}점 ({cs['grade']})** (조정: {'+' if cs['total_delta']>=0 else ''}{cs['total_delta']}점){extra_section}

{tier_info}{fin_section}
### 📋 추천 포트폴리오 (샘플)

| 순위 | 보험 종류 | 추천 이유 | 예상 월보험료 |
|------|-----------|-----------|--------------|
| 1순위 | 실손의료보험 (5세대) | 기본 의료비 보장 필수 | 2~4만원 |
| 2순위 | 암보험 | 3대 질병 집중 보장 | 3~5만원 |
| 3순위 | 종신보험 | 사망/노후 자산 형성 | 5~8만원 |

> 실제 포트폴리오는 Live 모드에서 OpenAI API 키 설정 후 이용하세요.
"""
        from data.credit_model import parse_recommended_products, calculate_policy_loans
        mock_loan = calculate_policy_loans(parse_recommended_products(mock_result))
        return jsonify({'result': mock_result, 'avg_score': avg_score, 'composite_score_data': cs, 'policy_loan_data': mock_loan})


@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    message = data.get('message', '').strip()
    sid = data.get('session_id', 'default')

    if not message:
        return jsonify({'error': '메시지가 비어있습니다.'}), 400

    if sid not in sessions:
        sessions[sid] = {'context': MockContext(), 'chatbot': None}

    sess = sessions[sid]

    api_live = _check_api_live()
    effective = _get_effective_mode(api_live)

    # Live mode
    if effective == 'live':
        try:
            if sess['chatbot'] is None:
                from agents.orchestrator import InsuranceChatbot
                sess['chatbot'] = InsuranceChatbot()
            response = sess['chatbot'].chat(message)
            return jsonify({'response': response, 'mode': 'live'})
        except Exception as e:
            err = str(e)
            _check_api_live._cache = {'ts': None, 'result': False}
            sess['chatbot'] = None
            # 강제 Live 모드인데 실패하면 오류 반환
            if forced_mode == 'live':
                return jsonify({'error': f'Live Mode 오류: {err}'}), 500
            # Auto 모드면 Mock으로 fallback
            if 'credit' not in err.lower() and '400' not in err:
                return jsonify({'error': err}), 500

    # Mock mode
    try:
        response = mock_response(message, sess['context'])
        return jsonify({'response': response, 'mode': 'mock'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/chat/stream', methods=['POST'])
def chat_stream():
    data = request.json
    message = data.get('message', '').strip()
    sid = data.get('session_id', 'default')

    if not message:
        return jsonify({'error': '메시지가 비어있습니다.'}), 400

    if sid not in sessions:
        sessions[sid] = {'context': MockContext(), 'chatbot': None}

    sess = sessions[sid]
    api_live = _check_api_live()
    effective = _get_effective_mode(api_live)

    def generate():
        if effective == 'live':
            try:
                if sess['chatbot'] is None:
                    from agents.orchestrator import InsuranceChatbot
                    sess['chatbot'] = InsuranceChatbot()
                for event in sess['chatbot'].stream_chat(message):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                return
            except Exception as e:
                err = str(e)
                _check_api_live._cache['ts'] = None
                sess['chatbot'] = None
                if forced_mode == 'live':
                    yield f"data: {json.dumps({'type': 'error', 'message': f'Live Mode 오류: {err}'}, ensure_ascii=False)}\n\n"
                    return

        # Mock mode — return full response as single done event
        try:
            response = mock_response(message, sess['context'])
            yield f"data: {json.dumps({'type': 'done', 'full_text': response}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return Response(
        stream_with_context(generate()),
        content_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


@app.route('/api/reset', methods=['POST'])
def reset():
    sid = request.json.get('session_id', 'default')
    if sid in sessions:
        sessions[sid] = {'context': MockContext(), 'chatbot': None}
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    print("=" * 50)
    print("  보험 상담 AI 웹 서버 시작")
    print("=" * 50)
    print("  접속 주소: http://localhost:5000")
    print("  종료: Ctrl+C")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=False)
