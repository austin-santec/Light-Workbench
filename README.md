# Light Workbench

This folder contains Light Workbench, a guided Windows application for optical
testing and measurement. Its current workflow measures insertion loss in
**SM (1310/1550 nm)** or **MM (850/1300 nm)** mode and controls:

- An ILM-100 exposed to the vendor DLL as an **OP815**
- A Santec **OSX-100 or OSX-150** optical switch connected through USB VISA

The operator moves the output cable when prompted. The program changes the
switch channel, takes both wavelength readings, displays the calculated losses,
and saves accepted readings to a CSV file that opens directly in Excel.

## What the application can do

At startup, the program offers three workflows:

1. **Full pass** — tests every logical channel configured in the connected Santec switch.
2. **One channel** — tests a single logical channel.
3. **Specific channels and ranges** — accepts individual channels, inclusive
   ranges, or both in one comma-separated entry. For example,
   `1, 9, 10-15, 27` tests 1, 9, 10 through 15, and 27 in that order.

Repeated channels are tested only once. For example, `1, 1-3` tests channels
1, 2, and 3 rather than testing channel 1 twice.

Quality criteria are selected from the connected OSX-100 or OSX-150 model.
OSX-100 uses a 0.8 dB formal-failure limit with no optimization-warning band;
OSX-150 uses a 2.25 dB optimization warning and a 2.5 dB formal-failure
limit. Too-good checks are below 0.2 dB and 0.5 dB. These criteria are
read-only during normal testing and are stored with each new run.
Administrators can change them through Edit > Admin Mode... and Edit > Admin
Config...; the admin session is not persisted.

Select **SM (1310/1550)** or **MM (850/1300)** in Hardware test setup before
calculating the reference. This is an operator-selected test mode; Light
Workbench does not infer SM/MM from the ILM identity, firmware, serial number,
product option, power, or cached history. SM configures the 1310/1550 sequence
and MM configures the 850/1300 sequence. The selected mode is stored with the
reference, readings, logs, and run metadata. Each mode has its own model
limits. MM data can be reviewed, analyzed, and exported, but the current COC
workflow remains SM-only until approved MM report rules and templates exist.

For every channel, it can:

- Automatically route the connected OSX-100/OSX-150 to the requested logical channel.
- Measure absolute power at the two wavelengths selected by the active mode.
- Calculate insertion loss using an explicit calculated reference session; only
  Admin Mode can authorize a manually entered production reference.
- Display both insertion-loss values before saving them.
- Accept the displayed reading with Enter.
- Discard and retest the same channel by entering `-` and pressing Enter.
- Record switch and main-board metadata and automatically detect swapped ports
  encountered during the selected test channels.
- Use the entered serial numbers in the run folder and CSV names.
- Preserve every previously accepted row if the run is stopped with Ctrl+C.
- Store multiple numbered runs for one unit while sharing completed replacements
  and designated spare ports across those runs.

The application does **not** change the references saved in the ILM or edit the
replacement-channel configuration saved in the OSX-150.

The **Connected hardware** panel appears in the top header beside the
**Connect Hardware...** menu and shows the ILM/power-meter and optical-switch
state, model, and serial number. Use the button itself to connect everything
needed for a normal run, or its menu to connect/disconnect measurement hardware
and the switch independently. Connections persist between runs and tools until
the operator disconnects them or closes Light Workbench. The panel updates
through Connecting, Connected, In use, Disconnected, and Error states. If a switch
reports a recognized model that has not been verified for this application,
the run is refused with an explicit unsupported-device message; unknown device
identities are not silently treated as compatible.

When a supported OSX connects and no run is loaded or active, its reported
device serial automatically fills **Main board serial** and Light Workbench
looks up the matching part number in the designated folder. This network
lookup runs in the background. If it fails, the hardware remains connected,
the detected serial remains in the setup form, and the operator can enter a
part number manually or retry with **Lookup Part Number**. The separately
entered **Switch serial** is never changed by this convenience feature, and
loaded or active run metadata is never overwritten.

From `Tools > Red Light Test...`, the operator can open a separate pre-test
window for checking a switch with a VFL. Opening the menu item does not connect
to the switch. Click `Start Red Light Test` to connect and select channel 1;
then use the channel number, Up/Down keys, Previous/Next buttons, or a typed
channel number to route the switch. The dialog reports the physical port
returned by the switch and releases it when stopped or closed. The switch
remains connected to Light Workbench for later use. It does not
measure IL, create run files, or affect COC data.

From `Tools > Live IL Reading...`, the operator can connect or borrow only the
ILM/OP815 and read the current insertion loss at the selected wavelength pair. It uses
the session reference for the selected wavelength mode, supports
repeated reads, and never connects to the switch or saves run data. `Start Live
Updates` automatically refreshes both values without saving data and changes to
`Stop Live Updates` while active.

From `Tools > Power Measurement Diagnostics...`, the operator can connect or borrow
the meter without starting a run and view raw absolute power at both
wavelengths alongside the exact insertion-loss calculation. Its labels,
history, analysis, and explicit exports follow the active SM/MM mode. The tool can also
connect to the switch independently so a logical channel can be routed before
the reading. Diagnostic readings and history stay in memory only; they do not
change the active run or create CSV, JSON, COC, or other output files.

The diagnostics history also records whether each sample was collected
manually or through monitoring. `Analyze Repeatability` uses only manual
readings, representing cable disconnect/reconnect samples. `Analyze Stability`
uses only automatic monitoring readings, representing an undisturbed optical
connection. Both analyses show average, minimum, maximum, range, sample
standard deviation, and first-to-last change for each wavelength; results are
temporary and are not saved.

Use `Export History...` to explicitly save the complete diagnostic history as
CSV or JSON. The export asks whether to include the optional in-memory hardware
trace. If selected, CSV creates a companion `<history-stem>-hardware-trace.csv`
and JSON adds a `hardware_trace` object with session metadata and chronological
OP815 command events. The trace includes raw power, references, wavelength and
source state, channel context, status codes, timing, and errors. It is not
created by normal runs and exporting does not modify the active run or any run
files.
When available, the trace session also includes the detected meter and switch
manufacturer, model, serial, raw identification string, and VISA resource
address.

From `Tools > Get IP...`, the operator can read the configured LAN address from
an already-connected OSX-100 or OSX-150. The tool never opens a second VISA
session or connects the switch automatically. It uses the persistent connection,
validates the response as a usable IPv4 or IPv6 address, and displays it in a
selectable dialog with an explicit `Copy to Clipboard` button. It does not
change switch routing or save run data.

Diagnostic exports default to local-time names such as
`diagnostic-history-20260930-110405.csv` (or `.json`). If that automatically
suggested name already exists, a deterministic `-01`, `-02`, and so on is
used. The final wavelength is verified again immediately before each raw
power read; a mismatch or invalid wavelength report blocks that sample rather
than allowing an ambiguous reading into diagnostic history.

Variation Analysis appears to the right of the reading history by default.
Use `Hide Variation Analysis` to give the history table more room, or
`Show Variation Analysis` to restore the panel. The splitter between the two
areas can also be resized.

When results are displayed, `Copy Analysis` copies the formatted variation
summary to the system clipboard for pasting into notes or another document.

Light Workbench also keeps always-on engineering support logs under
`%LOCALAPPDATA%\LightWorkbench\logs`. Use `Help > Support Logs` to open the
folder, copy its path, inspect logging health, or explicitly export a dated
support bundle. These JSONL logs include workflow, hardware, temporary
measurement, calculation, persistence, and export evidence. They exclude
clipboard contents, free-form notes, credentials, and complete run/COC files.
They do not change production data and are not a tamper-proof audit record.
See [`docs/SUPPORT_LOGGING.md`](docs/SUPPORT_LOGGING.md) for retention,
redaction, and support-bundle details.

## Folder contents

| File or folder | Purpose |
| --- | --- |
| `ilm_app.py` | Current Light Workbench PyQt5 desktop application and hardware-test UI |
| `ILMReadLoss.py` | Legacy console workflow retained for compatibility |
| `run_data.py` | CSV loader and configurable over-limit analysis model |
| `domain/models.py` | Typed vendor-neutral measurement, device, unit, run, reference, and workflow models |
| `domain/wavelengths.py` | Operator-selected SM/MM OPM/source profiles and legacy classification support |
| `domain/part_numbers.py` | Validated OSX part-number parsing and front-panel channel-count resolution |
| `domain/run_data.py` | Domain run model and over-limit analysis rules |
| `domain/measurement_attempts.py` | Typed append-only accepted-reading and retest history |
| `domain/raw_export.py` | Pure tab-separated formatting for copying accepted readings to Excel |
| `domain/coc_preparation.py` | Pure multi-run COC merge, provenance, completeness, port-map, and publication rules |
| `domain/diagnostic_analysis.py` | In-memory diagnostic samples and variation statistics |
| `domain/diagnostic_trace.py` | Typed in-memory hardware trace event model |
| `domain/support_events.py` | Typed allowlisted engineering support-event schema |
| `config/app_config.py` | Centralized default paths and injectable application path configuration |
| `config/app_info.py` | Single source for application name, version, tagline, and About text |
| `application/run_controller.py` | Hardware-run lifecycle controller and queued worker command boundary |
| `application/hardware_connection.py` | Persistent serialized hardware ownership, capability leases, and managed device proxies |
| `application/part_number_lookup.py` | Non-blocking part-number lookup controller and lookup-failure classification |
| `application/coc_workflow.py` | Repository-backed COC source-run loading and preparation workflow |
| `application/live_controller.py` | Live IL meter worker lifecycle controller |
| `application/red_light_controller.py` | Red Light Test switch worker lifecycle controller |
| `application/power_diagnostics_controller.py` | Non-recording raw-power diagnostic lifecycle controller |
| `application/diagnostic_trace.py` | Thread-safe in-memory recorder for optional diagnostic trace events |
| `application/support_logging.py` | Bounded support-log queue, correlation IDs, trace fan-out, and exception hooks |
| `application/timing.py` | Shared pacing defaults for automatic live readings |
| `infrastructure/csv_run_loader.py` | CSV parsing adapter for current and legacy run files |
| `infrastructure/run_persistence.py` | Atomic CSV/JSON run recorder and filename rules |
| `infrastructure/unit_persistence.py` | Atomic unit JSON records and numbered-run paths |
| `infrastructure/coc_export.py` | COC template lookup, workbook export, and drawing preservation |
| `infrastructure/run_query.py` | Read-only queries over indexed unit runs |
| `infrastructure/run_reports.py` | File-backed multi-run reporting service |
| `infrastructure/diagnostic_export.py` | Explicit CSV/JSON export for diagnostic history and optional hardware trace |
| `infrastructure/support_log_writer.py` | JSONL redaction, daily/size rotation, compression, retention, and fallback writing |
| `infrastructure/support_bundle.py` | Explicit dated support-bundle ZIP and SHA-256 manifest export |
| `infrastructure/schema.py` | Run and unit schema versions and migrations |
| `run_persistence.py` | Compatibility facade for infrastructure run persistence |
| `unit_persistence.py` | Compatibility facade for infrastructure unit persistence |
| `coc_export.py` | Compatibility facade for infrastructure COC export |
| `ilm_app.spec` | PyInstaller one-folder build definition for the desktop application |
| `build_windows.ps1` | Repeatable 32-bit Windows build command |
| `verify_release.ps1` | Verifies the executable distribution layout and support files |
| `package_release.ps1` | Creates a versioned deployment ZIP after verification |
| `smoke_test_release.ps1` | Optionally starts and closes the packaged executable to verify startup |
| `requirements-win32.txt` | Pinned 32-bit application and packaging dependencies |
| `requirements-dev.txt` | Optional contributor tooling for formatting, linting, typing, and hooks |
| `.pre-commit-config.yaml` | Optional local quality checks for contributors |
| `op815_driver.py` | Documented 32-bit DLL wrapper for the ILM/OP815 |
| `application/measurement_worker.py` | Background hardware-run orchestration worker |
| `application/run_start.py` | Hardware-run planning and controller-request preparation |
| `ui/live_il_reading.py` | Meter-only Live IL dialog and worker presentation module |
| `ui/power_measurement_diagnostics.py` | Raw-power diagnostics dialog with optional switch routing |
| `ui/red_light_test.py` | Separate VFL pre-test dialog presentation module |
| `ui/support_logs.py` | Support logging status and bundle date-range dialogs |
| `ui/coc_export_dialog.py` | Front-panel count, source-run selection, and COC validation preview |
| `ui/reading_history.py` | Read-only current/superseded accepted-reading history viewer |
| `tools/dependency_check.py` | Non-destructive prerequisite and connection diagnostics |
| `hardware/interfaces.py` | Vendor-neutral power-meter, laser-source, and optical-switch contracts |
| `domain/hardware_connection.py` | Vendor-neutral hardware capabilities, readiness snapshots, and connection errors |
| `hardware/device_identity.py` | Compatibility-safe identity reporting for hardware adapters |
| `hardware/power_meter.py` | Integrated OP815 adapter and simulated meter implementations |
| `hardware/optical_switch.py` | Extensible Santec switch identity registry and OSX-100/OSX-150 adapter |
| `ui/hardware_status.py` | Connected hardware status presentation panel |
| `hardware/factory.py` | Lazy composition of real and future hardware adapters |
| `power_meter.py` | Compatibility facade for the hardware power-meter adapters |
| `osx150_driver.py` | Compatibility facade for the Santec optical-switch adapter |
| `red_light_test.py` | Compatibility facade for the Red Light presentation module |
| `live_il_reading.py` | Compatibility facade for the Live IL presentation module |
| `app_info.py` | Compatibility facade for application release metadata |
| `dependency_check.py` | Compatibility facade for dependency diagnostics |
| `OP815M.dll` | Vendor library used to communicate with the ILM |
| `Templates/OSX-150 Single Mode COC Template 2 (45max).xlsx` | Bundled OSX-150 COC template for 1-45 front-panel channels |
| `Templates/OSX-150 Single Mode COC Template 1 (48max).xlsx` | Bundled OSX-150 COC template for 46-48 front-panel channels |
| `assets/C&C lulu.png` | Normal application and header icon |
| `assets/C&C lulu white eyes.png` | Admin Mode application and header icon |
| `README_INSTALL.txt` | Light Workbench ZIP deployment, prerequisite, and quick-start instructions |
| `Check Dependencies.cmd` | Optional launcher for the bundled dependency and connection report |
| `ILM_READING_GUIDE.html` | Browser-based operator guide for the hardware IL-reading workflow |
| `docs/` | Architecture, coding standards, hardware boundaries, data rules, testing, and refactor guidance |
| `ILM-Reads/` | Automatically generated unit folders containing numbered `Run-N-[switch serial]` folders; legacy timestamped and unsuffixed numbered run folders remain supported |
| `tests/` | Hardware-free automated tests for the application and data models |

The vendor `OP815M.dll` is not modified by this project. The hardware adapter
in `hardware/power_meter.py` keeps the measurement workflow dependent on a
small Python interface: the real `SantecPowerMeter` delegates to the existing
`OP815` wrapper, while `SimulatedPowerMeter` supplies deterministic readings
for tests and future UI development without connected equipment. The root
`power_meter.py` module remains a compatibility facade for existing imports.

Before making code changes, review the relevant documents in `docs/`. Start
with `docs/README.md`, then read `PROGRAM_DESIGN.md` and the specialist guide
for the area being changed. The documentation describes the target architecture
and the incremental refactor rules for keeping future ILM, OPM, and separate
laser support maintainable.

The vendor-neutral contracts in `hardware/interfaces.py` are the first step
toward supporting more equipment. The current integrated ILM implements the
`PowerMeter` contract and the Santec OSX-100/OSX-150 adapter implements the
`OpticalSwitch` contract.
A future OPM plus separate laser can implement `PowerMeter` and `LaserSource`
independently without requiring the application workflow to know the vendor
or connection protocol. Existing top-level driver modules remain in place for
backward compatibility while the architecture is being migrated incrementally.
The hardware factory loads the real vendor adapters lazily, so contract-only
code and hardware-free tests do not need to open or initialize equipment.

The Light Workbench desktop application can be started with:

```powershell
py -3.11-32 ilm_app.py
```

Use `Help > About` to view the running application's version, a
summary of supported capabilities, and copyable project information. The
current source version is **1.27.0**; an existing executable keeps its prior
version until rebuilt.

For architecture, coding standards, testing, and contribution guidance, see
the [`docs/README.md`](docs/README.md) documentation index.

Use `Help > IL Instructions` to open the bundled browser-based operator guide
for the hardware IL-reading workflow.

Use `Tools > Dark Mode` to switch between the light and dark application
themes. New installations start in dark mode, and the last selected theme is
saved for the next launch. The red operator-action accent remains the same in
both themes.

It can open an existing CSV, display both wavelength values, show recorded
metadata, highlight channels over the configurable loss limit, and summarize
1310 nm, 1550 nm, and dual-wavelength exceedances. A file can also be opened
directly from PowerShell:

```powershell
py -3.11-32 ilm_app.py path\to\output.csv
```

When the same-named JSON file is beside the selected CSV, the viewer also restores the saved
warning limit, physical-port mappings, and switch-test timing metadata.

Select one or more completed rows in the results table and choose `Retest
Selected`. The latest accepted value replaces that channel in the CSV and
table, while the JSON run record keeps an append-only history of every
accepted attempt. Open `View Reading History...` in the Run information box
to review current and superseded readings without connecting hardware.

Use `Select Over-Limit` to select every channel above the current warning
limit. Each flagged row identifies whether 1310 nm, 1550 nm, or both
wavelengths exceeded the limit.

The Analysis panel shows the total number of channels, the total number over
the warning limit, and the channel numbers over the limit at each wavelength.
For example, `2 (3, 7)` means two channels—3 and 7—exceeded the limit at that
wavelength.

The results table also has a `Show readings` filter with `All channels`,
`Within warning limit`, `Any wavelength over limit`, `1310 nm over limit`,
`1550 nm over limit`, and `Both wavelengths over limit`. Changing this view
only filters the table; it does not interrupt a hardware pass or change saved
data. A channel currently being measured remains visible until its reading is
written.

The desktop application provides editable keybind fields for the two primary
operator actions from `Edit > Keybinds`. The defaults are the normal keyboard
`Return`/`Enter` key for `Read IL Values` and `+` for `Write IL Values`; the
keypad Enter key is also supported. Changing either field updates the shortcut
immediately and persists it for the next launch. The `-` shortcut is not
assigned to an action.

During a hardware run, `Read IL Values` measures both wavelengths and displays
them in Current readings without writing the result. The active channel stays
in the table as `-` for both values with status `Taking measurement`. `Write
IL Values` then commits the result to the table and CSV/JSON files before the
worker advances to the next channel. Starting and stopping a run without
writing any measurement leaves no empty run folder, CSV, or JSON file behind.

`Tools > Live Write Mode` provides an optional workflow. After the run
routs each channel, the ILM automatically refreshes both wavelengths after a
250 ms software pacing delay. The displayed value is not saved until `Write IL` is pressed;
then the latest complete reading is committed and the run advances. The red
`LIVE` indicator appears while updates are active.
Live Write Mode is enabled by default on startup, lasts only for the current
application session, and cannot be changed during an active run.

The same panel includes a guarded `Start Run` path. It is enabled after the
measurement hardware and switch are connected and available so a missing setup
item can be explained in one preflight message. The run borrows
those persistent connections, asks the operator to move the cable before each
reading, and releases exclusive access without disconnecting the instruments.
Hardware-run results are currently displayed
and saved incrementally to the same CSV/JSON pair, including results accepted
before a stop or hardware error.

Before a production power sample is taken, the driver confirms that the actual
ILM wavelength matches the requested wavelength. A difference in the DLL's
diagnostic index/count convention alone does not stop the run when the actual
wavelength is correct; diagnostics retain those raw values as warnings.

The reference powers are displayed in the Reference panel beside Hardware
Controls below Current readings. Hardware Test Setup can be collapsed to give
the readings table more vertical space. References belong to the connected
measurement session rather than the loaded run. Normal
operators cannot edit or authorize them directly. Use
`Calculate Reference` with connected measurement hardware; Admin Mode provides
an explicit `Apply Manual Reference` action for controlled exceptions. A real
full-pass run queries the OSX-150 for its configured
logical channel count instead of relying on the simulation channel setting.

Before starting real hardware, the setup panel supports a full configured
pass, one channel, or specific channels and inclusive ranges. It also captures
the main-board serial, switch serial, operating band, and operator initials in
the run metadata.

Before a production run can start, use **Connect Hardware...** to connect all
required hardware, complete the required Hardware test setup fields, and use
`Calculate Reference`. The reference is displayed beside Hardware Controls in
the right column and belongs to the connected measurement session rather than
the loaded run. A
production run cannot start until a valid calculated reference exists for the
connected measurement hardware. Loading another run or CSV does not replace
the active session reference. A confirmed ILM disconnect clears it and
requires a new reference. Admin Mode can
explicitly continue without descriptive metadata, but it cannot bypass missing,
invalidated, stale, or mismatched references or disconnected hardware. The
preflight runs before run folders/files, switch routing, laser activation, or
measurement.
For initial hardware validation, use the one-channel or short-range modes.

The setup panel only shows the selector needed by the chosen channel mode:
single-channel mode shows `Channel`, specific-channel mode shows
`Channels/ranges`, and full-pass mode hides both selectors.

Full configured pass also has an optional `Choose channel order manually`
checkbox for scattered one-off setups. When enabled, the application asks for
the next channel before each measurement. Previously accepted channels may be
entered again; the newest accepted reading replaces that channel's current
row. After every
configured channel has been covered once, the operator can retest another
channel or finish the pass. The checkbox is off by default, so the normal
ordered full pass is unchanged.

## Multiple runs for one unit

Hardware test setup includes a `Run number` field. New numbered runs are stored
under a shared unit folder:

```text
ILM-Reads/
`-- Unit-17688/
    |-- unit.json
    |-- Run-1-12345678901/
    |   |-- Run-1-12345678901.csv
    |   `-- Run-1-12345678901.json
    `-- Run-2-12345678901/
        |-- Run-2-12345678901.csv
        `-- Run-2-12345678901.json
```

The operating band, tested-by initials, timing, and written measurements belong
to each run. Main board identity, part number, completed replacements, and
designated spare ports belong to the unit. The switch serial belongs to the
individual run because a failed switch can be replaced without changing the
unit. Use `Load Run`
beside the run number to open an existing numbered run for the entered unit.
Replacement recommendations are recalculated from the selected run and are not
stored as permanent results.

The table also has an optional `Compare with` selector. Choose another numbered
run for the same unit to add read-only 1310 nm and 1550 nm comparison columns.
Choose `No comparison` to hide them again. Comparison values are matched by
logical channel, do not affect the current run's analysis or filters, and are
not written back to either run.

## Replacement analysis for switches with extra physical ports

Some 48-channel switches contain extra physical ports, such as ports 49 and
50, while the finished switch is still designed to use only 48 channels. After
a full pass, open `Analyze Replacements` in the analysis panel. The application
derives the designed/front-panel channel count from the three-digit channel
field in the saved OSX part number; it does not ask the operator to enter a
second count. Rows beyond that derived count are treated as measured extras.
A 48-channel run with exactly 48 measured rows has no extras, so the analysis
is reported as not applicable.

The analysis recommends a swap only when the extra is at or below the warning
limit at both wavelengths and improves the target channel's worse wavelength by
at least the selected minimum improvement (0.05 dB by default). It processes
the worst production channels first, removes each selected extra from the
candidate pool, adds displaced production ports back into the spare pool, and
then designates the best remaining readings as the requested spares. The
default is two designated spares, and they do not have to be within the
warning limit because they are emergency-use backups; this is shown explicitly.
Recommendations for channels currently over the warning limit are shown as
required replacements. Improvements to channels already within the limit are
shown separately as `Optional Replacements`.

The logical channel, measured physical port, and both losses are preserved in
the run's CSV/JSON files. Replacement recommendations are calculated and shown
on screen only; they are not stored as run data.
The program does not change the OSX-150 replacement configuration; the
recommendations are an analysis for the operator to act on physically.

After a successful full configured pass with every planned channel written, the
application offers to open the existing replacement-analysis workflow. Choosing
No dismisses the offer; choosing Yes opens the same advisory analysis used by
the analysis panel. The prompt does not change run data, replacement records,
switch mappings, or COC output. The prompt is not shown for partial, selected,
stopped, failed, retest-only, loaded-only, or unsupported MM runs.

After physically performing swaps, use `Manage Port Replacements...` in the
Replacement analysis panel. The operator records the `Current Port`,
`Replacement Port`, reason, and initials; the application supplies the UTC
timestamp. Recommended swaps can be pre-filled, and designated spare ports
remain available. Replacement events are append-only, so a later change such
as `14 -> 41 -> 43` preserves the entire chain while normal COC consumers use
the effective `14 -> 43` projection. Records and designated spares are saved
in the unit's shared `unit.json`; recording them does not alter measurements
or recommendations and never commands or verifies the switch. The workflow
does not use `CLOSe?`; general routing behavior is documented separately.
Use `Copy Replacement Notes` beside the management button to copy the active
replacement records with their available reason, operator, and timestamp for
pasting into the Unit Editor notes.

## COC workbook export

`Write COC...` opens a preparation dialog instead of immediately exporting the
active table. The dialog derives the front-panel channel count from the
selected base run's part number, displays it read-only, and lets the operator
choose one persisted base run and optionally one replacement/retest run.
COC preparation starts only when the operator explicitly clicks the Hardware
Controls button or selects File > Write COC...; completing, stopping, or
failing a hardware run does not automatically ask whether to create a COC.

If COC preparation or export cannot complete, the dialog explains whether the
attempt was blocked by validation, canceled, or failed technically. Technical
failures include the failed stage, the exception type/message, and a suggested
operator action. Each explicit attempt is also correlated in the local support
logs with a `coc_attempt_id`; if the workbook was created but provenance
metadata could not be saved, the operator is told where the partially saved
workbook is located.
Saved readings remain available for a later explicit export.
Supplemental readings replace complete 1310/1550 pairs by logical channel;
the source run and reported physical port remain traceable. A changed physical
port must match a completed Current Port -> Replacement Port record.

The report is blocked if a required front-panel channel is missing, invalid,
negative, physically inconsistent, or has either displayed four-decimal value
greater than or equal to 2.5000 dB. There is no incomplete-report override.
When the combined result passes but a channel is above 2.2500 dB and a measured
replacement candidate is available, the operator is warned and may return to
the run or write the passing COC anyway. Source run measurements are never
changed by preparing or exporting a combined report.

The 45-channel template is selected automatically for counts 1-45; the
48-channel template is selected for counts 46-48. The `OSX Template` sheet
uses rows 11-55 for channels 1-45 and rows 67-69 for channels 46-48. The
1310 nm values go in column D and 1550 nm values go in column E. The Part
Number is written to merged `B4:C4` through `B4`, the Main Board serial to
merged `D4:E4` through `D4`, the current date to `F4`, and the Tested by
initials to `G4`. Other template
values and formatting are preserved. Rows below the final required channel are
removed, affected merged ranges are repaired, and the print area ends at the
completed report.

The first output is named `COC OSX-150 <Main Board serial>_YYMMDD-HHMMSS.xlsx`
and is saved in the selected base run folder. Existing files receive a numeric suffix instead of being
overwritten. The original template is never modified. The COC export uses
`openpyxl`, so Microsoft Excel is not required on the target computer.
Template graphics are preserved when present. Base/supplemental run numbers,
front-panel count, and supplemental channel/physical-port overrides are stored
as COC provenance in the base run metadata.

The three-digit channel field in a supported OSX-100/OSX-150 part number is the
front-panel count. A Full configured pass may measure additional physical
switch ports; those ports are available to replacement analysis but are not
written to the COC. Missing or invalid part numbers block replacement analysis
and COC preparation instead of allowing the operator to guess a count.

## Copy raw readings for Excel

The `Copy Raw Data...` button in Hardware Controls copies the accepted readings
from the active run to the Windows clipboard as tab-separated text. Paste it
directly into Excel or another spreadsheet. The output contains only the
logical channel, 1310 nm IL, and 1550 nm IL values, in channel order, with four
decimal places. It intentionally has no header row so it can be pasted into an
existing spreadsheet table:

```text
1	0.7421	0.5138
2	0.8014	0.6042
```

Only readings that were written to the run are included. Current/live readings,
unfinished channels, metadata, analysis, replacements, and designated spares
are excluded. The table's display filter does not affect the copied rows, and
copying does not create or modify CSV, JSON, COC, or other output files.

The Hardware test setup includes a Part number field and a lookup button. The
default lookup folder is
`U:\Product Log\Units-COCs-Param Files\OSX-150`. For a Main Board serial such
as `17688`, the lookup finds a directory beginning with
`SN17688_` and uses the remainder of that directory name as the part number.
`File > Part Number Lookup Folder` opens the designated lookup folder in
Windows File Explorer. The location is fixed and is not editable in the
application. The part number can always be entered manually. Connecting a
supported OSX also uses the serial already returned by its identity response
to fill Main Board serial and start this lookup in the background when no run
is loaded or active. A missing network folder or match does not disconnect the
hardware or prevent manual entry.
The Part number field is also an editable drop-down containing the current
standard OSX-150 part numbers. Operating band is selected from `O band` or
`C band`. The `Tested by` field accepts the operator's initials and is saved
with the run and copied into `G4` of the COC workbook.
The read-only `Front-panel channels` value beside the setup fields is derived
from the part number's three-digit channel field. It is not manually editable.

The packaged ZIP includes `Check Dependencies.cmd`, which launches a
non-destructive report for bundled files, VISA, connected instruments, run
folder permissions, the optional U: lookup path, and Santec Terminal status.
Its timestamp and computer name are diagnostic-only and are never added to run
metadata or COC exports.

When continuing a loaded run, Light Workbench loads its part number and both
serial fields back into Hardware test setup. If those values are corrected,
the program asks whether to update the saved metadata and whether to rename the
run folder, same-named CSV/JSON files, and existing COC workbook. Renaming
preserves the original run timestamp, avoids overwriting an existing run, and
updates the COC filename to the new Main Board serial.

Real switch runs also record their first start time, latest stop time,
continuation timestamps, session count, and accumulated switch-test duration in
CSV metadata. The structured JSON stores each session separately. Live IL and
Red Light Test activity is intentionally excluded.

## Requirements

- Windows
- **32-bit Python 3.11**
- The vendor's 32-bit `OP815M.dll`
- The approved OptoTest OP-USB driver ([download package](https://santec-inst.files.svdcdn.com/production/USB-Driver-for-Santec-CA-Optotest.zip?dm=1768835182))
- `openpyxl==3.1.5` for XLSX COC export
- The USB driver needed by the ILM/OP815
- PyVISA installed in the 32-bit Python environment
- A VISA implementation available to PyVISA, such as NI-VISA
- The ILM and OSX-150 connected by USB and powered on

For the packaged executable, the target computer must also have the compatible
32-bit VISA runtime installed. The executable does not modify or bundle a
VISA installation.

The DLL is 32-bit, so 64-bit Python cannot load it. Installing both Python
architectures on the same computer is fine as long as this application is
explicitly started with the 32-bit interpreter.

## Initial setup

Open PowerShell or Command Prompt in this folder and install PyVISA into the
32-bit Python environment:

```powershell
py -3.11-32 -m pip install pyvisa
```

Install the pinned application and packaging dependencies with:

```powershell
py -3.11-32 -m pip install -r requirements-win32.txt
```

Build the one-folder Windows distribution with:

```powershell
py -3.11-32 -m PyInstaller --noconfirm --clean ilm_app.spec
```

The result is written to `dist\LightWorkbench\`. Launch
`LightWorkbench.exe` from that folder. If PowerShell blocks `.ps1` scripts due
to the local execution policy, run the PyInstaller command above directly.

After testing the distribution, create a deployment ZIP with:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\package_release.ps1
```

The archive is written to `releases\LightWorkbench-v<version>.zip`. Add
`-Force` only when intentionally replacing an archive with the same version.

Before distributing a newly built executable, optionally run the packaged
startup smoke test:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\smoke_test_release.ps1
```

For the legacy console workflow, keep these source files together:

```text
ILM Python Testing/
|-- ILMReadLoss.py
|-- op815_driver.py
|-- osx150_driver.py
|-- OP815M.dll
`-- README.md
```

If Santec Terminal is open, disconnect it from the OSX-150 or close it before
running this program. Two applications attempting to control the same VISA
resource can cause a resource-busy or device-not-found error.

## Legacy console workflow

The following instructions apply to `ILMReadLoss.py`, the older console
workflow. The current desktop workflow is `ilm_app.py` or the packaged
`LightWorkbench.exe` described above.

### Running a test

From this folder, run:

```powershell
py -3.11-32 ILMReadLoss.py
```

Run the hardware-free power-meter tests with:

```powershell
py -3.11-32 -m unittest -v tests.test_power_meter
```

The CSV loader and analysis model are covered by:

```powershell
py -3.11-32 -m unittest -v tests.test_run_data
```

Then follow these steps:

1. Choose full pass, one channel, or specific channels/ranges.
2. The program connects to the OSX-150 and reads its configured logical channel
   count.
3. If option 2 was selected, enter one channel. For option 3, enter a mixture
   such as `1, 9, 10-15, 27`.
4. Enter the main board serial, or press Enter to leave it blank.
5. Enter the switch serial, or press Enter to leave it blank. The field accepts
   any length and does not require the value to be numeric.
6. Connect measurement hardware and select `Calculate Reference`.
7. The program connects to the ILM.
8. Move the cable to the channel shown in the prompt and press Enter.
9. Review the displayed 1310 nm and 1550 nm insertion losses.
10. Press Enter to accept the reading, write it to the CSV, and continue. To
    clean the connection and try again, enter `-` and press Enter; the rejected
    values are not saved and the switch stays on the same channel.
11. After all selected channels are complete, enter any completed channels or
    ranges to retest, or press Enter to finish. Accepted retest readings
    replace the earlier row for that channel in the CSV.

During an active run, `Change Channel...` can replace the current uncommitted
step without disconnecting the instruments. Manual-order runs reopen the channel
selector. Ordered full passes also ask whether to continue sequentially from the
new channel or resume the interrupted channel afterward. Previously saved data
is preserved until a replacement reading is written.

Each accepted reading stores the immutable reference snapshot used for its
calculation, including values, method, timestamp, snapshot ID, and connected
measurement-device identity. Loading an old run displays its historical
reference for review but never authorizes it for a new acquisition.

## How insertion loss is calculated

For each wavelength, the program uses:

```text
insertion loss (dB) = reference power (dBm) - measured power (dBm)
```

The ILM measurement sequence matches its front-panel behavior:

1. Make sure both sources are off.
2. Select 1310 nm, turn on its laser, wait briefly, read power, and turn it off.
3. Select 1550 nm, turn on its laser, wait briefly, read power, and turn it off.
4. Restore the detector wavelength that was selected before the measurement.

The source IDs used by `OP815M.dll` are zero-based: source `0` is 1310 nm and
source `1` is 1550 nm.

## Logical channels and replacement physical ports

The program always requests a **logical test channel**, such as channel 2. The
OSX-150 applies whatever replacement mapping is saved in its own configuration.

For example, if logical channel 2 has been replaced by physical port 49:

```text
OSX-150 test channel 2 is using replacement physical port 49.
```

This is informational and does not stop the test. The CSV records logical
channel `2`, because that is the position being tested. The same behavior works
for other replacements, including physical ports 50-56, without hard-coded
mappings in Python.

Every mismatch encountered while routing a tested channel is automatically
added to the `Swapped ports` metadata row in the form `2->49, 36->52`. If no
mismatches are encountered, the row says `None detected in tested channels`.
For a one-channel or partial-range run, this describes only the channels tested
in that run; the program does not move through unselected channels merely to
inspect their mappings.

The full-pass and range limits come from `CFG:SWT:END?`, so the program adapts
to different switches and configured logical channel counts.

## Output names

Every run gets its own folder under `IL-Reads`. Names use the local month, day,
hour, and minute at which the output is created.

| Serials provided | Run folder | CSV file |
| --- | --- | --- |
| Switch and main board | `[switch]-[main board]-IL_MM-DD_HH-MM` | `[switch]-[main board]-output_MM-DD_HH-MM.csv` |
| Switch only | `[switch]-IL_MM-DD_HH-MM` | `[switch]-output_MM-DD_HH-MM.csv` |
| Main board only | `[main board]-IL_MM-DD_HH-MM` | `[main board]-output_MM-DD_HH-MM.csv` |
| Neither | `IL-Read_MM-DD_HH-MM` | `output_MM-DD_HH-MM.csv` |

For example:

```text
IL-Reads/
`-- 18760-MB123-IL_09-02_14-25/
    `-- 18760-MB123-output_09-02_14-25.csv
```

If an identical folder name already exists because two runs started during the
same minute, the program adds `-2`, `-3`, and so on to the new folder instead
of overwriting an earlier test.

Characters that cannot safely be used in a Windows filename are converted to
hyphens in the folder and CSV names. The original serial entry is preserved in
the metadata table.

The current desktop GUI stores runs under `Documents\ILM-Reads` using folders
named `ILM-Run_YYMMDD_HHMMSS_[main board serial]-[switch serial]`. Missing serials
are omitted, and the run CSV uses the final folder name with a `.csv` extension.
The Open Existing CSV dialog starts in this same folder. The
File > Data Output Folder menu item opens this folder directly. The legacy
console workflow above retains its separate naming convention.

## CSV tables

The measurement table occupies columns A-C. Column D is intentionally blank,
and the metadata table occupies columns E-F so both tables are easy to read in
Excel:

```csv
channel,1310 IL,1550 IL,,Metadata,Value
1,2.2290,1.4990,,Main board serial,MB123
2,2.1840,1.4720,,Switch serial,12345678901
,,,,Swapped ports,2->49
,,,,Operating band,O band
```

The insertion-loss columns are in dB. The file can be opened directly in Excel
for averages, charts, conditional formatting, outlier analysis, or additional
test documentation. The extra timestamped folder is intentionally available
for other files associated with that test run.

The operating band is currently hardcoded to `O band`. A `TODO` comment in
`ILMReadLoss.py` marks this as something to query or prompt for later.

## Stopping safely

Press Ctrl+C to stop a run. The complete output is safely updated after every
accepted reading, so completed work remains available in the partial CSV.

During normal cleanup the program:

- Turns both ILM laser sources off.
- Disables ILM remote mode.
- Closes the ILM DLL driver.
- Closes the OSX-150 VISA session.

The program changes the active OSX-150 channel during testing and leaves it on
the last channel selected.

## Reference and measurement validation

Calculated production references reject a measured wavelength only when it is
strictly below **-40.0 dBm**. A value of exactly -40.0 dBm is accepted by this
dark-signal rule. A rejected reference cannot authorize a run; the warning
identifies the affected wavelength values and recommends checking the cable,
source, and optical connection.

Insertion loss remains `reference power - measured power`. A completed sample
is invalid when either wavelength is negative after rounding to four decimal
places. The values remain visible for troubleshooting, but Write IL is
disabled and the worker also rejects direct write requests. Live Write Mode
continues monitoring without showing a modal warning on every refresh; a later
valid sample clears the status. One negative sample does not invalidate the
active reference. Check and reseat the cable, retest, recalculate the
reference if needed, and write only after both values are valid.

## Troubleshooting

### Python says the DLL is not a valid Win32 application

The script is probably running under 64-bit Python. Use:

```powershell
py -3.11-32 ILMReadLoss.py
```

### `OP815M.dll was not found`

Place `OP815M.dll` beside `op815_driver.py`. Do not rename the DLL.

### `No OP815/ILM was detected over USB`

- Confirm that the ILM is powered on.
- Reconnect its USB cable.
- Confirm that its Windows USB driver is installed.
- Close other software that may have the ILM driver open.
- Reboot the ILM, wait for it to finish starting, and try again.

If multiple OP815 devices are found, the application lists their descriptions
and USB serial numbers and asks which index to use.

### `No supported Santec OSX switch was detected over USB VISA`

- Confirm that the switch is powered on and connected through USB.
- Close or disconnect Santec Terminal so it releases the VISA session.
- Confirm that PyVISA and a compatible VISA implementation are installed.
- Verify that Santec Terminal can still identify the switch when used by itself.
- If VISA enumeration misses a switch whose address is known, enter that exact
  address under **Tools > Switch VISA Address...** and reconnect. Clearing the
  field restores automatic discovery. The setting applies to the next switch
  connection and does not replace a missing or incompatible VISA driver.

The switch connection tries a manual address, a separately remembered working
address, and then a USB-only VISA discovery query. It automatically tries LF
and then CRLF for `*IDN?`, retains the working ending, and validates the
configured channel count before routing. A detected switch that reports zero
channels is identified by model, serial, firmware, and address, but channel
commands remain blocked until its configuration is restored.

### The displayed loss does not match the ILM screen

- Confirm that the entered 1310 nm and 1550 nm references match the current
  front-panel references.
- Check that the optical cable is connected to the channel shown in the prompt.
- Clean and reseat the connection, then enter `-` to discard and retest.
- Remember that reference power is entered in dBm, while calculated insertion
  loss is reported in dB.

### A run was interrupted

Look at the path printed after the interruption. All channels accepted before
the interruption remain in that CSV.

## Code structure for future development

New user workflows should normally be added to `ilm_app.py` and the appropriate
`application/`, `ui/`, `domain/`, `hardware/`, or `infrastructure/` module.
Raw ILM DLL calls belong in `op815_driver.py`, and raw OSX-150 VISA/SCPI
commands belong in `hardware/optical_switch.py`. Keeping those responsibilities
separate makes it easier to support an OPM and separate laser source later.
`ILMReadLoss.py` remains the legacy console entry point, and root-level driver
modules remain compatibility facades where documented.

Before making code changes, read [`docs/README.md`](docs/README.md) and the
specialist architecture document for the area being changed.

Metadata collection, automatic swap tracking, and `metadata_table_rows()` are
separate from `write_combined_csv()`. If metadata is moved to a dedicated CSV
later, the metadata structure can remain unchanged; only the final writer will
need to be adjusted.
