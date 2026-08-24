"""Movie-file selection and Real-Debrid link matching."""

import re
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
