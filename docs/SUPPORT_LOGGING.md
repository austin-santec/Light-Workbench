# Engineering Support Logging

## Purpose and scope

Light Workbench 1.13.1 adds always-on, local engineering support logs. Their
purpose is to help engineering reconstruct operator workflows, hardware
communication, two-wavelength measurements, insertion-loss calculations,
connection ownership, persistence, exports, and failures.

Support logging is best-effort instrumentation. It does not control hardware,
change measurement timing or calculations, commit readings, or replace the
authoritative CSV/JSON run record. The files are local and editable; they are
not a tamper-proof audit trail and do not satisfy the future immutable audit
history described by FUN-048.

## Location, naming, and lifecycle

The normal per-user directory is:

```text
%LOCALAPPDATA%\LightWorkbench\logs\
```

Files are newline-delimited JSON (JSONL):

```text
light-workbench-YYYY-MM-DD.jsonl
light-workbench-YYYY-MM-DD-part02.jsonl
light-workbench-YYYY-MM-DD-part03.jsonl
```

The date is the workstation's local calendar date. Multiple application
launches append to the same daily file. A new file is selected at midnight
while the program remains open. A part rolls at 25 MB. Inactive files older
than seven days are gzip-compressed and retained indefinitely. No managed log
is automatically deleted. When the combined managed-log size exceeds 500 MB,
the application displays a warning asking the operator to archive or delete
older files. Cleanup and compression only consider names matching the Light
Workbench support-log pattern; the active file is never compressed.

If the normal folder is unavailable, the writer tries the operating system's
temporary directory under `LightWorkbench\logs`. If neither folder can be
written, a bounded in-memory buffer retains recent events. The main window
shows a non-blocking degraded-status warning; testing continues normally.

## Event schema and correlation

Each line is one JSON object using `schema_version: 1`. Core fields are:

- `timestamp_utc`: ISO-8601 UTC time with millisecond precision.
- `local_date`: local date used for daily file selection.
- `level`, `category`, and `event`.
- `application_name`, `application_version`, and `app_instance_id`.
- Optional `workflow_id` and `operation_id`.

Each launch receives a new `app_instance_id`. Normal runs, reference
calculations, Live IL, Red Light Test, and Power Diagnostics receive workflow
identifiers. Hardware operations and complete measurements use operation or
measurement identifiers when available. Useful searches therefore include:

```powershell
Select-String -Path "$env:LOCALAPPDATA\LightWorkbench\logs\*.jsonl" `
  -Pattern '"workflow_id":"wf-'
```

Python and common JSONL tools can parse one line at a time without loading an
entire day into memory.

## Categories and collected data

Current categories are `application`, `workflow`, `measurement`, `hardware`,
`connection`, `persistence`, `export`, `operator`, and `logging`.

Depending on the event, logs may contain:

- Application version, launch instance, workflow, and operation identifiers.
- Tested-by initials and unit, switch, or instrument serial numbers.
- Hardware manufacturer, model, firmware, resource address, connection state,
  discovery method, and lease owner.
- Sanitized OP815 DLL and switch SCPI events, status codes, bounded responses,
  source state, requested/verified wavelengths, and command timing.
- Logical channel, reported physical port, raw optical power, reference power,
  calculated insertion loss, and whether both wavelengths completed.
- Whether a reading was temporary, repeated, accepted, written, overwritten,
  diagnostic-only, or failed.
- Run/unit save requests and results, atomic file replacement, measurement
  counts, export results, and sanitized destinations.
- Warning bypasses such as continuing without metadata or with both references
  at zero.

The OP815 trace uses independent subscribers. The global logger remains
subscribed while Power Diagnostics temporarily records the same events in
memory. Closing that tool removes only its own callback. The optical-switch
adapter emits equivalent discovery, identity, configuration, routing, and
cleanup events without changing its commands or timeouts.

## Redaction and excluded data

The event model uses an allowlist. The writer removes prohibited key names,
limits raw responses and detail text, and replaces the current user-profile
prefix in paths with `%USERPROFILE%`.

Support logs never intentionally include passwords, tokens, credentials,
environment-variable dumps, clipboard contents, free-form notes, screenshots,
native handles, arbitrary object representations, or complete run/COC files.
Raw hardware responses are length-limited. Logs may contain internal equipment
identifiers, operator initials, and measurement evidence because those values
are needed for engineering correlation.

## Support Logs menu

`Help > Support Logs` provides:

- **Open Logs Folder**: opens the active log directory.
- **Export Support Bundle...**: exports an explicit local-date range.
- **Copy Logs Folder Path**: copies only the folder path.
- **Logging Status...**: shows health, active file/folder, application instance,
  schema, queue depth, dropped count, last error, current managed-log size,
  retention/size limits, and fallback state.

There is intentionally no operator control that disables logging.

## Support bundles

The export dialog defaults to today and the previous two days. Its ZIP contains
only matching managed support logs, `manifest.json`, `dependency-report.txt`,
`sanitized-configuration.json`, and `README.txt`. The manifest records the
selected dates, versions, file list, and SHA-256 hash of each included file.

Bundles do not automatically include run CSV/JSON, COC workbooks, diagnostic
history, or clipboard data. They are never uploaded and require no network
connection. Existing destinations receive a collision-safe numeric suffix.
The logger is flushed before export, and the result is logged only after the
ZIP closes successfully.

## Failure and shutdown behavior

Producers use a bounded background queue and do not wait for disk I/O. Queue
overflow increments a dropped-event counter; warning/error events displace an
older queued event where practical, and a later `logging.events_dropped` event
records the loss. Serialization, redaction, maintenance, subscriber, and writer
errors are isolated from production operations.

Normal shutdown performs a bounded flush and records cleanup. Uncaught Python
exceptions are captured through preserving main- and worker-thread hooks.
Events still in memory cannot be guaranteed to survive power loss, forced
termination, native DLL abort, or operating-system process termination.

## Relationship to other records

- **Run CSV/JSON**: authoritative accepted production results; changed only by
  existing run persistence.
- **Diagnostic export**: explicit Power Diagnostics history and optional
  session trace selected by the operator.
- **Support logs**: always-on, local engineering evidence that includes
  temporary measurements and workflow/hardware context.
- **Future audit history**: a controlled, immutable, attributable record that
  has not yet been implemented.

A future release may add controlled central collection, authentication,
authorization, and database ingestion. Version 1.13.1 performs no upload and
has no graphical log viewer.
