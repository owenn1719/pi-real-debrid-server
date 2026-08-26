import unittest

from discover.candidates import TorrentCandidate
from discover.real_debrid import RealDebridError
from discover.tv_resolver import EpisodeResolver
from discover.tv_selection import EpisodeRequest, SeriesIdentity


HASH = "a" * 40
FILES = [
    {"id": 1, "path": "/Show/Show.S01E01.mkv", "bytes": 1000, "selected": 0},
    {"id": 2, "path": "/Show/Show.S01E02.mkv", "bytes": 1000, "selected": 0},
    {"id": 3, "path": "/Show/sample.mkv", "bytes": 100, "selected": 0},
]
REQUEST = EpisodeRequest(
    SeriesIdentity(1, "tt0000001", "Show", 2024, "en"),
    1,
    1,
    frozenset({1, 2}),
)
CANDIDATE = TorrentCandidate("Show.S01.1080p.WEB.DL", HASH, "fixture", file_index=0)


class FakeClient:
    def __init__(self, statuses, existing=None):
        self.statuses = list(statuses)
        self.existing = existing or []
        self.selected = []
        self.deleted = []

    def torrents(self):
        return self.existing

    def add_magnet(self, magnet):
        return "new-id"

    def torrent_info(self, torrent_id):
        if len(self.statuses) > 1:
            return self.statuses.pop(0)
        return self.statuses[0]

    def select_files(self, torrent_id, file_ids):
        self.selected.append((torrent_id, file_ids))

    def unrestrict(self, link):
        return {"streamable": 1, "download": "https://rd.invalid/episode"}

    def delete_torrent(self, torrent_id):
        self.deleted.append(torrent_id)


class TvResolverTests(unittest.TestCase):
    def resolver(self, client):
        return EpisodeResolver(client, cached_grace_seconds=0.05, poll_interval_seconds=0)

    def test_selects_complete_season_and_returns_pilot(self):
        waiting = {"status": "waiting_files_selection", "files": FILES}
        downloaded_files = [
            {**item, "selected": 1 if item["id"] in {1, 2} else 0}
            for item in FILES
        ]
        downloaded = {
            "status": "downloaded",
            "files": downloaded_files,
            "links": ["restricted-1", "restricted-2"],
        }
        client = FakeClient([waiting, downloaded])
        result = self.resolver(client).acquire_cached_season(CANDIDATE, REQUEST)
        self.assertEqual(client.selected, [("new-id", [1, 2])])
        self.assertEqual(result[2], "/Show/Show.S01E01.mkv")
        self.assertFalse(client.deleted)

    def test_rejects_incomplete_new_pack_and_deletes_probe(self):
        incomplete = {"status": "waiting_files_selection", "files": FILES[:1]}
        client = FakeClient([incomplete])
        with self.assertRaisesRegex(RealDebridError, "missing expected"):
            self.resolver(client).acquire_cached_season(CANDIDATE, REQUEST)
        self.assertEqual(client.deleted, ["new-id"])

    def test_leaves_incomplete_existing_torrent_untouched(self):
        downloaded = {
            "status": "downloaded",
            "files": [{**FILES[0], "selected": 1}],
            "links": ["restricted-1"],
        }
        client = FakeClient(
            [downloaded], existing=[{"id": "old-id", "hash": HASH, "status": "downloaded"}]
        )
        with self.assertRaisesRegex(RealDebridError, "missing expected"):
            self.resolver(client).acquire_cached_season(CANDIDATE, REQUEST)
        self.assertFalse(client.selected)
        self.assertFalse(client.deleted)


if __name__ == "__main__":
    unittest.main()
