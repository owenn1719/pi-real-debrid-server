"""Small dependency-free client for the Real-Debrid operations we validated."""

import json
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_ROOT = "https://api.real-debrid.com/rest/1.0"


class RealDebridError(RuntimeError):
    """A safe-to-log Real-Debrid API failure."""


def load_token(config_path: Path) -> str:
    for line in config_path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^token:\s*(.*?)\s*$", line)
        if match:
            token = match.group(1).strip("'\"")
            if token and token != "YOUR_REAL_DEBRID_TOKEN":
                return token
    raise RealDebridError(f"No Real-Debrid token found in {config_path}")


class RealDebridClient:
    def __init__(self, token: str, timeout_seconds: int = 20) -> None:
        self._token = token
        self._timeout_seconds = timeout_seconds

    def _request(
        self,
        method: str,
        path: str,
        form: dict[str, str] | None = None,
    ) -> dict:
        data = urlencode(form).encode() if form is not None else None
        request = Request(
            f"{API_ROOT}{path}",
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "pi-infuse-discover/0.1",
            },
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                body = response.read()
                return json.loads(body) if body else {}
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RealDebridError(
                f"Real-Debrid returned HTTP {error.code}: {detail}"
            ) from error
        except URLError as error:
            raise RealDebridError(
                f"Real-Debrid request failed: {error.reason}"
            ) from error

    def torrent_info(self, torrent_id: str) -> dict:
        return self._request("GET", f"/torrents/info/{torrent_id}")

    def torrents(self, limit: int = 5000) -> list[dict]:
        result = self._request("GET", f"/torrents?limit={limit}")
        if not isinstance(result, list):
            raise RealDebridError("Real-Debrid returned an invalid torrent list")
        return result

    def add_magnet(self, magnet: str) -> str:
        result = self._request("POST", "/torrents/addMagnet", {"magnet": magnet})
        torrent_id = result.get("id")
        if not isinstance(torrent_id, str) or not torrent_id:
            raise RealDebridError("Real-Debrid did not return a torrent ID")
        return torrent_id

    def select_files(self, torrent_id: str, file_ids: list[int]) -> None:
        files = ",".join(str(file_id) for file_id in file_ids)
        self._request("POST", f"/torrents/selectFiles/{torrent_id}", {"files": files})

    def unrestrict(self, restricted_link: str) -> dict:
        return self._request("POST", "/unrestrict/link", {"link": restricted_link})

    def delete_torrent(self, torrent_id: str) -> None:
        self._request("DELETE", f"/torrents/delete/{torrent_id}")
