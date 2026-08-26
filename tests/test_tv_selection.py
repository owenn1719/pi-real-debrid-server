import unittest

from discover.candidates import TorrentCandidate
from discover.real_debrid import RealDebridError
from discover.tv_selection import (
    EpisodeRequest,
    EpisodeSelectionService,
    SeriesIdentity,
    candidate_matches_series,
)


REQUEST = EpisodeRequest(
    SeriesIdentity(95396, "tt11280740", "Severance", 2022, "en"),
    1,
    1,
    frozenset(range(1, 10)),
)


def candidate(name, info_hash="a" * 40):
    return TorrentCandidate(
        name, info_hash, "fixture", size_bytes=40_000_000_000, filename=name
    )


class FakeProvider:
    def __init__(self, candidates):
        self.candidates = candidates
        self.requests = []

    def search_episode(self, imdb_id, season, episode):
        self.requests.append((imdb_id, season, episode))
        return self.candidates


class FakeResolver:
    def __init__(self, outcomes):
        self.outcomes = outcomes
        self.requests = []

    def acquire_cached_season(self, item, request):
        self.requests.append(item.info_hash)
        outcome = self.outcomes[item.info_hash]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class TvSelectionTests(unittest.TestCase):
    def test_matches_season_pack_but_not_single_episode_or_wrong_show(self):
        self.assertTrue(candidate_matches_series(
            candidate("Severance.S01.2160p.WEB.DL.mkv"), REQUEST
        ))
        self.assertFalse(candidate_matches_series(
            candidate("Severance.S01E01.2160p.WEB.DL.mkv"), REQUEST
        ))
        self.assertFalse(candidate_matches_series(
            candidate("Other.Show.S01.2160p.WEB.DL.mkv"), REQUEST
        ))

    def test_tries_ranked_season_packs_until_complete_cached_result(self):
        first = candidate("Severance.S01.2160p.REMUX.mkv", "a" * 40)
        second = candidate("Severance.S01.1080p.WEB.DL.mkv", "b" * 40)
        resolver = FakeResolver({
            first.info_hash: RealDebridError("missing expected aired season episodes: 9"),
            second.info_hash: (
                "https://rd.invalid/pilot", "torrent-id", "/S01E01.mkv",
                tuple(f"/S01E{number:02d}.mkv" for number in range(1, 10)),
            ),
        })
        result = EpisodeSelectionService(
            FakeProvider([first, second]), resolver
        ).resolve(REQUEST)
        self.assertEqual(result.torrent_id, "torrent-id")
        self.assertEqual(resolver.requests, [first.info_hash, second.info_hash])


if __name__ == "__main__":
    unittest.main()
