from __future__ import annotations

import re

import pysubs2
import pytest

import translation_engine
from translation_engine import (
    InvalidTranslationResponse,
    build_sliding_prompt,
    parse_marked_translations,
    translate_subs,
)


class FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"choices": [{"message": {"content": self.content}}]}


def subtitles(*texts: str) -> pysubs2.SSAFile:
    result = pysubs2.SSAFile()
    for index, text in enumerate(texts):
        result.append(
            pysubs2.SSAEvent(
                start=index * 2_000,
                end=index * 2_000 + 1_500,
                text=text,
            )
        )
    return result


def marked(values: dict[int, str]) -> str:
    return "\n".join(
        f"[[SF_{index:06d}]]\n{value}\n[[/SF_{index:06d}]]"
        for index, value in values.items()
    )


def requested_ids(payload: dict) -> list[int]:
    user_content = payload["messages"][1]["content"]
    return [
        int(value)
        for value in re.findall(r"\[\[SF_(\d{6})\]\]", user_content)
    ]


def test_marker_parser_requires_exactly_the_requested_ids() -> None:
    assert parse_marked_translations(marked({2: "Deux", 3: "Trois"}), [2, 3]) == [
        "Deux",
        "Trois",
    ]

    with pytest.raises(InvalidTranslationResponse, match="missing SF_000003"):
        parse_marked_translations(marked({2: "Deux"}), [2, 3])


def test_sliding_prompt_includes_prior_translation_and_future_source() -> None:
    prompt = build_sliding_prompt(
        ["Before", "Translate me", "After"],
        [1],
        ["Avant", None, None],
        previous_context=1,
        next_context=1,
    )

    assert "ACCEPTED TARGET:\nAvant" in prompt
    assert "[[SF_000001]]\nTranslate me\n[[/SF_000001]]" in prompt
    assert "SOURCE SF_000002:\nAfter" in prompt


def test_sliding_translation_preserves_timing_and_uses_accepted_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []

    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        calls.append(json)
        ids = requested_ids(json)
        return FakeResponse(marked({index: f"T{index}" for index in ids}))

    monkeypatch.setattr(translation_engine.requests, "post", fake_post)
    subs = subtitles("A", "B", "C")
    timings = [(line.start, line.end) for line in subs]

    updates = list(
        translate_subs(
            subs,
            "http://localhost:1234/v1/",
            "model",
            "English",
            "French",
            mode="sliding",
            group_size=2,
            previous_context=2,
            next_context=2,
            consistency_pass=False,
        )
    )

    assert [line.text for line in subs] == ["T0", "T1", "T2"]
    assert [(line.start, line.end) for line in subs] == timings
    assert [update[0] for update in updates] == [0.5, 1.0]
    assert "ACCEPTED TARGET:\nT0" in calls[1]["messages"][1]["content"]
    assert calls[0]["temperature"] == 0.4


def test_consistency_pass_revises_validated_translation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []

    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        calls.append(json)
        ids = requested_ids(json)
        reviewing = "consistency review" in json["messages"][0]["content"]
        prefix = "R" if reviewing else "T"
        return FakeResponse(marked({index: f"{prefix}{index}" for index in ids}))

    monkeypatch.setattr(translation_engine.requests, "post", fake_post)
    subs = subtitles("A", "B", "C", "D")

    updates = list(
        translate_subs(
            subs,
            "http://localhost/v1",
            "model",
            "English",
            "French",
            group_size=4,
            consistency_pass=True,
            consistency_group_size=4,
            consistency_context=8,
        )
    )

    assert [line.text for line in subs] == ["R0", "R1", "R2", "R3"]
    assert [update[0] for update in updates] == [0.5, 1.0]
    assert len(calls) == 2
    assert calls[0]["temperature"] == 0.4
    assert calls[1]["temperature"] == 0.3


def test_invalid_group_is_retried_then_falls_back_to_individual(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []

    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        calls.append(json)
        ids = requested_ids(json)
        if ids:
            return FakeResponse("marker format was not followed")
        source = json["messages"][1]["content"]
        return FakeResponse(f"T-{source}")

    monkeypatch.setattr(translation_engine.requests, "post", fake_post)
    subs = subtitles("A", "B")

    list(
        translate_subs(
            subs,
            "http://localhost/v1",
            "model",
            "English",
            "French",
            group_size=2,
            consistency_pass=False,
            retry_invalid=True,
        )
    )

    assert [line.text for line in subs] == ["T-A", "T-B"]
    assert len(calls) == 5


def test_invalid_consistency_review_keeps_first_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_number = 0

    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        nonlocal call_number
        call_number += 1
        ids = requested_ids(json)
        if call_number == 1:
            return FakeResponse(marked({index: f"T{index}" for index in ids}))
        return FakeResponse("invalid review")

    monkeypatch.setattr(translation_engine.requests, "post", fake_post)
    subs = subtitles("A", "B")

    list(
        translate_subs(
            subs,
            "http://localhost/v1",
            "model",
            "English",
            "French",
            group_size=2,
            consistency_pass=True,
            consistency_group_size=2,
        )
    )

    assert [line.text for line in subs] == ["T0", "T1"]


def test_individual_mode_protects_formatting_and_line_breaks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_post(url: str, json: dict, timeout: int) -> FakeResponse:
        protected = json["messages"][1]["content"]
        assert "<i>" not in protected
        assert r"\N" not in protected
        return FakeResponse(
            "__SF_FMT_000__Bonjour__SF_FMT_001____SF_FMT_002__ici"
        )

    monkeypatch.setattr(translation_engine.requests, "post", fake_post)
    subs = subtitles(r"<i>Hello</i>\Nthere")

    list(
        translate_subs(
            subs,
            "http://localhost/v1",
            "model",
            "English",
            "French",
            mode="individual",
            consistency_pass=False,
        )
    )

    assert subs[0].text == r"<i>Bonjour</i>\Nici"
