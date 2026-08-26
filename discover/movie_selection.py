"""Coordinate movie candidates, quality ranking, and cached-only RD resolution."""

import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Protocol

from .candidates import TorrentCandidate
from .quality import MovieQualityProfile, ScoredCandidate, rank_candidates
from .real_debrid import RealDebridError


class CandidateProvider(Protocol):
    def search_movie(self, imdb_id: str) -> list[TorrentCandidate]: ...


class CachedResolver(Protocol):
    def acquire_cached_hash(self, info_hash: str) -> tuple[str, str, str]: ...


@dataclass(frozen=True, slots=True)
class MovieIdentity:
    tmdb_id: int
    imdb_id: str
    title: str
    year: int
    original_language: str


@dataclass(frozen=True, slots=True)
class CandidateAttempt:
    info_hash: str
    release_title: str
    score: int
    outcome: str


@dataclass(frozen=True, slots=True)
class ResolvedMovie:
    movie: MovieIdentity
    scored_candidate: ScoredCandidate
    stream_url: str
    torrent_id: str
    selected_path: str
    attempts: tuple[CandidateAttempt, ...]


class NoCachedReleaseAvailable(RuntimeError):
    def __init__(self, message: str, attempts: tuple[CandidateAttempt, ...] = ()) -> None:
        super().__init__(message)
        self.attempts = attempts


def _release_words(value: str) -> list[str]:
    """Return comparison words while treating release-name punctuation as separators."""
    value = unicodedata.normalize("NFKD", value).casefold()
    value = "".join(character for character in value if not unicodedata.combining(character))
    # Release names commonly omit apostrophes rather than replacing them with a dot.
    value = value.replace("'", "").replace("\u2019", "")
    return re.findall(r"[a-z0-9]+", value)


def candidate_matches_movie(candidate: TorrentCandidate, movie: MovieIdentity) -> bool:
    """Require the canonical title immediately followed by the exact release year."""
    expected = _release_words(movie.title)
    year = str(movie.year)
    width = len(expected)
    sources = (candidate.filename, candidate.title) if candidate.filename else (candidate.title,)
    for source in sources:
        release = _release_words(source)
        if any(
            release[index : index + width] == expected
            and index + width < len(release)
            and release[index + width] == year
            for index in range(len(release) - width)
        ):
            return True
    return False


class MovieSelectionService:
    def __init__(
        self,
        provider: CandidateProvider,
        resolver: CachedResolver,
        *,
        max_candidates: int | None = None,
        total_budget_seconds: float = 20,
        profile_template: MovieQualityProfile | None = None,
    ) -> None:
        self.provider = provider
        self.resolver = resolver
        self.max_candidates = (
            max_candidates if max_candidates is not None and max_candidates > 0 else None
        )
        self.total_budget_seconds = total_budget_seconds
        self.profile_template = profile_template or MovieQualityProfile()

    def _attempt_order(self, ranked: list[ScoredCandidate]) -> list[ScoredCandidate]:
        """Mix 1080p fallbacks into a 2160p-preferred ranked result."""
        if not self.profile_template.prefer_2160p:
            return ranked

        preferred = [item for item in ranked if item.resolution == "2160p"]
        fallbacks = [item for item in ranked if item.resolution == "1080p"]
        remaining = [
            item for item in ranked if item.resolution not in {"2160p", "1080p"}
        ]
        if not preferred or not fallbacks:
            return ranked

        mixed: list[ScoredCandidate] = []
        while preferred or fallbacks:
            mixed.extend(preferred[:2])
            del preferred[:2]
            if fallbacks:
                mixed.append(fallbacks.pop(0))
        return mixed + remaining

    def _profile(self, movie: MovieIdentity) -> MovieQualityProfile:
        template = self.profile_template
        return MovieQualityProfile(
            original_language=movie.original_language,
            prefer_2160p=template.prefer_2160p,
            min_2160p_bytes=template.min_2160p_bytes,
            min_1080p_bytes=template.min_1080p_bytes,
            max_bytes=template.max_bytes,
            trusted_groups=template.trusted_groups,
        )

    def resolve(self, movie: MovieIdentity) -> ResolvedMovie:
        candidates = self.provider.search_movie(movie.imdb_id)
        candidates = [
            candidate for candidate in candidates
            if candidate_matches_movie(candidate, movie)
        ]
        ranked, _ = rank_candidates(candidates, self._profile(movie))
        if not ranked:
            raise NoCachedReleaseAvailable("provider returned no acceptable releases")

        deadline = time.monotonic() + self.total_budget_seconds
        attempts: list[CandidateAttempt] = []
        attempt_order = self._attempt_order(ranked)
        if self.max_candidates is not None:
            attempt_order = attempt_order[: self.max_candidates]
        for scored in attempt_order:
            if time.monotonic() >= deadline:
                break
            candidate = scored.candidate
            try:
                stream_url, torrent_id, selected_path = self.resolver.acquire_cached_hash(
                    candidate.info_hash
                )
            except RealDebridError as error:
                attempts.append(
                    CandidateAttempt(
                        candidate.info_hash,
                        candidate.title,
                        scored.score,
                        str(error),
                    )
                )
                continue

            attempts.append(
                CandidateAttempt(
                    candidate.info_hash,
                    candidate.title,
                    scored.score,
                    "selected cached release",
                )
            )
            return ResolvedMovie(
                movie,
                scored,
                stream_url,
                torrent_id,
                selected_path,
                tuple(attempts),
            )

        raise NoCachedReleaseAvailable(
            "no acceptable candidate became immediately available",
            tuple(attempts),
        )
