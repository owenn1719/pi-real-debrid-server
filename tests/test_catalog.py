import tempfile
import unittest
from pathlib import Path

from discover.catalog import CatalogSync, safe_filename
from discover.tmdb import TmdbCatalogMovie, TmdbCatalogSeries


class FakeTmdb:
    def __init__(self):
        self.requests = []

    def catalog_movies(self, path, *, limit=100, min_vote_count=0):
        self.requests.append((path, limit, min_vote_count))
        return [
            TmdbCatalogMovie(502356, "The Super Mario Bros. Movie", 2023),
            TmdbCatalogMovie(1, "Bad: Name?", 2024),
        ][:limit]

    def catalog_series(self, path, *, limit=50, min_vote_count=0):
        self.requests.append((path, limit, min_vote_count))
        return [TmdbCatalogSeries(95396, "Severance", 2022)][:limit]


class SplitTmdb:
    def catalog_movies(self, path, *, limit=100, min_vote_count=0):
        if path == "trending/movie/week":
            return [TmdbCatalogMovie(1, "Trending", 2024)]
        return [
            TmdbCatalogMovie(1, "Trending", 2024),
            TmdbCatalogMovie(2, "Popular", 2023),
        ]

    def catalog_series(self, path, *, limit=50, min_vote_count=0):
        return []


class CatalogTests(unittest.TestCase):
    def test_rebuilds_only_managed_discover_folder(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manual = root / "Infuse Test Catalog" / "manual.strm"
            manual.parent.mkdir()
            manual.write_text("keep me", encoding="utf-8")
            stale = root / "Discover" / "Trending Movies" / "stale.strm"
            stale.parent.mkdir(parents=True)
            stale.write_text("stale", encoding="utf-8")

            tmdb = FakeTmdb()
            counts = CatalogSync(tmdb, root, limit=2).sync()

            self.assertEqual(counts, {"Discover Movies": 2, "Discover TV Shows": 1})
            self.assertEqual(
                tmdb.requests,
                [
                    ("trending/movie/week", 2, 1_000),
                    ("trending/tv/week", 50, 1_000),
                    ("tv/popular", 50, 1_000),
                ],
            )
            self.assertEqual(manual.read_text(encoding="utf-8"), "keep me")
            self.assertFalse(stale.exists())
            generated = root / "Discover" / "Discover Movies"
            mario = generated / "The Super Mario Bros. Movie (2023).strm"
            self.assertEqual(
                mario.read_text(encoding="utf-8"),
                "http://192.168.4.58:8090/play/movie/502356\n",
            )
            self.assertTrue((generated / "Bad- Name- (2024).strm").exists())
            pilot = root / "Discover" / "Discover TV Shows" / "Severance (2022) - S01E01.strm"
            self.assertEqual(
                pilot.read_text(encoding="utf-8"),
                "http://192.168.4.58:8090/play/series/95396/1/1\n",
            )

    def test_filename_removes_path_characters(self):
        self.assertEqual(safe_filename('A/B:C*D?"E'), "A-B-C-D--E")

    def test_popular_movies_fill_remaining_catalog_slots(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            counts = CatalogSync(SplitTmdb(), root, limit=2).sync()

            self.assertEqual(counts, {"Discover Movies": 2, "Discover TV Shows": 0})
            generated = root / "Discover" / "Discover Movies"
            self.assertTrue((generated / "Trending (2024).strm").exists())
            self.assertTrue((generated / "Popular (2023).strm").exists())


if __name__ == "__main__":
    unittest.main()
