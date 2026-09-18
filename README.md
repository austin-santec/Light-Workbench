# Light Workbench

This folder contains Light Workbench, a guided Windows application for optical
testing and measurement. Its current workflow measures insertion loss at
**1310 nm** and **1550 nm** and controls:

- An ILM-100 exposed to the vendor DLL as an **OP815**
- A Santec **OSX-150** optical switch connected through USB VISA

The operator moves the output cable when prompted. The program changes the
switch channel, takes both wavelength readings, displays the calculated losses,
and saves accepted readings to a CSV file that opens directly in Excel.

## What the application can do

At startup, the program offers three workflows:

1. **Full pass** — tests every logical channel configured in the OSX-150.
2. **One channel** — tests a single logical channel.
3. **Specific channels and ranges** — accepts individual channels, inclusive
   ranges, or both in one comma-separated entry. For example,
   `1, 9, 10-15, 27` tests 1, 9, 10 through 15, and 27 in that order.

Repeated channels are tested only once. For example, `1, 1-3` tests channels
1, 2, and 3 rather than testing channel 1 twice.

For every channel, it can:

- Automatically route the OSX-150 to the requested logical channel.
- Measure absolute power at 1310 nm and 1550 nm.
- Calculate insertion loss using reference values entered by the operator.
- Display both insertion-loss values before saving them.
- Accept the displayed reading with Enter.
- Discard and retest the same channel by entering `-` and pressing Enter.
- Record switch and main-board metadata and automatically detect swapped ports
  encountered during the selected test channels.
- Use the entered serial numbers in the run folder and CSV names.
- Preserve every previously accepted row if the run is stopped with Ctrl+C.

The application does **not** change the references saved in the ILM or edit the
replacement-channel configuration saved in the OSX-150.

From `Tools > Red Light Test...`, the operator can open a separate pre-test
window for checking a switch with a VFL. Opening the menu item does not connect
to the switch. Click `Start Red Light Test` to connect and select channel 1;
then use the channel number, Up/Down keys, Previous/Next buttons, or a typed
channel number to route the switch. The dialog reports the physical port
returned by the switch and disconnects when stopped or closed. It does not
measure IL, create run files, or affect COC data.

From `Tools > Live IL Reading...`, the operator can connect only to the
ILM/OP815 and read the current insertion loss at 1310 nm and 1550 nm. It uses
editable reference powers initialized from Hardware test setup, supports
repeated reads, and never connects to the switch or saves run data. `Start Live
Updates` automatically refreshes both values without saving data and changes to
`Stop Live Updates` while active.

## Folder contents

| File or folder | Purpose |
| --- | --- |
| `ILMReadLoss.py` | Main application: prompts, calculations, retesting, and CSV output |
| `ilm_app.py` | Light Workbench PyQt5 desktop application for saved CSV runs, loss-limit analysis, and hardware control |
| `run_data.py` | CSV loader and configurable over-limit analysis model |
| `run_persistence.py` | Atomic CSV/JSON run persistence and retest attempt history |
| `coc_export.py` | XLSX COC template copying, cell mapping, serial lookup, and export |
| `ilm_app.spec` | PyInstaller one-folder build definition for the desktop application |
| `build_windows.ps1` | Repeatable 32-bit Windows build command |
| `requirements-win32.txt` | Pinned 32-bit application and packaging dependencies |
| `op815_driver.py` | Documented 32-bit DLL wrapper for the ILM/OP815 |
| `power_meter.py` | Application adapter for the OP815 driver plus a simulated meter for testing |
| `osx150_driver.py` | Documented PyVISA/SCPI driver for the OSX-150 |
| `red_light_test.py` | Separate VFL pre-test dialog for manually routing switch channels |
| `live_il_reading.py` | Meter-only live IL reading dialog with no switch control or run persistence |
| `app_info.py` | Single source for the Light Workbench name, version, tagline, and About text |
| `OP815M.dll` | Vendor library used to communicate with the ILM |
| `Templates/OSX-100 Single Mode COC Template 1.xlsx` | XLSX COC template bundled with the desktop application |
| `assets/Lulu - CandC.png` | Compact header logo bundled with the desktop application |
| `README_INSTALL.txt` | Light Workbench ZIP deployment, prerequisite, and quick-start instructions |
| `Check Dependencies.cmd` | Optional launcher for the bundled dependency and connection report |
| `IL-Reads/` | Automatically generated measurement-run folders; desktop runs use `ILM-Run_YYMMDD_HHMMSS_[main board serial]-[switch serial]` with missing serials omitted, and the CSV uses the same base name as its folder |
| `tests/` | Hardware-free automated tests for the application and data models |

The vendor `OP815M.dll` is not modified by this project. `power_meter.py`
keeps the measurement workflow dependent on a small Python interface: the
real `SantecPowerMeter` delegates to the existing `OP815` wrapper, while
`SimulatedPowerMeter` supplies deterministic readings for tests and future UI
development without connected equipment.

The Light Workbench desktop application can be started with:

```powershell
py -3.11-32 ilm_app.py
```

Use `Help > About` to view the current release version, a
summary of supported capabilities, and copyable project information. The
current Light Workbench release is version **1.6.2**.

Use `Tools > Dark Mode` to switch between the light and dark application
themes. The preference is saved for the next launch; the red operator-action
accent remains the same in both themes.

It can open an existing CSV, display both wavelength values, show recorded
metadata, highlight channels over the configurable loss limit, and summarize
1310 nm, 1550 nm, and dual-wavelength exceedances. A file can also be opened
directly from PowerShell:

```powershell
py -3.11-32 ilm_app.py path\to\output.csv
```

When the same-named JSON file is beside the selected CSV, the viewer also restores the saved
warning limit and displays the number of retest attempts recorded for that run.

Select one or more completed rows in the results table and choose `Retest
Selected`. The latest accepted value replaces that channel in the CSV and
table, while the JSON attempt history retains the earlier value.

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

The same panel includes a guarded `Start Real Hardware` path. It runs the
existing OP815 DLL and OSX-150 VISA calls in a background worker, asks the
operator to move the cable before each reading, and provides a stop control
that releases both instruments. Hardware-run results are currently displayed
and saved incrementally to the same CSV/JSON pair, including results accepted
before a stop or hardware error.

The 1310 nm and 1550 nm reference powers are configurable in the desktop
setup panel. A real full-pass run queries the OSX-150 for its configured
logical channel count instead of relying on the simulation channel setting.

Before starting real hardware, the setup panel supports a full configured
pass, one channel, or specific channels and inclusive ranges. It also captures
the main-board serial, switch serial, and operating band in the run metadata.
For initial hardware validation, use the one-channel or short-range modes.

The setup panel only shows the selector needed by the chosen channel mode:
single-channel mode shows `Channel`, specific-channel mode shows
`Channels/ranges`, and full-pass mode hides both selectors.

Full configured pass also has an optional `Choose channel order manually`
checkbox for scattered one-off setups. When enabled, the application asks for
the next channel before each measurement. Previously accepted channels may be
entered again; the newest accepted reading replaces that channel's current
row while the JSON attempt history retains the earlier value. After every
configured channel has been covered once, the operator can retest another
channel or finish the pass. The checkbox is off by default, so the normal
ordered full pass is unchanged.

## Replacement analysis for switches with extra physical ports

Some 48-channel switches contain extra physical ports, such as ports 49 and
50, while the finished switch is still designed to use only 48 channels. After
a full pass, open `Analyze Replacements` in the analysis panel and enter the
designed channel count. Rows beyond that count are treated as measured extras.
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

The logical channel, measured physical port, both losses, and accepted reading
history are preserved in `run.json`. Replacement recommendations and the
post-replacement designated-spare selections are also written to the CSV
metadata, so they remain available when the run is opened on another computer.
The program does not change the OSX-150 replacement configuration; the
recommendations are an analysis for the operator to act on physically.

## COC workbook export

The desktop application can write a partial or complete run to a copied XLSX
COC template. The export is offered after a hardware run completes, is stopped,
or fails after producing a run, and is also available from the controls and
`File` menu. Channels without accepted readings remain blank, and readings
above the warning limit are still written.

The current template's `OSX Template` sheet receives the values in its split
table: channels 1-45 use rows 11-55 and channels 46-48 use rows 67-69. The
1310 nm values go in column D and 1550 nm values go in column E. The Part
Number is written to merged `B4:C4` through `B4`, the Main Board serial to
merged `D4:E4` through `D4`, and the current date to `F4`. Other template
values, formatting, formulas, and print settings are preserved.

The first output is named `COC OSX-150 <Main Board serial>.xlsx` and is saved
in the run folder. Existing files receive a numeric suffix instead of being
overwritten. The original template is never modified. The COC export uses
`openpyxl`, so Microsoft Excel is not required on the target computer.
The template's embedded graphics are preserved in each exported workbook.

The Hardware test setup includes a Part number field and a lookup button. The
default lookup folder is
`U:\Product Log\Units-COCs-Param Files\OSX-150`. For a Main Board serial such
as `17688`, the lookup finds a directory beginning with
`SN17688_` and uses the remainder of that directory name as the part number.
The lookup folder can be changed from `File > Part Number Lookup Folder...`,
and the part number can always be entered manually.
The Part number field is also an editable drop-down containing the current
standard OSX-150 part numbers. Operating band is selected from `O band` or
`C band`.

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

Keep these files together in the same folder:

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

## Running a test

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
6. Enter the ILM's current 1310 nm and 1550 nm reference powers in dBm.
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

At a reference prompt, pressing Enter without typing a number uses the default
shown in square brackets. Entering the actual references for the current setup
is recommended.

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

### `No Santec OSX-150 was detected over USB VISA`

- Confirm that the switch is powered on and connected through USB.
- Close or disconnect Santec Terminal so it releases the VISA session.
- Confirm that PyVISA and a compatible VISA implementation are installed.
- Verify that Santec Terminal can still identify the switch when used by itself.

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

New user workflows should normally be added to `ILMReadLoss.py`. Raw ILM DLL
calls belong in `op815_driver.py`, and raw OSX-150 VISA/SCPI commands belong in
`osx150_driver.py`. Keeping those responsibilities separate makes it easier to
add standardized switch metadata and other output files later without mixing
device protocol details into the application workflow.

Metadata collection, automatic swap tracking, and `metadata_table_rows()` are
separate from `write_combined_csv()`. If metadata is moved to a dedicated CSV
later, the metadata structure can remain unchanged; only the final writer will
need to be adjusted.
