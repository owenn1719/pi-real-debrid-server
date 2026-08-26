import unittest
from unittest.mock import patch
import io

from discover.providers.stremio import StremioStreamProvider, parse_streams


class StremioProviderTests(unittest.TestCase):
    def test_parses_comet_direct_torrent_shape(self) -> None:
        payload = {
            "streams": [
                {
                    "name": "[TORRENT] Comet 2160p",
                    "infoHash": "6cae9f613d3b2c47f9fcf825bea5f1239baee086",
                    "fileIdx": 0,
                    "behaviorHints": {
                        "filename": "Example.Movie.2023.2160p.REMUX.MULTi.mkv",
                        "videoSize": 62_218_745_579,
                    },
                }
            ]
        }
        candidate = parse_streams(payload, "fixture")[0]
        self.assertEqual(candidate.title, "Example.Movie.2023.2160p.REMUX.MULTi.mkv")
        self.assertEqual(candidate.size_bytes, 62_218_745_579)
        self.assertEqual(candidate.file_index, 0)
        self.assertEqual(candidate.source, "fixture")

    def test_extracts_hash_from_resolve_url(self) -> None:
        payload = {
            "streams": [
                {
                    "title": "Example Movie 1080p WEB-DL 8.5 GB",
                    "url": (
                        "https://provider.invalid/resolve/service/"
                        "0123456789abcdef0123456789abcdef01234567/file"
                    ),
                }
            ]
        }
        candidate = parse_streams(payload, "fixture")[0]
        self.assertEqual(
            candidate.info_hash,
            "0123456789abcdef0123456789abcdef01234567",
        )
        self.assertEqual(candidate.size_bytes, 8_500_000_000)

    @patch("discover.providers.stremio.urlopen")
    def test_requests_standard_series_episode_identifier(self, urlopen) -> None:
        response = io.BytesIO(b'{"streams":[]}')
        response.__enter__ = lambda item: item
        response.__exit__ = lambda item, *args: item.close()
        urlopen.return_value = response
        StremioStreamProvider("https://comet.invalid/").search_episode(
            "tt11280740", 1, 1
        )
        request = urlopen.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "https://comet.invalid/stream/series/tt11280740:1:1.json",
        )


if __name__ == "__main__":
    unittest.main()
