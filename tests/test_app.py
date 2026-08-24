import unittest

from discover.app import DiscoverApplication, safe_attempt_category
from discover.candidates import TorrentCandidate
from discover.quality import ScoredCandidate
from discover.selection import MovieIdentity, ResolvedMovie


MOVIE = MovieIdentity(502356, "tt6718170", "Mario", 2023, "en")
CANDIDATE = TorrentCandidate("Mario.2160p.ENG.REMUX.mkv", "a" * 40, "fixture")
SCORED = ScoredCandidate(CANDIDATE, True, 900, "2160p", "remux", "english")


class FakeResolver:
    def __init__(self):
        self.refreshes = 0

    def resolve_existing(self, torrent_id):
        self.refreshes += 1
        return "https://rd.invalid/refreshed", "/movie.mkv"


class FakeSelection:
    def __init__(self):
        self.resolver = FakeResolver()
        self.calls = 0

    def resolve(self, movie):
        self.calls += 1
        return ResolvedMovie(
            movie, SCORED, "https://rd.invalid/initial", "torrent-id", "/movie.mkv", ()
        )


class FakeMovieLookup:
    def __init__(self):
        self.calls = 0

    def movie_identity(self, tmdb_id):
        self.calls += 1
        return MOVIE


class AppTests(unittest.TestCase):
    def test_attempt_logging_uses_fixed_safe_categories(self):
        self.assertEqual(
            safe_attempt_category(
                "candidate was not immediately available; newly created probe was deleted"
            ),
            "not_immediately_available",
        )
        self.assertEqual(
            safe_attempt_category("Real-Debrid returned HTTP 500: arbitrary detail"),
            "rd_error",
        )

    def test_initial_selection_then_repeat_refreshes_existing_torrent(self):
        selection = FakeSelection()
        app = DiscoverApplication(selection, {MOVIE.tmdb_id: MOVIE})
        first = app.resolve_movie(MOVIE.tmdb_id)
        second = app.resolve_movie(MOVIE.tmdb_id)
        self.assertEqual(first.stream_url, "https://rd.invalid/initial")
        self.assertEqual(second.stream_url, "https://rd.invalid/refreshed")
        self.assertEqual(selection.calls, 1)
        self.assertEqual(selection.resolver.refreshes, 1)

    def test_unknown_movie_is_rejected(self):
        app = DiscoverApplication(FakeSelection(), {MOVIE.tmdb_id: MOVIE})
        with self.assertRaises(KeyError):
            app.resolve_movie(999)

    def test_unknown_movie_is_loaded_from_tmdb_and_cached(self):
        lookup = FakeMovieLookup()
        app = DiscoverApplication(FakeSelection(), movie_lookup=lookup)
        app.resolve_movie(MOVIE.tmdb_id)
        self.assertEqual(app.movies[MOVIE.tmdb_id], MOVIE)
        self.assertEqual(lookup.calls, 1)


if __name__ == "__main__":
    unittest.main()
