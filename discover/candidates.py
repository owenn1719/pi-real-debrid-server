"""Provider-neutral torrent candidate model."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TorrentCandidate:
    title: str
    info_hash: str
    source: str
    size_bytes: int | None = None
    filename: str | None = None
    file_index: int | None = None
    cached_hint: bool | None = None

    @property
    def magnet(self) -> str:
        return f"magnet:?xt=urn:btih:{self.info_hash}"
