"""주간 갱신 안전장치 — 막아야 할 것을 실제로 막는가."""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import hub_guard as g  # noqa: E402

REL_HEAD = ",".join(g.RELEASE_COLS)
MEDIA_OK = ",".join(g.MEDIA_COLS) + "\n전자신문,일간,3,4\n"
META_OK = {"기준일": "2026-11-10"}


def rel_text(n: int, link: str = "https://www.kitech.re.kr/pages/61?id=1") -> str:
    row = f"1,2026-10-01,제목,3,2,,전자신문,2026-10-01,0,확정,{link}"
    return "﻿" + REL_HEAD + "\n" + "\n".join([row] * n) + "\n"


def test_valid_perf_passes() -> None:
    assert g.validate_perf(rel_text(10), MEDIA_OK, META_OK, prev_rel_rows=10) == []


def test_forbidden_column_blocked() -> None:
    bad = rel_text(1).replace("매체명", "매체(기자)")
    probs = g.validate_perf(bad, MEDIA_OK, META_OK, 0)
    assert any("공개 금지" in p for p in probs)


def test_shrink_blocked() -> None:
    probs = g.validate_perf(rel_text(90), MEDIA_OK, META_OK, prev_rel_rows=100)
    assert any("줄었습니다" in p for p in probs)
    assert g.validate_perf(rel_text(96), MEDIA_OK, META_OK, prev_rel_rows=100) == []


def test_non_homepage_link_blocked() -> None:
    probs = g.validate_perf(rel_text(2, link=""), MEDIA_OK, META_OK, 0)
    assert any("홈페이지 링크" in p for p in probs)


def test_missing_meta_date_blocked() -> None:
    assert g.validate_perf(rel_text(1), MEDIA_OK, {}, 0) == ["meta에 기준일이 없습니다"]


def test_dataset_shrink_detects_wiped_channel() -> None:
    prev = Counter({"보도자료": 247, "포토뉴스": 1085})
    assert g.shrink_problems(prev, Counter({"보도자료": 260, "포토뉴스": 1100})) == []
    assert g.shrink_problems(prev, Counter({"보도자료": 260})) == ["포토뉴스: 1085→0건"]


def test_channel_counts_handles_bom() -> None:
    text = "﻿채널,제목\n보도자료,a\n블로그,b\n블로그,c\n"
    assert g.channel_counts(text) == Counter({"보도자료": 1, "블로그": 2})
