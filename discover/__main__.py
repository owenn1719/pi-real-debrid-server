"""Production process entry point for the Discover service."""

import os
from pathlib import Path

from .app import DiscoverApplication, serve
from .catalog import CatalogSync, start_catalog_scheduler
from .providers.stremio import StremioStreamProvider
from .real_debrid import RealDebridClient, load_token
from .resolver import MovieResolver
from .selection import MovieSelectionService
from .tmdb import TmdbClient


def main() -> None:
    config_path = Path(os.getenv("DISCOVER_ZURG_CONFIG", "/app/config.yml"))
    comet_url = os.getenv("DISCOVER_COMET_URL", "https://comet.feels.legal/")
    host = os.getenv("DISCOVER_HOST", "0.0.0.0")
    port = int(os.getenv("DISCOVER_PORT", "8090"))
    catalog_path = Path(os.getenv("DISCOVER_CATALOG_PATH", "/catalog"))
    public_url = os.getenv("DISCOVER_PUBLIC_URL", "http://192.168.4.58:8090")
    sync_interval = int(os.getenv("DISCOVER_SYNC_INTERVAL_SECONDS", "43200"))
    max_candidates_value = int(os.getenv("DISCOVER_MAX_CANDIDATES", "0"))
    max_candidates = max_candidates_value if max_candidates_value > 0 else None
    tmdb_token = os.getenv("TMDB_BEARER_TOKEN", "")
    if not tmdb_token:
        raise RuntimeError("TMDB_BEARER_TOKEN is required")

    resolver = MovieResolver(
        RealDebridClient(load_token(config_path)),
        cached_grace_seconds=3,
        poll_interval_seconds=0.5,
    )
    selection = MovieSelectionService(
        StremioStreamProvider(comet_url),
        resolver,
        max_candidates=max_candidates,
        total_budget_seconds=18,
    )
    tmdb = TmdbClient(tmdb_token)
    start_catalog_scheduler(
        CatalogSync(tmdb, catalog_path, public_base_url=public_url),
        sync_interval,
    )
    serve(
        DiscoverApplication(selection, movie_lookup=tmdb),
        host=host,
        port=port,
    )


if __name__ == "__main__":
    main()
