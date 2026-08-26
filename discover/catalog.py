"""Generate the Infuse STRM catalog from TMDB lists."""

import re
import shutil
import time
from pathlib import Path
from threading import Event, Thread
from uuid import uuid4

from .tmdb import TmdbClient, TmdbError


MOVIE_CATALOGS = (
    ("Discover Movies", ("trending/movie/week", "movie/popular")),
)
TV_CATALOGS = (
    ("Discover TV Shows", ("trending/tv/week", "tv/popular")),
)
INVALID_FILENAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def safe_filename(title: str) -> str:
    cleaned = INVALID_FILENAME.sub("-", title).strip().rstrip(".")
    return re.sub(r"\s+", " ", cleaned) or "Untitled"


class CatalogSync:
    def __init__(
        self,
        tmdb: TmdbClient,
        catalog_root: Path,
        *,
        public_base_url: str = "http://192.168.4.58:8090",
        limit: int = 250,
        tv_limit: int = 50,
        min_vote_count: int = 1_000,
    ) -> None:
        self.tmdb = tmdb
        self.catalog_root = catalog_root
        self.public_base_url = public_base_url.rstrip("/")
        self.limit = limit
        self.tv_limit = tv_limit
        self.min_vote_count = min_vote_count

    def sync(self) -> dict[str, int]:
        self.catalog_root.mkdir(parents=True, exist_ok=True)
        target = self.catalog_root / "Discover"
        staging = self.catalog_root / f".discover-build-{uuid4().hex}"
        backup = self.catalog_root / f".discover-previous-{uuid4().hex}"
        counts: dict[str, int] = {}
        try:
            staging.mkdir()
            for folder_name, endpoints in MOVIE_CATALOGS:
                folder = staging / folder_name
                folder.mkdir()
                movies = []
                seen_movies: set[int] = set()
                for endpoint in endpoints:
                    source_movies = self.tmdb.catalog_movies(
                        endpoint,
                        limit=self.limit,
                        min_vote_count=self.min_vote_count,
                    )
                    for movie in source_movies:
                        if movie.tmdb_id in seen_movies:
                            continue
                        seen_movies.add(movie.tmdb_id)
                        movies.append(movie)
                        if len(movies) == self.limit:
                            break
                    if len(movies) == self.limit:
                        break
                used_names: set[str] = set()
                for movie in movies:
                    stem = f"{safe_filename(movie.title)} ({movie.year})"
                    if stem.casefold() in used_names:
                        stem += f" [{movie.tmdb_id}]"
                    used_names.add(stem.casefold())
                    (folder / f"{stem}.strm").write_text(
                        f"{self.public_base_url}/play/movie/{movie.tmdb_id}\n",
                        encoding="utf-8",
                    )
                counts[folder_name] = len(movies)

            for folder_name, endpoints in TV_CATALOGS:
                folder = staging / folder_name
                folder.mkdir()
                series_items = []
                seen_series: set[int] = set()
                for endpoint in endpoints:
                    source_series = self.tmdb.catalog_series(
                        endpoint,
                        limit=self.tv_limit,
                        min_vote_count=self.min_vote_count,
                    )
                    for series in source_series:
                        if series.tmdb_id in seen_series:
                            continue
                        seen_series.add(series.tmdb_id)
                        series_items.append(series)
                        if len(series_items) == self.tv_limit:
                            break
                    if len(series_items) == self.tv_limit:
                        break
                used_names: set[str] = set()
                for series in series_items:
                    stem = f"{safe_filename(series.title)} ({series.year}) - S01E01"
                    if stem.casefold() in used_names:
                        stem += f" [{series.tmdb_id}]"
                    used_names.add(stem.casefold())
                    (folder / f"{stem}.strm").write_text(
                        f"{self.public_base_url}/play/series/{series.tmdb_id}/1/1\n",
                        encoding="utf-8",
                    )
                counts[folder_name] = len(series_items)

            if target.exists():
                target.rename(backup)
            try:
                staging.rename(target)
            except Exception:
                if backup.exists() and not target.exists():
                    backup.rename(target)
                raise
            if backup.exists():
                shutil.rmtree(backup)
            return counts
        finally:
            if staging.exists():
                shutil.rmtree(staging)


def start_catalog_scheduler(sync: CatalogSync, interval_seconds: int = 43200) -> Thread:
    def run() -> None:
        while True:
            started = time.monotonic()
            try:
                counts = sync.sync()
                print("TMDB catalog sync complete: " + ", ".join(
                    f"{name}={count}" for name, count in counts.items()
                ))
            except (OSError, TmdbError) as error:
                print(f"TMDB catalog sync failed; previous catalog retained: {error}")
            Event().wait(max(1, interval_seconds - int(time.monotonic() - started)))

    thread = Thread(target=run, name="catalog-sync", daemon=True)
    thread.start()
    return thread
