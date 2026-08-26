"""Minimal TMDB movie identity client used by the playback resolver."""

import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .movie_selection import MovieIdentity
from .tv_selection import SeriesIdentity


class TmdbError(RuntimeError):
    pass


class TmdbMovieNotFound(TmdbError):
    pass


class TmdbSeriesNotFound(TmdbError):
    pass


@dataclass(frozen=True, slots=True)
class TmdbCatalogMovie:
    tmdb_id: int
    title: str
    year: int


@dataclass(frozen=True, slots=True)
class TmdbCatalogSeries:
    tmdb_id: int
    title: str
    year: int


@dataclass(frozen=True, slots=True)
class TmdbEpisode:
    season_number: int
    episode_number: int
    title: str
    air_date: str | None


class TmdbClient:
    def __init__(
        self,
        bearer_token: str,
        *,
        base_url: str = "https://api.themoviedb.org/3/",
        timeout_seconds: int = 10,
    ) -> None:
        if not bearer_token.strip():
            raise ValueError("TMDB bearer token is empty")
        self.bearer_token = bearer_token.strip()
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout_seconds = timeout_seconds

    def _get(self, path: str, params: dict[str, str | int] | None = None) -> dict:
        endpoint = f"{self.base_url}{path.lstrip('/')}"
        if params:
            endpoint += "?" + urlencode(params)
        request = Request(
            endpoint,
            headers={
                "Authorization": f"Bearer {self.bearer_token}",
                "Accept": "application/json",
                "User-Agent": "pi-infuse-discover/0.1",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.load(response)
        except HTTPError as error:
            raise TmdbError(f"TMDB returned HTTP {error.code}") from error
        except (URLError, json.JSONDecodeError) as error:
            raise TmdbError(f"TMDB request failed: {error}") from error

        if not isinstance(payload, dict):
            raise TmdbError("TMDB returned an invalid response")
        return payload

    def movie_identity(self, tmdb_id: int) -> MovieIdentity:
        if tmdb_id <= 0:
            raise ValueError("TMDB movie ID must be positive")
        try:
            payload = self._get(
                f"movie/{tmdb_id}", {"append_to_response": "external_ids"}
            )
        except TmdbError as error:
            if "HTTP 404" in str(error):
                raise TmdbMovieNotFound(f"TMDB movie {tmdb_id} was not found") from error
            raise

        title = payload.get("title")
        language = payload.get("original_language")
        release_date = payload.get("release_date", "")
        external_ids = payload.get("external_ids", {})
        imdb_id = external_ids.get("imdb_id") if isinstance(external_ids, dict) else None
        if not isinstance(title, str) or not title.strip():
            raise TmdbError(f"TMDB movie {tmdb_id} has no title")
        if not isinstance(imdb_id, str) or not imdb_id.startswith("tt"):
            raise TmdbError(f"TMDB movie {tmdb_id} has no IMDb ID")
        if not isinstance(language, str) or not language:
            raise TmdbError(f"TMDB movie {tmdb_id} has no original language")
        try:
            year = int(release_date[:4])
        except (TypeError, ValueError):
            raise TmdbError(f"TMDB movie {tmdb_id} has no valid release year") from None

        return MovieIdentity(tmdb_id, imdb_id, title.strip(), year, language)

    def series_identity(self, tmdb_id: int) -> SeriesIdentity:
        if tmdb_id <= 0:
            raise ValueError("TMDB series ID must be positive")
        try:
            payload = self._get(f"tv/{tmdb_id}", {"append_to_response": "external_ids"})
        except TmdbError as error:
            if "HTTP 404" in str(error):
                raise TmdbSeriesNotFound(f"TMDB series {tmdb_id} was not found") from error
            raise
        title = payload.get("name")
        language = payload.get("original_language")
        first_air_date = payload.get("first_air_date", "")
        external_ids = payload.get("external_ids", {})
        imdb_id = external_ids.get("imdb_id") if isinstance(external_ids, dict) else None
        if not isinstance(title, str) or not title.strip():
            raise TmdbError(f"TMDB series {tmdb_id} has no title")
        if not isinstance(imdb_id, str) or not imdb_id.startswith("tt"):
            raise TmdbError(f"TMDB series {tmdb_id} has no IMDb ID")
        if not isinstance(language, str) or not language:
            raise TmdbError(f"TMDB series {tmdb_id} has no original language")
        try:
            year = int(first_air_date[:4])
        except (TypeError, ValueError):
            raise TmdbError(f"TMDB series {tmdb_id} has no valid first-air year") from None
        return SeriesIdentity(tmdb_id, imdb_id, title.strip(), year, language)

    def season_episodes(self, tmdb_id: int, season_number: int) -> list[TmdbEpisode]:
        if tmdb_id <= 0 or season_number <= 0:
            raise ValueError("TMDB series ID and season number must be positive")
        payload = self._get(f"tv/{tmdb_id}/season/{season_number}", {"language": "en-US"})
        episodes = payload.get("episodes")
        if not isinstance(episodes, list):
            raise TmdbError("TMDB season response has no episodes list")
        result: list[TmdbEpisode] = []
        for item in episodes:
            if not isinstance(item, dict):
                continue
            season = item.get("season_number")
            number = item.get("episode_number")
            title = item.get("name")
            air_date = item.get("air_date")
            if season != season_number or not isinstance(number, int) or number <= 0:
                continue
            if not isinstance(title, str) or not title.strip():
                title = f"Episode {number}"
            result.append(TmdbEpisode(
                season, number, title.strip(), air_date if isinstance(air_date, str) else None
            ))
        return result

    def catalog_movies(
        self,
        path: str,
        *,
        limit: int = 100,
        min_vote_count: int = 0,
    ) -> list[TmdbCatalogMovie]:
        if limit <= 0:
            return []
        movies: list[TmdbCatalogMovie] = []
        seen: set[int] = set()
        page = 1
        # Read extra pages when TMDB entries lack a usable title or release
        # year, while keeping every catalog sync strictly bounded.
        while len(movies) < limit and page <= 25:
            payload = self._get(path, {"language": "en-US", "page": page})
            results = payload.get("results")
            if not isinstance(results, list):
                raise TmdbError("TMDB catalog response has no results list")
            for item in results:
                if not isinstance(item, dict):
                    continue
                tmdb_id = item.get("id")
                title = item.get("title")
                release_date = item.get("release_date", "")
                vote_count = item.get("vote_count", 0)
                try:
                    year = int(release_date[:4])
                except (TypeError, ValueError):
                    continue
                if (
                    not isinstance(tmdb_id, int)
                    or tmdb_id in seen
                    or not isinstance(title, str)
                    or not title.strip()
                    or not isinstance(vote_count, int)
                    or vote_count < min_vote_count
                ):
                    continue
                seen.add(tmdb_id)
                movies.append(TmdbCatalogMovie(tmdb_id, title.strip(), year))
                if len(movies) == limit:
                    break
            if page >= payload.get("total_pages", page):
                break
            page += 1
        return movies

    def catalog_series(
        self,
        path: str,
        *,
        limit: int = 50,
        min_vote_count: int = 0,
    ) -> list[TmdbCatalogSeries]:
        if limit <= 0:
            return []
        series: list[TmdbCatalogSeries] = []
        seen: set[int] = set()
        page = 1
        while len(series) < limit and page <= 25:
            payload = self._get(path, {"language": "en-US", "page": page})
            results = payload.get("results")
            if not isinstance(results, list):
                raise TmdbError("TMDB TV catalog response has no results list")
            for item in results:
                if not isinstance(item, dict):
                    continue
                tmdb_id = item.get("id")
                title = item.get("name")
                first_air_date = item.get("first_air_date", "")
                vote_count = item.get("vote_count", 0)
                try:
                    year = int(first_air_date[:4])
                except (TypeError, ValueError):
                    continue
                if (
                    not isinstance(tmdb_id, int) or tmdb_id in seen
                    or not isinstance(title, str) or not title.strip()
                    or not isinstance(vote_count, int) or vote_count < min_vote_count
                ):
                    continue
                seen.add(tmdb_id)
                series.append(TmdbCatalogSeries(tmdb_id, title.strip(), year))
                if len(series) == limit:
                    break
            if page >= payload.get("total_pages", page):
                break
            page += 1
        return series
