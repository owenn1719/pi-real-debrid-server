"""Reusable movie acquisition and resolution workflow."""

import time

from .media import generated_stream_url, largest_video, restricted_link_for_file
from .real_debrid import RealDebridClient, RealDebridError


TERMINAL_FAILURES = {"magnet_error", "error", "virus", "dead"}


class MovieResolver:
    def __init__(
        self,
        client: RealDebridClient,
        poll_seconds: int = 30,
        cached_grace_seconds: float = 6,
        poll_interval_seconds: float = 0.5,
    ) -> None:
        self.client = client
        self.poll_seconds = poll_seconds
        self.cached_grace_seconds = cached_grace_seconds
        self.poll_interval_seconds = poll_interval_seconds

    def _existing_torrent(self, info_hash: str) -> dict | None:
        normalized = info_hash.lower()
        return next(
            (
                torrent
                for torrent in self.client.torrents()
                if str(torrent.get("hash", "")).lower() == normalized
            ),
            None,
        )

    def resolve_existing(self, torrent_id: str) -> tuple[str, str]:
        info = self.client.torrent_info(torrent_id)
        if info.get("status") != "downloaded":
            raise RealDebridError(
                f"torrent status is {info.get('status')!r}, not 'downloaded'"
            )
        movie = largest_video(
            [item for item in info.get("files", []) if item.get("selected")]
        )
        restricted = restricted_link_for_file(info, movie.get("path"))
        target = generated_stream_url(self.client.unrestrict(restricted))
        return target, movie.get("path", "")

    def acquire_magnet(self, magnet: str) -> tuple[str, str, str]:
        torrent_id = self.client.add_magnet(magnet)
        deadline = time.monotonic() + self.poll_seconds
        selected_path: str | None = None

        while time.monotonic() < deadline:
            info = self.client.torrent_info(torrent_id)
            status = info.get("status")
            if status in TERMINAL_FAILURES:
                raise RealDebridError(f"torrent entered terminal status {status!r}")

            if status == "waiting_files_selection" and info.get("files"):
                movie = largest_video(info["files"])
                self.client.select_files(torrent_id, [movie["id"]])
                selected_path = movie.get("path")
            elif status == "downloaded":
                restricted = restricted_link_for_file(info, selected_path)
                target = generated_stream_url(self.client.unrestrict(restricted))
                movie_path = selected_path or largest_video(
                    [item for item in info.get("files", []) if item.get("selected")]
                ).get("path", "")
                return target, torrent_id, movie_path

            time.sleep(self.poll_interval_seconds)

        raise RealDebridError(
            f"torrent was not ready within {self.poll_seconds} seconds"
        )

    def acquire_cached_hash(self, info_hash: str) -> tuple[str, str, str]:
        """Resolve a hash only when it is already cached by Real-Debrid.

        Existing torrents are never deleted. A newly-created probe is deleted
        only when it misses the short cached grace window.
        """
        normalized = info_hash.lower()
        if not re_full_hash(normalized):
            raise ValueError("info hash must be 40 hexadecimal characters")

        existing = self._existing_torrent(normalized)
        if existing:
            torrent_id = str(existing.get("id", ""))
            if existing.get("status") != "downloaded":
                raise RealDebridError(
                    "matching torrent already exists but is not downloaded; left untouched"
                )
            target, path = self.resolve_existing(torrent_id)
            return target, torrent_id, path

        torrent_id = self.client.add_magnet(f"magnet:?xt=urn:btih:{normalized}")
        deadline = time.monotonic() + self.cached_grace_seconds
        selected_path: str | None = None
        files_selected = False
        completed = False
        try:
            while time.monotonic() < deadline:
                info = self.client.torrent_info(torrent_id)
                status = info.get("status")
                if status in TERMINAL_FAILURES:
                    raise RealDebridError(f"torrent entered terminal status {status!r}")

                if (
                    status == "waiting_files_selection"
                    and info.get("files")
                    and not files_selected
                ):
                    movie = largest_video(info["files"])
                    self.client.select_files(torrent_id, [movie["id"]])
                    selected_path = movie.get("path")
                    files_selected = True
                elif status == "downloaded":
                    restricted = restricted_link_for_file(info, selected_path)
                    target = generated_stream_url(self.client.unrestrict(restricted))
                    movie_path = selected_path or largest_video(
                        [item for item in info.get("files", []) if item.get("selected")]
                    ).get("path", "")
                    completed = True
                    return target, torrent_id, movie_path

                time.sleep(self.poll_interval_seconds)

            raise RealDebridError(
                "candidate was not immediately available; newly created probe was deleted"
            )
        finally:
            if not completed:
                try:
                    self.client.delete_torrent(torrent_id)
                except RealDebridError:
                    # Preserve the acquisition error. A later request still treats
                    # this torrent as pre-existing and will never delete it blindly.
                    pass


def re_full_hash(value: str) -> bool:
    return len(value) == 40 and all(character in "0123456789abcdef" for character in value)
