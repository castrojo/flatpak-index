# AGENTS.md — agent guide for tuna-os/flatpak-index

The **TunaOS Flatpak remote**: the OCI index that `flatpak remote-add tuna-os`
resolves against, plus the scripts that maintain it.

Human docs: [`README.md`](README.md) (app list, and the step-by-step for adding
a new Flatpak), [`docs/`](docs/).

## This repo builds the index; it does not serve it

The remote is served **from [`tuna-os/docs`](https://github.com/tuna-os/docs)**
via the `tunaos-org` Cloudflare Worker, which deploys that repository's static
assets at `https://tunaos.org/flatpak/`. So publishing is a two-repo operation,
and a correct index here can still be stale in production.

That matters for CI: `check-metadata.yml` **curls the live served index** —

```yaml
run: curl -sSfL -o served-index.json https://tunaos.org/flatpak/index/static
run: ./scripts/enrich-index.py served-index.json --check
```

— so it validates production, not this branch. **A failure there can mean a
deploy hasn't propagated, not that your change is wrong.** Read it as a
monitoring signal that happens to live in CI.

## The label rule that has already bitten

`scripts/update-index.py` keeps only labels matching:

```python
KEEP_LABEL_PREFIXES = ("org.flatpak.", "org.freedesktop.appstream.")
```

Both prefixes are load-bearing. `flatpak build-bundle --oci` writes the app's
AppStream catalogue and scaled icons into the image config as
`org.freedesktop.appstream.appdata`, `.icon-64` and `.icon-128`, and Flatpak
builds the remote's AppStream catalogue from exactly those. An earlier revision
kept only `org.flatpak.*` and dropped them — the result was apps rendering in
Bazaar, GNOME Software and Discover as a bare `org.tunaos.<app>` string with an
"Unknown" licence and no screenshots, despite a complete catalogue already
being published. Do not narrow that tuple.

`scripts/oci.py` declares the same rule independently as
`FLATPAK_LABEL_PREFIX`/`APPSTREAM_LABEL_PREFIX` and `keep_label()`, used by
`enrich-index.py` to audit the *live* remote against the registry.
`update-index.py` can't import `oci.py` (see below), so this is two
declarations of one invariant. `tests/test_label_policy.py` pins them to each
other — update both together, and let that test tell you if they've drifted.

## Three copies of one script — the vendoring contract

`scripts/update-index.py` is the **single source of truth**. It is vendored,
byte-for-byte, by application repositories at `.github/scripts/update-index.py`
and by the `update-flatpak-index` composite action in `tuna-os/.github`. No copy
is hand-edited in place: a change belongs here first, then propagates to the
others.

The sync guard is `flatpak-tooling-drift-check.yml` in `tuna-os/.github`. It
reads the SHA of *this* file from `tuna-os/flatpak-index` and fails the run when
any vendored copy differs, so "matches the composite action" means "matches this
file". That weekly check is the only thing standing between these copies and
silent divergence — keep it green.

Change boundaries:

- **Internals are free; propagate them.** Implementation details that do not
  change the CLI, the index format, or which labels are kept can be edited here;
  the same edit must then be copied to every vendored spot.
- **The public interface is shared; coordinate it.** The CLI contract, the index
  format (including the `ApplicationMetadata` block that `APP_LEVEL_LABELS` feeds
  into), and `KEEP_LABEL_PREFIXES` are identical across every copy. Change them
  here and treat the change as unmerged until the sync check has been re-run. A
  fix landing in only one copy is the failure mode this arrangement invites.

`tests/test_label_policy.py` pins the label-filter half of that contract to
`scripts/oci.py` (the auditor); `tests/test_app_level_labels_contract.py` pins
the index-format half. Together they catch the two ways the copies diverge:
label filtering and the `ApplicationMetadata` format.

Current state: the composite-action copy in `tuna-os/.github` predates the
`ApplicationMetadata` work (#146) and still lacks `APP_LEVEL_LABELS`, so it
differs from canonical and the sync check flags it. Syncing that copy is a
change in `tuna-os/.github`, not here.

`scripts/oci.py` holds the registry plumbing, `enrich-index.py` the validation
used by the live check above.

## Skill: add-flatpak-to-remote

Adding a new app to the TunaOS remote (the long form is in the README):

1. Fork the upstream app into `tuna-os/` (`gh repo fork <upstream> --org tuna-os --fork-name <app>`).
2. Add `org.tunaos.<app>.json` at that repo's root. GNOME 50 apps use
   `org.gnome.Platform` / `org.gnome.Sdk` runtime-version `50`.
3. Have that repo's publish workflow run `flatpak build-bundle --oci` and then
   the vendored `update-index.py`, so the new entry carries both the
   `org.flatpak.*` and `org.freedesktop.appstream.*` labels.
4. Add the app to the README table here.
5. After publishing, confirm the served index really carries it —
   `curl -sSfL https://tunaos.org/flatpak/index/static` — since this repo is
   not what serves it.
