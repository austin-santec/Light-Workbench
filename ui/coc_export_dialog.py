"""Qt presentation for selecting and validating COC source runs."""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from domain.coc_preparation import CocPreparationResult, CocSourceRun


class CocExportDialog(QDialog):
    """Collect explicit report scope and show its validation summary."""

    def __init__(
        self,
        run_options,
        prepare_callback,
        *,
        initial_channel_count: int = 1,
        current_run_path: str | Path | None = None,
        validation_blocked_callback=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Prepare COC")
        self.resize(650, 520)
        self.run_options = list(run_options)
        self.prepare_callback = prepare_callback
        self.validation_blocked_callback = validation_blocked_callback
        self.current_run_path = (
            Path(current_run_path).resolve() if current_run_path else None
        )
        self.preparation_result: CocPreparationResult | None = None

        layout = QVBoxLayout(self)
        explanation = QLabel(
            "Choose the front-panel channel count and the persisted runs that "
            "will supply the final COC readings."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        form = QFormLayout()
        self.channel_count_spin = QSpinBox()
        self.channel_count_spin.setRange(1, 48)
        self.channel_count_spin.setValue(max(1, min(48, int(initial_channel_count))))
        self.channel_count_spin.setToolTip(
            "Only logical channels 1 through this front-panel count are written."
        )
        form.addRow("Front panel channels:", self.channel_count_spin)

        self.base_run_combo = QComboBox()
        for option in self.run_options:
            self.base_run_combo.addItem(option.label, option.source)
        form.addRow("Base run:", self.base_run_combo)

        self.use_supplemental_checkbox = QCheckBox("Use replacement/retest run")
        form.addRow("", self.use_supplemental_checkbox)
        self.supplemental_run_combo = QComboBox()
        self.supplemental_run_combo.setEnabled(False)
        form.addRow("Replacement/retest run:", self.supplemental_run_combo)
        layout.addLayout(form)

        summary_label = QLabel("Preparation summary")
        summary_label.setObjectName("metric")
        layout.addWidget(summary_label)
        self.summary = QPlainTextEdit()
        self.summary.setReadOnly(True)
        self.summary.setMinimumHeight(260)
        layout.addWidget(self.summary, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        self.write_button = QPushButton("Validate and Write COC")
        self.write_button.clicked.connect(self._validate_and_accept)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.write_button)
        layout.addLayout(buttons)

        self._choose_defaults()
        self._rebuild_supplemental_options()
        self.channel_count_spin.valueChanged.connect(self.refresh_summary)
        self.base_run_combo.currentIndexChanged.connect(
            self._base_selection_changed
        )
        self.use_supplemental_checkbox.toggled.connect(
            self._supplemental_toggled
        )
        self.supplemental_run_combo.currentIndexChanged.connect(
            self.refresh_summary
        )
        self.refresh_summary()

    @property
    def base_run(self) -> CocSourceRun | None:
        return self.base_run_combo.currentData()

    @property
    def supplemental_run(self) -> CocSourceRun | None:
        if not self.use_supplemental_checkbox.isChecked():
            return None
        return self.supplemental_run_combo.currentData()

    def _choose_defaults(self):
        count = self.channel_count_spin.value()

        def coverage(option):
            channels = {
                record.channel
                for record in option.source.measurements
                if 1 <= record.channel <= count
            }
            try:
                result = self.prepare_callback(option.source, count, None)
                compatible = not result.validation_issues
            except (TypeError, ValueError):
                compatible = False
            return (int(compatible), len(channels), -option.source.run_number)

        if self.run_options:
            best = max(range(len(self.run_options)), key=lambda index: coverage(self.run_options[index]))
            self.base_run_combo.setCurrentIndex(best)

    def _rebuild_supplemental_options(self):
        previous = self.supplemental_run_combo.currentData()
        base = self.base_run
        self.supplemental_run_combo.blockSignals(True)
        self.supplemental_run_combo.clear()
        preferred_index = -1
        for option in self.run_options:
            if base is not None and option.source.run_number == base.run_number:
                continue
            index = self.supplemental_run_combo.count()
            self.supplemental_run_combo.addItem(option.label, option.source)
            if previous is not None and option.source.run_number == previous.run_number:
                preferred_index = index
            elif (
                self.current_run_path is not None
                and option.source.source_path.resolve() == self.current_run_path
            ):
                preferred_index = index
        if preferred_index >= 0:
            self.supplemental_run_combo.setCurrentIndex(preferred_index)
            self.use_supplemental_checkbox.setChecked(True)
        self.supplemental_run_combo.blockSignals(False)
        available = self.supplemental_run_combo.count() > 0
        self.use_supplemental_checkbox.setEnabled(available)
        if not available:
            self.use_supplemental_checkbox.setChecked(False)
        self.supplemental_run_combo.setEnabled(
            available and self.use_supplemental_checkbox.isChecked()
        )

    def _base_selection_changed(self, _index):
        self._rebuild_supplemental_options()
        self.refresh_summary()

    def _supplemental_toggled(self, checked):
        self.supplemental_run_combo.setEnabled(
            checked and self.supplemental_run_combo.count() > 0
        )
        self.refresh_summary()

    def refresh_summary(self, *_args):
        base = self.base_run
        if base is None:
            self.preparation_result = None
            self.summary.setPlainText("No persisted run with written readings is available.")
            self.write_button.setEnabled(False)
            return
        try:
            result = self.prepare_callback(
                base,
                self.channel_count_spin.value(),
                self.supplemental_run,
            )
        except (TypeError, ValueError) as error:
            self.preparation_result = None
            self.summary.setPlainText(str(error))
            self.write_button.setEnabled(False)
            return
        self.preparation_result = result
        self.summary.setPlainText(format_coc_summary(result))
        self.write_button.setEnabled(True)

    def _validate_and_accept(self):
        self.refresh_summary()
        result = self.preparation_result
        if result is None:
            return
        if not result.eligible:
            if self.validation_blocked_callback is not None:
                self.validation_blocked_callback(result)
            QMessageBox.warning(
                self,
                "COC cannot be written",
                format_coc_blocking_message(result),
            )
            return
        self.accept()


def format_coc_summary(result: CocPreparationResult) -> str:
    """Return a concise operator-readable preview of prepared report data."""
    lines = [
        "Required front-panel channels: %d" % result.front_panel_channel_count,
        "Completed channels available: %d" % len(result.channels),
        "Base run: Run %d" % result.base_run_number,
        "Replacement/retest run: %s"
        % (
            "Run %d" % result.supplemental_run_number
            if result.supplemental_run_number is not None
            else "Not used"
        ),
        "Template: %d-channel maximum" % result.template_capacity,
    ]
    if result.overridden_channels:
        lines.append("Supplemental overrides:")
        lines.extend(
            "  Channel %d = Run %d / Physical Port %d"
            % (
                channel.record.channel,
                channel.source_run_number,
                channel.physical_port,
            )
            for channel in result.overridden_channels
        )
    else:
        lines.append("Supplemental overrides: None")

    lines.append(
        "Missing channels: %s"
        % (", ".join(map(str, result.missing_channels)) or "None")
    )
    if result.failures:
        lines.append("Formal failures:")
        lines.extend(
            "  Channel %d, %d nm: %.4f dB (Run %d, Physical Port %d)"
            % (
                failure.channel,
                failure.wavelength_nm,
                failure.value_db,
                failure.source_run_number,
                failure.physical_port,
            )
            for failure in result.failures
        )
    else:
        lines.append("Formal failures: None")
    if result.invalid_readings or result.validation_issues:
        lines.append("Validation problems:")
        lines.extend(
            "  %s" % issue.message
            for issue in result.invalid_readings + result.validation_issues
        )
    else:
        lines.append("Validation problems: None")
    lines.append(
        "Optimization-review channels: %s"
        % (", ".join(map(str, result.optimization_channels)) or "None")
    )
    lines.append(
        "Available optimization recommendations: %d"
        % len(result.optimization_recommendations)
    )
    lines.append("")
    lines.append(
        "Ready to write COC."
        if result.eligible
        else "Resolve the items above before writing the COC."
    )
    return "\n".join(lines)


def format_coc_blocking_message(result: CocPreparationResult) -> str:
    """Return one complete validation message for a blocked export."""
    lines = ["The COC cannot be written until the following items are resolved:"]
    if result.missing_channels:
        lines.append(
            "Missing required channel(s): %s."
            % ", ".join(map(str, result.missing_channels))
        )
    lines.extend(
        "Channel %d from Run %d has %.4f dB at %d nm (Physical Port %d); "
        "the COC requires every value to be below 2.5000 dB."
        % (
            failure.channel,
            failure.source_run_number,
            failure.value_db,
            failure.wavelength_nm,
            failure.physical_port,
        )
        for failure in result.failures
    )
    lines.extend(issue.message for issue in result.invalid_readings)
    lines.extend(issue.message for issue in result.validation_issues)
    return "\n\n".join(lines)


def format_optimization_warning(result: CocPreparationResult) -> str:
    """Return the advisory text shown before an eligible optimized export."""
    lines = [
        "This COC passes the formal limit, but additional optimization is available.",
        "",
    ]
    for item in result.optimization_recommendations:
        lines.append(
            "Channel %(logical_channel)d / Physical Port %(current_physical_port)d: "
            "%(current_loss_1310_db).4f dB at 1310 nm, "
            "%(current_loss_1550_db).4f dB at 1550 nm"
            % item
        )
        lines.append(
            "  Suggested Physical Port %(candidate_physical_port)d: "
            "%(candidate_loss_1310_db).4f / %(candidate_loss_1550_db).4f dB "
            "(%(improvement_db).4f dB improvement)" % item
        )
    return "\n".join(lines)


__all__ = [
    "CocExportDialog",
    "format_coc_blocking_message",
    "format_coc_summary",
    "format_optimization_warning",
]
