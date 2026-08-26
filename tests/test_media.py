import unittest

from discover.media import (
    episode_reference,
    largest_video,
    requested_episode_file,
    season_episode_files,
)
from discover.real_debrid import RealDebridError


class MediaTests(unittest.TestCase):
    def test_ignores_large_trailer_when_selecting_movie_file(self):
        movie = {"id": 1, "path": "/Movie.2025.1080p.mkv", "bytes": 5_000}
        trailer = {"id": 2, "path": "/Movie.Trailer.4K.mov", "bytes": 10_000}
        self.assertEqual(largest_video([trailer, movie]), movie)

    def test_rejects_torrent_containing_only_promotional_video(self):
        files = [{"id": 1, "path": "/Movie.Teaser.4K.mov", "bytes": 10_000}]
        with self.assertRaisesRegex(RealDebridError, "non-promotional"):
            largest_video(files)

    def test_parses_common_episode_names(self):
        self.assertEqual(episode_reference("Show.S01E02.mkv").episodes, frozenset({2}))
        self.assertEqual(episode_reference("Show.1x03.mkv").episodes, frozenset({3}))

    def test_collects_regular_season_files_and_ignores_extras(self):
        files = [
            {"id": 1, "path": "/Show/Show.S01E01.mkv"},
            {"id": 2, "path": "/Show/Show.S01E02.mkv"},
            {"id": 3, "path": "/Show/Show.S00E01.mkv"},
            {"id": 4, "path": "/Show/Show.S01E03.Trailer.mkv"},
        ]
        self.assertEqual(set(season_episode_files(files, 1)), {1, 2})

    def test_rejects_provider_index_for_wrong_episode(self):
        files = [
            {"id": 1, "path": "/Show.S01E01.mkv"},
            {"id": 2, "path": "/Show.S01E02.mkv"},
        ]
        with self.assertRaisesRegex(RealDebridError, "file index"):
            requested_episode_file(
                files, season=1, episode=1, preferred_index=1
            )


if __name__ == "__main__":
    unittest.main()
