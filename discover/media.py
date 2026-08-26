"""Movie-file selection and Real-Debrid link matching."""

import re
from dataclasses import dataclass
from pathlib import Path

from .real_debrid import RealDebridError


VIDEO_EXTENSIONS = {
    ".3gp", ".avi", ".divx", ".flv", ".m2ts", ".m4v", ".mkv", ".mov",
    ".mp4", ".mpeg", ".mpg", ".mts", ".ts", ".webm", ".wmv",
}
PROMOTIONAL_VIDEO = re.compile(
    r"(?:^|[. _-])(trailer(?![. _-]+park(?:$|[. _-]))|teaser|featurette)(?:$|[. _-])",
    re.I,
)
EPISODE_PATTERN = re.compile(
    r"(?i)(?:^|[^a-z0-9])s(\d{1,2})e(\d{1,3})(?:e(\d{1,3}))?"
)
X_EPISODE_PATTERN = re.compile(
    r"(?i)(?:^|[^a-z0-9])(\d{1,2})x(\d{1,3})(?:[^a-z0-9]|$)"
)


@dataclass(frozen=True, slots=True)
class EpisodeReference:
    season: int
    episodes: frozenset[int]


def is_video(path: str) -> bool:
    return Path(path).suffix.lower() in VIDEO_EXTENSIONS


def largest_video(files: list[dict]) -> dict:
    videos = [
        item
        for item in files
        if is_video(item.get("path", ""))
        and not PROMOTIONAL_VIDEO.search(Path(item.get("path", "")).name)
    ]
    if not videos:
        raise RealDebridError("torrent contains no non-promotional video files")
    return max(videos, key=lambda item: item.get("bytes", 0))


def episode_reference(path: str) -> EpisodeReference | None:
    name = Path(path).name
    match = EPISODE_PATTERN.search(name)
    if match:
        episodes = {int(match.group(2))}
        if match.group(3):
            episodes.add(int(match.group(3)))
        return EpisodeReference(int(match.group(1)), frozenset(episodes))
    match = X_EPISODE_PATTERN.search(name)
    if match:
        return EpisodeReference(int(match.group(1)), frozenset({int(match.group(2))}))
    return None


def season_episode_files(files: list[dict], season: int) -> dict[int, dict]:
    """Return one unambiguous regular video file for each episode in a season."""
    matches: dict[int, dict] = {}
    ambiguous: set[int] = set()
    for item in files:
        path = item.get("path", "")
        if (
            not is_video(path)
            or PROMOTIONAL_VIDEO.search(Path(path).name)
        ):
            continue
        reference = episode_reference(path)
        if reference is None or reference.season != season or len(reference.episodes) != 1:
            continue
        episode = next(iter(reference.episodes))
        if episode in matches:
            ambiguous.add(episode)
        else:
            matches[episode] = item
    for episode in ambiguous:
        matches.pop(episode, None)
    return matches


def requested_episode_file(
    files: list[dict],
    *,
    season: int,
    episode: int,
    preferred_index: int | None = None,
) -> dict:
    matches = season_episode_files(files, season)
    desired = matches.get(episode)
    if desired is None:
        raise RealDebridError("torrent does not contain one unambiguous requested episode file")
    if preferred_index is not None:
        indexed = files[preferred_index] if 0 <= preferred_index < len(files) else None
        if indexed is not None and indexed.get("path") != desired.get("path"):
            raise RealDebridError("provider file index did not match the requested episode")
    return desired


def restricted_link_for_file(info: dict, desired_path: str | None = None) -> str:
    selected = [item for item in info.get("files", []) if item.get("selected")]
    links = info.get("links", [])
    if not selected or len(selected) != len(links):
        raise RealDebridError(
            "downloaded torrent did not expose matching selected files and links"
        )

    if desired_path is None:
        desired = largest_video(selected)
    else:
        desired = next(
            (item for item in selected if item.get("path") == desired_path),
            None,
        )
        if desired is None:
            raise RealDebridError("selected movie file was not present after acquisition")

    return links[selected.index(desired)]


def generated_stream_url(result: dict) -> str:
    if result.get("streamable") != 1:
        raise RealDebridError("Real-Debrid did not mark the generated link as streamable")
    target = result.get("download")
    if not isinstance(target, str) or not target.startswith("https://"):
        raise RealDebridError("Real-Debrid did not return a valid generated URL")
    return target
