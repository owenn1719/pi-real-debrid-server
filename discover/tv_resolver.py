"""Cached-only acquisition of a complete aired TV season and one episode link."""

import time

from .candidates import TorrentCandidate
from .media import (
    generated_stream_url,
    requested_episode_file,
    restricted_link_for_file,
    season_episode_files,
)
from .movie_resolver import TERMINAL_FAILURES, re_full_hash
from .real_debrid import RealDebridClient, RealDebridError
from .tv_selection import EpisodeRequest


class EpisodeResolver:
    def __init__(
        self,
        client: RealDebridClient,
        *,
        cached_grace_seconds: float = 6,
        poll_interval_seconds: float = 0.5,
    ) -> None:
        self.client = client
        self.cached_grace_seconds = cached_grace_seconds
        self.poll_interval_seconds = poll_interval_seconds

    def _existing_torrent(self, info_hash: str) -> dict | None:
        return next(
            (
                torrent for torrent in self.client.torrents()
                if str(torrent.get("hash", "")).lower() == info_hash
            ),
            None,
        )

    @staticmethod
    def _validated_season_files(info: dict, request: EpisodeRequest) -> dict[int, dict]:
        season_files = season_episode_files(info.get("files", []), request.season)
        missing = sorted(request.expected_season_episodes - set(season_files))
        if missing:
            raise RealDebridError(
                "candidate is missing expected aired season episodes: "
                + ",".join(str(number) for number in missing)
            )
        if request.episode not in season_files:
            raise RealDebridError("candidate does not contain the requested episode")
        return {
            number: season_files[number]
            for number in sorted(request.expected_season_episodes)
        }

    def _resolve_downloaded(
        self,
        info: dict,
        request: EpisodeRequest,
        *,
        preferred_index: int | None,
    ) -> tuple[str, str, tuple[str, ...]]:
        selected = [item for item in info.get("files", []) if item.get("selected")]
        season_files = self._validated_season_files({"files": selected}, request)
        episode = requested_episode_file(
            selected,
            season=request.season,
            episode=request.episode,
            preferred_index=None,
        )
        restricted = restricted_link_for_file(info, episode.get("path"))
        target = generated_stream_url(self.client.unrestrict(restricted))
        return target, episode.get("path", ""), tuple(
            item.get("path", "") for item in season_files.values()
        )

    def resolve_existing(
        self, torrent_id: str, request: EpisodeRequest
    ) -> tuple[str, str, tuple[str, ...]]:
        info = self.client.torrent_info(torrent_id)
        if info.get("status") != "downloaded":
            raise RealDebridError(
                f"torrent status is {info.get('status')!r}, not 'downloaded'"
            )
        return self._resolve_downloaded(info, request, preferred_index=None)

    def acquire_cached_season(
        self,
        candidate: TorrentCandidate,
        request: EpisodeRequest,
    ) -> tuple[str, str, str, tuple[str, ...]]:
        info_hash = candidate.info_hash.lower()
        if not re_full_hash(info_hash):
            raise ValueError("info hash must be 40 hexadecimal characters")

        existing = self._existing_torrent(info_hash)
        if existing:
            torrent_id = str(existing.get("id", ""))
            if existing.get("status") != "downloaded":
                raise RealDebridError(
                    "matching torrent already exists but is not downloaded; left untouched"
                )
            info = self.client.torrent_info(torrent_id)
            target, path, selected_paths = self._resolve_downloaded(
                info, request, preferred_index=candidate.file_index
            )
            return target, torrent_id, path, selected_paths

        torrent_id = self.client.add_magnet(candidate.magnet)
        deadline = time.monotonic() + self.cached_grace_seconds
        completed = False
        files_selected = False
        requested_path: str | None = None
        try:
            while time.monotonic() < deadline:
                info = self.client.torrent_info(torrent_id)
                status = info.get("status")
                if status in TERMINAL_FAILURES:
                    raise RealDebridError(f"torrent entered terminal status {status!r}")
                if status == "waiting_files_selection" and info.get("files") and not files_selected:
                    season_files = self._validated_season_files(info, request)
                    requested = requested_episode_file(
                        info["files"],
                        season=request.season,
                        episode=request.episode,
                        preferred_index=candidate.file_index,
                    )
                    requested_path = requested.get("path")
                    self.client.select_files(
                        torrent_id, [item["id"] for item in season_files.values()]
                    )
                    files_selected = True
                elif status == "downloaded":
                    target, path, selected_paths = self._resolve_downloaded(
                        info, request, preferred_index=None
                    )
                    if requested_path and path != requested_path:
                        raise RealDebridError(
                            "requested episode path changed after file selection"
                        )
                    completed = True
                    return target, torrent_id, path, selected_paths
                time.sleep(self.poll_interval_seconds)
            raise RealDebridError(
                "candidate was not immediately available; newly created probe was deleted"
            )
        finally:
            if not completed:
                try:
                    self.client.delete_torrent(torrent_id)
                except RealDebridError:
                    pass
