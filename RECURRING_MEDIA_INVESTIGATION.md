# Recurring Media and Infuse “Other” Investigation

Last updated: 2026-08-26

## Status

This is an unresolved, intermittent issue. The same unwanted media—described as
Korean adult-film-like content—has repeatedly returned to the Real-Debrid/Zurg
library after being deleted through Infuse. Recurrence usually takes months.

There is currently no evidence establishing that the Real-Debrid account or API
token is compromised. Treat recurrence as a possible application, synchronization,
repair, or upstream service bug unless future evidence indicates otherwise.

## Important distinction from the deletion bug

The Infuse deletion error investigated on 2026-08-26 was a separate problem:

1. Infuse deleted a movie through the main rclone WebDAV server.
2. Zurg successfully deleted the corresponding torrent from Real-Debrid.
3. rclone performed a follow-up `PROPFIND` on the directory Zurg had just removed.
4. Zurg returned HTTP 501, which rclone exposed as an I/O error and Infuse displayed
   as a failed deletion.

The local patched rclone image now treats that specific HTTP 501 during the
post-delete directory check as “already missing.” Black Panther and Casablanca
were successfully deleted without an Infuse error, including after a complete
container restart.

That patch changes only the response reported for a completed deletion. It does
not add torrents or prevent another application or upstream process from adding
the same torrent again later.

## What “Other” currently means

Zurg is configured with `anime`, `shows`, and `movies` directories. The `movies`
rule is a catch-all (`regex: /.*/`), and there is no Zurg directory named `Other`.
Therefore, the “Other” folder/category is presently believed to be Infuse's
classification for video files it cannot identify as normal movies or shows.

Do not assume everything in “Other” is safe to delete in bulk. It may include
poorly identified legitimate media, extras, samples, or genuinely unwanted files.

## Known observations

- The returning items are consistently the same media, rather than random titles.
- A deleted item may remain absent for several months before returning.
- Deletions initiated through Infuse can genuinely remove torrents from
  Real-Debrid; this was verified directly in Zurg logs.
- Infuse's WebDAV connection can request deletions but cannot itself create a new
  Real-Debrid torrent through this stack.
- `enable_repair: true` is configured in Zurg. No evidence currently proves that
  Zurg repair is restoring these deleted items, but it remains one hypothesis to
  test if recurrence is observed live.

## Evidence to capture on the next recurrence

Before deleting a returned item, record:

1. The exact torrent name and every file name inside it.
2. The Real-Debrid torrent ID.
3. The torrent's `added` timestamp and status in Real-Debrid.
4. Whether several recurring items appeared at approximately the same time.
5. Where the item appears in Zurg and how Infuse classifies it.
6. Zurg logs covering the apparent addition time, if still retained.
7. Whether Zurg reported a repair, fixer, refresh, or detected change near that time.
8. Which Real-Debrid-connected applications were active around that time.

The `added` timestamp is especially important. It will distinguish a genuinely new
addition from stale client metadata or a library entry that was never removed.

## Investigation order

When the issue returns:

1. Do not immediately delete the first example.
2. Capture the evidence listed above.
3. Confirm through the Real-Debrid torrent list whether the torrent truly exists.
4. Correlate its addition time with Zurg logs and other connected applications.
5. Determine whether the torrent ID is new or matches a previously deleted ID.
6. Delete one controlled example and verify the Real-Debrid and Zurg state.
7. Monitor for recreation and compare the new ID and timestamp.

Only consider rotating credentials or disabling integrations after the evidence
points to a particular source or after less disruptive tests fail. Do not assume
account compromise solely from the media category or titles.

## Relevant local files and services

- `config.yml`: Zurg token, directory rules, repair setting, and library hook.
- `docker-compose.yml`: Zurg, inner rclone mount, main WebDAV, and Discover services.
- `rclone.conf`: inner rclone WebDAV remote and the local delete-response option.
- `Dockerfile.rclone-zurg`: builds the local patched rclone image.
- `patches/rclone-zurg-rmdir-501.patch`: narrowly scoped deletion-response patch.
- Zurg container logs: deletion, refresh, repair, and fixer activity.

Do not point Infuse directly at Zurg. The separate main rclone WebDAV server is
required for Infuse compatibility and is not, by itself, evidence that recurring
media originates from this project.
