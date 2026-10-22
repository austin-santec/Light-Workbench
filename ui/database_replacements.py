"""Database-aware replacement editor for append-only routing documentation."""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from application.replacement_persistence_workflow import (
    ReplacementChangeRequest,
    ReplacementEditorModel,
)


class DatabaseReplacementDialog(QDialog):
    """Collect explicit operator approvals without touching switch hardware."""

    def __init__(self, model: ReplacementEditorModel, parent=None) -> None:
        super().__init__(parent)
        self.model = model
        self.replacement_requests: tuple[ReplacementChangeRequest, ...] = ()
        self.spares_to_designate: tuple[int, ...] = ()
        self.spares_to_undesignate: tuple[int, ...] = ()
        self.spare_operator = model.default_operator
        self._pending: list[ReplacementChangeRequest] = []
        self._selected_recommendation = None

        self.setWindowTitle("Manage Port Replacements")
        self.setMinimumSize(980, 720)
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Physical rerouting is completed outside Light Workbench. "
                "This screen records operator-supplied documentation; it does not "
                "command or verify the switch mapping."
            )
        )
        layout.addWidget(
            QLabel(
                f"Unit: {model.unit_label or 'Not recorded'}    "
                f"Switch: {model.switch_label or 'Not recorded'}    "
                f"Assignment: {model.assignment_id}    Run: {model.related_run_id}"
            )
        )

        tabs = QTabWidget()
        tabs.addTab(self._build_record_tab(), "Record Replacements")
        tabs.addTab(self._build_spares_tab(), "Designated Spares")
        tabs.addTab(self._build_history_tab(), "Audit History")
        layout.addWidget(tabs, 1)

        self.physical_completion_check = QCheckBox(
            "I confirm that each queued physical port replacement was completed "
            "outside Light Workbench. Light Workbench did not change or verify the mapping."
        )
        layout.addWidget(self.physical_completion_check)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept_changes)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _build_record_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        layout.addWidget(QLabel("Replacement-analysis recommendations (advisory):"))
        self.recommendation_table = QTableWidget(0, 6)
        self.recommendation_table.setHorizontalHeaderLabels(
            ["Logical", "Current Port", "Proposed Port", "Category", "Improvement", "Evidence"]
        )
        self.recommendation_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.recommendation_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.recommendation_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for recommendation in self.model.recommendations:
            row = self.recommendation_table.rowCount()
            self.recommendation_table.insertRow(row)
            values = (
                recommendation.logical_channel,
                recommendation.current_effective_physical_port,
                recommendation.proposed_replacement_physical_port,
                recommendation.category.title(),
                (
                    ""
                    if recommendation.improvement_db is None
                    else f"{recommendation.improvement_db:.4f} dB"
                ),
                (
                    "Accepted measurement"
                    if recommendation.has_measurement_evidence
                    else "No accepted measurement"
                ),
            )
            for column, value in enumerate(values):
                self.recommendation_table.setItem(row, column, QTableWidgetItem(str(value)))
        self.recommendation_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.recommendation_table)

        action_row = QHBoxLayout()
        use_recommendation = QPushButton("Use Selected Recommendation")
        use_recommendation.clicked.connect(self.use_selected_recommendation)
        action_row.addWidget(use_recommendation)
        manual = QPushButton("Add Manual Replacement")
        manual.clicked.connect(self.begin_manual_replacement)
        action_row.addWidget(manual)
        correction = QPushButton("Record Correction/Reversal...")
        correction.clicked.connect(self.begin_correction)
        action_row.addWidget(correction)
        action_row.addStretch()
        layout.addLayout(action_row)

        form = QFormLayout()
        self.logical_channel_combo = QComboBox()
        for route in self.model.channel_map:
            self.logical_channel_combo.addItem(str(route.logical_channel), route.logical_channel)
        self.logical_channel_combo.currentIndexChanged.connect(self._logical_channel_changed)
        self.current_port_edit = QLineEdit()
        self.current_port_edit.setReadOnly(True)
        self.proposed_port_spin = QSpinBox()
        self.proposed_port_spin.setRange(1, 4096)
        self.proposed_port_spin.valueChanged.connect(self._refresh_evidence)
        self.category_edit = QLineEdit()
        self.category_edit.setReadOnly(True)
        self.improvement_edit = QLineEdit()
        self.improvement_edit.setReadOnly(True)
        self.reason_edit = QLineEdit()
        self.operator_edit = QLineEdit(self.model.default_operator)
        self.details_edit = QLineEdit()
        self.evidence_label = QLabel()
        form.addRow("Logical channel:", self.logical_channel_combo)
        form.addRow("Current effective physical port:", self.current_port_edit)
        form.addRow("Proposed replacement physical port:", self.proposed_port_spin)
        form.addRow("Recommendation category:", self.category_edit)
        form.addRow("Measured improvement:", self.improvement_edit)
        form.addRow("Measurement evidence:", self.evidence_label)
        form.addRow("Reason:", self.reason_edit)
        form.addRow("Operator:", self.operator_edit)
        form.addRow("Optional details:", self.details_edit)
        layout.addLayout(form)

        queue_row = QHBoxLayout()
        queue_button = QPushButton("Queue Replacement for Save")
        queue_button.clicked.connect(self.queue_replacement)
        queue_row.addWidget(queue_button)
        remove_button = QPushButton("Remove Selected Queued Replacement")
        remove_button.clicked.connect(self.remove_queued_replacement)
        queue_row.addWidget(remove_button)
        queue_row.addStretch()
        layout.addLayout(queue_row)

        self.pending_table = QTableWidget(0, 7)
        self.pending_table.setHorizontalHeaderLabels(
            ["Logical", "Current", "Proposed", "Category", "Improvement", "Reason", "Operator"]
        )
        self.pending_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.pending_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.pending_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.pending_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(QLabel("Queued append-only records (nothing is saved until Save):"))
        layout.addWidget(self.pending_table)

        layout.addWidget(QLabel("Current effective assignment mapping:"))
        self.active_mapping_table = QTableWidget(0, 3)
        self.active_mapping_table.setHorizontalHeaderLabels(
            ["Logical Channel", "Initial Port", "Current Effective Port"]
        )
        self.active_mapping_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.active_mapping_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.active_mapping_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for route in self.model.channel_map:
            row = self.active_mapping_table.rowCount()
            self.active_mapping_table.insertRow(row)
            for column, value in enumerate(
                (route.logical_channel, route.initial_physical_port, route.effective_physical_port)
            ):
                self.active_mapping_table.setItem(row, column, QTableWidgetItem(str(value)))
        self.active_mapping_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.active_mapping_table)
        self.begin_manual_replacement()
        return page

    def _build_spares_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(
            QLabel(
                "Existing spares start selected. Analysis recommendations are preselected "
                "for review, but no spare event is recorded until Save."
            )
        )
        self.spare_table = QTableWidget(0, 3)
        self.spare_table.setHorizontalHeaderLabels(["Keep/Designate", "Physical Port", "Source"])
        existing = set(self.model.existing_spares)
        recommended = set(self.model.recommended_spares)
        for port in sorted(existing.union(recommended)):
            row = self.spare_table.rowCount()
            self.spare_table.insertRow(row)
            checkbox = QTableWidgetItem()
            checkbox.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            checkbox.setCheckState(Qt.Checked)
            checkbox.setData(Qt.UserRole, port)
            if port in existing and port in recommended:
                source = "Existing; recommended"
            elif port in existing:
                source = "Existing designated spare"
            else:
                source = "New analysis recommendation"
            self.spare_table.setItem(row, 0, checkbox)
            self.spare_table.setItem(row, 1, QTableWidgetItem(str(port)))
            self.spare_table.setItem(row, 2, QTableWidgetItem(source))
        self.spare_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.spare_table)
        return page

    def _build_history_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(
            QLabel(
                "SQL replacement history is append-only. Corrections and reversals are "
                "recorded as new rows."
            )
        )
        self.history_table = QTableWidget(0, 9)
        self.history_table.setHorizontalHeaderLabels(
            [
                "ID", "Logical", "Previous", "Replacement", "Reason", "Operator",
                "Replaced (UTC)", "Related Run ID", "Notes",
            ]
        )
        self.history_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for record in self.model.replacement_history:
            row = self.history_table.rowCount()
            self.history_table.insertRow(row)
            values = (
                record.replacement_id,
                record.logical_channel,
                record.previous_physical_port,
                record.replacement_physical_port,
                record.reason,
                record.replaced_by,
                record.replaced_at_utc.isoformat(),
                "" if record.related_run_id is None else record.related_run_id,
                record.notes or "",
            )
            for column, value in enumerate(values):
                self.history_table.setItem(row, column, QTableWidgetItem(str(value)))
        self.history_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.history_table)
        return page

    def begin_manual_replacement(self) -> None:
        self._selected_recommendation = None
        self.category_edit.clear()
        self.improvement_edit.clear()
        self.reason_edit.clear()
        self.details_edit.clear()
        self.operator_edit.setText(self.model.default_operator)
        self._logical_channel_changed()

    def use_selected_recommendation(self) -> None:
        row = self.recommendation_table.currentRow()
        if row < 0:
            QMessageBox.information(
                self,
                "Select a recommendation",
                "Select one recommendation first.",
            )
            return
        recommendation = self.model.recommendations[row]
        self._selected_recommendation = recommendation
        index = self.logical_channel_combo.findData(recommendation.logical_channel)
        self.logical_channel_combo.setCurrentIndex(index)
        self.current_port_edit.setText(str(recommendation.current_effective_physical_port))
        self.proposed_port_spin.setValue(recommendation.proposed_replacement_physical_port)
        self.category_edit.setText(recommendation.category.title())
        self.improvement_edit.setText(
            ""
            if recommendation.improvement_db is None
            else f"{recommendation.improvement_db:.4f} dB"
        )
        self.reason_edit.setText(recommendation.default_reason)
        self.operator_edit.setText(self.model.default_operator)
        self.details_edit.clear()
        self._refresh_evidence()

    def begin_correction(self) -> None:
        row = self.active_mapping_table.currentRow()
        if row < 0:
            QMessageBox.information(
                self, "Select a mapping", "Select the logical channel to correct or replace again."
            )
            return
        logical_channel = int(self.active_mapping_table.item(row, 0).text())
        self.begin_manual_replacement()
        self.logical_channel_combo.setCurrentIndex(
            self.logical_channel_combo.findData(logical_channel)
        )
        self.reason_edit.setPlaceholderText("Required correction or reversal reason")

    def _logical_channel_changed(self, _index=None) -> None:
        logical_channel = self.logical_channel_combo.currentData()
        if logical_channel is None:
            self.current_port_edit.clear()
            return
        self.current_port_edit.setText(str(self.model.current_effective_port(logical_channel)))

    def _refresh_evidence(self, _value=None) -> None:
        port = self.proposed_port_spin.value()
        if port in set(self.model.measured_physical_ports):
            self.evidence_label.setText(
                "Accepted measurement data is available for this physical port."
            )
            self.evidence_label.setStyleSheet("")
        else:
            self.evidence_label.setText(
                "Warning: no accepted measurement evidence is available for this physical port."
            )
            self.evidence_label.setStyleSheet("color: #d98200;")

    def queue_replacement(self) -> None:
        logical_channel = int(self.logical_channel_combo.currentData())
        current_port = self.model.current_effective_port(logical_channel)
        proposed_port = self.proposed_port_spin.value()
        reason = self.reason_edit.text().strip()
        operator = self.operator_edit.text().strip()
        if proposed_port == current_port:
            QMessageBox.warning(
                self,
                "Invalid replacement",
                "The proposed port must differ from the current effective port.",
            )
            return
        if not reason:
            QMessageBox.warning(self, "Reason required", "Enter the replacement reason.")
            return
        if not operator:
            QMessageBox.warning(
                self,
                "Operator required",
                "Enter who performed or recorded the replacement.",
            )
            return
        request = ReplacementChangeRequest(
            logical_channel=logical_channel,
            replacement_physical_port=proposed_port,
            reason=reason,
            replaced_by=operator,
            notes=self.details_edit.text().strip() or None,
        )
        self._pending.append(request)
        category = self.category_edit.text().strip()
        improvement = self.improvement_edit.text().strip()
        row = self.pending_table.rowCount()
        self.pending_table.insertRow(row)
        for column, value in enumerate(
            (logical_channel, current_port, proposed_port, category, improvement, reason, operator)
        ):
            self.pending_table.setItem(row, column, QTableWidgetItem(str(value)))
        self.pending_table.selectRow(row)
        self.begin_manual_replacement()

    def remove_queued_replacement(self) -> None:
        row = self.pending_table.currentRow()
        if row >= 0:
            self.pending_table.removeRow(row)
            self._pending.pop(row)

    def _spare_changes(self) -> tuple[tuple[int, ...], tuple[int, ...]]:
        existing = set(self.model.existing_spares)
        selected = set()
        for row in range(self.spare_table.rowCount()):
            item = self.spare_table.item(row, 0)
            if item.checkState() == Qt.Checked:
                selected.add(int(item.data(Qt.UserRole)))
        return tuple(sorted(selected - existing)), tuple(sorted(existing - selected))

    def accept_changes(self) -> None:
        if self._pending and not self.physical_completion_check.isChecked():
            QMessageBox.warning(
                self,
                "Physical completion confirmation required",
                "Confirm that the queued physical replacements were completed outside "
                "Light Workbench before saving.",
            )
            return
        designate, undesignate = self._spare_changes()
        self.replacement_requests = tuple(self._pending)
        self.spares_to_designate = designate
        self.spares_to_undesignate = undesignate
        operators = [request.replaced_by for request in self._pending]
        self.spare_operator = (operators[0] if operators else self.model.default_operator).strip()
        if (designate or undesignate) and not self.spare_operator:
            QMessageBox.warning(
                self,
                "Operator required",
                "Enter Tested by before changing designated spares.",
            )
            return
        self.accept()


__all__ = ["DatabaseReplacementDialog"]
