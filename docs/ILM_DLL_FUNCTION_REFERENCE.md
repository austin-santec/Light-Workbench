# OP815M.dll Function Reference and Usage Rules

## Purpose

This document records the functions documented in
`C:\Users\Austin\Documents\OPL-SDK\OP831MDLL.html`, the functions exported by
the installed `OP815M.dll`, and the rules for using them in Light Workbench.
It is intentionally explicit about commands that must not be added to normal
production measurements.

The installed DLL is a 32-bit Windows DLL. The application must continue to
use a 32-bit Python/runtime for this driver.

## Current production path

These functions are already used by `op815_driver.py` and are approved for the
existing production workflow:

| DLL function | Current use |
| --- | --- |
| `GetUSBDeviceCount` | Enumerate compatible USB devices. |
| `GetUSBDeviceDescription` | Identify the USB device as `OP815`. |
| `GetUSBSerialNumber` | Read the ILM serial number. |
| `OpenUSBDevice` | Open the selected USB device. |
| `OpenDriver` | Initialize the DLL driver. |
| `RemoteMode` | Enter and leave remote mode. |
| `OperationMode` | Existing startup command; its OP831-specific meaning requires vendor clarification before changing it. |
| `SetWavelength` | Select the OPM calibration wavelength (1310/1550 nm for SM or 850/1300 nm for MM). It does not select or prove the physical laser wavelength. |
| `GetWavelength` | Read back the selected OPM wavelength before reading power. It does not verify the emitted physical source wavelength. |
| `SourceON` | Turn the selected physical source on or off. |
| `ReadPower` | Read absolute optical power in dBm. |
| `CloseDriver` | Release the initialized driver and USB session. This export exists in the installed DLL even though it is not listed in the supplied HTML function index. |

Production measurements must continue to use the application’s own reference
snapshot and insertion-loss calculation:

```text
insertion loss (dB) = reference power (dBm) - measured power (dBm)
```

The DLL’s internal relative-loss/reference functions must not replace this
calculation.

The physical source is selected separately with `SourceON(source_id, state)`.
Its nominal wavelength comes from the adapter-declared source-capability
profile. The current OP815 profile defines source 0 as 1310 nm and source 1 as
1550 nm. Because the DLL does not expose a dependable source table,
`GetWavelength`, `GetModuleID`, and the OPM wavelength index must never be used
to infer a source's emitted wavelength.

## Approved future diagnostic candidates

These functions are exported and can be considered for a non-recording ILM
diagnostics panel or support log. They must use separate wrappers because not
all functions share the normal `1 = success` return convention.

| DLL function | Observed result or documented purpose | Rule |
| --- | --- | --- |
| `GetDLLRev` | Returned `104`. | Safe read-only support metadata. |
| `GetDLLStatus` | Returned `1` after initialization and `0` before initialization during testing. | Safe status diagnostic; document the state-dependent return values. |
| `GetFWRevision` | Returned `202` after `OpenDriver`; caused an access violation before initialization. | Only call after successful driver initialization and guard failures. |
| `GetModuleID` | Returned status `1` and ID `14`. The HTML maps `14` to `OP930`. | Diagnostic-only until Santec explains the OP815/OP930 discrepancy. Never use it alone for model selection. |
| `GetActiveChannel` | Returned status `1` and channel `1`. | Diagnostic-only; this is an internal OPM channel, not the external OSX logical channel. |
| `GetTemperature` | Returned status `1` and `76.257 °C` during testing. | Diagnostic-only until the sensor meaning and expected range are confirmed. Do not create pass/fail limits from it yet. |
| `GetUSBStatus` | Returned `0` with `haveError = False`. | Useful after communication failures; use its documented status convention separately from normal DLL calls. |
| `ReadAnalog` | Returns raw ADC, gain, and measurement-mode values. | Candidate for engineering diagnostics only; interpretation needs validation. |

Adding any of these functions should not change normal wavelength order, source
settling, reference calculation, run persistence, or COC behavior.

## Explicitly prohibited in normal production measurements

The following functions are documented or exported but must not be used in the
normal Light Workbench measurement path:

| DLL function | Why it is prohibited |
| --- | --- |
| `ReferencePower` | Creates an internal DLL reference instead of using the application’s recorded reference snapshot. |
| `SetReference` | Switches the instrument into internal relative/dB reference mode. |
| `ReadLoss` | Reads DLL-calculated loss using the DLL’s internal reference, bypassing the application’s transparent math and metadata. |
| `SetAbsolute` | Changes the instrument measurement mode and can interfere with the application’s controlled measurement state. |
| `SetAutoRange` | Changes autorange/range-hold behavior and therefore changes measurement conditions. |
| `SetGain` | Changes detector gain and is only valid with autorange disabled; it requires a separately validated measurement procedure. |
| `SetSourcePower` | Changes laser output power and invalidates the established reference/measurement conditions. |
| `NextWavelength` | Changes wavelength selection without the application explicitly requesting and validating a target wavelength. |
| `SetActiveChannel` | Changes an internal OPM channel and must not be confused with OSX logical-channel routing. |
| `SelectModule` | Changes the selected internal module and could redirect later DLL calls. |
| `Backlight` | Only changes the front-panel display and is unrelated to measurement. |
| `GetChannelBuffer` / `ReadChannelBuffer` | Described for OP930 multi-channel buffering, not the current ILM measurement path. |
| `GetBidirectionalReference` | OP831-specific internal bidirectional reference operation. |
| `ReadABPower` / `ReadBAPower` | OP831-specific bidirectional power readings, not the current ILM-100 path. |

These functions may only be used in a separately approved engineering tool or
hardware-validation test with explicit documentation of the state changes.

## Functions unavailable in the installed DLL

The supplied HTML documents these functions, but the installed DLL did not
export them under the names expected by the current wrapper:

- `GetModuleNumber`
- `GetNumSources`
- `GetSourceTable`

Do not bind or call them unless a replacement DLL is supplied and its exports
are independently verified. The current driver therefore keeps the known
source mapping explicit rather than trying to discover it from these functions.

The HTML also contains OP925 functions such as `OP925_ReadCWRL`; those are not
part of the current OP815/ILM production path.

## Verified hardware observations

The controlled test against the connected device reported:

```text
USB description: OP815
USB serial: 00016582
DLL revision: 104
DLL status after initialization: 1
Firmware revision: 202
Module ID: 14
Active internal channel: 1
Temperature: 76.257 °C
Current wavelength: 1550 nm
Wavelength index/count: 5/7
USB error status: 0 / no error
Driver closed cleanly: yes
```

The USB description and module ID do not agree with the HTML’s model mapping:
the USB description says `OP815`, while module ID `14` is documented as
`OP930`. This is retained as a diagnostic observation only. It must not change
automatic device selection until the vendor clarifies what `GetModuleID`
represents for this ILM.

## Rules for future changes

1. Read this document before binding a new DLL export.
2. Keep vendor calls inside `op815_driver.py`; do not call `ctypes` from the UI,
   domain, or workflow layers.
3. Treat every function’s initialization and return convention independently.
4. Keep diagnostic reads non-recording unless a separate requirement explicitly
   adds persistence.
5. Do not use internal DLL references or relative-loss results for production
   IL calculations.
6. Do not use module ID, active channel, or temperature as model-selection or
   pass/fail criteria without vendor clarification and hardware validation.
7. Add hardware-free tests for bindings and parsing, then perform a controlled
   hardware test that leaves both sources off and closes the driver cleanly.
