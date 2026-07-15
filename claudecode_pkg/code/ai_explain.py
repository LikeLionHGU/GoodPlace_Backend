"""
AI 해설 생성 (담당 B · P4). 리포트 확정 수치 → 창업자용 자연어 3~5문장.

환각 억제(근거 게이트의 LLM 판 — 08 §4.5·09 보드 확정):
- 입력 = 우리가 계산한 **확정 수치 JSON만**. 시스템 지시에 "이 수치 외 새 숫자·업종·사실 생성 금지,
  성공/수익 보장 표현 금지, '투자/펀딩' 금지" 고정.
- 출력 검증: 생성문의 숫자를 뽑아 화이트리스트(입력 수치)에 없으면 폐기·재생성(숫자 화이트리스트 검사).
  금칙어·보장 표현 있으면 폐기. 실패 시 해설 없이 None(수치 리포트만 — 조용한 대체·환각 금지).
- 키는 환경변수 OPENAI_API_KEY 에만. 코드·로그·응답에 평문·원문 body 노출 금지. 키 없으면 해설 None.

모델: OpenAI GPT(팀 보유 키). model·base_url 은 env 로 교체 가능(OPENAI_MODEL/OPENAI_BASE_URL).
※ 실제 API 호출 경로는 키 확보 후 검증 대상. 순수 로직(facts·프롬프트·검증)은 키 없이 테스트된다.
"""
import os
import re

# '투자/펀딩' 등은 단어 자체 금지(유사수신 회피 · 용어 규칙).
BANNED_WORDS = ("투자", "펀딩")

SYSTEM_PROMPT = (
    "너는 창업 리포트의 확정 수치를 예비창업자에게 설명하는 도우미다. 규칙을 반드시 지켜라:\n"
    "1) 입력 JSON 에 있는 숫자·업종·지명만 쓴다. 새로운 숫자·통계·업종·지명을 만들지 마라.\n"
    "2) 성공이나 수익을 보장하는 표현을 쓰지 마라. '투자·펀딩'이라는 단어를 쓰지 마라(선결제·쿠폰).\n"
    "3) 3~5문장, 담백한 한국어. 과장 없이 이미 있는 수치의 '의미'만 풀어 설명한다.\n"
    "4) 확정 수요(대기 고객)와 경쟁 상황을 중심으로, 이 자리를 '후보로 볼 이유'만 말한다."
)


def facts_from_report(report: dict) -> dict:
    """리포트에서 해설 입력으로 쓸 확정 수치만 추린다(순수). 새 값을 만들지 않는다."""
    c = report["conclusion"]
    wc = report["waiting_customers"]
    comp = report["competition"]
    demand = report["reasoning"]["factors"]["수요"]
    return {
        "공실": report["vacancy"]["name"],
        "추천업종": c["recommended_industry"],
        "적합도_percent": c["adequacy_pct"],
        "포화플래그": c["saturation_flag"],
        "대기고객_명": wc["count"],
        "쿠폰단가_원": wc["coupon_value_won"],
        "쿠폰총액_원": wc["count"] * wc["coupon_value_won"],
        "직접투표_명": demand["direct_votes"],
        "경쟁_동일업종_개수": comp["count"]["value"],
        "동네평균_개수": comp["neighborhood_avg"]["value"],
        "동네평균대비_배수": comp["competition_ratio"],
        "반경_m": comp["radius_m"],
    }


def allowed_numbers(facts: dict) -> set:
    """화이트리스트 = facts 안의 모든 수치(float 정규화)."""
    return {float(v) for v in facts.values() if isinstance(v, (int, float))}


_NUM_RE = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")


def extract_numbers(text: str) -> list:
    """텍스트에서 숫자 토큰 추출 → float. 천단위 콤마 제거."""
    return [float(tok.replace(",", "")) for tok in _NUM_RE.findall(text)]


def _has_guarantee(text: str) -> bool:
    """'보장' 표현 탐지. 단 '보장하지 않'·'보장 없' 같은 부정형은 허용(DISCLAIMER 정합)."""
    for m in re.finditer(r"보장", text):
        tail = text[m.end():m.end() + 4]
        if "않" in tail or "없" in tail:
            continue
        return True
    return False


def validate(text: str, allowed: set) -> tuple:
    """(ok, reason). 금칙어 → 보장 표현 → 숫자 화이트리스트 순으로 검사."""
    for w in BANNED_WORDS:
        if w in text:
            return False, f"금칙어: {w}"
    if _has_guarantee(text):
        return False, "성공/수익 보장 표현"
    for n in extract_numbers(text):
        if n not in allowed:
            return False, f"화이트리스트 밖 숫자: {n}"
    return True, "ok"


def build_messages(facts: dict) -> list:
    """OpenAI chat 메시지(system+user). 입력은 확정 수치 JSON 만."""
    import json
    user = ("다음은 한 빈 상가에 대한 확정 수치다. 이 수치만 근거로 3~5문장 해설을 써라.\n"
            + json.dumps(facts, ensure_ascii=False, indent=2))
    return [{"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user}]


def generate_explanation(report: dict, *, max_retries: int = 2, timeout: float = 20.0):
    """리포트 → AI 해설 {value, source} 또는 None.

    None 인 경우(전부 '조용한 실패' 아니라 '해설 없이 수치 리포트만'):
      - 키(OPENAI_API_KEY) 없음 / httpx 없음 / 호출 실패 / 재시도 후에도 검증 실패.
    성공: 검증 통과한 3~5문장 + 태그 'AI생성(수치는 원출처)'.
    """
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    try:
        import httpx
    except ImportError:
        return None

    facts = facts_from_report(report)
    allowed = allowed_numbers(facts)
    messages = build_messages(facts)
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")

    for _ in range(max_retries + 1):
        try:
            resp = httpx.post(
                f"{base}/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": model, "messages": messages, "temperature": 0.4},
                timeout=timeout,
            )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            return None   # 호출 실패 — 키·원문 노출 없이 조용히 해설만 생략
        ok, _reason = validate(text, allowed)
        if ok:
            return {"value": text, "source": "AI생성(수치는 원출처)"}
    return None            # 재시도 후에도 화이트리스트/금칙 위반 → 해설 없음
