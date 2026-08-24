"""Minimal HTTP application for the validated movie-only Discover workflow."""

import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from typing import Protocol

from .real_debrid import RealDebridError
from .selection import MovieIdentity, MovieSelectionService, NoCachedReleaseAvailable, ResolvedMovie
from .tmdb import TmdbError, TmdbMovieNotFound


class MovieLookup(Protocol):
    def movie_identity(self, tmdb_id: int) -> MovieIdentity: ...


def safe_attempt_category(outcome: str) -> str:
    lowered = outcome.lower()
    if "not immediately available" in lowered:
        return "not_immediately_available"
    if "already exists but is not downloaded" in lowered:
        return "existing_not_downloaded"
    if outcome == "selected cached release":
        return "selected"
    return "rd_error"


class DiscoverApplication:
    def __init__(
        self,
        selection: MovieSelectionService,
        movies: dict[int, MovieIdentity] | None = None,
        movie_lookup: MovieLookup | None = None,
    ) -> None:
        self.selection = selection
        self.movies = movies if movies is not None else {}
        self.movie_lookup = movie_lookup
        self._selected: dict[int, ResolvedMovie] = {}
        self._locks: dict[int, Lock] = {}
        self._locks_guard = Lock()

    def _lock_for(self, tmdb_id: int) -> Lock:
        with self._locks_guard:
            return self._locks.setdefault(tmdb_id, Lock())

    def resolve_movie(self, tmdb_id: int) -> ResolvedMovie:
        movie = self.movies.get(tmdb_id)
        if movie is None:
            if self.movie_lookup is None:
                raise KeyError(tmdb_id)
            movie = self.movie_lookup.movie_identity(tmdb_id)
            self.movies[tmdb_id] = movie
        with self._lock_for(tmdb_id):
            previous = self._selected.get(tmdb_id)
            if previous:
                try:
                    url, path = self.selection.resolver.resolve_existing(previous.torrent_id)
                    refreshed = ResolvedMovie(
                        previous.movie, previous.scored_candidate, url,
                        previous.torrent_id, path, previous.attempts,
                    )
                    self._selected[tmdb_id] = refreshed
                    return refreshed
                except RealDebridError:
                    self._selected.pop(tmdb_id, None)
            result = self.selection.resolve(movie)
            self._selected[tmdb_id] = result
            return result


class DiscoverHandler(BaseHTTPRequestHandler):
    application: DiscoverApplication

    def _request_context(self, tmdb_id: int) -> tuple[str, float, bool]:
        request_id = f"{time.monotonic_ns() & 0xFFFFFF:06x}"
        started = time.monotonic()
        memory_hit = tmdb_id in self.application._selected
        print(
            f"request={request_id} client={self.client_address[0]} "
            f"method={self.command} tmdb={tmdb_id} started "
            f"memory_selection={'hit' if memory_hit else 'miss'}"
        )
        return request_id, started, memory_hit

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return round((time.monotonic() - started) * 1000)

    def dispatch(self) -> None:
        if self.path == "/health":
            body = b'{"status":"ok"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
            return
        match = re.fullmatch(r"/play/movie/(\d+)", self.path)
        if not match:
            self.send_error(404, "Use /play/movie/TMDB_ID")
            return
        tmdb_id = int(match.group(1))
        request_id, started, memory_hit = self._request_context(tmdb_id)
        try:
            result = self.application.resolve_movie(tmdb_id)
        except (KeyError, TmdbMovieNotFound):
            print(
                f"request={request_id} tmdb={tmdb_id} status=404 "
                f"elapsed_ms={self._elapsed_ms(started)} outcome=unknown_movie"
            )
            self.send_error(404, "Unknown movie")
            return
        except TmdbError as error:
            print(
                f"request={request_id} tmdb={tmdb_id} status=502 "
                f"elapsed_ms={self._elapsed_ms(started)} outcome=tmdb_error "
                f"detail={error}"
            )
            self.send_error(502, "Movie metadata lookup failed")
            return
        except NoCachedReleaseAvailable as error:
            outcomes: dict[str, int] = {}
            for attempt in error.attempts:
                category = safe_attempt_category(attempt.outcome)
                outcomes[category] = outcomes.get(category, 0) + 1
            summary = ",".join(
                f"{outcome}={count}" for outcome, count in sorted(outcomes.items())
            ) or "no_attempts"
            print(
                f"request={request_id} tmdb={tmdb_id} status=503 "
                f"elapsed_ms={self._elapsed_ms(started)} outcome=no_cached_release "
                f"attempts={len(error.attempts)} summary={summary}"
            )
            self.send_error(503, "No acceptable cached release is currently available")
            return
        except Exception as error:
            print(
                f"request={request_id} tmdb={tmdb_id} status=500 "
                f"elapsed_ms={self._elapsed_ms(started)} "
                f"outcome=unexpected_error type={type(error).__name__}"
            )
            self.send_error(500, "Unexpected resolver error")
            return
        chosen = result.scored_candidate
        print(
            f"request={request_id} tmdb={tmdb_id} status=302 "
            f"elapsed_ms={self._elapsed_ms(started)} outcome=redirect "
            f"selection={'memory' if memory_hit else 'fresh'} "
            f"quality={chosen.resolution}/{chosen.source_type}/{chosen.language}"
        )
        self.send_response(302)
        self.send_header("Location", result.stream_url)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_HEAD(self) -> None:
        self.dispatch()

    def do_GET(self) -> None:
        self.dispatch()

    def log_message(self, format: str, *args: object) -> None:
        return


def serve(application: DiscoverApplication, host: str = "0.0.0.0", port: int = 8090) -> None:
    DiscoverHandler.application = application
    server = ThreadingHTTPServer((host, port), DiscoverHandler)
    print(f"Discover listening on http://{host}:{port}")
    print("Movie route: /play/movie/TMDB_ID")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped")
