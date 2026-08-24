import io
import unittest
from unittest.mock import patch

from discover.tmdb import TmdbClient, TmdbError


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class TmdbTests(unittest.TestCase):
    @patch("discover.tmdb.urlopen")
    def test_movie_identity_includes_imdb_id(self, urlopen):
        urlopen.return_value = FakeResponse(
            b'{"id":502356,"title":"The Super Mario Bros. Movie",'
            b'"release_date":"2023-04-05","original_language":"en",'
            b'"external_ids":{"imdb_id":"tt6718170"}}'
        )
        movie = TmdbClient("secret").movie_identity(502356)
        self.assertEqual(movie.imdb_id, "tt6718170")
        self.assertEqual(movie.year, 2023)
        request = urlopen.call_args.args[0]
        self.assertIn("append_to_response=external_ids", request.full_url)
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")

    @patch("discover.tmdb.urlopen")
    def test_movie_without_imdb_id_is_rejected(self, urlopen):
        urlopen.return_value = FakeResponse(
            b'{"title":"Movie","release_date":"2023-01-01",'
            b'"original_language":"en","external_ids":{}}'
        )
        with self.assertRaises(TmdbError):
            TmdbClient("secret").movie_identity(1)

    @patch("discover.tmdb.urlopen")
    def test_catalog_filters_movies_below_minimum_vote_count(self, urlopen):
        urlopen.return_value = FakeResponse(
            b'{"page":1,"total_pages":1,"results":['
            b'{"id":1,"title":"Broad Hit","release_date":"2024-01-01","vote_count":5000},'
            b'{"id":2,"title":"Niche Favorite","release_date":"2024-01-01","vote_count":50}'
            b']}'
        )

        movies = TmdbClient("secret").catalog_movies(
            "trending/movie/week", limit=150, min_vote_count=1000
        )

        self.assertEqual([movie.tmdb_id for movie in movies], [1])


if __name__ == "__main__":
    unittest.main()
