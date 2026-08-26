import unittest

from discover.app import DiscoverApplication, safe_attempt_category
from discover.candidates import TorrentCandidate
from discover.quality import ScoredCandidate
from discover.movie_selection import MovieIdentity, ResolvedMovie
from discover.tmdb import TmdbEpisode
from discover.tv_selection import EpisodeRequest, ResolvedEpisode, SeriesIdentity


MOVIE = MovieIdentity(502356, "tt6718170", "Mario", 2023, "en")
CANDIDATE = TorrentCandidate("Mario.2160p.ENG.REMUX.mkv", "a" * 40, "fixture")
SCORED = ScoredCandidate(CANDIDATE, True, 900, "2160p", "remux", "english")
SERIES = SeriesIdentity(95396, "tt11280740", "Severance", 2022, "en")


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


class FakeEpisodeResolver:
    def resolve_existing(self, torrent_id, request):
        return "https://rd.invalid/refreshed-pilot", "/S01E01.mkv", ("/S01E01.mkv",)


class FakeEpisodeSelection:
    def __init__(self):
        self.resolver = FakeEpisodeResolver()
        self.calls = 0

    def resolve(self, request):
        self.calls += 1
        return ResolvedEpisode(
            request, SCORED, "https://rd.invalid/pilot", "season-torrent",
            "/S01E01.mkv", ("/S01E01.mkv",), (),
        )


class FakeSeriesLookup:
    def series_identity(self, tmdb_id):
        return SERIES

    def season_episodes(self, tmdb_id, season_number):
        return [TmdbEpisode(1, 1, "Good News About Hell", "2022-02-17")]


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

    def test_pilot_is_resolved_and_then_refreshed(self):
        selection = FakeEpisodeSelection()
        app = DiscoverApplication(
            FakeSelection(),
            episode_selection=selection,
            series_lookup=FakeSeriesLookup(),
        )
        first = app.resolve_episode(SERIES.tmdb_id, 1, 1)
        second = app.resolve_episode(SERIES.tmdb_id, 1, 1)
        self.assertEqual(first.stream_url, "https://rd.invalid/pilot")
        self.assertEqual(second.stream_url, "https://rd.invalid/refreshed-pilot")
        self.assertEqual(selection.calls, 1)

    def test_unaired_episode_is_rejected_before_selection(self):
        selection = FakeEpisodeSelection()
        app = DiscoverApplication(
            FakeSelection(),
            episode_selection=selection,
            series_lookup=FakeSeriesLookup(),
        )
        with self.assertRaises(KeyError):
            app.resolve_episode(SERIES.tmdb_id, 1, 2)
        self.assertEqual(selection.calls, 0)


if __name__ == "__main__":
    unittest.main()
