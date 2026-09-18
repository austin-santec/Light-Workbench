# Light Workbench — AI Handoff

This document is a working orientation guide for another AI or developer
continuing this project. It describes the code as found on 2026-09-16. The
files on disk are the source of truth; this folder did not contain a usable Git
worktree when inspected (git status reported that it was not a repository).

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

The current user-facing release is **Light Workbench 1.6.1**. The single
source of truth for the displayed name, version, tagline, and About text is
`app_info.py`; bump the patch version for small fixes, the minor version for
backward-compatible features, and the major version for incompatible changes.
The main window exposes this through `Help > About`.

| File | Responsibility |
| --- | --- |
| ilm_app.py | Current PyQt5 desktop viewer and real-hardware UI. Loads CSV runs, analyzes limits, starts hardware runs, displays readings, and commits accepted results. The header includes the bundled Lulu - CandC logo; the UI uses a light-grey shell and `#e60013` primary accent. |
| measurement_worker.py | Qt worker/orchestrator. Connects instruments, routes channels, waits for operator cable placement, supports repeated reads, emits readings/progress, and always closes instruments. |
| power_meter.py | Application-facing meter interface. SantecPowerMeter wraps the OP815 driver; SimulatedPowerMeter is deterministic and hardware-free. |
| op815_driver.py | ctypes wrapper around the 32-bit OP815M.dll. Owns DLL discovery, function signatures, device selection, source control, wavelength selection, measurements, and cleanup. |
| osx150_driver.py | PyVISA/SCPI driver for USB OSX-150 discovery, logical channel routing, configured-channel count, and physical-port reporting. |
| red_light_test.py | Separate VFL pre-test dialog. Tools > Red Light Test opens it without connecting; its Start button connects and routes channels without creating readings or run/COC data. |
| live_il_reading.py | Meter-only Live IL Reading dialog. It connects only to the OP815, calculates both wavelength losses from editable references, supports non-persistent reconnect repeatability testing and timed live updates, and never controls the switch or persists data. |
| app_info.py | User-facing Light Workbench name, version, tagline, and About text. |
| run_data.py | MeasurementRecord, RunData, CSV loading, over-limit filtering, and analysis counts. |
| run_persistence.py | Modern atomic CSV/JSON persistence and accepted-attempt history for the desktop app. |
| switch_timing.py | Real switch-test session timing; accumulates across continuation sessions and excludes Live IL/Red Light Test. |
| replacement_analysis.py | Hardware-independent selection of worthwhile replacements and best remaining designated spares, including displaced production ports. |
| coc_export.py | XLSX COC template export, merged-cell mapping, collision-safe filenames, Main Board serial lookup, and preservation of embedded template graphics. |
| ILMReadLoss.py | Older, still functional console workflow. Owns prompts, validation, calculations, legacy CSV naming/output, retests, and legacy replacement-port metadata. |
| ilm_app.spec | PyInstaller one-folder build for ilm_app.py, including OP815M.dll. |
| assets/Lulu - CandC.png | Bundled header logo displayed at a capped size so it does not increase the window layout height. |
| assets/Lulu - C&C-white_square.ico | Windows application and taskbar icon generated from the square logo. |
| README_INSTALL.txt | Plain-text deployment guide intended to ship beside the packaged executable in the ZIP. |
| Check Dependencies.cmd | Optional launcher for `LightWorkbench.exe --check-dependencies`. |
| build_windows.ps1 | Repeatable 32-bit PyInstaller build command. |
| tests/ | Hardware-free unit tests for the viewer, worker, meter adapters, CSV model, and persistence. |

The normal direction for new desktop behavior is ilm_app.py; keep raw
instrument protocol code in the two driver modules. Treat ILMReadLoss.py as a
legacy/console path unless a change explicitly needs to preserve or improve it.

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
8. On completion, stop, or hardware failure, the instruments are closed. Rows
   accepted before interruption remain persisted.
9. Existing CSVs can be opened for analysis. The table highlights either
wavelength over the warning limit and Select Over-Limit selects rows for
retest.
10. `Analyze Replacements` uses measured rows whose channel is above the
configured designed-channel count as extra physical-port candidates. It
selects worthwhile replacements, adds displaced production ports back into the
spare pool, then ranks the best remaining readings as designated spares. The
spares do not need to be within the warning limit because they are emergency-
use backups. The result is stored on `RunData`, in `run.json`, and
as readable CSV metadata. A run with no extra measured rows reports the
analysis as not applicable.
11. COC export is available after a hardware completion, stop, or failure with
a run, and from the controls/File menu. It accepts partial and over-limit data;
missing logical channels stay blank. `coc_export.py` copies the bundled XLSX
template and writes the `OSX Template` sheet's split rows, Part Number, Main
Board serial, and date while preserving other workbook content. It uses
`openpyxl`, so Excel is not required. The default part lookup is
`U:\Product Log\Units-COCs-Param Files\OSX-150` and can be changed from the
File menu.

12. `Tools > Red Light Test...` opens a non-recording VFL pre-test dialog. The
menu item only opens the dialog; `Start Red Light Test` performs the connection
and selects channel 1. The operator can type a channel number, use the Up/Down
keys, or use Previous/Next. The dialog displays the selected logical channel,
configured total, and physical port, and disconnects when stopped or closed.

13. `Tools > Live IL Reading...` opens a meter-only dialog. It does not connect
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

osx150_driver.py filters VISA resources by Santec USB vendor/product IDs
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

### Modern desktop CSV/JSON (run_persistence.py)

RunRecorder defaults to `Documents\ILM-Reads`. Each run is stored in a folder
named `ILM-Run_YYMMDD_HHMMSS_[main board serial]-[switch serial]`; missing serials
are omitted and unsafe filename characters are normalized. The run CSV uses the
final folder name with a `.csv` extension. The Open Existing CSV dialog starts
in this same default run folder, and File > Data Output Folder opens it directly.
Each run writes same-named CSV and JSON files. Older runs using output.csv and
run.json remain supported. Both are written through a temporary
file and os.replace() so an accepted row is not lost to a partial write.
Real switch runs add readable timing metadata for first start, latest stop,
continuation times, session count, and accumulated duration; JSON also stores
the individual session records. Live IL and Red Light Test do not affect these
fields.
The CSV remains compatible with load_run_csv; JSON contains the warning
limit, metadata, current measurements, and an attempts list with timestamp,
channel, physical port, losses, and retest flag.

The difference between project-local legacy output and Documents-based desktop
output is intentional in the current code but should be resolved or clearly
versioned before broad deployment.

Replacement-analysis details are saved under the metadata keys `Replacement
recommendation N` and `Recommended designated spare N`. The structured `run.json` also stores
the full replacement-analysis result and each current measurement's
`physical_port`. The CSV measurement table remains three columns so it stays
compatible with Excel and older CSV loading.

COC export metadata includes `Part number`, `COC output file`, `COC output
path`, `COC exported at`, and `COC template`. The current XLSX mapping is
`OSX Template!D11:D55` and `E11:E55` for channels 1-45,
`D67:D69` and `E67:E69` for channels 46-48, `B4` for the merged part-number
cell, `D4` for the merged Main Board serial cell, and `F4` for the date.

## Known issues and inconsistencies

These are observations from source inspection, not assumed fixes:

1. Retesting a loaded CSV is not currently persisted. load_path() sets
   self.run_recorder = None. retest_selected() starts a hardware retest,
   but the retest branch of start_hardware() does not reconstruct a recorder
   for the existing CSV/JSON. commit_hardware_reading() therefore updates the
   in-memory table only when retesting an opened run. The intended behavior in
   README.md is to replace the CSV value and append the JSON attempt history.
   Fix this first, with a test proving an opened run's CSV and JSON are changed
   only after Write IL Values.

2. The documented simulation UI is disconnected. SimulatedPowerMeter and
   start_demo(), measure_demo(), and related methods remain in ilm_app.py, but
   _build_ui() creates no demo_channel_count, measure_demo_button, or
   accept_demo_button, and no UI action calls start_demo(). Calling the stale
   method would hit undefined widget attributes. Either wire simulation back
   into the GUI and test it, or remove the dead workflow and update the README.
   Keep SimulatedPowerMeter if it remains useful for worker/UI tests.

3. Modern desktop runs preserve the physical port in `run.json` and use it for
   replacement analysis, but the CSV measurement table intentionally remains
   logical-channel-only. If a human-readable mapping of every observed logical
   channel is needed in CSV metadata, add it without changing the CSV's first
   three measurement columns.

4. The README describes one unified output convention, but the code has two.
   ILMReadLoss.py uses serial/timestamp names in project-local IL-Reads, while
   RunRecorder uses generic output.csv/run.json in a Documents folder.
   run_data.py can read both layouts, but users and future tooling need an
   explicit compatibility policy.

5. The build log reports a non-fatal missing hidden import warning for `sip`.
   PyInstaller nevertheless completes successfully; validate the packaged
   executable on a clean 32-bit Windows machine.

6. No hardware integration tests are present. Unit tests use fakes and do not
   validate actual DLL return codes, VISA resource discovery, SCPI syntax,
   optical settling, replacement mappings, or cleanup on a real device.
   Hardware tests should be opt-in, visibly destructive, and never part of the
   normal unit-test command.

7. COC export has hardware-free XLSX tests and a real-template round-trip
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
