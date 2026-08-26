import unittest

from discover.candidates import TorrentCandidate
from discover.real_debrid import RealDebridError
from discover.movie_selection import (
    MovieIdentity,
    MovieSelectionService,
    NoCachedReleaseAvailable,
    candidate_matches_movie,
)


def item(name: str, info_hash: str, size_gb: int = 20) -> TorrentCandidate:
    return TorrentCandidate(
        title=name,
        filename=name,
        info_hash=info_hash,
        source="fixture",
        size_bytes=size_gb * 1_000_000_000,
    )


class FakeProvider:
    def __init__(self, candidates):
        self.candidates = candidates
        self.requests = []

    def search_movie(self, imdb_id):
        self.requests.append(imdb_id)
        return self.candidates


class FakeResolver:
    def __init__(self, outcomes):
        self.outcomes = dict(outcomes)
        self.requests = []

    def acquire_cached_hash(self, info_hash):
        self.requests.append(info_hash)
        outcome = self.outcomes[info_hash]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


MOVIE = MovieIdentity(502356, "tt6718170", "Movie", 2023, "en")


class SelectionTests(unittest.TestCase):
    def test_title_and_year_match_is_exact(self):
        movie = MovieIdentity(1, "tt0000001", "The Odyssey", 2026, "en")

        self.assertTrue(candidate_matches_movie(
            item("The.Odyssey.2026.2160p.ENG.WEB-DL.mkv", "a" * 40), movie
        ))
        self.assertFalse(candidate_matches_movie(
            item("Odyssey.2025.2160p.ENG.WEB-DL.mkv", "b" * 40), movie
        ))
        self.assertFalse(candidate_matches_movie(
            item("The.Odyssey.2025.2160p.ENG.WEB-DL.mkv", "c" * 40), movie
        ))

    def test_mismatched_identity_never_reaches_resolver(self):
        wrong_hash = "a" * 40
        right_hash = "b" * 40
        movie = MovieIdentity(1, "tt0000001", "The Odyssey", 2026, "en")
        resolver = FakeResolver(
            {right_hash: ("https://rd.invalid/movie", "torrent-id", "/movie.mkv")}
        )
        provider = FakeProvider([
            item("Odyssey.2025.2160p.ENG.REMUX.mkv", wrong_hash, 60),
            item("The.Odyssey.2026.1080p.ENG.WEB.DL.mkv", right_hash, 10),
        ])

        result = MovieSelectionService(provider, resolver).resolve(movie)

        self.assertEqual(result.scored_candidate.candidate.info_hash, right_hash)
        self.assertEqual(resolver.requests, [right_hash])

    def test_tries_ranked_candidates_until_cached_winner(self):
        best_hash = "a" * 40
        fallback_hash = "b" * 40
        provider = FakeProvider(
            [
                item("Movie.2023.2160p.ENG.REMUX-CiNEPHiLES.mkv", best_hash, 60),
                item("Movie.2023.1080p.ENG.WEB.DL-FLUX.mkv", fallback_hash, 10),
            ]
        )
        resolver = FakeResolver(
            {
                best_hash: RealDebridError("cache miss; probe deleted"),
                fallback_hash: ("https://rd.invalid/movie", "torrent-id", "/movie.mkv"),
            }
        )
        result = MovieSelectionService(provider, resolver).resolve(MOVIE)
        self.assertEqual(result.scored_candidate.candidate.info_hash, fallback_hash)
        self.assertEqual(resolver.requests, [best_hash, fallback_hash])
        self.assertEqual(len(result.attempts), 2)

    def test_never_sends_rejected_language_to_resolver(self):
        rejected_hash = "a" * 40
        good_hash = "b" * 40
        provider = FakeProvider(
            [
                item("Movie.2023.2160p.RUS.REMUX.mkv", rejected_hash, 60),
                item("Movie.2023.1080p.ENG.WEB.DL.mkv", good_hash, 10),
            ]
        )
        resolver = FakeResolver(
            {good_hash: ("https://rd.invalid/movie", "torrent-id", "/movie.mkv")}
        )
        MovieSelectionService(provider, resolver).resolve(MOVIE)
        self.assertEqual(resolver.requests, [good_hash])

    def test_reports_attempts_when_no_cached_release_exists(self):
        info_hash = "a" * 40
        provider = FakeProvider([item("Movie.2023.2160p.ENG.REMUX.mkv", info_hash, 60)])
        resolver = FakeResolver({info_hash: RealDebridError("cache miss; probe deleted")})
        with self.assertRaises(NoCachedReleaseAvailable) as caught:
            MovieSelectionService(provider, resolver).resolve(MOVIE)
        self.assertEqual(len(caught.exception.attempts), 1)

    def test_has_no_default_candidate_count_cap(self):
        candidates = [
            item(f"Movie.2023.2160p.ENG.WEB.DL.Release{i}.mkv", str(i) * 40)
            for i in range(1, 7)
        ]
        outcomes = {
            candidate.info_hash: RealDebridError("cache miss")
            for candidate in candidates
        }
        outcomes[candidates[-1].info_hash] = (
            "https://rd.invalid/movie", "torrent-id", "/movie.mkv"
        )

        result = MovieSelectionService(
            FakeProvider(candidates), FakeResolver(outcomes)
        ).resolve(MOVIE)

        self.assertEqual(result.scored_candidate.candidate.info_hash, candidates[-1].info_hash)
        self.assertEqual(len(result.attempts), 6)

    def test_interweaves_1080p_fallbacks_with_2160p_candidates(self):
        four_k = [
            item(f"Movie.2023.2160p.ENG.REMUX.Release{i}.mkv", str(i) * 40, 50)
            for i in range(1, 5)
        ]
        fallback = item("Movie.2023.1080p.ENG.WEB.DL.mkv", "f" * 40, 10)
        resolver = FakeResolver(
            {
                **{candidate.info_hash: RealDebridError("cache miss") for candidate in four_k},
                fallback.info_hash: ("https://rd.invalid/movie", "torrent-id", "/movie.mkv"),
            }
        )

        MovieSelectionService(FakeProvider(four_k + [fallback]), resolver).resolve(MOVIE)

        self.assertEqual(
            resolver.requests,
            [four_k[0].info_hash, four_k[1].info_hash, fallback.info_hash],
        )

    def test_rejects_untagged_non_english_original(self):
        info_hash = "a" * 40
        movie = MovieIdentity(1, "tt0000001", "Foreign Movie", 2020, "ja")
        provider = FakeProvider([item("Foreign.Movie.2020.2160p.REMUX.mkv", info_hash, 50)])
        resolver = FakeResolver({})
        with self.assertRaisesRegex(NoCachedReleaseAvailable, "no acceptable"):
            MovieSelectionService(provider, resolver).resolve(movie)
        self.assertFalse(resolver.requests)


if __name__ == "__main__":
    unittest.main()
