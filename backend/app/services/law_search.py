"""국가법령정보 공동활용(law.go.kr) Open API — 법령 조문 검색.

AI 도우미 법령 탭의 grounding 자료를 만든다.

law.go.kr의 본문검색(``search=2``)은 전체 법령(수만 건)에서 키워드가 한 번이라도
나오는 법령을 관련도 순이 아니라 사실상 법령명 순으로 반환한다 — 세무사 질문 같은
자연어 검색에는 쓸 수 없다 (실측: "상실신고"로 647건, 상위 결과가 전부 무관한 법).

대신 이 서비스가 다루는 영역의 핵심 법령만 고정 목록으로 들고, 그 조문 전체를
한 번 받아 프로세스 메모리에 캐싱한 뒤, 질문 키워드와 조문 텍스트를 직접
매칭해서 상위 N개 조문만 골라 grounding 자료로 쓴다. 임베딩 없는 단순 키워드
스코어링이지만, 법령당 조문이 수백 개 수준이라 이 정도로 충분하다.

인증은 OC 파라미터(가입 이메일의 @ 앞부분) 하나뿐, 별도 API 키 없음.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_SEARCH_URL = "http://www.law.go.kr/DRF/lawSearch.do"
_SERVICE_URL = "http://www.law.go.kr/DRF/lawService.do"

# 세무사사무소 업무 범위의 핵심 법령. 이름으로 검색하면 법률과 시행령이 함께
# 반환되므로(law.go.kr의 법령명 검색이 부분일치) 베이스 이름만 적는다.
#
# 국세법령정보시스템(taxlaw.nts.go.kr) "조세법령목록"(action.do, actionId=
# ASISTA001MR01)의 주요세법·기타세법 및 관련법령 전체(2026-10-01 조회, 34건) +
# 4대보험 관련법(국민연금법 등, NTS 목록엔 없지만 원천세·급여 업무에 필수).
_CORE_LAWS = [
    # --- 주요세법 (국세법령정보시스템) ---
    "국세기본법",
    "국세징수법",
    "조세특례제한법",
    "농ㆍ축산ㆍ임ㆍ어업용 기자재 및 석유류에 대한 부가가치세 영세율 및 면세 적용 등에 관한 특례규정",
    "외국인관광객 등에 대한 부가가치세 및 개별소비세 특례규정",
    "소득세법",
    "법인세법",
    "국제조세조정에 관한 법률",
    "상속세 및 증여세법",
    "종합부동산세법",
    "부가가치세법",
    "개별소비세법",
    "주세법",
    "주류 면허 등에 관한 법률",
    "교통ㆍ에너지ㆍ환경세법",
    "인지세법",
    "증권거래세법",
    # --- 기타세법 및 관련법령 (국세법령정보시스템) ---
    "과세자료의 제출 및 관리에 관한 법률",
    "관세법",
    "교육세법",
    "국세청과 그 소속기관 직제",
    "금융실명거래 및 비밀보장에 관한 법률",
    "농어촌특별세법",
    "부동산 실권리자명의 등기에 관한 법률",
    "상가건물 임대차보호법",
    "자산재평가법",
    "조세범 처벌법",
    "조세범 처벌절차법",
    "지방세법",
    "지방세기본법",
    "지방세징수법",
    "지방세특례제한법",
    "질서위반행위규제법",
    "취업 후 학자금 상환 특별법",
    # --- 4대보험 (NTS 목록 외, 원천세·급여 업무 필수) ---
    "국민연금법",
    "국민건강보험법",
    "고용보험법",
    "고용보험 및 산업재해보상보험의 보험료징수 등에 관한 법률",
]

# 법률+시행령까지만 가져온다 (시행규칙=서식 위주라 Q&A grounding 가치가 낮고 양만 늘어남).
_VARIANTS_PER_LAW = 2

_PARTICLES = (
    "으로부터", "에게서", "까지는", "부터는",
    "으로써", "으로서", "에게", "한테", "부터", "까지", "에서", "에는",
    "이나", "이란", "라는", "이라",
    "은", "는", "이", "가", "을", "를", "의", "에", "로", "와", "과", "도", "만",
)

# 세무사가 구어체로 묻는 표현이 법령 원문엔 그대로 안 나오는 경우가 많다
# (예: "4대보험"은 법령에 없고 각 법이 국민연금/건강보험/고용보험/산재보험을 따로 부른다).
# 매칭 재현율을 위해 질문 키워드에서 법령 용어를 보충한다.
_ALIASES: dict[str, list[str]] = {
    "4대보험": ["국민연금", "건강보험", "고용보험", "산재보험", "산업재해보상보험"],
    "퇴사자": ["퇴직", "자격상실"],
    "퇴사": ["퇴직", "자격상실"],
    "원천세": ["원천징수"],
    "부가세": ["부가가치세"],
}

_cache_lock = asyncio.Lock()
_articles_cache: dict[str, list[dict[str, Any]]] | None = None


async def search_laws(query: str, oc: str, *, display: int = 3) -> list[dict[str, Any]]:
    """법령명으로 법령을 검색한다 (부분일치 — 법률+시행령+시행규칙이 함께 나온다)."""
    params = {"OC": oc, "target": "law", "type": "JSON", "query": query, "display": display}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(_SEARCH_URL, params=params)
    resp.raise_for_status()
    data = resp.json()
    laws = data.get("LawSearch", {}).get("law", [])
    if isinstance(laws, dict):
        laws = [laws]
    return laws


async def fetch_law_articles(mst: str, oc: str) -> list[dict[str, Any]]:
    """법령 전체 조문을 가져온다 (법령일련번호 MST 기준)."""
    params = {"OC": oc, "target": "law", "MST": mst, "type": "JSON"}
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(_SERVICE_URL, params=params)
    resp.raise_for_status()
    data = resp.json()
    units = data.get("법령", {}).get("조문", {}).get("조문단위", [])
    return _as_list(units)


# law.go.kr 법령명 검색은 순수 부분일치가 아니라 느슨한 매칭이라, 예를 들어
# "지방세법"을 검색하면 "지방교부세법"이 더 먼저 나와 display 개수 안에 정작
# "지방세법"이 못 들어오는 경우가 있다 — 넓게 가져온 뒤 정확히 일치하는 것만 쓴다.
_SEARCH_DISPLAY = 20


async def _with_retry(coro_fn, *, attempts: int = 2):
    last_exc: BaseException | None = None
    for i in range(attempts):
        try:
            return await coro_fn()
        except httpx.HTTPError as e:
            last_exc = e
            if i < attempts - 1:
                await asyncio.sleep(1)
    raise last_exc  # type: ignore[misc]


async def _load_core_law_pool(oc: str) -> dict[str, list[dict[str, Any]]]:
    """``_CORE_LAWS``의 조문을 전부 받아 ``{법령명: 조문단위[]}``로 캐싱한다.

    프로세스 생애주기 동안 1회만 받는다 — 법령 개정은 자주 일어나지 않고,
    배포 때마다 프로세스가 재시작되므로 그때 자연스럽게 갱신된다.
    """
    global _articles_cache
    if _articles_cache is not None:
        return _articles_cache

    async with _cache_lock:
        if _articles_cache is not None:
            return _articles_cache

        resolved: list[tuple[str, str]] = []  # (법령명, MST)
        search_results = await asyncio.gather(
            *(
                _with_retry(lambda n=name: search_laws(n, oc, display=_SEARCH_DISPLAY))
                for name in _CORE_LAWS
            ),
            return_exceptions=True,
        )
        for query_name, result in zip(_CORE_LAWS, search_results, strict=True):
            if isinstance(result, BaseException):
                logger.warning("law.go.kr search failed for %r", query_name, exc_info=result)
                continue
            matched = [
                law
                for law in result
                if (law.get("법령명한글") or "") == query_name
                or (law.get("법령명한글") or "").startswith(query_name + " ")
            ]
            if not matched:
                logger.warning("law.go.kr search returned no exact match for %r", query_name)
            for law in matched[:_VARIANTS_PER_LAW]:
                mst = law.get("법령일련번호")
                law_name = law.get("법령명한글")
                if mst and law_name:
                    resolved.append((law_name, mst))

        fetch_results = await asyncio.gather(
            *(_with_retry(lambda m=mst: fetch_law_articles(m, oc)) for _, mst in resolved),
            return_exceptions=True,
        )
        pool: dict[str, list[dict[str, Any]]] = {}
        for (law_name, _mst), units in zip(resolved, fetch_results, strict=True):
            if isinstance(units, BaseException):
                logger.warning("law.go.kr fetch failed for %r", law_name, exc_info=units)
                continue
            pool[law_name] = units

        _articles_cache = pool
        return pool


def _strip_particle(word: str) -> str:
    for p in _PARTICLES:
        if len(word) > len(p) + 1 and word.endswith(p):
            return word[: -len(p)]
    return word


def _extract_keywords(query: str) -> tuple[list[str], list[str]]:
    """(핵심 키워드, 별칭 키워드) — 질문에 직접 쓰인 단어 vs 동의어 확장."""
    raw = [w for w in re.split(r"[\s,·/()]+", query) if len(w) >= 2]
    core = {_strip_particle(w) for w in raw}
    aliases: set[str] = set()
    for w in core:
        aliases.update(_ALIASES.get(w, []))
    aliases -= core
    return list(core), list(aliases)


def _article_label(unit: dict[str, Any]) -> str:
    label = f"제{unit.get('조문번호')}조"
    branch = unit.get("조문가지번호")
    if branch:
        label += f"의{branch}"
    return label


def _as_list(value: Any) -> list[Any]:
    """law.go.kr은 단일 원소일 때 리스트 대신 dict/str 하나만 준다 — 정규화."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _article_text(unit: dict[str, Any]) -> str:
    """조문단위 하나를 조문내용 + 항 + 호 텍스트로 풀어 이어붙인다."""
    parts = []
    content = (unit.get("조문내용") or "").strip()
    if content:
        parts.append(content)
    for hang in _as_list(unit.get("항")):
        if isinstance(hang, str):
            if hang.strip():
                parts.append(hang.strip())
            continue
        hang_text = (hang.get("항내용") or "").strip()
        if hang_text:
            parts.append(hang_text)
        for ho in _as_list(hang.get("호")):
            if isinstance(ho, str):
                if ho.strip():
                    parts.append("  " + ho.strip())
                continue
            ho_text = (ho.get("호내용") or "").strip()
            if ho_text:
                parts.append("  " + ho_text)
    return "\n".join(parts)


def _title_weight(keyword: str) -> int:
    """짧은 낱말일수록 여러 무관한 복합어 안에 부분 일치로 끼어들 확률이 높다.

    "기한"(2자)은 "납부기한"·"제출기한"·"신고기한"처럼 전혀 다른 주제의 제목에
    흔히 섞여 있어, 긴 복합어("상실신고" 등)와 같은 가중치를 주면 흔한 낱말이
    구체적인 낱말을 밀어낸다. 글자 수로 구체성을 근사한다 — 진짜 IDF는 아니지만
    이 정도면 충분하다.
    """
    n = len(keyword)
    if n >= 4:
        return 12
    if n == 3:
        return 6
    return 2


def _keyword_score(title: str, body: str, core_kw: list[str], alias_kw: list[str]) -> int:
    """핵심 키워드는 제목 일치에 큰 가중치, 별칭은 본문 보강에만 쓴다.

    두 가지 문제를 추가로 교정한다:
    1. 본문 반복은 "기한" 같은 흔한 낱말이 긴 조문 안에서 수없이 반복돼 점수를
       부풀리므로, 조문당 최대 3회까지만 반영.
    2. 법령 원문은 "상실 신고"처럼 띄어 쓰지만 질문은 "상실신고"로 붙여 쓰는 경우가
       많아 제목이 매칭되지 않는 문제 → 제목은 공백을 제거하고 비교.
    3. "4대보험" 같은 별칭 확장 키워드를 제목 매칭에 그대로 쓰면, 그 법 전체가
       해당 주제라서(예: 보험료징수법의 거의 모든 조문 제목에 "산재보험") 무관한
       조문까지 상위로 몰린다 → 별칭은 본문 보강에만 쓰고 제목 가중치는 주지 않는다.
    """
    title_nospace = title.replace(" ", "")
    score = 0
    for kw in core_kw:
        score += _title_weight(kw) * title_nospace.count(kw)
        score += min(body.count(kw), 3)
    for kw in alias_kw:
        score += min(body.count(kw), 2)
    return score


async def build_law_context(query: str, oc: str, *, max_articles: int = 6) -> str:
    """질문과 관련된 조문을 모아 LLM 프롬프트에 넣을 grounding 텍스트를 만든다.

    관련 조문을 못 찾으면 빈 문자열을 반환한다 — 호출부는 이 경우 grounding
    없이(=학습 지식 기반으로만) 답하도록 처리해야 한다.
    """
    core_kw, alias_kw = _extract_keywords(query)
    if not core_kw:
        return ""

    pool = await _load_core_law_pool(oc)
    if not pool:
        return ""

    scored: list[tuple[int, str, dict[str, Any], str]] = []
    for law_name, units in pool.items():
        for unit in units:
            if unit.get("조문여부") != "조문":
                continue
            text = _article_text(unit)
            if not text:
                continue
            score = _keyword_score(unit.get("조문제목") or "", text, core_kw, alias_kw)
            if score > 0:
                scored.append((score, law_name, unit, text))

    scored.sort(key=lambda t: t[0], reverse=True)
    blocks = [
        f"[{law_name} {_article_label(unit)}] {text}"
        for _score, law_name, unit, text in scored[:max_articles]
    ]
    return "\n\n".join(blocks)


__all__ = ["build_law_context", "fetch_law_articles", "search_laws"]
