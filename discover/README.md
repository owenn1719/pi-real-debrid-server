# Discover Service

Discover adds an Infuse-friendly movie catalog and on-demand Real-Debrid
resolver to this stack. It is a small, dependency-free Python service: the
Raspberry Pi handles metadata and redirects, while Infuse streams video
directly from Real-Debrid.

The current implementation is movie-only. TV seasons and episodes are outside
the alpha scope.

## Request flow

```text
TMDB lists -> generated .strm catalog -> Infuse
                                          |
                                          v
                              GET /play/movie/TMDB_ID
                                          |
                     TMDB identity (title/year/IMDb ID)
                                          |
                          Comet-compatible torrent results
                                          |
                       identity filter and quality ranking
                                          |
                           cached-only Real-Debrid probe
                                          |
                             HTTP 302 directly to media
```

The resolver requires the normalized release title followed by the exact TMDB
release year before a candidate can reach Real-Debrid. It then rejects known
bad sources and unsuitable audio, ranks the remaining releases, and tries them
within a bounded time budget. A newly created cache-miss probe is deleted;
pre-existing Real-Debrid torrents are never deleted.

## Python modules

### Package and startup

- `discover/__init__.py` identifies the package.
- `discover/__main__.py` is the production entry point used by
  `python -m discover`. It reads environment configuration, constructs the
  TMDB, provider, selection, and Real-Debrid components, starts catalog sync,
  and serves HTTP.

### HTTP and orchestration

- `discover/app.py` implements `/health` and
  `GET|HEAD /play/movie/{tmdb_id}`. It caches movie identities and successful
  selections in memory, serializes concurrent requests for the same TMDB ID,
  refreshes temporary Real-Debrid links, and returns safe HTTP errors and
  diagnostics.
- `discover/selection.py` coordinates provider search, exact title/year
  validation, quality ranking, 2160p/1080p attempt ordering, the overall
  selection deadline, and structured attempt history. It returns the first
  acceptable release that Real-Debrid exposes immediately.
- `discover/candidates.py` defines the provider-neutral torrent candidate
  model shared by provider adapters and selection.

### Metadata and catalog

- `discover/tmdb.py` calls TMDB for canonical movie identity (title, year,
  language, and IMDb ID) and for curated catalog pages. It validates malformed
  or incomplete responses before they enter the resolver.
- `discover/catalog.py` builds the managed `Discover/Discover Movies` STRM
  tree from weekly trending and popular TMDB movies. It sanitizes filenames,
  deduplicates titles, and atomically swaps a completed staging tree into
  place. A background scheduler runs once at startup and then at the configured
  interval.

### Candidate discovery and quality

- `discover/providers/__init__.py` marks the provider adapter package.
- `discover/providers/stremio.py` reads a Comet-compatible Stremio movie stream
  endpoint and normalizes hashes, filenames, sizes, file indexes, and cache
  hints into `TorrentCandidate` objects. The provider never receives the
  Real-Debrid token.
- `discover/quality.py` rejects promotional videos, CAM/TS and other unwanted
  sources, implausible sizes, incompatible language tags, and the literal
  hyphenated `web-dl` filename substring rejected by Real-Debrid. Dotted
  `WEB.DL`, joined `WEBDL`, and `WEB.H265` names remain eligible. It scores the
  survivors by resolution, source, codec, HDR, audio, size, and release group.

### Real-Debrid and media handling

- `discover/real_debrid.py` loads the existing Zurg token without logging it
  and wraps the Real-Debrid torrent, file-selection, deletion, and unrestriction
  API calls with sanitized errors.
- `discover/media.py` recognizes video files, excludes samples and trailers,
  chooses the largest feature file, matches selected files to restricted
  links, and validates generated HTTPS stream URLs.
- `discover/resolver.py` reuses downloaded torrents already in Real-Debrid or
  creates a short-lived cached-only magnet probe. It selects the movie file,
  unrestricts its link, and removes only a probe it created when that probe is
  not immediately available.

## Runtime services

The `discover` Compose service builds `Dockerfile.discover`, listens on port
8090, and mounts `config.yml` read-only. The separate `discover-webdav` service
publishes the generated catalog read-only on port 8091.

Current deployment defaults:

- Resolver: `http://192.168.4.58:8090`
- Catalog WebDAV: `http://192.168.4.58:8091`
- Generated catalog: `test-catalog/Discover/Discover Movies`
- Catalog size: up to 150 movies with at least 1,000 TMDB votes
- Catalog sync: startup and every 12 hours
- Provider: `https://comet.feels.legal/`
- Cached-probe grace period: 3 seconds
- Overall selection budget: 18 seconds

Rebuild and start only the Discover services with:

```sh
docker compose up -d --build discover discover-webdav
```

Check health and follow resolver logs with:

```sh
curl --fail http://127.0.0.1:8090/health
docker compose logs -f --tail 100 discover
```

## Configuration

`TMDB_BEARER_TOKEN` is required in `.env`. Set `DISCOVER_PUBLIC_URL` there when
the Pi does not use the default `192.168.4.58` address. The other settings have
defaults in `docker-compose.yml`:

| Variable | Purpose |
| --- | --- |
| `DISCOVER_ZURG_CONFIG` | Path to the Zurg YAML containing the RD token |
| `DISCOVER_COMET_URL` | Base URL of a Comet-compatible Stremio provider |
| `DISCOVER_HOST` | Resolver bind address |
| `DISCOVER_PORT` | Resolver port |
| `DISCOVER_CATALOG_PATH` | Root where the managed catalog is generated |
| `DISCOVER_PUBLIC_URL` | Resolver URL written into STRM files |
| `DISCOVER_SYNC_INTERVAL_SECONDS` | Delay between catalog rebuilds |
| `DISCOVER_MAX_CANDIDATES` | Optional positive attempt cap; `0` means no cap |

`WEBDAV_PASSWORD` configures the catalog WebDAV login. Never commit `.env` or
`config.yml`; both contain credentials and are ignored.

## Tests

The maintained test suite is under `tests/`. Run it from the repository root:

```sh
python3 -m unittest discover -s tests -v
```

The old standalone scripts under `scripts/` were validation spikes and were
removed when the package reached alpha. The unit tests are the supported test
surface now.

## Operational notes

Successful selections and TMDB identities are currently held only in process
memory. Restarting `discover` clears them. If a selected torrent is removed
manually from Real-Debrid, the service reselects on its next request, but Infuse
may retain the old redirect; removing and reimporting that Infuse item forces
it to read the STRM route again.

The service does not download, cache, proxy, or transcode video. Generated
Real-Debrid URLs and credentials are intentionally excluded from logs.

## Post-alpha backlog

1. Persist successful selection metadata and validate it across restarts.
2. Version STRM routes so Infuse notices a replaced selection reliably.
3. Prefer acceptable hashes already present in Real-Debrid before probing.
4. Add an independent provider fallback.
5. Add TV season and episode selection as a separate feature.
