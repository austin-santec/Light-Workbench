LIGHT WORKBENCH - INSTALLATION AND QUICK START
===============================================

This ZIP contains the Light Workbench desktop application. Its current
insertion-loss workflow uses an ILM/OP815 power meter and a Santec OSX-150
optical switch, with room for additional optical meters, lasers, and switch
workflows in the future.

IMPORTANT: Keep the complete LightWorkbench folder together. Do not copy or
run LightWorkbench.exe by itself. The _internal folder contains required
application files.


1. WHAT IS REQUIRED
-------------------

The application files already include Python, PyQt5, PyVISA, openpyxl,
OP815M.dll, the COC template, and the company logo. These do not need to be
installed separately. Microsoft Excel is also not required for COC export.

The target computer needs:

  * Windows 10 or Windows 11.
  * The ILM/OP815 USB driver.
  * A compatible 32-bit VISA runtime, such as NI-VISA with 32-bit support.
  * The ILM and OSX-150 connected by USB and powered on for hardware tests.

The application is 32-bit. It normally runs on both 32-bit and 64-bit Windows,
but a 64-bit computer must still have the 32-bit VISA support installed.

Santec Terminal may already have installed VISA, but it does not necessarily
install the ILM/OP815 driver. Check with your equipment administrator or the
instrument vendor if either driver is missing.

Approved OptoTest OP-USB driver download:

  https://santec-inst.files.svdcdn.com/production/USB-Driver-for-Santec-CA-Optotest.zip?dm=1768835182

Download the ZIP, extract it, and run the included driver installer using the
approved company process. Administrator permission may be required. Follow
the driver's own instructions if it asks for the ILM to be connected during
installation.


2. INSTALL THE APPLICATION
--------------------------

  1. Extract the ZIP to a permanent location, for example:

       C:\Light Workbench\

  2. Open the extracted LightWorkbench folder.
  3. Create a desktop shortcut to LightWorkbench.exe if desired.
  4. Do not run the program from inside the ZIP or move the EXE away from
     the _internal folder.

The ZIP also includes Check Dependencies.cmd. Run it on a new computer for a
quick diagnostic report before attempting a hardware test. The checker does
not change run data or COC data, move switch channels, or turn on lasers.

Open ILM_READING_GUIDE.html in any web browser for the operator's ILM testing
instructions. It is a self-contained guide and does not require internet access.

No Python installation is needed.

Use Help > About inside the application to view the current
version and project capabilities. The current release is Light Workbench 1.10.0.


3. VERIFY VISA
--------------

If NI Measurement & Automation Explorer (NI MAX) is installed:

  1. Open NI MAX.
  2. Look under My System > Software for NI-VISA.
  3. With the OSX-150 powered and connected, check Devices and Interfaces.
  4. Confirm that the switch can be identified.

If VISA is missing, install the approved 32-bit VISA runtime before running a
hardware test. Do not copy random visa32.dll files into the application
folder; install VISA through the approved vendor installer.


4. FIRST HARDWARE TEST
----------------------

  1. Close Santec Terminal completely before starting the tester. It must not
     be holding the OSX-150 VISA connection. Check Task Manager if necessary.
  2. Connect and power on the ILM/OP815 and OSX-150.
  3. Start LightWorkbench.exe.
  4. Select Single channel and choose one channel for the first test.
  5. Enter the serial numbers. References start at 0.00 dBm until you click
     Calculate Reference, which reads both wavelengths from the ILM/OP815 and
     applies the measured offsets automatically; the values remain manually
     editable.
 6. Enter the numbered Run number for this test. Use 1 for the first test on
    the unit, 2 for the next test, and so on. Click Start Run and confirm the
    hardware warning.

OPTIONAL RED-LIGHT PRE-TEST

Before a measurement pass, use Tools > Red Light Test... to open the VFL
channel-check window. Opening the menu does not connect to the switch. Click
Start Red Light Test when the VFL and switch are ready, then select channels
with the number box, Up/Down keys, or Previous/Next buttons. This check does
not record IL readings or create run/COC data.
  7. Follow the prompt to move the cable, then click Read IL.
  8. Review the 1310 nm and 1550 nm readings. Click Read IL again if another
     sample is needed, or click Write IL to accept the reading.

Accepted results are saved automatically under:

Documents\ILM-Reads\Unit-[main board serial]\Run-[run number]-[switch serial]\

If the main board serial is unavailable, the part number is used for the unit
folder. The switch serial is stored with the individual run because a failed
switch can be replaced while the unit remains the same. Each numbered run
contains same-named CSV and JSON files. The unit folder also contains
unit.json, which stores completed port replacements and designated spare ports
shared by all runs for that unit.
Older timestamped runs containing output.csv and run.json remain supported.

When continuing a loaded run, the part number, Main Board serial, and Switch
serial are restored into Hardware test setup. If they are corrected, the
program asks whether to update the saved metadata and whether to rename the run
folder, CSV/JSON files, and existing COC workbook. The original run timestamp
is preserved and existing files are never overwritten.

Real switch runs also record start time, stop time, continuation times, session
count, and accumulated switch-test duration in the CSV metadata. Live IL and
Red Light Test are not included in this timing.

OPTIONAL POWER MEASUREMENT DIAGNOSTICS

Use Tools > Power Measurement Diagnostics... when you need to investigate the
raw ILM/OP815 power values without creating or changing a run. Connect the
meter, optionally connect the switch and route a logical channel, then click
Read Measured Power. The window shows the measured dBm values, the selected
references, and the exact calculation `reference - measured = insertion loss`.
Calculate Reference and Apply to Main Setup are available when a new baseline
is needed. The diagnostic history remains in memory only and is never written
to CSV, JSON, COC, or another output file.

Use Analyze Repeatability for manually triggered readings taken after
disconnecting and reconnecting the cable. Use Analyze Stability for readings
collected by Start Monitoring while the cable remains connected. The two
analyses are kept separate and show average, minimum, maximum, range, sample
standard deviation, and first-to-last change for 1310 nm and 1550 nm. Results
remain in memory only.

If the diagnostic history needs to be retained, click Export History... and
choose CSV or JSON. The export then offers Include Hardware Trace. If selected,
CSV also creates a companion `<history-stem>-hardware-trace.csv`; JSON adds a
`hardware_trace` object containing the in-memory OP815 command trace. This is
an explicit diagnostic export and does not modify the active switch-test run
or its CSV/JSON files.

Variation Analysis appears to the right of the history table. Use Hide
Variation Analysis or Show Variation Analysis to collapse or restore it; the
splitter between the table and panel can be resized.
When an analysis is displayed, Copy Analysis copies its formatted summary to
the clipboard for use in notes or another document.


5. SAVED RUNS AND COC EXPORT
----------------------------

Open Existing CSV starts in Documents\ILM-Reads. Select a run's same-named CSV to
review its written readings, warning-limit analysis, and replacement analysis.
For the new unit layout, enter the unit identity and run number in Hardware test
setup and click Load Run to load a numbered run directly.
File > Data Output Folder opens the same Documents\ILM-Reads folder containing
all saved run folders.
The table's Compare with selector can add read-only 1310 nm and 1550 nm columns
from another numbered run for the same unit. Choose No comparison to hide those
columns again. Comparison data is display-only and does not change analysis or
saved run files.

The Write COC... option can write partial or complete readings to a copied XLSX
COC template. Excel does not need to be installed. For automatic part-number
lookup, the computer must have access to:

  U:\Product Log\Units-COCs-Param Files\OSX-150

If that network path is unavailable, enter the part number manually.
The two graphics included in the COC template are preserved in exported files.
Replacement recommendations are calculated for the selected run but are not
stored as permanent results. Completed replacements and designated spare ports
are stored in the shared unit.json record.
Hardware test setup also provides an editable standard-part-number list and an
O band/C band operating-band selector.


6. COMMON PROBLEMS
------------------

"No OP815/ILM was detected over USB"
  Confirm the ILM is powered on, connected, and its Windows USB driver is
  installed. The approved OptoTest OP-USB driver is available at the download
  link in section 1. Close other software using the ILM.

"No Santec OSX-150 was detected over USB VISA"
  Confirm the switch is powered on and connected. Close Santec Terminal and
  verify that the compatible 32-bit VISA runtime is installed.

"Resource busy" or "device not found"
  Another program is using the switch. Fully close Santec Terminal and any
  other VISA instrument software, then restart the tester.

The program will not start
  Confirm LightWorkbench.exe and the _internal folder are still together and
  that the ZIP was fully extracted. If Windows shows a security warning, use
  the approved company process to allow this trusted application.


7. SAFE DEPLOYMENT CHECKLIST
----------------------------

  [ ] The complete LightWorkbench folder was extracted.
  [ ] ILM/OP815 USB driver is installed.
  [ ] 32-bit VISA runtime is installed.
  [ ] Santec Terminal is closed before testing.
  [ ] ILM and OSX-150 are powered and connected.
  [ ] Documents\ILM-Reads is writable.
  [ ] The U: lookup path is available if automatic part lookup is needed.
