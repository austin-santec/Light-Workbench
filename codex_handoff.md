# Light Workbench — AI Handoff

This document is a working orientation guide for another AI or developer
continuing this project. It was last reviewed on 2026-09-25. The files on disk
and the Git worktree are the source of truth.

## Mission

This project automates optical insertion-loss testing for an ILM-100/OP815
meter and a Santec OSX-150 optical switch. The operator selects logical switch
channels, moves the output cable when prompted, and obtains insertion loss at
1310 nm and 1550 nm.

For each wavelength:

    insertion loss (dB) = reference power (dBm) - measured absolute power (dBm)

The application does not modify the ILM's saved reference values or the
OSX-150 replacement-channel configuration. A logical channel can therefore
report a different physical port when the switch has a replacement mapping.

## Current architecture

The current user-facing release is **Light Workbench 1.7.2**. The single
source of truth for the displayed name, version, tagline, and About text is
`app_info.py`; bump the patch version for small fixes, the minor version for
backward-compatible features, and the major version for incompatible changes.
The main window exposes this through `Help > About`.

| File | Responsibility |
| --- | --- |
| ilm_app.py | Current PyQt5 desktop viewer and real-hardware UI. Loads CSV runs, analyzes limits, starts hardware runs, displays readings, and commits accepted results. The header includes the bundled Lulu - CandC logo; the UI uses a light-grey shell and `#e60013` primary accent. |
| application/measurement_worker.py | Qt worker/orchestrator. Connects instruments, routes channels, waits for operator cable placement, supports repeated reads, emits readings/progress, and always closes instruments. |
| measurement_worker.py | Compatibility facade for the application measurement worker. |
| application/live_controller.py | Shared meter worker lifecycle used by Live IL and the main-window reference calculation. |
| application/hardware_planning.py | Normalizes channel-mode selections before a hardware run starts. |
| application/run_start.py | Prepares normalized hardware-run plans and controller requests without UI or hardware access. |
| application/run_controller.py | Owns hardware-run worker lifecycle, requests, commands, and terminal cleanup. |
| hardware/power_meter.py | Application-facing meter adapter. SantecPowerMeter wraps the OP815 driver; SimulatedPowerMeter is deterministic and hardware-free. |
| power_meter.py | Compatibility facade for the hardware power-meter adapters and PowerMeter contract. |
| hardware/interfaces.py | Vendor-neutral PowerMeter, LaserSource, and OpticalSwitch protocols. This is the starting boundary for future OPM plus separate laser support. |
| application/ | Workflow controllers, measurement worker, planning, and transient hardware-run state. |
| domain/ | Vendor-neutral models, calculations, replacement rules, timing, and reporting. |
| hardware/ | Hardware contracts, factories, simulated adapters, and composed sessions. |
| infrastructure/ | File repositories, schema migration, run queries, reports, and COC adapters. |
| infrastructure/run_persistence.py | Atomic CSV/JSON recorder and run filename rules; root `run_persistence.py` is a compatibility facade. |
| infrastructure/unit_persistence.py | Atomic unit JSON records and numbered-run paths; root `unit_persistence.py` is a compatibility facade. |
| infrastructure/coc_export.py | COC template lookup, XLSX writing, and drawing preservation; root `coc_export.py` is a compatibility facade. |
| op815_driver.py | ctypes wrapper around the 32-bit OP815M.dll. Owns DLL discovery, function signatures, device selection, source control, wavelength selection, measurements, and cleanup. |
| hardware/optical_switch.py | PyVISA/SCPI adapter for USB OSX-150 discovery, logical channel routing, configured-channel count, and physical-port reporting. |
| osx150_driver.py | Compatibility facade for the OSX-150 hardware adapter. |
| red_light_test.py | Separate VFL pre-test dialog. Tools > Red Light Test opens it without connecting; its Start button connects and routes channels without creating readings or run/COC data. |
| live_il_reading.py | Meter-only Live IL Reading dialog. It connects only to the OP815, calculates both wavelength losses from editable references, supports non-persistent reconnect repeatability testing and timed live updates, and never controls the switch or persists data. |
| app_info.py | User-facing Light Workbench name, version, tagline, and About text. |
| domain/run_data.py | RunData and over-limit analysis rules; the root `run_data.py` remains a compatibility facade. |
| infrastructure/csv_run_loader.py | Current and legacy CSV parsing for RunData. |
| run_persistence.py | Compatibility facade for the infrastructure CSV/JSON persistence implementation. |
| unit_persistence.py | Compatibility facade for infrastructure unit records, numbered runs, replacements, and spares. |
| switch_timing.py | Real switch-test session timing; accumulates across continuation sessions and excludes Live IL/Red Light Test. |
| replacement_analysis.py | Hardware-independent selection of worthwhile replacements and best remaining designated spares, including displaced production ports, plus completed-replacement record validation and metadata formatting. |
| coc_export.py | Compatibility facade for the infrastructure COC exporter. |
| ILMReadLoss.py | Older, still functional console workflow. Owns prompts, validation, calculations, legacy CSV naming/output, retests, and legacy replacement-port metadata. |
| ilm_app.spec | PyInstaller one-folder build for ilm_app.py, including OP815M.dll. |
| assets/Lulu - CandC.png | Bundled header logo displayed at a capped size so it does not increase the window layout height. |
| assets/Lulu - C&C-white_square.ico | Windows application and taskbar icon generated from the square logo. |
| README_INSTALL.txt | Plain-text deployment guide intended to ship beside the packaged executable in the ZIP. |
| Check Dependencies.cmd | Optional launcher for `LightWorkbench.exe --check-dependencies`. |
| build_windows.ps1 | Repeatable 32-bit PyInstaller build command. |
| tests/ | Hardware-free unit tests for the viewer, worker, meter adapters, CSV model, and persistence. |

The normal direction for new desktop behavior is ilm_app.py; keep raw
instrument protocol code in the hardware adapter modules. Treat ILMReadLoss.py
as a legacy/console path unless a change explicitly needs to preserve or
improve it.

## Architecture refactor status

The incremental refactor has progressed without changing the current
operator workflow. `hardware/interfaces.py` now defines the application-facing
contracts for a power meter, separate laser source, and optical switch. The
existing OP815 meter and OSX-150 switch continue to be used exactly as before.
Their application-facing adapters now live in `hardware/power_meter.py` and
`hardware/optical_switch.py`; the root modules remain compatibility facades so
existing imports remain compatible.
`HardwareFactory` imports those concrete adapters lazily, keeping contract-only
imports and hardware-free tests independent of active VISA or DLL sessions.
The contracts are covered by hardware-free tests in
`tests/test_hardware_interfaces.py`.

The lifecycle, domain, repository, hardware-composition, reporting, and
release-tooling refactors are now in progress through incremental phases.
Review `docs/REFACTOR_ROADMAP.md` and `docs/PROJECT_LAYOUT.md` before starting
the next extraction. Do not move or rename compatibility modules without
regression tests and a documented migration path.

## Runtime and hardware requirements

- Windows.
- 32-bit Python 3.11. The vendor DLL is 32-bit and cannot be loaded by a
  64-bit Python process.
- PyQt5==5.15.11, PyVISA==1.16.2, and PyInstaller==6.22.2 from
  requirements-win32.txt, plus openpyxl==3.1.5 for XLSX COC export.
- OP815M.dll beside op815_driver.py for source runs, or beside the built
  executable in the PyInstaller distribution.
- The ILM/OP815 USB driver and a VISA implementation such as NI-VISA for the
  OSX-150.
- The approved OptoTest OP-USB driver package is available at
  `https://santec-inst.files.svdcdn.com/production/USB-Driver-for-Santec-CA-Optotest.zip?dm=1768835182`.
- Santec Terminal must release the OSX-150 VISA resource before this program
  connects.

In the inspected environment, python resolved to
C:\Users\Austin\AppData\Local\Programs\Python\Python311-32\python.exe
and reported Python 3.11.9. The py -3.11-32 launcher form reported “No
installed Python found,” so use the working 32-bit interpreter directly until
the Python launcher registration is repaired.

Useful commands from the project directory:

    python -m pip install -r requirements-win32.txt
    python -m unittest discover -s tests -v
    python -m compileall -q -f .
    python ILMReadLoss.py
    python ilm_app.py
    python -m PyInstaller --noconfirm --clean ilm_app.spec
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\verify_release.ps1
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\smoke_test_release.ps1
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\package_release.ps1

The last two application commands can connect to or move real hardware. Use
the GUI's explicit hardware confirmation and begin with one channel or a
short range.

## Desktop application workflow

1. Start ilm_app.py or LightWorkbench.exe.
2. Configure full configured pass, one channel, or specific channels/ranges.
   The GUI parser accepts entries such as 1, 9, 10-15, 27, removes duplicate
   channels while preserving first-entered order, and rejects malformed or
   non-positive values.
3. Enter optional main-board serial, unrestricted full switch serial, operating band,
   and the two reference powers. References default to 0.00 dBm until
   `Calculate Reference` temporarily connects to the meter, reads both
   wavelengths with a zero software reference, disconnects, and applies the
   resulting two-decimal offsets back to the setup without opening the Live IL
   window. Reference calibration uses a dedicated stabilized timing profile
   and does not slow normal production measurements.
4. Choose Start Real Hardware and confirm the warning dialog.
5. The worker connects to the OSX-150 and OP815, routes a logical channel, and
   emits operator_required(channel, physical_port).
6. The operator moves the cable and chooses Read IL Values. The worker
   measures both wavelengths and emits reading_ready(channel, physical_port,
   loss_1310, loss_1550).
7. The operator can read again or choose Write IL Values. The accepted value
    replaces any existing row for that channel and is saved immediately.
    `RunRecorder` defers creating the run folder and output files until the
    first accepted measurement, so a zero-written run leaves no empty artifact.
    `Change Channel...` can replace the current uncommitted step without
    disconnecting the instruments. Manual-order runs reopen the channel picker;
    ordered full passes ask whether to continue sequentially from the selected
    channel or resume the interrupted channel. Existing saved data is preserved
    until a replacement is written.
    As an optional one-step alternative, `Tools > Noah Mode` changes the Read
    button/keybind to Read & Write IL: successful readings are committed
    immediately and the worker advances; failed reads are not saved. The mode
    requires confirmation, cannot be toggled during a run, defaults off, and
    is not persisted between application sessions.
8. `Tools > Live Write Mode` is an optional hardware-run workflow. After the
    worker routes each channel, it automatically emits complete IL readings
    about once per second; the operator moves the cable to the shown channel
    while the values update. The UI keeps the newest value pending until
    `Write IL` is pressed; only then is it committed and the worker advances.
    The mode has a red `LIVE` indicator, is mutually exclusive with Noah Mode,
    is disabled while a run is active, and defaults on each application
    session.
9. On completion, stop, or hardware failure, the instruments are closed. Rows
   accepted before interruption remain persisted.
10. Existing CSVs can be opened for analysis. The table highlights either
wavelength over the warning limit and Select Over-Limit selects rows for
retest.
11. `Analyze Replacements` uses measured rows whose channel is above the
configured designed-channel count as extra physical-port candidates. It
selects worthwhile replacements, adds displaced production ports back into the
spare pool, then ranks the best remaining readings as designated spares. The
spares do not need to be within the warning limit because they are emergency-
use backups. Recommendations for current channels over the warning limit are
classified as required; improvements to channels already within the limit are
classified as optional. The result is stored on `RunData` and displayed on
screen only; it is not stored as permanent run data. A run with no extra
measured rows reports the analysis as not applicable. `Record Replaced
Ports...` separately records physical swaps that were actually completed using
Current Port and Replacement Port fields, and accepts designated spare ports.
Completed swaps and designated spares are displayed in the Replacement
analysis panel and saved in the shared unit `unit.json`; they are available to
all numbered runs for that unit. Older replacement
records with a logical-channel field are migrated when loaded.
`Copy Replacement Notes` copies the completed Current Port -> Replacement Port
pairs in a plain-text format for the Unit Editor notes.
12. COC export is available after a hardware completion, stop, or failure with
a run, and from the controls/File menu. It accepts partial and over-limit data;
missing logical channels stay blank. `infrastructure/coc_export.py` copies the bundled XLSX
template and writes the `OSX Template` sheet's split rows, Part Number, Main
Board serial, and date while preserving other workbook content. It uses
`openpyxl`, so Excel is not required. The default part lookup is
`U:\Product Log\Units-COCs-Param Files\OSX-150`. `File > Part Number Lookup
Folder` opens that fixed location in Windows File Explorer; it is not editable
from the application.

13. `Tools > Red Light Test...` opens a non-recording VFL pre-test dialog. The
menu item only opens the dialog; `Start Red Light Test` performs the connection
and selects channel 1. The operator can type a channel number, use the Up/Down
keys, or use Previous/Next. The dialog displays the selected logical channel,
configured total, and physical port, and disconnects when stopped or closed.

14. `Tools > Live IL Reading...` opens a meter-only dialog. It does not connect
to the OSX-150. `Start Meter` connects to the OP815, `Read IL` can be pressed
repeatedly, and `Calculate Reference` derives both shared reference offsets
from a zero-reference meter reading. Manual reference edits stay synchronized
with the main setup. It never creates run files, changes the table, or writes
COC data. `Start Live Updates` automatically refreshes both values sequentially
with a short pause between completed readings; `Stop Live Updates` ends the
refresh cycle and hides its red indicator. `Repeatability Test` opens a
right-side in-memory table for an
initial reading followed by any number of manually triggered readings after
unplugging and reconnecting the cable. It reports high, low, and range for
each wavelength, without saving the results.

The worker runs in a QThread, but its actual wait/measurement loop is based on
threading events. continue_current() releases the cable-placement wait;
read_current() asks for another sample; write_current() accepts the current
sample; stop() releases waits and causes the run to stop at the next safe
check.

## Legacy console workflow

ILMReadLoss.py prompts for a full pass, one channel, or custom channels and
ranges. It connects the switch first so it can query CFG:SWT:END? and validate
the configured logical-channel range. It then collects metadata and reference
powers, prompts for cable movement, prints both losses, and accepts Enter or
rejects with - for a same-channel retest. A final optional retest pass can
replace previously accepted rows.

The legacy path tracks logical-to-physical replacements in the Swapped ports
metadata row and writes that metadata immediately when a mapping is detected.
It handles Ctrl+C and preserves accepted rows in its partial CSV.

## Instrument behavior that must not be guessed

### OP815 / ILM

op815_driver.py binds the vendor functions with ctypes, checks process bitness
before loading the DLL, discovers devices described as OP815, and prompts for
an index if multiple devices are present. DLL source IDs are zero-based:

    source 0 -> 1310 nm
    source 1 -> 1550 nm

measure_both_wavelengths() remembers the detector wavelength, turns sources
off, measures 1310 then 1550, turns each source off in a finally block, and
restores the original detector wavelength. Current settling constants are
0.1 s wavelength, 0.5 s source-on, and 0.1 s source-off. Do not change source
IDs, DLL signatures, or timing assumptions without a hardware validation plan.

### OSX-150

hardware/optical_switch.py filters VISA resources by Santec USB vendor/product IDs
0x2428 / 0xD00D, verifies identity using *IDN?, and uses:

- CFG:SWT:END? for the configured logical-channel count;
- CLOSe <logical channel> to route a test channel;
- CLOSe? to read the physical port actually selected.

The switch applies its own replacement mapping. Python should request the
logical test channel and record the reported physical port; it should not
hardcode replacement mappings.

## Output formats and locations

There are currently two persistence implementations.

### Legacy CSV (ILMReadLoss.py)

The default root is project-local IL-Reads\. Folder and CSV names include
serials and a local MM-DD_HH-MM timestamp, with a numeric suffix on a folder
collision. The CSV has measurement columns A-C, a blank D separator, and
metadata in E-F:

    channel,1310 IL,1550 IL,,Metadata,Value
    1,2.2290,1.4990,,Main board serial,MB123
    2,2.1840,1.4720,,Switch serial,12345678901
    ,,,,Swapped ports,2->49
    ,,,,Operating band,O band

### Modern desktop CSV/JSON (`infrastructure/run_persistence.py`)

RunRecorder defaults to `Documents\ILM-Reads`. New hardware runs are grouped
under `Unit-[main board serial]\Run-N-[switch serial]\`, with a same-named CSV
and JSON file in each numbered run folder. The unit folder also contains
`unit.json`, which stores main-board/part identity, completed replacements,
designated spares, and the index of available runs. Switch serial, operating
band, and tested-by initials are run-specific. Legacy timestamped runs and
older unsuffixed `Run-N` folders remain supported and can still be opened
directly.

Both run files and unit records are written through temporary files and
`os.replace()` so an accepted row is not lost to a partial write. Real switch
runs add readable timing metadata for first start, latest stop, continuation
times, session count, and accumulated duration; Live IL and Red Light Test do
not affect these fields. The CSV remains compatible with `load_run_csv`, and
the JSON stores the warning limit, metadata, current measurements, physical
ports, and timing sessions. Retest attempts and calculated replacement
recommendations are intentionally not persisted.

The difference between project-local legacy output and Documents-based desktop
output is intentional in the current code but should be resolved or clearly
versioned before broad deployment.

Replacement analysis is calculated from the selected run and displayed in the
UI only. Manually completed replacements and designated spare ports are stored
in the shared `unit.json`, so they carry across numbered runs without changing
the measurement table. The CSV measurement table remains three columns so it
stays compatible with Excel and older CSV loading.

The UI table has an optional `Compare with` selector populated from the active
unit's numbered-run index. Selecting a previous run adds two read-only columns
for that run's 1310 nm and 1550 nm values, matched by logical channel. Selecting
`No comparison` removes them. Comparison data is never included in the active
run's analysis, filtering, or saved output.

COC export metadata includes `Part number`, `COC output file`, `COC output
path`, `COC exported at`, and `COC template`. The current XLSX mapping is
`OSX Template!D11:D55` and `E11:E55` for channels 1-45,
`D67:D69` and `E67:E69` for channels 46-48, `B4` for the merged part-number
cell, `D4` for the merged Main Board serial cell, `F4` for the date, and `G4`
for the Tested by initials.

## Known issues and inconsistencies

These are observations from source inspection, not assumed fixes:

1. The documented simulation UI is disconnected. SimulatedPowerMeter and
   start_demo(), measure_demo(), and related methods remain in ilm_app.py, but
   _build_ui() creates no demo_channel_count, measure_demo_button, or
   accept_demo_button, and no UI action calls start_demo(). Calling the stale
   method would hit undefined widget attributes. Either wire simulation back
   into the GUI and test it, or remove the dead workflow and update the README.
   Keep SimulatedPowerMeter if it remains useful for worker/UI tests.

2. Modern desktop runs preserve the physical port in `run.json` and use it for
   replacement analysis, but the CSV measurement table intentionally remains
   logical-channel-only. If a human-readable mapping of every observed logical
   channel is needed in CSV metadata, add it without changing the CSV's first
   three measurement columns.

3. The README describes one unified output convention, but the code has two.
   ILMReadLoss.py uses serial/timestamp names in project-local IL-Reads, while
   RunRecorder uses generic output.csv/run.json in a Documents folder.
   run_data.py can read both layouts, but users and future tooling need an
   explicit compatibility policy.

4. The build log reports a non-fatal missing hidden import warning for `sip`.
   PyInstaller nevertheless completes successfully; validate the packaged
   executable on a clean 32-bit Windows machine.

5. No hardware integration tests are present. Unit tests use fakes and do not
   validate actual DLL return codes, VISA resource discovery, SCPI syntax,
   optical settling, replacement mappings, or cleanup on a real device.
   Hardware tests should be opt-in, visibly destructive, and never part of the
   normal unit-test command.

6. COC export has hardware-free XLSX tests and a real-template round-trip
smoke check, but its final printed appearance should still be reviewed once
on the target printer. The network U: lookup path is environment-dependent;
the application provides a configurable folder and manual part-number fallback.

## Validation status at handoff

Completed in the inspected environment:

- python -m unittest discover -s tests -v: 33 tests passed, including replacement
  selection, bottom-spare ranking, persistence, XLSX cell mapping, template
  preservation, part-number lookup, and unrestricted switch-serial coverage.
- python -m compileall -q -f .: passed.
- py -3.11-32 -m unittest discover -v: could not start because the Python
  launcher did not recognize the installed interpreter, despite the direct
  python command being the required 32-bit Python 3.11.9.
- PyInstaller rebuilt successfully after confirming LightWorkbench.exe was
  not running. The current one-folder output is
  dist\LightWorkbench\LightWorkbench.exe; PyInstaller 6 places bundled
  support files, including OP815M.dll, under its `_internal` subfolder.

## Recommended contribution order

1. Add a focused test and fix persistence for retesting an opened run.
2. Choose a supported simulation story: wire the existing deterministic demo
   controls, or remove stale demo methods/documentation.
3. Unify or explicitly document output roots and schema versions.
4. Add GUI/worker tests for swap metadata, failed hardware startup, pending
   readings, stop behavior, and partial-run persistence.
5. Rebuild after closing any executable, then perform a one-channel physical
   validation of both instruments and cleanup behavior.

When changing hardware code, preserve the driver/application boundary, record
units in names and output headers, and prefer fakes for all automated tests.
Before any operation that can move the switch or enable an optical source,
confirm whether the path is simulated or real hardware.
