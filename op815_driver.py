"""Python wrapper for the 32-bit OP815M.dll used by the ILM-100.

This module contains only ILM hardware communication.  Keeping the DLL details
here means the application code does not need to work directly with ctypes,
Windows handles, source IDs, or DLL return codes.

OP815M.dll is a 32-bit Windows library, so the Python process that imports and
constructs :class:`OP815` must also be 32-bit.
"""

import ctypes
import struct
import time
from pathlib import Path


# The two physical laser sources installed in this ILM.  The DLL numbers the
# sources from zero even though users identify them by wavelength.
WAVELENGTHS_NM = (1310, 1550)
SOURCE_ID_BY_WAVELENGTH = {
    1310: 0,
    1550: 1,
}

# Short pauses let the wavelength calibration and physical source stabilize
# before a power sample is taken.  These values were verified against the ILM
# front-panel readings during development.
WAVELENGTH_SETTLING_TIME_SECONDS = 0.1
SOURCE_SETTLING_TIME_SECONDS = 0.5
SOURCE_OFF_SETTLING_TIME_SECONDS = 0.1

# Reference calibration is intentionally slower than production measurements.
# The ILM is freshly connected for this operation, so its wavelength selection,
# source output, and auto-ranging circuitry get additional time to settle
# before the single authoritative sample is taken.
REFERENCE_WAVELENGTH_SETTLING_TIME_SECONDS = 2.0
REFERENCE_SOURCE_SETTLING_TIME_SECONDS = 3.0
REFERENCE_SOURCE_OFF_SETTLING_TIME_SECONDS = 0.5


def find_op815_dll(dll_path=None):
    """Return the OP815 DLL path or raise a clear error if it is missing.

    Normally OP815M.dll should be kept beside this driver.  The current working
    directory is also checked so this module remains useful if it is imported
    by another program.
    """
    if dll_path is not None:
        candidates = (Path(dll_path),)
    else:
        candidates = (
            Path(__file__).resolve().with_name("OP815M.dll"),
            Path.cwd() / "OP815M.dll",
        )

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()

    raise FileNotFoundError(
        "OP815M.dll was not found. Keep it beside op815_driver.py or pass "
        "its path to OP815."
    )


class OP815:
    """Manage one ILM/OP815 connection through the vendor's Windows DLL.

    Public methods expose meaningful operations such as ``connect`` and
    ``measure_both_wavelengths``.  All ctypes buffers and raw DLL functions are
    deliberately kept inside this class.
    """

    def __init__(self, dll_path=None):
        # A 64-bit Python process cannot load this 32-bit DLL.  Check before
        # attempting to load it so the user gets an actionable error message.
        if struct.calcsize("P") * 8 != 32:
            raise RuntimeError(
                "OP815M.dll is 32-bit. Run this script with: "
                "py -3.11-32 ILMReadLoss.py"
            )

        resolved_dll_path = find_op815_dll(dll_path)
        self.dll = ctypes.WinDLL(str(resolved_dll_path))
        self.driver_open = False
        self.remote_enabled = False
        self.description = None
        self.usb_serial = None
        self._bind_functions()

    def _bind(self, name, argument_types):
        """Declare a DLL function's arguments and integer return status."""
        function = getattr(self.dll, name)
        function.argtypes = argument_types
        function.restype = ctypes.c_int
        return function

    def _bind_functions(self):
        """Bind every vendor function used by this application.

        Declaring signatures is important: it tells ctypes how to safely
        convert Python values and where the DLL will write returned values.
        """
        int_pointer = ctypes.POINTER(ctypes.c_int)
        double_pointer = ctypes.POINTER(ctypes.c_double)
        uint32_pointer = ctypes.POINTER(ctypes.c_uint32)
        wide_string_pointer = ctypes.POINTER(ctypes.c_wchar_p)

        self.get_device_count = self._bind(
            "GetUSBDeviceCount",
            [int_pointer],
        )
        self.get_device_description = self._bind(
            "GetUSBDeviceDescription",
            [ctypes.c_int, wide_string_pointer],
        )
        self.get_usb_serial = self._bind(
            "GetUSBSerialNumber",
            [ctypes.c_int, wide_string_pointer],
        )
        self.open_usb_device = self._bind(
            "OpenUSBDevice",
            [ctypes.c_int, uint32_pointer],
        )
        self.open_driver = self._bind(
            "OpenDriver",
            [ctypes.c_uint32],
        )
        self.remote_mode = self._bind(
            "RemoteMode",
            [ctypes.c_int],
        )
        self.operation_mode = self._bind(
            "OperationMode",
            [ctypes.c_int],
        )
        self.get_wavelength = self._bind(
            "GetWavelength",
            [int_pointer, int_pointer, int_pointer],
        )
        self.set_wavelength = self._bind(
            "SetWavelength",
            [ctypes.c_int],
        )
        self.source_on = self._bind(
            "SourceON",
            [ctypes.c_int, ctypes.c_ubyte],
        )
        self.read_power = self._bind(
            "ReadPower",
            [double_pointer],
        )
        self.close_driver = self._bind("CloseDriver", [])

    @staticmethod
    def _require_success(operation, status):
        """Convert a failed DLL status into a useful Python exception."""
        if status != 1:
            raise RuntimeError("%s failed with status %d" % (operation, status))

    def _get_string(self, function, device_index, operation):
        """Read a text property that the DLL returns through a pointer."""
        value = ctypes.c_wchar_p()
        status = function(device_index, ctypes.byref(value))
        self._require_success(operation, status)
        return value.value or "Unknown"

    def find_devices(self):
        """Return all connected USB devices identified by the DLL as OP815."""
        device_count = ctypes.c_int()
        status = self.get_device_count(ctypes.byref(device_count))
        self._require_success("GetUSBDeviceCount", status)

        devices = []
        for device_index in range(device_count.value):
            description = self._get_string(
                self.get_device_description,
                device_index,
                "GetUSBDeviceDescription",
            )
            serial = self._get_string(
                self.get_usb_serial,
                device_index,
                "GetUSBSerialNumber",
            )

            if description.upper() == "OP815":
                devices.append((device_index, description, serial))

        return devices

    def select_device(self):
        """Select the only ILM automatically or prompt when several exist."""
        devices = self.find_devices()
        if not devices:
            raise RuntimeError("No OP815/ILM was detected over USB.")

        if len(devices) == 1:
            return devices[0]

        print("Detected multiple OP815 devices:")
        for selection, device in enumerate(devices):
            print(
                "  [%d] %s - USB serial %s"
                % (selection, device[1], device[2])
            )

        while True:
            value = input("Select ILM index: ").strip()
            try:
                selection = int(value)
            except ValueError:
                print("Please enter a numeric index.")
                continue

            if 0 <= selection < len(devices):
                return devices[selection]

            print(
                "Please select an index from 0 through %d."
                % (len(devices) - 1)
            )

    def connect(self):
        """Open the selected ILM, enable remote mode, and leave lasers off."""
        device_index, self.description, self.usb_serial = self.select_device()
        handle = ctypes.c_uint32()

        status = self.open_usb_device(device_index, ctypes.byref(handle))
        self._require_success("OpenUSBDevice", status)

        status = self.open_driver(handle.value)
        self._require_success("OpenDriver", status)
        self.driver_open = True

        status = self.remote_mode(1)
        self._require_success("RemoteMode(1)", status)
        self.remote_enabled = True

        # This legacy DLL build does not return a dependable status from
        # OperationMode.  The physical sources are therefore controlled
        # explicitly for every measurement below.
        self.operation_mode(1)
        time.sleep(0.5)
        self.turn_all_sources_off()
        time.sleep(SOURCE_OFF_SETTLING_TIME_SECONDS)

    def set_source_state(self, source_id, enabled):
        """Turn one zero-based physical laser source on or off."""
        state = 1 if enabled else 0
        status = self.source_on(source_id, state)
        self._require_success(
            "SourceON(%d, %d)" % (source_id, state),
            status,
        )

    def turn_all_sources_off(self):
        """Put both laser sources into a known, safe off state."""
        for source_id in sorted(set(SOURCE_ID_BY_WAVELENGTH.values())):
            self.set_source_state(source_id, False)

    def current_wavelength(self):
        """Return the detector's currently selected wavelength in nanometers."""
        wavelength = ctypes.c_int()
        wavelength_index = ctypes.c_int()
        wavelength_count = ctypes.c_int()
        status = self.get_wavelength(
            ctypes.byref(wavelength),
            ctypes.byref(wavelength_index),
            ctypes.byref(wavelength_count),
        )
        self._require_success("GetWavelength", status)
        return wavelength.value

    def measure_wavelength(
        self,
        wavelength_nm,
        wavelength_settling_seconds=WAVELENGTH_SETTLING_TIME_SECONDS,
        source_settling_seconds=SOURCE_SETTLING_TIME_SECONDS,
        source_off_settling_seconds=SOURCE_OFF_SETTLING_TIME_SECONDS,
    ):
        """Enable one laser, take one absolute-power reading, then disable it."""
        if wavelength_nm not in SOURCE_ID_BY_WAVELENGTH:
            raise ValueError("No source is configured for %d nm." % wavelength_nm)

        source_id = SOURCE_ID_BY_WAVELENGTH[wavelength_nm]

        # Only one laser should be active.  This matches the ILM front panel's
        # rapid 1310-on/read/off then 1550-on/read/off sequence.
        for other_source_id in set(SOURCE_ID_BY_WAVELENGTH.values()):
            if other_source_id != source_id:
                self.set_source_state(other_source_id, False)

        status = self.set_wavelength(wavelength_nm)
        self._require_success("SetWavelength(%d)" % wavelength_nm, status)
        time.sleep(wavelength_settling_seconds)

        actual_wavelength = self.current_wavelength()
        if actual_wavelength != wavelength_nm:
            raise RuntimeError(
                "Requested %d nm, but the ILM selected %d nm."
                % (wavelength_nm, actual_wavelength)
            )

        self.set_source_state(source_id, True)
        try:
            time.sleep(source_settling_seconds)
            power = ctypes.c_double()
            self._require_success(
                "ReadPower",
                self.read_power(ctypes.byref(power)),
            )
        finally:
            # A source is always turned off, including when ReadPower fails.
            self.set_source_state(source_id, False)
            time.sleep(source_off_settling_seconds)

        return power.value

    def measure_both_wavelengths(
        self,
        wavelength_settling_seconds=WAVELENGTH_SETTLING_TIME_SECONDS,
        source_settling_seconds=SOURCE_SETTLING_TIME_SECONDS,
        source_off_settling_seconds=SOURCE_OFF_SETTLING_TIME_SECONDS,
    ):
        """Return absolute dBm readings keyed by 1310 and 1550 wavelength."""
        original_wavelength = self.current_wavelength()
        measurements = {}

        try:
            self.turn_all_sources_off()
            time.sleep(source_off_settling_seconds)
            for wavelength_nm in WAVELENGTHS_NM:
                measurements[wavelength_nm] = self.measure_wavelength(
                    wavelength_nm,
                    wavelength_settling_seconds,
                    source_settling_seconds,
                    source_off_settling_seconds,
                )
        finally:
            # Preserve the user's original display wavelength and never leave
            # a laser enabled after a completed or interrupted measurement.
            self.turn_all_sources_off()
            self.set_wavelength(original_wavelength)

        return measurements

    def measure_reference_wavelengths(self):
        """Take one deliberately stabilized absolute sample per wavelength."""
        return self.measure_both_wavelengths(
            wavelength_settling_seconds=REFERENCE_WAVELENGTH_SETTLING_TIME_SECONDS,
            source_settling_seconds=REFERENCE_SOURCE_SETTLING_TIME_SECONDS,
            source_off_settling_seconds=REFERENCE_SOURCE_OFF_SETTLING_TIME_SECONDS,
        )

    def close(self):
        """Turn sources off, leave remote mode, and release the DLL driver."""
        cleanup_error = None
        if self.driver_open:
            try:
                for source_id in sorted(set(SOURCE_ID_BY_WAVELENGTH.values())):
                    self.source_on(source_id, 0)
            except Exception as error:
                cleanup_error = error
        try:
            if self.remote_enabled:
                self.remote_mode(0)
        except Exception as error:
            if cleanup_error is None:
                cleanup_error = error
        finally:
            self.remote_enabled = False

        if self.driver_open:
            try:
                self.close_driver()
            except Exception as error:
                if cleanup_error is None:
                    cleanup_error = error
            finally:
                self.driver_open = False

        if cleanup_error is not None:
            raise cleanup_error
