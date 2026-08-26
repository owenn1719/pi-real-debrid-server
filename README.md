# Pi Real-Debrid Server

Docker Compose deployment for a Raspberry Pi media server built around
[Zurg](https://github.com/debridmediamanager/zurg),
[rclone](https://rclone.org/), Real-Debrid, and Infuse.

The stack turns a Real-Debrid torrent library into a filesystem at
`/mnt/zurg`. Infuse connects through a separate rclone WebDAV server because
newer Infuse versions can have trouble with Zurg's built-in WebDAV endpoint.

## Architecture

```text
Real-Debrid
    |
    v
Zurg :9999
    |
    v
rclone FUSE mount -> /mnt/zurg
    |
    +--> rclone WebDAV :8080 -> Infuse

TMDB -> Discover catalog -> WebDAV :8091 -> Infuse
                             |
                             +--> Discover resolver :8090
                                      |
                                      +--> Comet metadata
                                      +--> Real-Debrid -> direct stream
```

The Compose stack contains five containers:

| Container | Purpose |
| --- | --- |
| `zurg` | Connects to Real-Debrid and exposes the configured media directories |
| `rclone` | Mounts Zurg at `/mnt/zurg` using FUSE |
| `webdav` | Publishes `/mnt/zurg` as standard WebDAV for Infuse |
| `discover` | Generates movie selections and redirects Infuse to Real-Debrid |
| `discover-webdav` | Publishes the generated Discover STRM catalog read-only |

## Quick Start

Clone the repository and enter the project directory:

```sh
git clone https://github.com/owenn1719/pi-real-debrid-server.git
cd pi-real-debrid-server
```

Create the local Zurg configuration and add your Real-Debrid API token:

```sh
cp config.example.yml config.yml
```

Create `.env` with the WebDAV password, a TMDB API Read Access Token, and the
LAN URL Infuse should use to reach Discover:

```dotenv
WEBDAV_PASSWORD=choose-a-password
TMDB_BEARER_TOKEN=your-tmdb-read-access-token
DISCOVER_PUBLIC_URL=http://192.168.4.58:8090
```

Replace the example address if the Raspberry Pi uses a different LAN IP.

Create the host mount and start the stack:

```sh
sudo mkdir -p /mnt/zurg
docker compose up -d
```

Check that the containers are running and the media mount is populated:

```sh
docker compose ps
find /mnt/zurg -maxdepth 1 -type d -print
```

Never commit `config.yml` or `.env`. Both are ignored by Git because they
contain local credentials.

## Connections

### Infuse

Use a WebDAV connection with:

| Setting | Value |
| --- | --- |
| Protocol | WebDAV |
| Address | Raspberry Pi address, for example `192.168.4.58` |
| Port | `8080` |
| Path | `/` |
| Username | `oarters` |
| Password | Value of `WEBDAV_PASSWORD` in `.env` |

The WebDAV mount is intentionally writable. Deleting an unwanted item from
Infuse can delete it from the underlying Zurg/Real-Debrid library. Do not use
Zurg's native `:9999/dav` endpoint for normal Infuse access.

For the separate movie discovery catalog on port `8091`, including its module
guide, configuration, selection rules, and operations, see
[discover/README.md](discover/README.md).

## Useful Commands

```sh
# Validate the Compose file
docker compose config

# Start, stop, or restart the stack
docker compose up -d
docker compose down
docker compose restart zurg

# Follow service logs
docker logs -f --tail 50 zurg
docker logs -f --tail 50 rclone
docker logs -f --tail 50 webdav

# Test the WebDAV endpoint
export DAV_AUTH='oarters:your-webdav-password'
curl -i -u "$DAV_AUTH" \\
  -X PROPFIND \\
  -H 'Depth: 1' \\
  http://127.0.0.1:8080/movies/
```

A healthy WebDAV `PROPFIND` request returns `HTTP/1.1 207 Multi-Status`.

For the full Infuse troubleshooting procedure, mount checks, and restart
details, see [SETUP.md](SETUP.md).

## Configuration

Edit the local `config.yml` to change Zurg behavior. The checked-in
`config.example.yml` defines the current directory layout:

- `anime`: torrents matching an eight-character hexadecimal identifier
- `shows`: torrents containing episodes
- `movies`: torrents whose largest file is exposed

The rclone remote in [rclone.conf](rclone.conf) points at Zurg's internal
Docker address, `http://zurg:9999/dav`.

## Security Notes

- Keep the Real-Debrid token in the ignored local `config.yml` only.
- Keep the WebDAV password in the ignored `.env` file only.
- Port `8080` is the Infuse-facing service. Do not expose it to the public
  internet without adding appropriate network security.
- Delete operations through Infuse are real library operations, not just
  local filesystem cleanup.

## Upstream Documentation

Zurg's general configuration and command documentation is maintained in the
[upstream Zurg repository](https://github.com/debridmediamanager/zurg-testing).
