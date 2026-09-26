"""Non-destructive prerequisite and connection checks for the desktop app."""

import csv
import platform
import socket
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"
OPTO_TEST_DRIVER_URL = (
    "https://santec-inst.files.svdcdn.com/production/"
    "USB-Driver-for-Santec-CA-Optotest.zip?dm=1768835182"
)


@dataclass(frozen=True)
class DependencyResult:
    """One check result shown to the operator."""

    name: str
    status: str
    details: str
    remedy: str = ""


@dataclass(frozen=True)
class DependencyReport:
    """A diagnostic report kept separate from measurement/run metadata."""

    checked_at: str
    computer_name: str
    results: tuple[DependencyResult, ...]

    @property
    def overall_status(self):
        if any(result.status == FAIL for result in self.results):
            return "ACTION REQUIRED"
        if any(result.status == WARN for result in self.results):
            return "READY WITH WARNINGS"
        return "READY"

    def as_text(self):
        """Return a copyable plain-text version of the diagnostic report."""
        lines = [
            "Light Workbench dependency report",
            "Checked: %s" % self.checked_at,
            "Computer: %s" % self.computer_name,
            "Overall status: %s" % self.overall_status,
            "",
        ]
        for result in self.results:
            lines.append("[%s] %s: %s" % (result.status, result.name, result.details))
            if result.remedy:
                lines.append("      Action: %s" % result.remedy)
        return "\n".join(lines)


def _runtime_root():
    """Locate bundled files in source and PyInstaller one-folder runs."""
    if getattr(sys, "_MEIPASS", None):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def check_bundled_file(name, relative_path, runtime_root=None):
    path = (runtime_root or _runtime_root()) / relative_path
    if path.is_file():
        return DependencyResult(name, PASS, "Found %s." % path.name)
    return DependencyResult(
        name,
        FAIL,
        "Missing %s." % path,
        "Re-extract the complete LightWorkbench folder from the ZIP.",
    )


def check_visa(resource_manager_factory=None):
    """Load the VISA backend and list resources without changing hardware."""
    try:
        if resource_manager_factory is None:
            import pyvisa

            resource_manager_factory = pyvisa.ResourceManager
        resource_manager = resource_manager_factory()
        try:
            resources = tuple(resource_manager.list_resources())
        finally:
            resource_manager.close()
    except Exception as error:  # VISA backends expose several exception types.
        return DependencyResult(
            "VISA runtime",
            FAIL,
            "Could not load the VISA backend: %s" % error,
            "Install the approved 32-bit VISA runtime, such as NI-VISA.",
        )

    if resources:
        return DependencyResult(
            "VISA runtime",
            PASS,
            "Backend loaded; %d VISA resource(s) listed." % len(resources),
        )
    return DependencyResult(
        "VISA runtime",
        PASS,
        "Backend loaded; no VISA resources are currently listed.",
    )


def check_osx150(switch_factory=None):
    """Identify the OSX-150 using the same read-only connection path as runs."""
    switch = None
    try:
        if switch_factory is None:
            from hardware.optical_switch import OSX150

            switch_factory = OSX150
        switch = switch_factory()
        switch.connect()
        return DependencyResult(
            "OSX-150",
            PASS,
            "Detected %s at %s." % (switch.identity or "OSX-150", switch.address),
        )
    except Exception as error:
        return DependencyResult(
            "OSX-150",
            WARN,
            "No usable OSX-150 connection was found: %s" % error,
            "Power on and connect the switch, then close Santec Terminal before testing.",
        )
    finally:
        if switch is not None:
            switch.close()


def check_op815(meter_factory=None):
    """Load the OP815 DLL and enumerate ILM devices without opening a driver."""
    meter = None
    try:
        if meter_factory is None:
            from op815_driver import OP815

            meter_factory = OP815
        meter = meter_factory()
        devices = meter.find_devices()
    except FileNotFoundError as error:
        return DependencyResult(
            "ILM/OP815 driver",
            FAIL,
            str(error),
            "Install the approved OptoTest OP-USB driver from %s"
            % OPTO_TEST_DRIVER_URL,
        )
    except Exception as error:
        return DependencyResult(
            "ILM/OP815 driver",
            FAIL,
            "Could not load or query the OP815 driver: %s" % error,
            "Install the approved OptoTest OP-USB driver from %s"
            % OPTO_TEST_DRIVER_URL,
        )
    finally:
        if meter is not None:
            meter.close()

    if devices:
        return DependencyResult(
            "ILM/OP815 driver",
            PASS,
            "DLL loaded; %d OP815 device(s) detected." % len(devices),
        )
    return DependencyResult(
        "ILM/OP815 driver",
        WARN,
        "DLL loaded, but no OP815 device is currently connected.",
        "Connect and power on the ILM before starting a hardware run.",
    )


def check_santec_terminal(process_runner=None):
    """Warn if a process that appears to be Santec Terminal is running."""
    try:
        if process_runner is None:
            process_runner = subprocess.run
        completed = process_runner(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        process_names = [row[0] for row in csv.reader(completed.stdout.splitlines()) if row]
    except Exception as error:
        return DependencyResult(
            "Santec Terminal",
            WARN,
            "Could not inspect running processes: %s" % error,
            "Confirm Santec Terminal is fully closed before a hardware run.",
        )

    terminal_names = [
        name
        for name in process_names
        if "santec" in name.lower() and "terminal" in name.lower()
    ]
    if terminal_names:
        return DependencyResult(
            "Santec Terminal",
            WARN,
            "Appears to be running (%s)." % ", ".join(terminal_names),
            "Close Santec Terminal so it releases the OSX-150 VISA session.",
        )
    return DependencyResult("Santec Terminal", PASS, "No Santec Terminal process found.")


def check_run_folder(run_root=None):
    """Verify that the normal Documents run folder can be written."""
    if run_root is None:
        run_root = Path.home() / "Documents" / "ILM-Reads"
    run_root = Path(run_root)
    try:
        run_root.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            prefix=".dependency-check-",
            suffix=".tmp",
            dir=run_root,
            delete=True,
            encoding="utf-8",
        ) as temporary_file:
            temporary_file.write("ok")
    except OSError as error:
        return DependencyResult(
            "Run-folder write access",
            FAIL,
            "Cannot write to %s: %s" % (run_root, error),
            "Choose a writable Documents folder or update the user's permissions.",
        )
    return DependencyResult("Run-folder write access", PASS, "Can write to %s." % run_root)


def check_lookup_folder(lookup_root=None):
    """Check the optional network location used for automatic part lookup."""
    if lookup_root is None:
        from config.app_config import DEFAULT_PART_LOOKUP_ROOT

        lookup_root = DEFAULT_PART_LOOKUP_ROOT
    lookup_root = Path(lookup_root)
    if lookup_root.is_dir():
        return DependencyResult(
            "Part-number lookup path",
            PASS,
            "Available: %s." % lookup_root,
        )
    return DependencyResult(
        "Part-number lookup path",
        WARN,
        "Not available: %s." % lookup_root,
        "Map the U: drive if automatic lookup is needed; manual part entry still works.",
    )


def collect_dependency_report(
    runtime_root=None,
    run_root=None,
    lookup_root=None,
    resource_manager_factory=None,
    switch_factory=None,
    meter_factory=None,
    process_runner=None,
):
    """Run the complete non-destructive diagnostic suite."""
    results = [
        check_bundled_file("OP815M.dll", "OP815M.dll", runtime_root),
        check_bundled_file(
            "COC template",
            Path("Templates") / "OSX-100 Single Mode COC Template 1.xlsx",
            runtime_root,
        ),
        check_bundled_file(
            "Company logo",
            Path("assets") / "Lulu - CandC.png",
            runtime_root,
        ),
        check_santec_terminal(process_runner),
        check_run_folder(run_root),
        check_lookup_folder(lookup_root),
    ]
    visa_result = check_visa(resource_manager_factory)
    results.append(visa_result)
    if visa_result.status == FAIL:
        results.append(
            DependencyResult(
                "OSX-150",
                WARN,
                "Skipped because the VISA runtime is unavailable.",
            )
        )
    else:
        results.append(check_osx150(switch_factory))
    results.append(check_op815(meter_factory))
    return DependencyReport(
        checked_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        computer_name=socket.gethostname() or platform.node() or "Unknown",
        results=tuple(results),
    )


__all__ = [
    "FAIL",
    "OPTO_TEST_DRIVER_URL",
    "PASS",
    "WARN",
    "DependencyReport",
    "DependencyResult",
    "check_bundled_file",
    "check_lookup_folder",
    "check_op815",
    "check_osx150",
    "check_run_folder",
    "check_santec_terminal",
    "check_visa",
    "collect_dependency_report",
]
