"""Run guided insertion-loss tests with an ILM and OSX-150 switch.

Run this script with 32-bit Python:

    py -3.11-32 ILMReadLoss.py

The hardware-specific code lives in op815_driver.py and osx150_driver.py. This
file handles prompts, insertion-loss calculations, retesting, and CSV output.
"""

import csv
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from pyvisa.errors import VisaIOError

# Hardware-specific communication is kept in driver and adapter modules. This
# file can therefore focus on prompts, calculations, retesting, and CSV output.
from op815_driver import WAVELENGTHS_NM
from osx150_driver import MIN_SWITCH_CHANNEL, OSX150
from power_meter import SantecPowerMeter


# Pressing Enter at a reference prompt uses these convenient defaults.  The
# values saved inside the ILM are never changed by this application.
DEFAULT_REFERENCE_POWER_DBM = {
    1310: 0.72,
    1550: 0.28,
}

# TODO: Query or prompt for the operating band when that information becomes
# available. It is intentionally hardcoded to O band for the current workflow.
HARDCODED_OPERATING_BAND = "O band"


@dataclass
class TestMetadata:
    """Identification plus replacement ports detected during one test run."""

    main_board_serial: str
    switch_serial: str
    operating_band: str = HARDCODED_OPERATING_BAND
    swapped_ports: dict = field(default_factory=dict)


def prompt_workflow():
    """Ask which logical switch channels should be measured."""
    print("\nChoose a measurement workflow:")
    print("  1. Full pass through all configured test channels")
    print("  2. Read one channel")
    print("  3. Read specific channels and ranges")

    while True:
        value = input("Enter 1, 2, or 3: ").strip()

        if value == "1":
            return "full_pass"

        if value == "2":
            return "single_channel"

        if value == "3":
            return "custom_channels"

        print("Please enter 1, 2, or 3.")


def prompt_single_channel(channel_count):
    """Return one valid logical channel selected by the user."""
    while True:
        channel_value = input(
            "Test channel to read (%d-%d): "
            % (MIN_SWITCH_CHANNEL, channel_count)
        ).strip()
        try:
            channel = int(channel_value)
        except ValueError:
            print("Please enter a numeric channel.")
            continue

        if MIN_SWITCH_CHANNEL <= channel <= channel_count:
            return channel

        print(
            "Test channel must be from %d through %d."
            % (MIN_SWITCH_CHANNEL, channel_count)
        )


def parse_channel_selection(value, channel_count):
    """Expand comma-separated channels and ranges into an ordered list.

    For example, ``1, 9, 10-15, 27`` becomes channels 1, 9, 10 through 15,
    and 27. Duplicate channels are removed while their first-entered order is
    preserved.
    """
    if not value.strip():
        raise ValueError("Enter at least one channel or range.")

    channels = []
    seen_channels = set()

    for entry in value.split(","):
        entry = entry.strip()
        if not entry:
            raise ValueError("Empty entries are not allowed between commas.")

        if "-" in entry:
            endpoints = entry.split("-")
            if len(endpoints) != 2:
                raise ValueError("Invalid range %r. Use a format such as 10-15." % entry)

            try:
                first_channel = int(endpoints[0].strip())
                last_channel = int(endpoints[1].strip())
            except ValueError:
                raise ValueError(
                    "Invalid range %r. Both ends must be numeric." % entry
                )

            if first_channel > last_channel:
                raise ValueError(
                    "Invalid range %r. The starting channel must come first."
                    % entry
                )

            # Python stops before the second range argument, so adding one
            # makes the operator's ending channel inclusive.
            entry_channels = range(first_channel, last_channel + 1)
        else:
            try:
                entry_channels = (int(entry),)
            except ValueError:
                raise ValueError(
                    "Invalid channel %r. Enter a number or numeric range." % entry
                )

        for channel in entry_channels:
            if not MIN_SWITCH_CHANNEL <= channel <= channel_count:
                raise ValueError(
                    "Channel %d is outside the configured range %d-%d."
                    % (channel, MIN_SWITCH_CHANNEL, channel_count)
                )

            if channel not in seen_channels:
                channels.append(channel)
                seen_channels.add(channel)

    return channels


def prompt_channel_selection(channel_count):
    """Prompt until a valid mixture of specific channels and ranges is entered."""
    while True:
        value = input(
            "Test channels/ranges (for example, 1, 9, 10-15, 27): "
        )
        try:
            return parse_channel_selection(value, channel_count)
        except ValueError as error:
            print(error)


def prompt_retest_selection(tested_channels):
    """Return tested channels selected for an optional final retest pass."""
    tested_channel_set = set(tested_channels)

    while True:
        value = input(
            "Enter channels to retest, or press Enter to finish: "
        )
        if not value.strip():
            return []

        try:
            channels = parse_channel_selection(
                value,
                max(tested_channels),
            )
        except ValueError as error:
            print(error)
            continue

        untested_channels = [
            channel for channel in channels if channel not in tested_channel_set
        ]
        if untested_channels:
            print(
                "Only completed channels can be retested: %s."
                % ", ".join(str(channel) for channel in untested_channels)
            )
            continue

        return channels


def prompt_test_metadata():
    """Collect the optional serial numbers that identify this test run."""
    print("\nEnter metadata for this OSX-150 test.")

    while True:
        main_board_serial = input(
            "Main board serial number (press Enter to skip): "
        ).strip()
        if not main_board_serial or re.search(r"[A-Za-z0-9]", main_board_serial):
            break
        print("The main board serial must contain at least one letter or number.")

    while True:
        switch_serial = input(
            "Last 5 digits of the switch serial number "
            "(press Enter to skip): "
        ).strip()
        if not switch_serial or (
            len(switch_serial) == 5
            and switch_serial.isascii()
            and switch_serial.isdigit()
        ):
            break
        print("Enter exactly 5 digits, or press Enter to skip.")

    return TestMetadata(
        main_board_serial=main_board_serial,
        switch_serial=switch_serial,
    )


def prompt_reference_powers():
    """Collect the absolute reference powers used to calculate IL."""
    references = {}

    print(
        "\nEnter the absolute reference powers shown on the ILM front panel."
    )
    for wavelength_nm in WAVELENGTHS_NM:
        default_reference = DEFAULT_REFERENCE_POWER_DBM[wavelength_nm]

        while True:
            value = input(
                "%d nm reference power in dBm [%.4f]: "
                % (wavelength_nm, default_reference)
            ).strip()

            if not value:
                references[wavelength_nm] = default_reference
                break

            try:
                references[wavelength_nm] = float(value)
                break
            except ValueError:
                print("Please enter a numeric reference power.")

    return references


def filename_safe_serial(serial):
    """Convert an entered serial into a safe Windows path component.

    The original operator entry is preserved in the metadata table. Only the
    copy used in a folder or filename is normalized.
    """
    safe_serial = re.sub(r"[^A-Za-z0-9_-]+", "-", serial.strip())
    return safe_serial.strip("-_")


def serial_filename_prefix(metadata):
    """Build the optional switch/main-board prefix in the requested order."""
    serials = (
        filename_safe_serial(metadata.switch_serial),
        filename_safe_serial(metadata.main_board_serial),
    )
    return "-".join(serial for serial in serials if serial)


def create_csv_path(metadata, now=None, output_root=None):
    """Create the metadata-based run folder and return its CSV path.

    A numeric suffix is added to the folder only if another run with the same
    serials was started during the same minute. This prevents overwriting data.
    """
    if now is None:
        now = datetime.now()
    timestamp = now.strftime("%m-%d_%H-%M")
    serial_prefix = serial_filename_prefix(metadata)

    if serial_prefix:
        folder_name = "%s-IL_%s" % (serial_prefix, timestamp)
        csv_name = "%s-output_%s.csv" % (serial_prefix, timestamp)
    else:
        folder_name = "IL-Read_%s" % timestamp
        csv_name = "output_%s.csv" % timestamp

    if output_root is None:
        output_root = Path(__file__).resolve().parent / "IL-Reads"
    else:
        output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    test_directory = output_root / folder_name
    duplicate_number = 2
    while test_directory.exists():
        test_directory = output_root / (
            "%s-%d" % (folder_name, duplicate_number)
        )
        duplicate_number += 1

    test_directory.mkdir()
    return test_directory / csv_name


def format_swapped_ports(swapped_ports):
    """Format detected logical-to-physical mappings for the metadata table."""
    if not swapped_ports:
        return "None detected in tested channels"

    return ", ".join(
        "%d->%d" % (test_channel, physical_port)
        for test_channel, physical_port in sorted(swapped_ports.items())
    )


def metadata_table_rows(metadata):
    """Return metadata independently of its current CSV destination.

    Keeping this function separate from the combined CSV writer makes it easy
    to place these rows in a dedicated metadata CSV in a future revision.
    """
    return [
        ["Main board serial", metadata.main_board_serial],
        ["Switch serial (last 5 digits)", metadata.switch_serial],
        ["Swapped ports", format_swapped_ports(metadata.swapped_ports)],
        ["Operating band", metadata.operating_band],
    ]


def write_combined_csv(csv_path, measurement_rows, metadata):
    """Write measurement columns A-C and metadata columns E-F.

    The complete file is first written beside the destination and then swapped
    into place. This keeps previously accepted data intact if writing fails.
    """
    measurement_table = [
        ["channel", "1310 IL", "1550 IL"],
        *measurement_rows,
    ]
    metadata_table = [
        ["Metadata", "Value"],
        *metadata_table_rows(metadata),
    ]
    row_count = max(len(measurement_table), len(metadata_table))
    temporary_path = csv_path.with_suffix(csv_path.suffix + ".tmp")

    try:
        with temporary_path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.writer(csv_file)
            for row_index in range(row_count):
                measurement_row = (
                    measurement_table[row_index]
                    if row_index < len(measurement_table)
                    else ["", "", ""]
                )
                metadata_row = (
                    metadata_table[row_index]
                    if row_index < len(metadata_table)
                    else ["", ""]
                )

                # One blank column (D) visually separates the two tables when
                # the CSV is opened in Excel.
                writer.writerow(measurement_row + [""] + metadata_row)

            csv_file.flush()
            os.fsync(csv_file.fileno())

        os.replace(temporary_path, csv_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def calculate_insertion_losses(measurements, reference_powers):
    """Calculate IL in dB as reference dBm minus measured power dBm."""
    return {
        wavelength_nm: (
            reference_powers[wavelength_nm] - measurements[wavelength_nm]
        )
        for wavelength_nm in WAVELENGTHS_NM
    }


def read_channel(
    instrument,
    switch,
    channel,
    routed_physical_port,
    wait_for_cable=True,
):
    """Wait for cable placement, verify routing, and read both wavelengths."""
    if wait_for_cable:
        input(
            "Move the cable to channel %d, then press Enter when ready: "
            % channel
        )

    # CLOSe? reports the physical port. A different number is normal when the
    # switch maps this logical test channel to a replacement port.
    actual_channel = switch.current_channel()
    if actual_channel != routed_physical_port:
        print(
            "Warning: test channel %d initially routed to physical port %d, "
            "but the OSX-150 now reports port %d. Continuing with port %d."
            % (
                channel,
                routed_physical_port,
                actual_channel,
                actual_channel,
            )
        )

    measurements = instrument.measure_both_wavelengths()
    return measurements, actual_channel


def print_switch_position(test_channel, reported_channel):
    """Explain whether a test channel is routed through a replacement port."""
    if reported_channel == test_channel:
        print("OSX-150 switched to channel %d." % test_channel)
    else:
        print(
            "OSX-150 test channel %d is using replacement physical port %d."
            % (test_channel, reported_channel)
        )


def record_detected_port_swap(metadata, test_channel, reported_channel):
    """Store a replacement-port mapping reported while routing a channel.

    Returns True only when the metadata changed, allowing the caller to avoid
    rewriting the CSV when the logical and physical channel numbers match.
    """
    if reported_channel == test_channel:
        # Remove an earlier mapping if the switch now reports the original
        # physical port for this logical test channel.
        return metadata.swapped_ports.pop(test_channel, None) is not None

    previous_port = metadata.swapped_ports.get(test_channel)
    metadata.swapped_ports[test_channel] = reported_channel
    return previous_port != reported_channel


def prompt_reading_decision(channel):
    """Return ``save`` or ``retest`` after the operator reviews a reading."""
    while True:
        choice = input(
            "Press Enter to save and continue, or enter - to "
            "discard and retest channel %d: " % channel
        ).strip()

        if choice == "":
            return "save"
        if choice == "-":
            return "retest"

        print("Please press Enter or enter -.")


def retest_completed_channels(
    instrument,
    switch,
    channels,
    reference_powers,
    metadata,
    csv_path,
    accepted_rows,
):
    """Retest selected completed channels and replace their saved rows."""
    for channel in channels:
        print("\nRetesting channel %d." % channel)
        reported_channel = switch.set_channel(channel)
        print_switch_position(channel, reported_channel)
        if record_detected_port_swap(
            metadata,
            channel,
            reported_channel,
        ):
            write_combined_csv(csv_path, accepted_rows, metadata)

        wait_for_cable = True
        while True:
            measurements, actual_physical_port = read_channel(
                instrument,
                switch,
                channel,
                reported_channel,
                wait_for_cable,
            )
            if record_detected_port_swap(
                metadata,
                channel,
                actual_physical_port,
            ):
                write_combined_csv(csv_path, accepted_rows, metadata)
            reported_channel = actual_physical_port
            wait_for_cable = False
            losses = calculate_insertion_losses(
                measurements,
                reference_powers,
            )

            print("\nRetest readings for channel %d:" % channel)
            print("  1310 IL: %.4f dB" % losses[1310])
            print("  1550 IL: %.4f dB" % losses[1550])

            if prompt_reading_decision(channel) == "retest":
                print("Discarding that reading and retesting channel %d." % channel)
                continue

            replacement_row = [
                channel,
                "%.4f" % losses[1310],
                "%.4f" % losses[1550],
            ]
            row_index = next(
                index
                for index, row in enumerate(accepted_rows)
                if row[0] == channel
            )
            accepted_rows[row_index] = replacement_row
            write_combined_csv(csv_path, accepted_rows, metadata)
            print("Channel %d retest saved to the CSV." % channel)
            break


def run_measurement_workflow(
    instrument,
    switch,
    channels,
    reference_powers,
    metadata,
    csv_path,
):
    """Measure requested channels and save only readings the user accepts."""
    accepted_rows = []

    # Create the CSV and metadata table before the first measurement. Every
    # accepted result rewrites this small table so partial runs remain usable.
    write_combined_csv(csv_path, accepted_rows, metadata)

    # Route the first channel before asking the user to move the cable.
    first_channel = channels[0]
    reported_channel = switch.set_channel(first_channel)
    print_switch_position(first_channel, reported_channel)
    if record_detected_port_swap(
        metadata,
        first_channel,
        reported_channel,
    ):
        # Save the detected mapping immediately, even before its measurement.
        write_combined_csv(csv_path, accepted_rows, metadata)

    for channel_index, channel in enumerate(channels):
        wait_for_cable = True

        # Retesting repeats this loop without changing switch channels.
        # A rejected reading is never added to the output table.
        while True:
            measurements, actual_physical_port = read_channel(
                instrument,
                switch,
                channel,
                reported_channel,
                wait_for_cable,
            )
            if record_detected_port_swap(
                metadata,
                channel,
                actual_physical_port,
            ):
                write_combined_csv(csv_path, accepted_rows, metadata)
            reported_channel = actual_physical_port
            wait_for_cable = False
            losses = calculate_insertion_losses(
                measurements,
                reference_powers,
            )

            print("\nReadings for channel %d:" % channel)
            print("  1310 IL: %.4f dB" % losses[1310])
            print("  1550 IL: %.4f dB" % losses[1550])

            if prompt_reading_decision(channel) == "retest":
                print(
                    "Discarding that reading and retesting channel %d."
                    % channel
                )
                continue

            accepted_rows.append([
                channel,
                "%.4f" % losses[1310],
                "%.4f" % losses[1550],
            ])
            write_combined_csv(csv_path, accepted_rows, metadata)
            print("Channel %d readings saved to the CSV." % channel)
            break

        has_next_channel = channel_index + 1 < len(channels)
        if has_next_channel:
            next_channel = channels[channel_index + 1]
            print("Done reading, moving to next channel")
            reported_channel = switch.set_channel(next_channel)
            print_switch_position(next_channel, reported_channel)
            if record_detected_port_swap(
                metadata,
                next_channel,
                reported_channel,
            ):
                write_combined_csv(csv_path, accepted_rows, metadata)
        else:
            print("Done reading all selected channels.")

    retest_channels = prompt_retest_selection(channels)
    if retest_channels:
        retest_completed_channels(
            instrument,
            switch,
            retest_channels,
            reference_powers,
            metadata,
            csv_path,
            accepted_rows,
        )
    else:
        print("No additional retests selected.")


def main():
    """Collect settings, connect both devices, run the test, and clean up."""
    workflow = prompt_workflow()

    instrument = None
    switch = OSX150()
    csv_path = None

    try:
        # The switch must be connected before a single channel or range can be
        # validated against its configured logical channel count.
        switch.connect()
        print("Connected to %s" % switch.identity)
        print("Current OSX-150 channel: %d" % switch.current_channel())
        channel_count = switch.configured_channel_count()
        print("OSX-150 configured test-channel count: %d" % channel_count)

        if workflow == "full_pass":
            channels = list(range(MIN_SWITCH_CHANNEL, channel_count + 1))
        elif workflow == "single_channel":
            channels = [prompt_single_channel(channel_count)]
        else:
            channels = prompt_channel_selection(channel_count)

        # Metadata is intentionally collected after channel selection so every
        # workflow presents prompts in the same predictable order.
        metadata = prompt_test_metadata()
        reference_powers = prompt_reference_powers()

        instrument = SantecPowerMeter()
        instrument.connect()
        print(
            "Connected to %s - USB serial %s"
            % (instrument.description, instrument.usb_serial)
        )
        print("The ILM's saved references will not be changed.")
        print(
            "Insertion loss will be calculated as reference power minus "
            "measured absolute power."
        )

        csv_path = create_csv_path(metadata)
        print("CSV output:\n%s" % csv_path)
        run_measurement_workflow(
            instrument,
            switch,
            channels,
            reference_powers,
            metadata,
            csv_path,
        )
        print("\nMeasurement data saved to:\n%s" % csv_path)

    except KeyboardInterrupt:
        print("\nStopping. Any completed readings remain saved in the CSV.")
        if csv_path is not None:
            print("Partial measurement data:\n%s" % csv_path)
    except (RuntimeError, OSError, VisaIOError) as error:
        print("\nMeasurement stopped: %s" % error)
        if csv_path is not None:
            print("Any completed readings remain saved in:\n%s" % csv_path)
    finally:
        # Always release both devices, even after Ctrl+C or a hardware error.
        switch.close()
        print("OSX-150 connection closed.")
        if instrument is not None:
            instrument.close()
        print("ILM connection closed.")


if __name__ == "__main__":
    main()
