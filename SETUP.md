# Zurg / rclone / WebDAV Setup

Last known-good setup: August 12, 2026

## Overview

The Raspberry Pi runs three Docker containers:

Real-Debrid
    |
    v
Zurg
    |
    v
rclone mount
    |
    v
/mnt/zurg
    |
    v
separate rclone WebDAV server
    |
    v
Infuse

The separate rclone WebDAV server exists because Zurg's built-in WebDAV endpoint has non-standard PROPFIND behavior that newer Infuse versions have trouble with.

The separate WebDAV server has been tested successfully and movies play through Infuse.

---

## Project location

Main project:

/home/oarters/zurg-testing

Compose file:

/home/oarters/zurg-testing/docker-compose.yml

Zurg configuration template:

/home/oarters/zurg-testing/config.example.yml

Create the local runtime configuration from the template:

cp config.example.yml config.yml

Add your Real-Debrid token to the local config.yml. The local config.yml is
ignored by Git and must not be committed.

rclone configuration:

/home/oarters/zurg-testing/rclone.conf

WebDAV password:

/home/oarters/zurg-testing/.env

The same `.env` file must define `TMDB_BEARER_TOKEN`. Set
`DISCOVER_PUBLIC_URL` when the Pi does not use `http://192.168.4.58:8090`.

Media mount:

/mnt/zurg

Do not put the actual WebDAV password in this file.

---

## Docker containers

There are five containers in the Compose stack. The three core media-library
containers are joined by the optional Discover resolver and its read-only
catalog server.

### zurg

Container:

zurg

Image:

ghcr.io/debridmediamanager/zurg-testing:latest

Port:

9999

Restart policy:

unless-stopped

Zurg connects to Real-Debrid and provides the media filesystem used by rclone.

---

### rclone

Container:

rclone

Image:

rclone/rclone:latest

It mounts:

zurg:

to:

/data

The host mount is:

/mnt/zurg

Important mount options:

--allow-other
--allow-non-empty
--dir-cache-time 10s
--vfs-cache-mode full

The container uses:

/dev/fuse

and SYS_ADMIN.

Restart policy:

unless-stopped

---

### webdav

Container:

webdav

Image:

rclone/rclone:latest

This is the WebDAV server used by Infuse.

It exposes:

host port 8080 -> container port 8080

It mounts:

/mnt/zurg

to:

/data

The WebDAV container mounts /mnt/zurg read-write intentionally. This allows
Infuse to delete unwanted or garbage torrents from the exposed library. A
delete performed through Infuse affects the underlying Zurg/Real-Debrid
library, so use it only for torrents you intend to remove.

Its command is equivalent to:

rclone serve webdav /data --addr :8080 --user oarters --pass ${WEBDAV_PASSWORD}

The password is stored in:

/home/oarters/zurg-testing/.env

The .env file should not be committed to Git.

Restart policy:

unless-stopped

---

### discover

The `discover` container runs the movie catalog resolver on port 8090. It uses
TMDB metadata, a Comet-compatible provider, and the existing Real-Debrid token
from the read-only `config.yml` mount. Set `TMDB_BEARER_TOKEN` in `.env`.

### discover-webdav

The `discover-webdav` container publishes `test-catalog` read-only on port
8091. Add it to Infuse as a second WebDAV source using the same username and
`WEBDAV_PASSWORD`. Unlike the main port 8080 library, this catalog cannot be
modified through Infuse.

See `discover/README.md` for the module guide, request flow, configuration, and
Discover-specific troubleshooting commands.

---

## Infuse configuration

The working Infuse connection is:

Protocol:
WebDAV

Address:
192.168.4.58

Port:
8080

Path:
/

Username:
oarters

Password:
the password stored in .env

Do NOT use the old Zurg WebDAV endpoint on port 9999 for Infuse.

---

## Why the separate WebDAV server exists

The original Infuse connection used Zurg's WebDAV endpoint:

Port 9999
Path /dav

Newer Infuse versions began producing Firecore errors when browsing or playing media.

Testing Zurg directly showed:

PROPFIND /dav

could work, but deeper requests such as:

PROPFIND /dav/movies/movies/

returned:

HTTP/1.1 501 Not Implemented

Zurg logs also showed:

Not implemented: PROPFIND /dav/movies/movies/

A separate rclone WebDAV server was therefore created on port 8080.

The new server returns normal WebDAV:

HTTP/1.1 207 Multi-Status

and Infuse successfully plays movies through it.

---

## WebDAV testing

Test the root:

curl -i -u "$DAV_AUTH" \
  -X PROPFIND \
  -H 'Depth: 1' \
  -H 'Content-Type: application/xml; charset="utf-8"' \
  --data '<?xml version="1.0" encoding="utf-8"?><propfind xmlns="DAV:"><prop><resourcetype/><displayname/></prop></propfind>' \
  http://127.0.0.1:8080/

Test the movies directory:

curl -i -u "$DAV_AUTH" \
  -X PROPFIND \
  -H 'Depth: 1' \
  -H 'Content-Type: application/xml; charset="utf-8"' \
  --data '<?xml version="1.0" encoding="utf-8"?><propfind xmlns="DAV:"><prop><resourcetype/><displayname/></prop></propfind>' \
  http://127.0.0.1:8080/movies/

A successful response should begin with:

HTTP/1.1 207 Multi-Status

The movies request should list the actual movie directories.

---

## Password convenience

A shell variable can be used to avoid repeatedly typing the password:

export DAV_AUTH='oarters:YOUR_PASSWORD'

This only lasts for the current terminal session.

The persistent WebDAV password is stored separately in:

.env

as:

WEBDAV_PASSWORD=YOUR_PASSWORD

Do not put the actual password into this documentation.

---

## Compose commands

Go to the project:

cd ~/zurg-testing

Check the running Compose services:

docker compose ps

Validate the configuration:

docker compose config

Start everything:

docker compose up -d

Stop everything:

docker compose down

Restart everything:

docker compose down
sleep 5
docker compose up -d

View WebDAV logs:

docker logs webdav

View Zurg logs:

docker logs -f --tail 20 zurg

---

## Automatic startup and weekly restart

All five containers use:

restart: unless-stopped

Therefore Docker automatically starts them after a Raspberry Pi reboot.

There is also a separate weekly systemd restart.

Systemd service:

zurg-compose-restart.service

Systemd timer:

zurg-compose-restart.timer

Script:

/usr/local/bin/zurg-compose-restart.sh

The script currently does:

#!/bin/bash
set -e

/usr/bin/docker compose -f /home/oarters/zurg-testing/docker-compose.yml down
sleep 5
/usr/bin/docker compose -f /home/oarters/zurg-testing/docker-compose.yml up -d

echo "Zurg compose restart completed: $(date)"

The timer runs every Monday at 1:00 AM.

The timer uses:

Persistent=true

Because zurg, rclone, and webdav are all in the same docker-compose.yml, the existing weekly restart automatically restarts all three.

Do not create a separate restart timer for WebDAV.

---

## Systemd commands

View the service:

sudo systemctl cat zurg-compose-restart.service

View the timer:

sudo systemctl cat zurg-compose-restart.timer

View scheduled timers:

sudo systemctl list-timers --all | grep -Ei 'docker|zurg|rclone|container'

---

## Important architecture notes

Do not remove the Zurg container.

Do not remove the rclone container.

Do not remove /mnt/zurg.

Do not remove Zurg port 9999.

Do not point Infuse back to port 9999 unless specifically troubleshooting.

Keep the separate rclone WebDAV server on port 8080.

Keep the WebDAV mount writable:

/mnt/zurg -> /data:rshared

The writable mount is intentional so unwanted torrents can be deleted from
Infuse. Deletions are propagated to the underlying Zurg/Real-Debrid library.

Keep webdav in the same docker-compose.yml as zurg and rclone.

Keep the WebDAV password in .env.

---

## Troubleshooting

If Infuse stops working:

1. Check containers:

docker ps

Expected:

zurg
rclone
webdav

2. Check WebDAV logs:

docker logs webdav

3. Test WebDAV:

curl -i -u "$DAV_AUTH" \
  -X PROPFIND \
  -H 'Depth: 1' \
  http://127.0.0.1:8080/movies/

Expected:

HTTP/1.1 207 Multi-Status

4. Check the rclone mount:

findmnt /mnt/zurg

5. Check the media directories:

ls -la /mnt/zurg

Expected directories include:

__all__
__unplayable__
anime
movies
shows

6. Check Zurg:

docker logs --tail 50 zurg

7. Validate Compose:

cd ~/zurg-testing
docker compose config

---

## Current known-good state

As of August 12, 2026:

Zurg:
working

rclone mount:
working

/mnt/zurg:
working

Separate rclone WebDAV:
working

WebDAV port:
8080

WebDAV root:
207 Multi-Status

WebDAV /movies/:
207 Multi-Status

Infuse:
successfully playing movies through the new WebDAV server

Existing Zurg WebDAV:
still present on port 9999 but should not be used by Infuse

Weekly Monday 1 AM restart:
preserved

All five Docker containers:
restart=unless-stopped
