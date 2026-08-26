"""Read torrent candidates from a Comet-compatible Stremio stream endpoint."""

import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from discover.candidates import TorrentCandidate


INFO_HASH = re.compile(r"(?<![0-9a-fA-F])([0-9a-fA-F]{40})(?![0-9a-fA-F])")
SIZE = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s*(TB|TiB|GB|GiB|MB|MiB)\b", re.I)
SIZE_FACTORS = {
    "TB": 1000**4,
    "TIB": 1024**4,
    "GB": 1000**3,
    "GIB": 1024**3,
    "MB": 1000**2,
    "MIB": 1024**2,
}


class StremioProviderError(RuntimeError):
    pass


def _info_hash(stream: dict) -> str | None:
    explicit = stream.get("infoHash") or stream.get("info_hash")
    if isinstance(explicit, str) and re.fullmatch(r"[0-9a-fA-F]{40}", explicit):
        return explicit.lower()

    url = stream.get("url")
    if isinstance(url, str):
        match = INFO_HASH.search(url)
        if match:
            return match.group(1).lower()
    return None


def _size_bytes(text: str) -> int | None:
    matches = list(SIZE.finditer(text))
    if not matches:
        return None
    match = matches[-1]
    return int(float(match.group(1)) * SIZE_FACTORS[match.group(2).upper()])


def _filename(stream: dict) -> str | None:
    hints = stream.get("behaviorHints")
    if isinstance(hints, dict):
        filename = hints.get("filename")
        if isinstance(filename, str) and filename.strip():
            return filename.strip()
    return None


def _video_size(stream: dict) -> int | None:
    hints = stream.get("behaviorHints")
    if isinstance(hints, dict):
        size = hints.get("videoSize")
        if isinstance(size, int) and size > 0:
            return size
    return None


def _cached_hint(stream: dict) -> bool | None:
    combined = f"{stream.get('name', '')}\n{stream.get('title', '')}".lower()
    if any(marker in combined for marker in ("[rd+]", "cached", "⚡", "💾 rd")):
        return True
    if any(marker in combined for marker in ("[rd download]", "uncached")):
        return False
    return None


def parse_streams(payload: dict, source: str) -> list[TorrentCandidate]:
    candidates: list[TorrentCandidate] = []
    seen: set[str] = set()
    streams = payload.get("streams", [])
    if not isinstance(streams, list):
        raise StremioProviderError("provider response has no streams list")

    for stream in streams:
        if not isinstance(stream, dict):
            continue
        info_hash = _info_hash(stream)
        if not info_hash or info_hash in seen:
            continue
        filename = _filename(stream)
        title = stream.get("title") or filename or stream.get("name")
        if not isinstance(title, str) or not title.strip():
            continue
        seen.add(info_hash)
        candidates.append(
            TorrentCandidate(
                title=title.strip(),
                info_hash=info_hash,
                source=source,
                size_bytes=_video_size(stream) or _size_bytes(title),
                filename=filename,
                file_index=stream.get("fileIdx") if isinstance(stream.get("fileIdx"), int) else None,
                cached_hint=_cached_hint(stream),
            )
        )
    return candidates


class StremioStreamProvider:
    def __init__(self, base_url: str, timeout_seconds: int = 15) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout_seconds = timeout_seconds

    def _streams(self, path: str) -> list[TorrentCandidate]:
        endpoint = urljoin(self.base_url, path)
        request = Request(endpoint, headers={"User-Agent": "pi-infuse-discover/0.1"})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.load(response)
        except HTTPError as error:
            raise StremioProviderError(
                f"provider returned HTTP {error.code}"
            ) from error
        except (URLError, json.JSONDecodeError) as error:
            raise StremioProviderError(f"provider request failed: {error}") from error
        return parse_streams(payload, self.base_url)

    def search_movie(self, imdb_id: str) -> list[TorrentCandidate]:
        if not re.fullmatch(r"tt\d+", imdb_id):
            raise ValueError("IMDb ID must look like tt6718170")
        return self._streams(f"stream/movie/{imdb_id}.json")

    def search_episode(
        self, imdb_id: str, season: int, episode: int
    ) -> list[TorrentCandidate]:
        if not re.fullmatch(r"tt\d+", imdb_id):
            raise ValueError("IMDb ID must look like tt11280740")
        if season <= 0 or episode <= 0:
            raise ValueError("season and episode must be positive")
        return self._streams(f"stream/series/{imdb_id}:{season}:{episode}.json")
