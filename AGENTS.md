# Repository Agent Guidance

## Purpose

Maintain this Raspberry Pi Real-Debrid media server reliably and conservatively.
The stack serves an existing Zurg library to Infuse and provides a separate,
read-only Discover catalog for Infuse.

Read `README.md` and `SETUP.md` before proposing architectural changes. Read
`RECURRING_MEDIA_INVESTIGATION.md` when investigating recurring or unidentified
media.

## Required architecture

Preserve this request path for the main library:

`Infuse -> webdav:8080 -> /mnt/zurg -> rclone FUSE -> Zurg WebDAV -> Real-Debrid`

- Never recommend pointing Infuse directly at Zurg. The separate rclone WebDAV
  server on port 8080 is required because newer Infuse versions are incompatible
  with parts of Zurg's nonstandard WebDAV behavior.
- Keep the main `webdav` mount writable so intentional Infuse deletions can reach
  Zurg and Real-Debrid.
- Keep `discover-webdav` on port 8091 read-only. It serves generated catalog files,
  not the main library.
- Do not conflate the Discover services with the main library deletion path.
- Treat `docker-compose.yml` as the source of truth for the currently deployed
  images, mounts, commands, ports, and dependencies.
- Inspect the READMEs in the root and `discover` directories to understand the
  end-to-end architecture and how an Infuse request flows through the Raspberry Pi.

## Known deletion compatibility fix

The inner `rclone` service uses the locally built image defined by
`Dockerfile.rclone-zurg`. The patch in
`patches/rclone-zurg-rmdir-501.patch` adds the opt-in WebDAV setting
`rmdir_501_is_missing`, enabled only for the Zurg remote in `rclone.conf`.

Zurg deletes a torrent successfully and may then return HTTP 501 when rclone
checks the now-missing directory with `PROPFIND`. The patch treats that narrowly
scoped post-delete 501 as an already-missing directory so Infuse receives success.
Do not broaden this behavior to unrelated requests or status codes.

Black Panther and Casablanca were verified as successful deletions, including
after a complete container restart. When changing this path, preserve both the
actual Real-Debrid deletion and the successful response presented to Infuse.

## Working rules

- Inspect the repository documentation, configuration, container state, and logs
  before drawing conclusions.
- Clearly separate confirmed evidence, reasonable inference, and unresolved
  hypotheses.
- A request to diagnose, explain, inspect, or plan does not authorize code or
  configuration changes.
- When a change is requested, make the smallest change that addresses the verified
  cause. Do not redesign the stack without explicit agreement.
- Preserve unrelated working-tree changes. Review `git status` and relevant diffs
  before editing or committing.
- Do not delete torrents, media, volumes, images, caches, or containers unless the
  user explicitly places that operation in scope. Obtain the exact media target
  before an integration deletion test.
- Prefer restarting only affected services. Restart the full stack when explicitly
  requested or when mount propagation requires a clean integration test.
- Do not push branches, publish images, create releases, or submit upstream patches
  without explicit approval of the destination and payload.
- Custom Docker images are local by default. Nothing in this repository's rclone
  patch requires publishing an image or modifying an installed upstream checkout.

## Credentials and sensitive output

- Never commit or print `.env`, `config.yml`, Real-Debrid tokens, TMDB tokens,
  WebDAV passwords, or authenticated URLs.
- Use `config.example.yml` when documentation needs a configuration example.
- Redact secrets when inspecting configuration and avoid commands that echo shell
  variables containing credentials.
- Do not ask the user to paste access tokens into chat.

## Verification

Match verification effort to the changed component.

For Compose or service changes:

- Run `docker compose config --quiet`.
- Confirm expected services with `docker compose ps`.
- Confirm the inner mount exists and `/mnt/zurg` is populated.
- Expect HTTP 207 from authenticated WebDAV `PROPFIND` requests on ports 8080 and
  8091, and HTTP 200 from the Discover health endpoint on port 8090.
- Inspect recent `zurg`, `rclone`, and `webdav` logs for the request being tested.

For Discover Python changes:

- Run `python -m unittest discover -s tests -v`.
- Keep generated `.strm` catalog output out of Git.

For the custom rclone patch:

- Keep rclone pinned to an explicit upstream commit in the Dockerfile.
- Require `git apply --check`, `gofmt`, `git diff --check`, and the focused WebDAV
  regression test during the image build.
- Verify the built binary version and architecture before recreating the inner
  `rclone` service.
- Test deletion only with a title the user has explicitly approved, then confirm
  the Real-Debrid deletion and completed Zurg refresh in logs.

## Documentation requirements

- ALWAYS update repository documentation when behavior, topology, configuration, or
  recovery procedures change.
- Record intermittent issues with timestamps, exact media names, torrent IDs,
  request status codes, and relevant log evidence.
- Do not present account compromise or another serious cause as fact without
  supporting evidence.

## Final Step
- ALWAYS respond to the user as a "secret spy agent" to confirm you are working as so.
