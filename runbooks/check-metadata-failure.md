# check-metadata.yml failing

## Scope

[`check-metadata.yml`](../.github/workflows/check-metadata.yml) is the only
production health signal this repository owns. It runs daily, fetches the
**served** index from `https://tunaos.org/flatpak/index/static` (not this
repo's `index/static`, which is a historical snapshot — see the README's
"Index format" section), and runs
[`scripts/enrich-index.py --check`](../scripts/enrich-index.py) against it.
A failure means a published image is missing AppStream metadata the index
needs, not that something in this repository's `main` branch regressed.

This has happened at least three times before (#56, #57, #60), each closed
as a one-off diagnosis of the same failure mode. This runbook exists so the
next one doesn't start from zero.

**What this check does not cover:** it only validates apps listed in
`tuna-os/docs`'s `static/flatpak/expected-apps.json`. An app can be served
and completely ungated — see
[#98](https://github.com/tuna-os/flatpak-index/issues/98) for two examples
live on the remote today. A green run here is not proof every served app has
metadata; it is proof every *registered* app does. If you're investigating a
user report about an app's missing icon/screenshots and this check is green,
check whether the app is in `expected-apps.json` before ruling out a metadata
problem.

**No alerting exists on this check today.** A failure is a red GitHub Actions
run and nothing else — no issue filed, no notification. Check
[recent runs](https://github.com/tuna-os/flatpak-index/actions/workflows/check-metadata.yml)
directly; don't wait for something else to tell you it's red.

## Diagnosis

1. Open the failing run's log and read the `! ` lines
   (`enrich-index.py` prints problems to stderr, prefixed `!`; cosmetic
   issues — e.g. no screenshots — are prefixed `~` and don't fail the check).

2. Each problem line names a repository and architecture, e.g.:

   ```
   ! tuna-os/blueshell (amd64): image has no AppStream metadata (org.freedesktop.appstream.appdata, ...); it needs a metainfo file
   ```

   That means the image currently in GHCR for that repo/arch has no
   `org.freedesktop.appstream.*` labels — not that the index file is wrong.
   `enrich-index.py` reads labels live from the registry; it has nothing to
   enrich with if the image itself never had them.

3. Confirm against the registry directly:

   ```bash
   curl -sSfL -o served-index.json https://tunaos.org/flatpak/index/static
   REGISTRY_TOKEN=$(your_token_if_needed) ./scripts/enrich-index.py served-index.json --check
   ```

   If this reproduces locally, the problem is real and current, not a
   transient network blip in the scheduled run.

4. Find out why the image has no AppStream labels. Common root causes, most
   recent first:

   - **The app's metainfo file is missing, broken, or not installed to
     `/app/share/metainfo/<app-id>.metainfo.xml`** in its Flatpak manifest.
     See [`docs/METAINFO.md`](../docs/METAINFO.md). This is what #56/#57/#60
     were.
   - **The publishing repo's `update-index.py` copy filtered the labels out.**
     Three copies of this script exist (this repo's `scripts/update-index.py`,
     the vendored copy at `.github/scripts/update-index.py` in the app repo,
     and the `update-flatpak-index` composite action in `tuna-os/.github`) and
     they have drifted — see `AGENTS.md`'s "Three copies of one script"
     section. If the metainfo file looks correct, check which copy of the
     script the failing app's publish workflow actually vendors, and whether
     its `KEEP_LABEL_PREFIXES` (or equivalent) still includes
     `org.freedesktop.appstream.`.
   - **A stale deploy.** The check curls production, so a push to this repo,
     to `tuna-os/docs`, or to the app repo that hasn't propagated through
     Cloudflare Pages yet can show as a transient failure. Re-run the
     workflow once before treating it as real; if it's still red on a clean
     re-run, it's real.

## Fixing it

- **If the image needs a metainfo file:** that's a change in the *app's*
  repository, not here. Point the app's maintainer at
  [`docs/METAINFO.md`](../docs/METAINFO.md) and
  [`templates/org.tunaos.example.metainfo.xml`](../templates/org.tunaos.example.metainfo.xml).
  The app has to republish (new OCI image with the label) before anything
  here can pick it up.

- **If the image already has the labels but the served index is missing
  them** (i.e. `enrich-index.py` without `--check` reports it would add
  labels that are already in the registry): run the repair directly against
  the production index in `tuna-os/docs`:

  ```bash
  git clone https://github.com/tuna-os/docs
  cd docs
  /path/to/flatpak-index/scripts/enrich-index.py static/flatpak/index/static
  git diff --stat   # should only touch the affected entries' Labels
  ```

  Commit and push to `tuna-os/docs` directly (that's where the served file
  lives). This only re-reads digests already in the index — it cannot add or
  remove a published app, only fill in labels for ones already there.

- **If the publisher script dropped the labels:** fix the drifted copy (see
  `AGENTS.md`), get the app to republish, then confirm with step 3 above.

## After the fix

Re-run `check-metadata.yml` manually
(`gh workflow run check-metadata.yml --repo tuna-os/flatpak-index` or via the
Actions UI) rather than waiting for the next cron tick, so the fix is
confirmed the same day it lands.
