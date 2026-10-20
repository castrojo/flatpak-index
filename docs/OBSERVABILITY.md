# Observability

This document defines how index scripts report status and how they handle
telemetry. It guides operators. It does not promise a telemetry service.

## Current state

This repository has no telemetry SDK, collector, metrics endpoint, tracing
exporter, or external backend. Python scripts write to standard output and
standard error. They also return process exit status.

GitHub Actions can keep this output in a workflow log. The scripts do not send
a second copy.

`scripts/enrich-index.py` and `scripts/oci.py` read OCI manifests and labels
from the registry named by the input index. The scheduled metadata workflow
also downloads the public served index.

These requests support index work. They do not send telemetry. Limit requests
to endpoints selected by the caller, input index, or workflow.

**Policy:** Diagnostics must not send telemetry outside this system. An
exporter, collector, data collection call, or error-reporting service needs
review. The `index/static` file and OCI labels hold product data. They are not
an observability store.

## Diagnostic contract

Command output is for people. It is not a stable machine API. Automation must
use exit status and the generated index file. Do not parse prose.

| Source | Normal signal | Warning or failure signal |
|---|---|---|
| `scripts/update-index.py` | Writes an `Updated ...` summary to stdout after it updates the index file. | Missing optional AppStream metadata writes `WARNING:` to stderr. Missing required labels, invalid JSON, or invalid OCI layout returns non-zero. `--require-appstream` makes missing AppStream metadata an error. |
| `scripts/enrich-index.py` | Writes registry read progress and a final count/status to stdout. In `--check` mode, exit `0` means the check found no repair or serious metadata problem. | `~` lines on stderr warn about presentation issues, such as missing screenshots. `!` lines report metadata or registry problems. In `--check` mode, a needed repair or serious problem returns `1`; other errors also return non-zero. |
| `scripts/oci.py` | Writes no normal output. It returns data to its caller. | Raises `RegistryError` when it cannot complete registry requests; the CLI caller displays the failure and exits non-zero. |

New diagnostics must follow these rules:

- Send progress and success summaries to stdout. Send warnings and errors to
  stderr.
- Use non-zero exit status only for an incomplete operation, failed validation,
  or a check that finds a required change.
- Name the operation, affected repository or relative file, and fix. Include
  architecture, bounded counts, and the OCI digest when they help find an
  index entry.
- Put one problem on each line when possible. This makes CI logs easy to
  search.
- Do not dump whole manifests, label maps, AppStream XML, or HTTP bodies.
- Use Python's standard `logging` module when you need log levels or output
  routing. Keep default output free of extra dependencies and easy to read.
  Do not install network logging handlers.

## Privacy and data

Safe diagnostic fields include public repository names, architectures, OCI
digests, limited counts, operation names, and repository-relative paths. The
source may be public. Log only fields needed to diagnose the operation.

Never emit registry tokens, authorization or cookie headers, credentials, or
URLs or query strings that contain secrets. Never emit full environment dumps,
complete HTTP responses, private label values, or unredacted AppStream
payloads.

Use a registry host, not a full URL. Use a relative path, not an absolute
workspace path. Redact sensitive values before you build a message. Do not
depend on CI to hide secrets in logs.

Keep diagnostics in the terminal that runs the command or in its CI system.
Scripts must not send diagnostics, identifiers, or usage data to another
endpoint. A telemetry failure must not stop index generation. The current
policy has no telemetry call.

## Signals for operators

| Signal | Meaning | Operator action |
|---|---|---|
| `Tests` workflow fails | Script tests, lint, or screenshot-action checks failed. | Inspect the failed job. Run only the named check. |
| Scheduled `Check remote metadata` fails | Registry labels differ from the served index; the registry lacks required metadata; or registry access failed. | Read `~` and `!` lines. Separate presentation warnings from hard problems. Repair the source that publishes the index or the reviewed index. |
| `Deploy Pages` fails | Pages deployment failed. | Inspect checkout, artifact upload, and deployment. This does not show an index-validation failure. |
| `update-index.py` returns non-zero | The candidate index failed a safety check. | Correct the reported layout, JSON, or label problem before publishing. |

The scheduled check gives a production health signal. No separate dashboard or
alert system exists. GitHub workflow status and logs give diagnostic evidence.

## Review path for metrics or tracing

Metrics, tracing, and error reporting need an explicit pull request and
CODEOWNER review. Before you add a dependency or network destination, write:

1. the operator question and why existing exit codes and workflow logs cannot
   answer it;
2. exact fields and data classification; destination and protocol; data
   retention, access controls, and deletion path;
3. credential source and least-privilege permissions;
4. bounded metric labels or span attributes; sample rate, expected volume, and
   cost;
5. timeout and failure behavior that cannot delay or fail index publication;
6. operator controls to enable and roll back.

Do not use repository names, digests, refs, paths, or free-form error text as
metric labels without bounds. Do not put manifests, labels, AppStream XML,
tokens, or HTTP bodies in spans. Until maintainers approve a proposal, keep
off-box telemetry export disabled.
