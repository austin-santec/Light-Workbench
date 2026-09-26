"""Compatibility facade for Light Workbench dependency diagnostics."""

from tools.dependency_check import (
    FAIL,
    OPTO_TEST_DRIVER_URL,
    PASS,
    WARN,
    DependencyReport,
    DependencyResult,
    check_bundled_file,
    check_lookup_folder,
    check_op815,
    check_osx150,
    check_run_folder,
    check_santec_terminal,
    check_visa,
    collect_dependency_report,
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
