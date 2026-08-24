"""Deterministic, movie-only release parsing and quality scoring."""

import re
from dataclasses import dataclass, field

from .candidates import TorrentCandidate


BAD_SOURCE = re.compile(
    r"(?:^|[. _-])(cam(?:rip)?|hdcam|ts|telesync|tc|telecine|scr|screener|dvdscr)(?:$|[. _-])",
    re.I,
)
PROMOTIONAL_VIDEO = re.compile(
    r"(?:^|[. _-])(trailer(?![. _-]+park(?:$|[. _-]))|teaser|featurette)(?:$|[. _-])",
    re.I,
)
RD_REJECTED_FILENAME = re.compile(r"web-dl", re.I)
EXPLICIT_ENGLISH = re.compile(r"(?:^|[. _-])(eng|english)(?:$|[. _-])", re.I)
MULTI_AUDIO = re.compile(r"(?:^|[. _-])(multi|multilingual)(?:$|[. _-])", re.I)
LANGUAGE_TOKENS = {
    "ru": {"rus", "russian"},
    "it": {"ita", "italian"},
    "fr": {"fre", "fra", "french"},
    "de": {"ger", "deu", "german"},
    "es": {"spa", "spanish", "latino"},
    "hi": {"hin", "hindi"},
    "uk": {"ukr", "ukrainian"},
    "pl": {"pol", "polish"},
    "ko": {"kor", "korean"},
    "ja": {"jpn", "japanese"},
    "zh": {"chi", "zho", "chinese", "mandarin"},
    "tr": {"tur", "turkish"},
    "pt": {"por", "portuguese"},
    "ar": {"ara", "arabic"},
}
NON_ENGLISH = frozenset().union(*LANGUAGE_TOKENS.values())
TOKEN = re.compile(r"[a-z0-9]+", re.I)


@dataclass(frozen=True, slots=True)
class MovieQualityProfile:
    original_language: str = "en"
    prefer_2160p: bool = True
    min_2160p_bytes: int = 8_000_000_000
    min_1080p_bytes: int = 2_000_000_000
    max_bytes: int = 90_000_000_000
    trusted_groups: frozenset[str] = frozenset(
        {"cinephiles", "framestor", "flux", "ntb", "don", "ctrlhd"}
    )


@dataclass(frozen=True, slots=True)
class ScoredCandidate:
    candidate: TorrentCandidate
    accepted: bool
    score: int
    resolution: str
    source_type: str
    language: str
    reasons: tuple[str, ...] = field(default_factory=tuple)


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in TOKEN.findall(text)}


def _resolution(text: str) -> str:
    lowered = text.lower()
    if re.search(r"(?:^|\D)(2160p|4k|uhd)(?:$|\D)", lowered):
        return "2160p"
    if re.search(r"(?:^|\D)1080[pi](?:$|\D)", lowered):
        return "1080p"
    if re.search(r"(?:^|\D)720p(?:$|\D)", lowered):
        return "720p"
    return "unknown"


def _source_type(text: str) -> str:
    lowered = text.lower().replace("-", " ").replace(".", " ")
    if "remux" in lowered or "bdremux" in lowered:
        return "remux"
    if "blu ray" in lowered or "bluray" in lowered or "bdrip" in lowered:
        return "bluray"
    if "web dl" in lowered or "webdl" in lowered:
        return "web-dl"
    if "webrip" in lowered:
        return "webrip"
    return "unknown"


def _language(text: str, original_language: str) -> tuple[str, str | None]:
    tokens = _tokens(text)
    has_english = bool(EXPLICIT_ENGLISH.search(text))
    has_multi = bool(MULTI_AUDIO.search(text))
    foreign = sorted(tokens.intersection(NON_ENGLISH))
    original_tokens = LANGUAGE_TOKENS.get(original_language.lower(), set())

    if has_english:
        return "english", None
    if has_multi:
        return "multi", None
    if tokens.intersection(original_tokens):
        return "original-language", None
    if foreign:
        return "non-english", f"explicit non-English-only tag: {foreign[0]}"
    if original_language.lower() == "en":
        return "assumed-original-english", None
    return "unknown", "English audio is not established"


def score_candidate(
    candidate: TorrentCandidate,
    profile: MovieQualityProfile,
) -> ScoredCandidate:
    text = f"{candidate.title} {candidate.filename or ''}"
    reasons: list[str] = []
    resolution = _resolution(text)
    source_type = _source_type(text)
    language, language_rejection = _language(text, profile.original_language)

    if BAD_SOURCE.search(text):
        reasons.append("rejected low-quality theatrical/screener source")
    if PROMOTIONAL_VIDEO.search(text):
        reasons.append("rejected trailer/teaser promotional video")
    if RD_REJECTED_FILENAME.search(text):
        reasons.append("Real-Debrid rejects the literal web-dl filename substring")
    if language_rejection:
        reasons.append(language_rejection)
    if candidate.size_bytes is not None:
        if candidate.size_bytes > profile.max_bytes:
            reasons.append("file exceeds configured maximum size")
        if resolution == "2160p" and candidate.size_bytes < profile.min_2160p_bytes:
            reasons.append("2160p file is implausibly small")
        if resolution == "1080p" and candidate.size_bytes < profile.min_1080p_bytes:
            reasons.append("1080p file is implausibly small")

    if reasons:
        return ScoredCandidate(
            candidate, False, -10_000, resolution, source_type, language, tuple(reasons)
        )

    score = 0
    if resolution == "2160p":
        score += 500 if profile.prefer_2160p else 300
    elif resolution == "1080p":
        score += 250
    elif resolution == "720p":
        score += 50
    else:
        score -= 100

    score += {
        "remux": 300,
        "bluray": 200,
        "web-dl": 140,
        "webrip": 60,
        "unknown": -50,
    }[source_type]
    score += {
        "english": 120,
        "multi": 100,
        "original-language": 120,
        "assumed-original-english": 40,
    }[language]

    lowered = text.lower()
    if any(codec in lowered for codec in ("hevc", "h265", "h.265", "x265")):
        score += 40
    if any(dynamic_range in lowered for dynamic_range in ("hdr", "dolby vision", "dovi", " dv ")):
        score += 30
    tokens = _tokens(text)
    if tokens.intersection(profile.trusted_groups):
        score += 75
    if candidate.size_bytes is None:
        score -= 30

    return ScoredCandidate(
        candidate, True, score, resolution, source_type, language, tuple()
    )


def rank_candidates(
    candidates: list[TorrentCandidate],
    profile: MovieQualityProfile,
) -> tuple[list[ScoredCandidate], list[ScoredCandidate]]:
    scored = [score_candidate(candidate, profile) for candidate in candidates]
    accepted = sorted(
        (item for item in scored if item.accepted),
        key=lambda item: item.score,
        reverse=True,
    )
    rejected = [item for item in scored if not item.accepted]
    return accepted, rejected
