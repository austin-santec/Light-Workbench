"""User-facing Light Workbench identity and release information."""

APP_NAME = "Light Workbench"
APP_VERSION = "1.14.0"
APP_TAGLINE = "Make light work, light work! Ha!"
APP_DESCRIPTION = (
    "Optical testing and measurement software for insertion-loss testing, "
    "switch control, analysis, and production documentation."
)


def about_text():
    """Return the copyable project information shown in About."""
    return "\n".join(
        (
            APP_NAME,
            "Version: %s" % APP_VERSION,
            "",
            APP_DESCRIPTION,
            "",
            "Current capabilities:",
            "- 1310 nm and 1550 nm insertion-loss measurements",
            "- Santec OSX-100/OSX-150 channel control and Red Light Test",
            "- Over-limit filtering and replacement analysis",
            "- XLSX COC export and saved run review",
            "- Headerless raw-data clipboard export for Excel",
            "- Live IL readings, reference calculation, and repeatability testing",
            "- Non-recording raw-power diagnostics with optional switch routing",
            "- Repeatability and stability variation analysis",
            "- CSV and JSON export for diagnostic reading history",
            "- Optional OP815 hardware trace export for diagnostics",
            "- Live Write Mode for continuous reading before acceptance",
            "- Connected hardware status and extensible device profiles",
            "- Always-on engineering support logs and local support bundles",
            "- Numbered runs grouped by unit with shared replacements and spares",
            "",
            "Designed for Windows optical production testing.",
        )
    )
