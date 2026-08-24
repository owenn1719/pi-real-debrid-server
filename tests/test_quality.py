import unittest

from discover.candidates import TorrentCandidate
from discover.quality import MovieQualityProfile, rank_candidates, score_candidate


def candidate(name: str, size_gb: float = 20) -> TorrentCandidate:
    return TorrentCandidate(
        title=name,
        filename=name,
        info_hash="0" * 40,
        source="fixture",
        size_bytes=int(size_gb * 1_000_000_000),
    )


class QualityTests(unittest.TestCase):
    profile = MovieQualityProfile(original_language="en")

    def test_rejects_russian_only(self) -> None:
        result = score_candidate(candidate("Movie.2023.2160p.RUS.WEB.DL.mkv"), self.profile)
        self.assertFalse(result.accepted)
        self.assertIn("non-English", result.reasons[0])

    def test_allows_multi_and_explicit_english(self) -> None:
        multi = score_candidate(candidate("Movie.2023.2160p.MULTi.REMUX.mkv", 50), self.profile)
        english = score_candidate(candidate("Movie.2023.1080p.English.WEB.DL.mkv"), self.profile)
        self.assertTrue(multi.accepted)
        self.assertTrue(english.accepted)

    def test_rejects_only_hyphenated_web_dl_substring(self) -> None:
        blocked = score_candidate(
            candidate("Movie.2023.2160p.English.WEB-DL.H265.mkv"),
            self.profile,
        )
        dotted = score_candidate(
            candidate("Movie.2023.2160p.English.WEB.DL.H265.mkv"),
            self.profile,
        )
        joined = score_candidate(
            candidate("Movie.2023.2160p.English.WEBDL.H265.mkv"),
            self.profile,
        )
        web_h265 = score_candidate(
            candidate("Movie.2023.2160p.English.WEB.H265.mkv"),
            self.profile,
        )

        self.assertFalse(blocked.accepted)
        self.assertIn("literal web-dl", blocked.reasons[0])
        self.assertTrue(dotted.accepted)
        self.assertTrue(joined.accepted)
        self.assertTrue(web_h265.accepted)

    def test_untagged_release_only_assumes_english_for_english_original(self) -> None:
        item = candidate("Movie.2023.2160p.REMUX.mkv", 50)
        self.assertTrue(score_candidate(item, self.profile).accepted)
        non_english_original = MovieQualityProfile(original_language="ja")
        self.assertFalse(score_candidate(item, non_english_original).accepted)

    def test_accepts_explicit_original_language_audio(self) -> None:
        profile = MovieQualityProfile(original_language="ja")
        result = score_candidate(
            candidate("Anime.Movie.2025.2160p.Japanese.WEB.DL.mkv", 20),
            profile,
        )
        self.assertTrue(result.accepted)
        self.assertEqual(result.language, "original-language")

    def test_rejects_unrelated_language_for_non_english_original(self) -> None:
        profile = MovieQualityProfile(original_language="ja")
        result = score_candidate(
            candidate("Anime.Movie.2025.2160p.Russian.WEB.DL.mkv", 20),
            profile,
        )
        self.assertFalse(result.accepted)
        self.assertIn("non-English-only", result.reasons[0])

    def test_rejects_cam_and_implausibly_small_4k(self) -> None:
        self.assertFalse(
            score_candidate(candidate("Movie.2023.2160p.CAM.ENG.mkv", 12), self.profile).accepted
        )
        self.assertFalse(
            score_candidate(candidate("Movie.2023.2160p.WEB.DL.ENG.mkv", 2), self.profile).accepted
        )

    def test_rejects_trailers_even_when_the_file_is_large(self) -> None:
        result = score_candidate(
            candidate("The.Odyssey.IMAX.Trailer-3.2160p.ProRes.mov", 15),
            self.profile,
        )
        self.assertFalse(result.accepted)
        self.assertIn("promotional", result.reasons[0])

    def test_prefers_4k_remux_over_1080p_webdl(self) -> None:
        accepted, rejected = rank_candidates(
            [
                candidate("Movie.2023.1080p.English.WEB.DL-FLUX.mkv", 10),
                candidate("Movie.2023.2160p.MULTi.UHD.BluRay.REMUX-CiNEPHiLES.mkv", 60),
            ],
            self.profile,
        )
        self.assertFalse(rejected)
        self.assertEqual(accepted[0].resolution, "2160p")
        self.assertEqual(accepted[0].source_type, "remux")

    def test_enforces_maximum_size(self) -> None:
        result = score_candidate(candidate("Movie.2023.2160p.ENG.REMUX.mkv", 100), self.profile)
        self.assertFalse(result.accepted)


if __name__ == "__main__":
    unittest.main()
