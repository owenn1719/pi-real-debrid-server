import unittest

from discover.real_debrid import RealDebridError
from discover.resolver import MovieResolver


HASH = "a" * 40
FILES = [{"id": 7, "path": "/Movie.2023.2160p.REMUX.mkv", "bytes": 50_000, "selected": 1}]
DOWNLOADED = {
    "id": "new-id",
    "hash": HASH,
    "status": "downloaded",
    "files": FILES,
    "links": ["restricted-link"],
}


class FakeClient:
    def __init__(self, existing=None, statuses=None, select_error=None):
        self.existing = existing or []
        self.statuses = list(statuses or [])
        self.select_error = select_error
        self.deleted = []
        self.added = []
        self.selected = []

    def torrents(self):
        return self.existing

    def add_magnet(self, magnet):
        self.added.append(magnet)
        return "new-id"

    def torrent_info(self, torrent_id):
        if self.statuses:
            return self.statuses.pop(0)
        return DOWNLOADED

    def select_files(self, torrent_id, file_ids):
        self.selected.append((torrent_id, file_ids))
        if self.select_error:
            raise self.select_error

    def unrestrict(self, link):
        return {"streamable": 1, "download": "https://rd.invalid/movie"}

    def delete_torrent(self, torrent_id):
        self.deleted.append(torrent_id)


class CachedResolverTests(unittest.TestCase):
    def resolver(self, client, grace=0.05):
        return MovieResolver(
            client,
            cached_grace_seconds=grace,
            poll_interval_seconds=0.001,
        )

    def test_reuses_downloaded_existing_torrent_without_deleting(self):
        existing = [{"id": "existing-id", "hash": HASH, "status": "downloaded"}]
        client = FakeClient(existing=existing, statuses=[DOWNLOADED])
        target, torrent_id, _ = self.resolver(client).acquire_cached_hash(HASH)
        self.assertEqual(target, "https://rd.invalid/movie")
        self.assertEqual(torrent_id, "existing-id")
        self.assertFalse(client.added)
        self.assertFalse(client.deleted)

    def test_leaves_preexisting_active_torrent_untouched(self):
        existing = [{"id": "existing-id", "hash": HASH, "status": "downloading"}]
        client = FakeClient(existing=existing)
        with self.assertRaisesRegex(RealDebridError, "left untouched"):
            self.resolver(client).acquire_cached_hash(HASH)
        self.assertFalse(client.added)
        self.assertFalse(client.deleted)

    def test_selects_and_returns_immediately_cached_probe(self):
        waiting = {
            "id": "new-id",
            "hash": HASH,
            "status": "waiting_files_selection",
            "files": [{**FILES[0], "selected": 0}],
            "links": [],
        }
        client = FakeClient(statuses=[waiting, DOWNLOADED])
        target, torrent_id, path = self.resolver(client).acquire_cached_hash(HASH)
        self.assertEqual(target, "https://rd.invalid/movie")
        self.assertEqual(torrent_id, "new-id")
        self.assertIn("Movie.2023", path)
        self.assertEqual(client.selected, [("new-id", [7])])
        self.assertFalse(client.deleted)

    def test_deletes_only_new_probe_after_cache_grace_timeout(self):
        downloading = {
            "id": "new-id",
            "hash": HASH,
            "status": "downloading",
            "files": FILES,
            "links": [],
        }
        client = FakeClient(statuses=[downloading] * 100)
        with self.assertRaisesRegex(RealDebridError, "probe was deleted"):
            self.resolver(client, grace=0.005).acquire_cached_hash(HASH)
        self.assertEqual(client.deleted, ["new-id"])

    def test_deletes_new_probe_when_file_selection_fails(self):
        waiting = {
            "id": "new-id",
            "hash": HASH,
            "status": "waiting_files_selection",
            "files": [{**FILES[0], "selected": 0}],
            "links": [],
        }
        client = FakeClient(
            statuses=[waiting],
            select_error=RealDebridError("file selection failed"),
        )

        with self.assertRaisesRegex(RealDebridError, "file selection failed"):
            self.resolver(client).acquire_cached_hash(HASH)

        self.assertEqual(client.deleted, ["new-id"])

    def test_deletes_new_probe_in_terminal_failure_state(self):
        failed = {
            "id": "new-id",
            "hash": HASH,
            "status": "magnet_error",
            "files": [],
            "links": [],
        }
        client = FakeClient(statuses=[failed])

        with self.assertRaisesRegex(RealDebridError, "terminal status"):
            self.resolver(client).acquire_cached_hash(HASH)

        self.assertEqual(client.deleted, ["new-id"])


if __name__ == "__main__":
    unittest.main()
