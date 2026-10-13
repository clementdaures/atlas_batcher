# -*- coding: utf-8 -*-
"""Tractor submission dialog UI

This module provides the UI for submitting render jobs to Tractor: ALF file
creation, blade selection by room and spooling. The Tractor host is read from
the .env file through the env module.

Author: Clement Daures
Website: clementdaures.com
Created: 2025
"""

# region Imports & Config

# python modules
from pathlib import Path
from typing import Dict, List, Callable, Optional
import webbrowser

# pyside modules
from PySide6 import QtWidgets, QtCore
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QMessageBox
)

# atlas modules
from atlas_manager.plugins.batcher.core import env, tractor, utils
from atlas_manager.plugins.batcher.core.tractor_scan import run_scan

# endregion

# ==========

# region Tractor Dialog

class TractorDialog(QDialog):
    """Dialog for creating ALF files and submitting them to Tractor.

    Args:
        parent (QWidget, optional): Parent widget.
        render_list (Dict, optional): Render entries per shot key.
        husk_path (Path, optional): Path of the husk executable.
        renderer (str): Renderer plugin name.
        render_dir (Path, optional): Output directory of the renders.
        log_callback (Callable[[str], None], optional): Logging callback, print by default.

    Example:
        dialog = TractorDialog(parent=window, render_list=render_list)
        dialog.exec()
    """

    def __init__(
            self,
            parent=None,
            render_list: Optional[Dict] = None,
            husk_path: Optional[Path] = None,
            renderer: str = "Karma",
            render_dir: Optional[Path] = None,
            log_callback: Optional[Callable[[str], None]] = None
    ):
        """Initialize the dialog and build its UI."""
        super().__init__(parent)

        self.render_list = render_list or {}
        self.husk_path = husk_path or Path("")
        self.renderer = renderer
        self.render_dir = render_dir or Path("")
        self.log_callback = log_callback or print
        self.alf_path: Optional[Path] = None

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        """Build the widgets and layouts."""
        self.setWindowTitle("Tractor Render Settings")
        self.resize(400, 300)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # User field
        layout.addWidget(QLabel("Username"))
        self.edit_user = QLineEdit(utils.user())
        layout.addWidget(self.edit_user)

        # Project field
        layout.addWidget(QLabel("Project"))
        self.edit_project = QLineEdit("Andhakara")
        layout.addWidget(self.edit_project)

        layout.addWidget(QLabel("Job Title"))
        self.edit_job = QLineEdit(f"{utils.user()}_task")
        layout.addWidget(self.edit_job)

        # Priority field
        layout.addWidget(QLabel("Priority"))
        self.edit_priority = QLineEdit("1")
        layout.addWidget(self.edit_priority)

        # Step field
        layout.addWidget(QLabel("Frame per PC"))
        self.edit_step = QLineEdit("5")
        layout.addWidget(self.edit_step)

        # EDITED
        layout.addWidget(QLabel("Max Blades (0 = unlimited)"))
        self.edit_max_blades = QLineEdit("0")
        layout.addWidget(self.edit_max_blades)

        # Room selector
        layout.addWidget(QLabel("Rooms"))
        rooms_widget = QtWidgets.QWidget()
        rooms_layout = QtWidgets.QFlowLayout(rooms_widget) if hasattr(QtWidgets, 'QFlowLayout') else QHBoxLayout(
            rooms_widget)
        self.room_checkboxes = {}
        ROOMS = env.get_list("TRACTOR_ROOMS")
        for room in ROOMS:
            cb = QtWidgets.QCheckBox(f"Room {room}")
            cb.setChecked(True)
            cb.stateChanged.connect(self._on_room_filter_changed)
            self.room_checkboxes[room] = cb
            rooms_layout.addWidget(cb)

        cb_all = QtWidgets.QCheckBox("All")
        cb_all.setChecked(True)
        cb_all.stateChanged.connect(self._on_all_rooms_toggled)
        self.room_checkboxes["all"] = cb_all
        rooms_layout.addWidget(cb_all)
        layout.addWidget(rooms_widget)

        # Blade list
        layout.addWidget(QLabel("Blades (select to restrict, none = all active)"))
        self.blade_list = QtWidgets.QListWidget()
        self.blade_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.blade_list.setMaximumHeight(120)
        layout.addWidget(self.blade_list)

        refresh_btn = QPushButton("Refresh Blades")
        refresh_btn.clicked.connect(self._refresh_blades)
        layout.addWidget(refresh_btn)

        self._all_blades = []  # full list from scanner

        # Action buttons
        btn_row = QHBoxLayout()
        self.create_alf_btn = QPushButton("Create ALF File")
        self.send_btn = QPushButton("Send to Tractor")
        self.open_btn = QPushButton("Open Tractor")
        btn_row.addWidget(self.create_alf_btn)
        btn_row.addWidget(self.send_btn)
        btn_row.addWidget(self.open_btn)
        layout.addLayout(btn_row)

        # Close button
        self.close_btn = QPushButton("Close")
        layout.addWidget(self.close_btn, alignment=QtCore.Qt.AlignRight)

    def _connect_signals(self):
        """Connect the UI signals to their slots."""
        self.create_alf_btn.clicked.connect(self._create_alf)
        self.send_btn.clicked.connect(self._send_to_tractor)
        self.close_btn.clicked.connect(self.accept)
        self.open_btn.clicked.connect(self._open_tractor_website)

    def _create_alf(self):
        """Create the ALF file from the render list."""
        if not self.render_list:
            QMessageBox.warning(self, "Empty Render List", "No files found in render list.")
            return

        user = self.edit_user.text().strip()
        project = self.edit_project.text().strip()
        job_title = self.edit_job.text().strip()

        # Validate configuration
        is_valid, error_msg = tractor.validate_tractor_config(
            self.husk_path,
            self.edit_user.text().strip(),
            self.edit_project.text().strip()
        )

        if not is_valid:
            QMessageBox.warning(self, "Configuration Error", error_msg)
            return

        try:
            # Get priority and step
            try:
                priority = int(self.edit_priority.text().strip() or 1)
            except ValueError:
                priority = 1

            try:
                step = int(self.edit_step.text().strip() or 5)
            except ValueError:
                step = 5

            try:
                max_blades = int(self.edit_max_blades.text().strip() or 0)
            except ValueError:
                max_blades = 0

            # Create ALF
            self.alf_path = tractor.create_alf_from_render_list(
                render_list=self.render_list,
                job_title=job_title,
                project=project,
                priority=priority,
                user=user,
                step=step,
                renderer=self.renderer,
                render_dir=self.render_dir,
                max_blades=max_blades,
            )

            if self.alf_path:
                #self.info_label.setText(f"ALF created: {self.alf_path.name}")
                self.log_callback(f"ALF file created: {self.alf_path}\n")
                self.log_callback(f"Job title: {job_title}\n")
                QMessageBox.information(
                    self,
                    "ALF File Created",
                    f"ALF file created:\n{self.alf_path}"
                )
            else:
                QMessageBox.warning(self, "Unable to Generate", "No ALF tasks found.")

        except Exception as e:
            import traceback
            error_msg = f"Unable to create ALF: {repr(e)}\n{traceback.format_exc()}"
            self.log_callback(error_msg)
            QMessageBox.critical(self, "ALF Creation Error", str(e))

    def _send_to_tractor(self):
        """Submit the ALF file to Tractor."""
        if not self.alf_path or not self.alf_path.exists():
            QMessageBox.warning(
                self,
                "Missing ALF",
                "Create ALF file before sending to Tractor."
            )
            return

        user = self.edit_user.text().strip()

        self.log_callback(f"\nSpooling to Tractor: {self.alf_path}\n")
        #self.info_label.setText("Spooling to Tractor...")
        QtWidgets.QApplication.processEvents()

        try:
            crews = self._get_selected_crews()
            try:
                priority = int(self.edit_priority.text().strip() or 1)
            except ValueError:
                priority = 1

            return_code, output = tractor.spool_to_tractor(
                self.alf_path,
                user=user,
                project=self.edit_project.text().strip(),
                priority=priority,
                crews=crews,
            )

            # Log output
            self.log_callback(output + "\n")

            if return_code == 0:
                QMessageBox.information(
                    self,
                    "Sent",
                    f"{self.alf_path.name} successfully spooled to Tractor."
                )
            else:
                QMessageBox.warning(
                    self,
                    "Spooling Failed",
                    f"Spooling ended with code {return_code}. Check logs for details."
                )

        except Exception as e:
            import traceback
            error_msg = f"Spooling error: {repr(e)}\n{traceback.format_exc()}"
            self.log_callback(error_msg)
            QMessageBox.critical(self, "Spooling Failed", str(e))


    def _open_tractor_website(self):
        """Open the Tractor web interface in the default browser."""
        url = f"{env.require('TRACTOR_HOST')}/tv/#"

        # Open in default browser
        webbrowser.open(url)

    def _refresh_blades(self):
        """Scan Tractor and populate the blade list."""
        try:
            by_state, _ = run_scan(do_ping=False)
            self._all_blades = (
                    by_state.get("idle", []) +
                    by_state.get("busy", [])
            )
            self._on_room_filter_changed()
            self.log_callback(f"Blades refreshed: {len(self._all_blades)} active\n")
        except Exception as e:
            self.log_callback(f"⚠ Could not refresh blades: {e}\n")

    def _on_all_rooms_toggled(self, state):
        """Check or uncheck all the room checkboxes.

        Args:
            state (int): Check state of the 'All' checkbox.
        """
        checked = bool(state)
        for key, cb in self.room_checkboxes.items():
            if key != "all":
                cb.blockSignals(True)
                cb.setChecked(checked)
                cb.blockSignals(False)
        self._on_room_filter_changed()

    def _on_room_filter_changed(self):
        """Filter the blade list based on the checked rooms.

        The room is read from the characters 4 and 5 of the blade name. Blades in
        nimby are not listed.
        """
        active_rooms = [
            room for room, cb in self.room_checkboxes.items()
            if room != "all" and cb.isChecked()
        ]

        self.blade_list.clear()
        for blade in self._all_blades:
            if blade["state"] == "nimby":
                continue

            name = blade["name"]
            room = name[4:6] if len(name) >= 6 else ""
            if room in active_rooms:
                item = QtWidgets.QListWidgetItem(
                    f"{name}  [{blade['state']}]"
                )
                item.setData(QtCore.Qt.UserRole, name)
                self.blade_list.addItem(item)

    def _get_selected_crews(self) -> list[str]:
        """Return the list of selected blade hostnames.

        If no blade is selected, all the visible blades (room filter only) are
        returned. If no blade is visible, an empty list is returned (no restriction).

        Returns:
            list[str]: Blade hostnames.
        """
        selected = [
            self.blade_list.item(i).data(QtCore.Qt.UserRole)
            for i in range(self.blade_list.count())
            if self.blade_list.item(i).isSelected()
        ]
        if selected:
            return selected

        return [
            self.blade_list.item(i).data(QtCore.Qt.UserRole)
            for i in range(self.blade_list.count())
        ]

# endregion
