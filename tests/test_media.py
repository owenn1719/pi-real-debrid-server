import unittest

from discover.media import largest_video
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


if __name__ == "__main__":
    unittest.main()
