"""Context-aware subtitle translation for OpenAI-compatible local APIs."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Iterator, Sequence

import requests


_MARKER_PATTERN = re.compile(
    r"\[\[SF_(\d{6})\]\]\s*(.*?)\s*\[\[/SF_\1\]\]",
    re.DOTALL,
)
_FORMAT_PATTERN = re.compile(r"\{[^}\r\n]*\}|</?[A-Za-z][^>]*>|\\[Nn]")


class InvalidTranslationResponse(ValueError):
    """Raised when a model does not return every requested subtitle marker."""


@dataclass(frozen=True)
class TranslationSettings:
    """Quality and context settings for subtitle translation."""

    mode: str = "sliding"
    group_size: int = 4
    previous_context: int = 8
    next_context: int = 8
    temperature: float = 0.4
    review_temperature: float = 0.3
    consistency_pass: bool = True
    consistency_group_size: int = 8
    consistency_context: int = 8
    retry_invalid: bool = True

    def validate(self) -> None:
        if self.mode not in {"individual", "sliding"}:
            raise ValueError("mode must be 'individual' or 'sliding'")
        for name in (
            "group_size",
            "previous_context",
            "next_context",
            "consistency_group_size",
            "consistency_context",
        ):
            value = getattr(self, name)
            minimum = 1 if "group_size" in name else 0
            if value < minimum:
                raise ValueError(f"{name} must be at least {minimum}")
        for name in ("temperature", "review_temperature"):
            if not 0 <= getattr(self, name) <= 2:
                raise ValueError(f"{name} must be between 0 and 2")


def _marker(index: int) -> str:
    return f"SF_{index:06d}"


def _marked_text(index: int, text: str) -> str:
    marker = _marker(index)
    return f"[[{marker}]]\n{text}\n[[/{marker}]]"


def _protect_formatting(text: str) -> tuple[str, dict[str, str]]:
    """Replace formatting and subtitle line breaks with immutable placeholders."""
    replacements: dict[str, str] = {}

    def replace(match: re.Match[str]) -> str:
        placeholder = f"__SF_FMT_{len(replacements):03d}__"
        replacements[placeholder] = match.group(0)
        return placeholder

    return _FORMAT_PATTERN.sub(replace, text), replacements


def _restore_formatting(text: str, replacements: dict[str, str]) -> str:
    for placeholder, original in replacements.items():
        if text.count(placeholder) != 1:
            raise InvalidTranslationResponse(
                f"The model changed subtitle formatting token {placeholder}"
            )
        text = text.replace(placeholder, original)
    return text


def _context_entry(
    index: int,
    source: str,
    translations: Sequence[str | None],
) -> str:
    result = f"SOURCE {_marker(index)}:\n{source}"
    if index < len(translations) and translations[index]:
        result += f"\nACCEPTED TARGET:\n{translations[index]}"
    return result


def build_sliding_prompt(
    lines: Sequence[str],
    indices: Sequence[int],
    translations: Sequence[str | None],
    previous_context: int,
    next_context: int,
) -> str:
    """Build a prompt that clearly separates context from requested output."""
    if not indices:
        raise ValueError("At least one subtitle index is required")

    first, last = indices[0], indices[-1]
    before = range(max(0, first - previous_context), first)
    after = range(last + 1, min(len(lines), last + 1 + next_context))

    sections = [
        "Use the surrounding dialogue to understand speakers, intent, idioms, "
        "pronouns, tone, and figurative meaning.",
    ]
    if before:
        sections.append(
            "CONTEXT BEFORE - read only; do not output:\n"
            + "\n\n".join(
                _context_entry(index, lines[index], translations) for index in before
            )
        )

    sections.append(
        "TRANSLATE THESE SUBTITLES:\n"
        + "\n\n".join(_marked_text(index, lines[index]) for index in indices)
    )

    if after:
        sections.append(
            "CONTEXT AFTER - read only; do not output:\n"
            + "\n\n".join(
                _context_entry(index, lines[index], translations) for index in after
            )
        )

    sections.append(
        "Return only the translated subtitles. Preserve each requested opening and "
        "closing SF marker exactly. Do not return context entries. Preserve subtitle "
        "formatting tags and intentional line breaks."
    )
    return "\n\n".join(sections)


def build_review_prompt(
    lines: Sequence[str],
    translations: Sequence[str],
    indices: Sequence[int],
    context_size: int,
) -> str:
    """Build a second-pass prompt for dialogue and terminology consistency."""
    first, last = indices[0], indices[-1]
    before = range(max(0, first - context_size), first)
    after = range(last + 1, min(len(lines), last + 1 + context_size))

    def pair(index: int) -> str:
        return (
            f"SOURCE {_marker(index)}:\n{lines[index]}\n"
            f"CURRENT TARGET:\n{translations[index]}"
        )

    sections = [
        "Review the translation for dialogue consistency, speaker tone, pronouns, "
        "terminology, jokes, idioms, and figurative meaning. Keep a good translation "
        "unchanged. Never merge, split, add, or remove subtitles."
    ]
    if before:
        sections.append(
            "CONTEXT BEFORE - read only; do not output:\n"
            + "\n\n".join(pair(index) for index in before)
        )

    sections.append(
        "REVIEW AND RETURN THESE CURRENT TRANSLATIONS:\n"
        + "\n\n".join(
            (
                f"SOURCE {_marker(index)}:\n{lines[index]}\n"
                f"CURRENT TARGET TO REVIEW:\n"
                f"{_marked_text(index, translations[index])}"
            )
            for index in indices
        )
    )

    if after:
        sections.append(
            "CONTEXT AFTER - read only; do not output:\n"
            + "\n\n".join(pair(index) for index in after)
        )

    sections.append(
        "Return only the final target text inside the exact markers for every "
        "requested ID. Preserve formatting tags and intentional line breaks."
    )
    return "\n\n".join(sections)


def parse_marked_translations(content: str, indices: Sequence[int]) -> list[str]:
    """Parse and strictly validate a marker-based model response."""
    if not isinstance(content, str) or not content.strip():
        raise InvalidTranslationResponse("The model returned empty content")

    parsed: dict[int, str] = {}
    for marker_number, value in _MARKER_PATTERN.findall(content.replace("```", "")):
        index = int(marker_number)
        if index in parsed:
            raise InvalidTranslationResponse(f"Duplicate subtitle marker {_marker(index)}")
        if not value.strip():
            raise InvalidTranslationResponse(f"Empty subtitle marker {_marker(index)}")
        parsed[index] = value.strip()

    expected = set(indices)
    if set(parsed) != expected:
        missing = sorted(expected - set(parsed))
        unexpected = sorted(set(parsed) - expected)
        details = []
        if missing:
            details.append("missing " + ", ".join(_marker(index) for index in missing))
        if unexpected:
            details.append(
                "unexpected " + ", ".join(_marker(index) for index in unexpected)
            )
        raise InvalidTranslationResponse("Invalid subtitle markers: " + "; ".join(details))

    return [parsed[index] for index in indices]


def _request_completion(
    base_url: str,
    model: str,
    system_content: str,
    user_content: str,
    temperature: float,
    max_tokens: int,
) -> str:
    response = requests.post(
        f"{base_url.rstrip('/')}/chat/completions",
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        timeout=120,
    )
    response.raise_for_status()
    payload = response.json()
    content = payload["choices"][0]["message"]["content"]
    if not isinstance(content, str) or not content.strip():
        raise InvalidTranslationResponse("The model returned empty content")
    return content.replace("```", "").strip()


def _system_prompt(
    source_lang: str,
    target_lang: str,
    context_info: str,
    contextual: bool,
) -> str:
    if not contextual:
        prompt = f"Translate the following text into {target_lang}."
    else:
        prompt = (
            f"Translate subtitles from {source_lang} into {target_lang}. "
            "Produce natural subtitle dialogue rather than a literal word-for-word "
            "translation. Preserve meaning, character voice, names, formatting tags, "
            "and intentional line breaks. Follow the requested marker format exactly."
        )
    if context_info.strip():
        prompt += f" Production context: {context_info.strip()}"
    return prompt


def _translate_individual(
    line: str,
    base_url: str,
    model: str,
    source_lang: str,
    target_lang: str,
    context_info: str,
    temperature: float,
) -> str:
    protected_line, formatting = _protect_formatting(line)
    system_prompt = _system_prompt(
        source_lang, target_lang, context_info, contextual=False
    )
    if formatting:
        system_prompt += " Preserve every SF formatting placeholder exactly."
    translated = _request_completion(
        base_url,
        model,
        system_prompt,
        protected_line,
        temperature,
        1000,
    )
    return _restore_formatting(translated, formatting)


def _translate_context_group(
    lines: Sequence[str],
    translations: list[str | None],
    indices: list[int],
    base_url: str,
    model: str,
    source_lang: str,
    target_lang: str,
    context_info: str,
    settings: TranslationSettings,
) -> list[str]:
    prompt_lines = list(lines)
    formatting_by_index: dict[int, dict[str, str]] = {}
    for index in indices:
        prompt_lines[index], formatting_by_index[index] = _protect_formatting(
            lines[index]
        )
    prompt = build_sliding_prompt(
        prompt_lines,
        indices,
        translations,
        settings.previous_context,
        settings.next_context,
    )
    try:
        content = _request_completion(
            base_url,
            model,
            _system_prompt(source_lang, target_lang, context_info, contextual=True),
            prompt,
            settings.temperature,
            4000,
        )
        parsed = parse_marked_translations(content, indices)
        return [
            _restore_formatting(value, formatting_by_index[index])
            for index, value in zip(indices, parsed)
        ]
    except InvalidTranslationResponse:
        if not settings.retry_invalid:
            raise
        if len(indices) == 1:
            return [
                _translate_individual(
                    lines[indices[0]],
                    base_url,
                    model,
                    source_lang,
                    target_lang,
                    context_info,
                    settings.temperature,
                )
            ]

        midpoint = len(indices) // 2
        left_indices, right_indices = indices[:midpoint], indices[midpoint:]
        left = _translate_context_group(
            lines,
            translations,
            left_indices,
            base_url,
            model,
            source_lang,
            target_lang,
            context_info,
            settings,
        )
        for index, value in zip(left_indices, left):
            translations[index] = value
        right = _translate_context_group(
            lines,
            translations,
            right_indices,
            base_url,
            model,
            source_lang,
            target_lang,
            context_info,
            settings,
        )
        return left + right


def _review_group(
    lines: Sequence[str],
    translations: list[str],
    indices: list[int],
    base_url: str,
    model: str,
    source_lang: str,
    target_lang: str,
    context_info: str,
    settings: TranslationSettings,
) -> list[str]:
    prompt_translations = list(translations)
    formatting_by_index: dict[int, dict[str, str]] = {}
    for index in indices:
        (
            prompt_translations[index],
            formatting_by_index[index],
        ) = _protect_formatting(translations[index])
    prompt = build_review_prompt(
        lines, prompt_translations, indices, settings.consistency_context
    )
    content = _request_completion(
        base_url,
        model,
        _system_prompt(source_lang, target_lang, context_info, contextual=True)
        + " This is a consistency review of an existing translation.",
        prompt,
        settings.review_temperature,
        6000,
    )
    parsed = parse_marked_translations(content, indices)
    return [
        _restore_formatting(value, formatting_by_index[index])
        for index, value in zip(indices, parsed)
    ]


def translate_subs(
    subs,
    base_url: str,
    model: str,
    source_lang: str,
    target_lang: str,
    context_info: str = "",
    batch_size: int | None = None,
    *,
    mode: str = "sliding",
    group_size: int = 4,
    previous_context: int = 8,
    next_context: int = 8,
    temperature: float = 0.4,
    review_temperature: float = 0.3,
    consistency_pass: bool = True,
    consistency_group_size: int = 8,
    consistency_context: int = 8,
    retry_invalid: bool = True,
) -> Iterator[tuple[float, list[str], list[str]]]:
    """Translate subtitles with optional overlapping dialogue context.

    The default quality mode translates four events while showing the model eight
    preceding and eight following events. A second pass reviews eight translations
    in a roughly 24-event window. Only ``line.text`` is changed; timing and styles
    on subtitle events remain untouched.

    ``batch_size`` is retained for callers of older releases. When supplied, one
    selects individual mode and values above one select sliding mode with that group
    size.
    """
    if batch_size is not None:
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        mode = "individual" if batch_size == 1 else "sliding"
        group_size = batch_size

    settings = TranslationSettings(
        mode=mode,
        group_size=group_size,
        previous_context=previous_context,
        next_context=next_context,
        temperature=temperature,
        review_temperature=review_temperature,
        consistency_pass=consistency_pass,
        consistency_group_size=consistency_group_size,
        consistency_context=consistency_context,
        retry_invalid=retry_invalid,
    )
    settings.validate()

    lines = [line.text for line in subs]
    if not lines:
        raise ValueError("The subtitle file contains no entries")

    initial_group_size = 1 if settings.mode == "individual" else settings.group_size
    initial_steps = math.ceil(len(lines) / initial_group_size)
    review_enabled = settings.consistency_pass and settings.mode == "sliding"
    review_steps = (
        math.ceil(len(lines) / settings.consistency_group_size)
        if review_enabled
        else 0
    )
    total_steps = initial_steps + review_steps
    completed_steps = 0
    working: list[str | None] = [None] * len(lines)

    for start in range(0, len(lines), initial_group_size):
        indices = list(range(start, min(len(lines), start + initial_group_size)))
        originals = [lines[index] for index in indices]
        if settings.mode == "individual":
            translated = [
                _translate_individual(
                    originals[0],
                    base_url,
                    model,
                    source_lang,
                    target_lang,
                    context_info,
                    settings.temperature,
                )
            ]
        else:
            translated = _translate_context_group(
                lines,
                working,
                indices,
                base_url,
                model,
                source_lang,
                target_lang,
                context_info,
                settings,
            )
        for index, value in zip(indices, translated):
            working[index] = value
        completed_steps += 1
        yield completed_steps / total_steps, originals, translated

    final_translations = [value or lines[index] for index, value in enumerate(working)]

    if review_enabled:
        for start in range(0, len(lines), settings.consistency_group_size):
            indices = list(
                range(start, min(len(lines), start + settings.consistency_group_size))
            )
            originals = [final_translations[index] for index in indices]
            try:
                reviewed = _review_group(
                    lines,
                    final_translations,
                    indices,
                    base_url,
                    model,
                    source_lang,
                    target_lang,
                    context_info,
                    settings,
                )
            except (
                InvalidTranslationResponse,
                KeyError,
                IndexError,
                TypeError,
                requests.exceptions.RequestException,
            ):
                # The review is deliberately non-destructive: a malformed response
                # or transient request failure keeps the validated first-pass text.
                reviewed = originals
            for index, value in zip(indices, reviewed):
                final_translations[index] = value
            completed_steps += 1
            yield completed_steps / total_steps, originals, reviewed

    for index, line in enumerate(subs):
        line.text = final_translations[index]
