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

The current `SantecPowerMeter` and `OSX150` classes are adapters for these
capabilities. The application should not import `OP815`, `pyvisa`, `ctypes`,
or vendor-specific SCPI details in its domain or UI code.

`hardware/factory.py` is the composition boundary for selecting concrete
adapters. UI workflows request capabilities from the factory instead of
constructing vendor adapters independently.

`hardware/simulated.py` provides contract-compatible laser and switch
implementations for hardware-free workflow tests. They are not used by the
production hardware path unless explicitly selected in a factory.

`hardware/session.py` owns lifecycle for a composed meter, optional laser, and
optional switch. It connects in dependency order and closes already-connected
devices if a later connection fails.

The normal measurement worker uses this session boundary for its meter and
switch. Live IL and Red Light retain their separate controller-owned sessions
because those tools intentionally operate independently.

Live IL and Red Light now use the same session boundary for their individual
meter-only and switch-only lifecycles. A failed connection is registered for
cleanup before the connect call completes, covering vendor sessions that open
partially before reporting an error.

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

- The controller or worker that opens an instrument owns its lifetime.
- Connect and close must be paired even when a measurement fails.
- Partial startup must also be cleaned up: if USB opens but driver or remote
  initialization fails, release the vendor session before reporting the error.
- A hardware object must not be shared between simultaneous workflows unless a
  dedicated session manager explicitly serializes access.
- Live IL, red light, and switch-test workflows should not silently reuse an
  active session owned by another workflow.
- Device discovery should be separate from an active measurement session.
- The Live IL and Red Light dialogs must communicate with their hardware
  through application controllers; dialogs should not call vendor hardware
  methods directly.

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
