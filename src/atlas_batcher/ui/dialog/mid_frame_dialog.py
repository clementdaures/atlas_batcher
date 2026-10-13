# -*- coding: utf-8 -*-
"""Mid frame dialog UI

This module provides the UI for setting a custom middle frame.

Author: Clement Daures
Website: clementdaures.com
Created: 2025
"""

# region Imports & Config

# python modules
from typing import Optional

# pyside modules
from PySide6 import QtWidgets, QtCore
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QMessageBox
)

# endregion

# ==========

# region Mid Frame Dialog

class MidFrameDialog(QDialog):
    """Dialog for setting a custom middle frame.

    Args:
        parent (QWidget, optional): Parent widget.
        start_frame (int): Current start frame.
        end_frame (int): Current end frame.

    Example:
        dialog = MidFrameDialog(parent, start_frame=1001, end_frame=1100)
        if dialog.exec() == QDialog.Accepted:
            mid = dialog.get_mid_frame()
    """

    def __init__(self, parent=None, start_frame: int = 1001, end_frame: int = 1100):
        """Initialize the dialog and build its UI."""
        super().__init__(parent)

        self.start_frame = start_frame
        self.end_frame = end_frame
        self.custom_mid_frame: Optional[int] = None

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        """Build the widgets and layouts."""
        self.setWindowTitle("Set Middle Frame")
        self.setModal(True)
        self.resize(350, 150)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Info label
        info_text = f"Current frame range: {self.start_frame} - {self.end_frame}"
        info_label = QLabel(info_text)
        layout.addWidget(info_label)

        # Calculate default middle
        default_mid = (self.start_frame + self.end_frame) // 2
        suggestion_text = f"Suggested middle frame: {default_mid}"
        suggestion_label = QLabel(suggestion_text)
        suggestion_label.setStyleSheet("color: #999;")
        layout.addWidget(suggestion_label)

        # Input field
        input_label = QLabel("Enter custom middle frame:")
        layout.addWidget(input_label)

        self.line_edit = QLineEdit()
        self.line_edit.setPlaceholderText(str(default_mid))
        layout.addWidget(self.line_edit)

        # Buttons
        button_box = QHBoxLayout()
        self.ok_button = QPushButton("OK")
        self.ok_button.setDefault(True)
        self.cancel_button = QPushButton("Cancel")
        button_box.addWidget(self.ok_button)
        button_box.addWidget(self.cancel_button)
        layout.addLayout(button_box)

    def _connect_signals(self):
        """Connect the UI signals to their slots."""
        self.ok_button.clicked.connect(self._on_ok)
        self.cancel_button.clicked.connect(self.reject)
        self.line_edit.returnPressed.connect(self._on_ok)

    def _on_ok(self):
        """Validate the entered frame and accept the dialog.

        An empty field means an automatic calculation. A frame outside the range, or
        that is not an integer, shows a warning and keeps the dialog open.
        """
        text = self.line_edit.text().strip()

        if not text:
            # Use automatic calculation (no custom frame)
            self.custom_mid_frame = None
            self.accept()
            return

        try:
            mid_frame = int(text)

            # Validate range
            if mid_frame < self.start_frame or mid_frame > self.end_frame:
                QMessageBox.warning(
                    self,
                    "Invalid Input",
                    f"Middle frame must be between {self.start_frame} and {self.end_frame}"
                )
                return

            self.custom_mid_frame = mid_frame
            self.accept()

        except ValueError:
            QMessageBox.warning(
                self,
                "Invalid Input",
                "Please enter a valid integer frame number."
            )

    def get_mid_frame(self) -> Optional[int]:
        """Get the custom middle frame.

        Returns:
            int | None: Custom middle frame, or None for the automatic calculation.
        """
        return self.custom_mid_frame

# endregion

# ==========

# region Module API Helpers

def show_mid_frame_dialog(
        parent=None,
        start_frame: int = 1001,
        end_frame: int = 1100
) -> Optional[int]:
    """Show the mid frame dialog and return its result.

    Args:
        parent (QWidget, optional): Parent widget.
        start_frame (int): Current start frame.
        end_frame (int): Current end frame.

    Returns:
        int | None: Custom middle frame, or None if cancelled or automatic.
    """
    dialog = MidFrameDialog(parent, start_frame, end_frame)

    if dialog.exec() == QDialog.Accepted:
        return dialog.get_mid_frame()

    return None

# endregion
