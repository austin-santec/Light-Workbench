# Hardware Architecture

## Hardware ports

Application workflows should depend on capability contracts in
`hardware/interfaces.py`:

- `PowerMeter`: connects, reads both wavelengths, reads reference values, and
  closes.
- `LaserSource`: connects, selects wavelength, enables/disables output, and
  closes.
- `OpticalSwitch`: connects, reports configured logical channels, selects a
  logical channel, and closes.

The current `SantecPowerMeter` and `SantecOpticalSwitch` classes are adapters for these
capabilities. The application should not import `OP815`, `pyvisa`, `ctypes`,
or vendor-specific SCPI details in its domain or UI code.

`hardware/factory.py` is the composition boundary for selecting concrete
adapters. UI workflows request capabilities from the factory instead of
constructing vendor adapters independently. Its default factories import the
OP815 and Santec OSX-100/OSX-150 implementations only when a real hardware object is created,
so importing the contracts and running hardware-free tests does not require an
active vendor session.

`hardware/power_meter.py` contains the integrated Santec OP815 adapter and the
hardware-free simulated meter. The vendor DLL wrapper remains in
`op815_driver.py`. `hardware/optical_switch.py` contains the Santec switch
identity parser and capability-profile registry. The verified OSX-100 and
OSX-150 profiles currently use the same PyVISA/SCPI commands, but remain
separate so a future model-specific command change is isolated. The legacy
`SANTEC,OSX,<serial>,<firmware>` identity is accepted as OSX-100 only when all
identity fields are present and is shown as a legacy-generic warning. Explicit
unsupported or malformed identities are rejected. The root `power_meter.py`
and `osx150_driver.py` modules are compatibility facades.

The Santec optical-switch adapter tries addresses in a bounded order: the optional manual
address, a separately stored last-known automatic address, then resources from
`list_resources("USB?*::INSTR")` filtered to Santec's USB VID/PID. This avoids
the backend failure seen with broad, all-interface VISA enumeration. Automatic
success updates only the last-known setting; it never overwrites the operator's
manual address.

For each candidate, the adapter opens a fresh session and probes only `*IDN?`
with LF, then CRLF if needed. A supported identity selects the session ending.
It then queries `CFG:SWT:END?` and requires a positive configured channel count
before the switch is considered ready. `CLOSe?` is not used during connection;
it is only used to verify the physical port after a `CLOSe <channel>` routing
command. A zero count, SCPI error, timeout, or nonnumeric response retains the
known model, serial, firmware, address, ending, command, and response in
transient diagnostics while safely closing the session and blocking routing.
These details are hardware status only and do not alter run CSV/JSON data or
measurement timing.

After a supported switch reaches the Connected state, the main window may use
the serial already present in `DeviceInfo` as the setup's Main board serial and
request a background part-number lookup. This is a presentation/application
convenience: it sends no additional SCPI command, does not alter the separate
operator-entered Switch serial, does not affect hardware readiness when lookup
fails, and cannot overwrite loaded or active run metadata.

`domain/models.py` owns the vendor-neutral `DeviceInfo`, `DeviceCategory`, and
`ConnectionState` models. `hardware/device_identity.py` provides a fallback
for older adapters and test doubles. The normal run worker reports Connecting,
Connected, Disconnected, and Error transitions through the run controller;
`ui/hardware_status.py` displays them with model and serial information. These
are transient status values and are not added to the existing run file formats.

`hardware/simulated.py` provides contract-compatible laser and switch
implementations for hardware-free workflow tests. They are not used by the
production hardware path unless explicitly selected in a factory.

`application/hardware_connection.py` owns persistent device instances and
serializes all native calls on a single long-lived executor thread. Workflow
workers receive capability proxies rather than raw devices. Their existing
`hardware/session.py` lifecycle acquires and releases exclusive leases through
those proxies; closing a workflow releases access but leaves the real device
connected. Explicit header disconnect actions and application shutdown close
the manager-owned devices.

Normal runs require available measurement hardware and a switch. Main-window
reference calculation requires measurement hardware only. Live IL, Red Light,
and Power Diagnostics may connect only their required capability and update the
same global status. Partial connection success is retained, and a lease conflict
is rejected in the application layer rather than relying on disabled buttons.

`PowerMeasurementDiagnosticsDialog` is also an independent, non-recording
workflow. `application/power_diagnostics_controller.py` owns the OP815/meter
worker and uses a meter-only session, while the dialog can optionally create a
separate `RedLightTestController` for switch routing. Neither connection is
opened when the dialog is launched. The operator explicitly connects each
device, and the switch is only changed after a logical channel is selected and
Set Channel is pressed. This keeps raw-power investigation useful with a
switch, without coupling the meter read to switch ownership or normal run
state.

The dialog records each complete sample in memory with its acquisition method:
manual readings support cable-reseat repeatability analysis, while monitoring
readings support undisturbed-connection stability analysis. Both analyses use
the same complete two-wavelength measurement result and do not change hardware
timing or create persistence files.

The diagnostics dialog also supports an optional in-memory OP815 hardware trace.
When enabled for export, the trace records vendor command outcomes, status
codes, wavelength/source state, raw power, references, timing, errors, and the
logical/physical channel context. Each complete two-wavelength history sample
and its trace events share a measurement ID. The trace is exported only when
the operator selects `Include Hardware Trace`: CSV creates a companion file
beside the history export, while JSON adds a `hardware_trace` collection.
The trace session also includes detected meter and switch manufacturer, model,
serial, raw identification string, and VISA resource address when available.
Trace callback failures are swallowed by the adapter so optional diagnostics
cannot change measurement behavior.

The OP815 adapter supports independent trace subscribers. The always-on
support logger receives production and tool hardware events while Power
Diagnostics can simultaneously attach its in-memory recorder; removing the
tool callback cannot remove the global subscriber. The switch adapter emits
the corresponding discovery, LF/CRLF identity, channel-count, route, response,
timing, failure, and cleanup events. Subscribers are failure-isolated and no
trace path may add hardware calls or change settling delays.

For each diagnostic wavelength, the OP815 sequence remains SetWavelength,
wavelength settling, source enable, source settling, and ReadPower. The
diagnostic path now inserts a final GetWavelength immediately after source
settling and immediately before ReadPower. That verification records a
`verified_before_read` trace event with the requested/actual wavelength,
source state, and result. A wavelength mismatch or unsupported wavelength
blocks ReadPower and therefore creates no diagnostic history row. If the
actual wavelength is correct but the DLL's index/count convention differs from
the assumed zero-based mapping, the trace records a warning with the raw
values instead of treating the sample as a wrong-wavelength measurement.
Normal production runs use the same actual-wavelength safety check but do not
fail solely on an index/count convention difference. The production
wavelength order and settling constants are unchanged.

Live IL and Red Light now use the same session boundary for their individual
meter-only and switch-only lifecycles. Their dialogs receive injected factory
callables, defaulting to `HardwareFactory` without binding vendor classes in
the UI constructor. A failed connection is registered for cleanup before the
connect call completes, covering vendor sessions that open partially before
reporting an error.

## Integrated ILM versus separate OPM and laser

The current ILM combines a source and meter from the application's point of
view. A future setup may use:

```text
LaserSource → optical path/switch → PowerMeter
```

That setup should be represented by composition rather than a new copy of the
entire run workflow. A measurement service can receive a power meter, an
optional laser source, and an optional optical switch.

An integrated ILM adapter may implement the power-meter contract while hiding
its internal source control. A separate-laser setup can expose those controls
explicitly without changing the insertion-loss calculation or saved result
model.

## Hardware ownership

- The persistent connection manager owns every real instrument it opens.
- Workflow workers own leases, not native sessions.
- Connect and close must be paired even when a measurement fails.
- Partial startup must also be cleaned up: if USB opens but driver or remote
  initialization fails, release the vendor session before reporting the error.
- Native calls are serialized on the manager's hardware executor thread.
- Live IL, Red Light, Power Diagnostics, reference calculation, and switch-test
  workflows reuse available connections only through exclusive managed leases.
- Device discovery should be separate from an active measurement session.
- The Live IL and Red Light dialogs must communicate with their hardware
  through application controllers; dialogs should not call vendor hardware
  methods directly.

## Shutdown and close behavior

Hardware-using dialogs must release their leases before closing. The main
window must complete persistent instrument cleanup
before releasing worker references or accepting a close event. Controllers
disconnect queued UI commands after the worker thread has stopped and do not
schedule worker deletion from the main thread after the worker event loop has
closed. If a hardware shutdown times out, the owning window remains open and
reports that cleanup is still in progress so an active vendor session cannot
be abandoned silently. Informational dialogs without hardware resources may
continue to use normal Qt `accept()`/`reject()` behavior.

Automatic Live IL and Live Write Mode use a shared 250 ms software pacing
delay after each complete two-wavelength measurement. This delay is separate
from wavelength, source, and source-off settling times; it controls when the
next measurement request begins and does not change instrument timing.

Reference and insertion-loss safety checks are performed after both wavelength
measurements complete. A calculated reference below -40.0 dBm is treated as a
dark or disconnected setup and cannot authorize production testing. A negative
insertion-loss value after four-decimal rounding remains visible for
troubleshooting but cannot be written. These checks do not change laser order,
settling delays, wavelength order, reference math, or native hardware commands.

## Measurement pipeline

The intended future pipeline is:

```text
select channel
    ↓
configure laser/source if needed
    ↓
wait for instrument settling
    ↓
read absolute power
    ↓
apply reference correction
    ↓
calculate insertion loss
    ↓
return a typed MeasurementResult
```

The pipeline should be testable with simulated meter, laser, and switch
objects. Tests should never require the vendor DLL or VISA installation.

## Adding a new instrument

1. Identify the capability it provides.
2. Implement or extend the appropriate interface.
3. Keep vendor protocol code in a dedicated adapter module.
4. Add a simulated/fake implementation for tests.
5. Add adapter contract tests.
6. Register the adapter through configuration or a factory rather than adding
   vendor conditionals throughout the UI.
