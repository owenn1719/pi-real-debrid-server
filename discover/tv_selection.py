"""Coordinate TV candidates and cached Season 1 resolution."""

import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Protocol

from .candidates import TorrentCandidate
from .movie_selection import CandidateAttempt, NoCachedReleaseAvailable
from .quality import ScoredCandidate, TvQualityProfile, rank_candidates
from .real_debrid import RealDebridError


class EpisodeCandidateProvider(Protocol):
    def search_episode(
        self, imdb_id: str, season: int, episode: int
    ) -> list[TorrentCandidate]: ...


class CachedSeasonResolver(Protocol):
    def acquire_cached_season(
        self, candidate: TorrentCandidate, request: "EpisodeRequest"
    ) -> tuple[str, str, str, tuple[str, ...]]: ...
    def resolve_existing(
        self, torrent_id: str, request: "EpisodeRequest"
    ) -> tuple[str, str, tuple[str, ...]]: ...


@dataclass(frozen=True, slots=True)
class SeriesIdentity:
    tmdb_id: int
    imdb_id: str
    title: str
    year: int
    original_language: str


@dataclass(frozen=True, slots=True)
class EpisodeRequest:
    series: SeriesIdentity
    season: int
    episode: int
    expected_season_episodes: frozenset[int]


@dataclass(frozen=True, slots=True)
class ResolvedEpisode:
    request: EpisodeRequest
    scored_candidate: ScoredCandidate
    stream_url: str
    torrent_id: str
    selected_path: str
    selected_episode_paths: tuple[str, ...]
    attempts: tuple[CandidateAttempt, ...]


def _release_words(value: str) -> list[str]:
    value = unicodedata.normalize("NFKD", value).casefold()
    value = "".join(character for character in value if not unicodedata.combining(character))
    value = value.replace("'", "").replace("\u2019", "")
    return re.findall(r"[a-z0-9]+", value)


def candidate_matches_series(candidate: TorrentCandidate, request: EpisodeRequest) -> bool:
    """Require the canonical series title followed by a Season 1 marker."""
    expected = _release_words(request.series.title)
    season = str(request.season)
    sources = (candidate.filename, candidate.title) if candidate.filename else (candidate.title,)
    for source in sources:
        words = _release_words(source)
        width = len(expected)
        for index in range(len(words) - width):
            if words[index : index + width] != expected:
                continue
            following = words[index + width : index + width + 4]
            if (
                f"s{request.season:02d}" in following
                or f"s{request.season}" in following
                or ("season" in following and season in following)
            ):
                return True
    return False


class EpisodeSelectionService:
    def __init__(
        self,
        provider: EpisodeCandidateProvider,
        resolver: CachedSeasonResolver,
        *,
        max_candidates: int | None = None,
        total_budget_seconds: float = 20,
    ) -> None:
        self.provider = provider
        self.resolver = resolver
        self.max_candidates = max_candidates if max_candidates and max_candidates > 0 else None
        self.total_budget_seconds = total_budget_seconds

    def resolve(self, request: EpisodeRequest) -> ResolvedEpisode:
        candidates = self.provider.search_episode(
            request.series.imdb_id, request.season, request.episode
        )
        candidates = [
            candidate for candidate in candidates
            if candidate_matches_series(candidate, request)
        ]
        profile = TvQualityProfile(original_language=request.series.original_language)
        ranked, _ = rank_candidates(candidates, profile)
        if not ranked:
            raise NoCachedReleaseAvailable("provider returned no acceptable TV releases")

        attempts: list[CandidateAttempt] = []
        deadline = time.monotonic() + self.total_budget_seconds
        attempt_order = ranked[: self.max_candidates] if self.max_candidates else ranked
        for scored in attempt_order:
            if time.monotonic() >= deadline:
                break
            candidate = scored.candidate
            try:
                stream_url, torrent_id, path, selected_paths = (
                    self.resolver.acquire_cached_season(candidate, request)
                )
            except RealDebridError as error:
                attempts.append(CandidateAttempt(
                    candidate.info_hash, candidate.title, scored.score, str(error)
                ))
                continue
            attempts.append(CandidateAttempt(
                candidate.info_hash, candidate.title, scored.score,
                "selected cached release",
            ))
            return ResolvedEpisode(
                request, scored, stream_url, torrent_id, path, selected_paths,
                tuple(attempts),
            )

        raise NoCachedReleaseAvailable(
            "no complete cached Season 1 candidate became immediately available",
            tuple(attempts),
        )
