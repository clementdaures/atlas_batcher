# -*- coding: utf-8 -*-
"""Atlas Batcher main UI class

This module provides the `AtlasBatcher` class to manage USD files, shot
rendering, and Tractor submission from within Atlas Batcher. It builds a
PySide6 interface with configuration handling, render list management, and
USD frame inspection.

Author: Clement Daures
Website: clementdaures.com
Created: 2025
"""

# region Imports & Config

# python modules
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

# pyside modules
from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtWidgets import *

# atlas modules
from atlas_manager.plugins.batcher.core import utils, render
from atlas_manager.plugins.batcher.ui.dialog.tractor_dialog import TractorDialog
from atlas_manager.plugins.batcher.ui.dialog.mid_frame_dialog import show_mid_frame_dialog

# endregion

# ==========

# region Render Data

@dataclass
class RenderEntry:
    """Data structure of a render list entry.

    Attributes:
        path (Path): Path of the USD file to render.
        start (int): Start frame.
        end (int): End frame.
        inc (int): Frame increment.
    """

    path: Path
    start: int
    end: int
    inc: int = 1

# endregion

# ==========

# region Main Window

class AtlasBatcher(QtWidgets.QMainWindow):
    """Main Atlas Batcher application window.

    Lists the USD files of a lookdev asset, a shot or a custom folder, builds a
    render list (full range, or first / middle / last frames), renders it locally
    with husk, or submits it to Tractor.

    Args:
        parent (QWidget, optional): Parent widget.

    Example:
        win = AtlasBatcher()
        win.show()
    """

    render_finished_signal = QtCore.Signal()

    def __init__(self, parent=None):
        """Initialize the window, its state and the render manager."""
        super(AtlasBatcher, self).__init__(parent)

        # ----- Window stylesheet -----
        self.setStyleSheet("""
            QWidget {
                background-color: #303030;
                color: #ddd;
                font-family: Segoe UI;
                font-size: 8pt;
            }
            QMenuBar:item:selected {
                background-color: #7a53cf;
                color: #ffffff;
            }
            QMenu::item:selected {
                background-color: #7a53cf;
                color: #fff;
            }
            QPushButton {
                background-color: #404040;
                border: 1px solid #262626;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QPushButton:hover {
                background-color: #404040;
                border: 1px solid #7a53cf;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QComboBox QAbstractItemView {
                selection-background-color: #7a53cf;  
                selection-color: #ffffff;              
                background-color: #262626;            
            }
            QComboBox:hover {
                border: 1px solid #7a53cf;
            }
            QDoubleSpinBox:hover {
                border: 1px solid #7a53cf;
            }
            QLineEdit, QComboBox, QDoubleSpinBox {
                background-color: #262626;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 2px;
            }
            QGroupBox {
                border: 1px solid #7a53cf;
                border-radius: 5px;
                margin-top: 6px;
                padding: 4px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QFrame#line {
                background-color: #303030;
                border: 1px solid #303030;
            }
            QTreeWidget {
                background-color: #262626;
                color: #ddd;
                font-family: Segoe UI;
                font-size: 8pt;
                border: 1px solid #555;
                border-radius: 3px;
            }
            QTreeWidget::item {
                height: 20px;
                padding-left: 4px;
                padding-right: 4px;
            }
            QTreeWidget::item:selected {
                background-color: #7a53cf;
                color: #ffffff;
            }
            QTreeWidget::item:hover {
                background-color: #5e3fbf;
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #404040;
                color: #ddd;
                padding: 4px;
                border: 1px solid #262626;
            }
            QHeaderView::section:pressed {
                background-color: #7a53cf;
                color: #ffffff;
            }
            QHeaderView::section:hover {
                background-color: #5e3fbf;
                color: #ffffff;
            }
                        QProgressBar {
                background-color: #404040;   /* bar background */
                color: #ddd;                 /* text color */
                border: 1px solid #262626;  /* border color */
                border-radius: 4px;
                text-align: center;
                height: 18px;
            }
            QProgressBar::chunk {
                background-color: #7a53cf;  /* progress fill (#7a53cf) */
                border-radius: 4px;
            }
            QListWidget {
                background-color: #262626;
                color: #ddd;
                border: 1px solid #555;
                border-radius: 3px;
                font-family: Segoe UI;
                font-size: 8pt;
            }

            QListWidget::item {
                background-color: #404040;
                padding: 4px;
                border-radius: 3px;
                margin: 2px;
                height: 22px;
            }

            QListWidget::item:hover {
                background-color: #5e3fbf;
                color: #fff;
            }

            QListWidget::item:selected {
                background-color: #7a53cf;
                color: #fff;
            }
            QComboBox QAbstractItemView {
                selection-background-color: #7a53cf;  
                selection-color: #ffffff;              
                background-color: #262626;            
            }
            QComboBox:hover {
                border: 1px solid #7a53cf;
            }
        """)

        self.setWindowFlags(QtCore.Qt.Window)
        self.root = self

        # ----- Window configuration -----
        self.setWindowTitle("Atlas Batcher v1.0.0 - Standalone")
        self.setWindowIcon(QtGui.QIcon('icon/atlas_main_ui.png'))
        self.resize(1250, 900)

        # ----- Var class -----
        class Var:
            """Minimal value holder used to bind widgets to a value."""

            def __init__(self, value):
                """Store the initial value.

                Args:
                    value (object): Initial value.
                """
                self._value = value

            def get(self):
                """Return the stored value.

                Returns:
                    object: The stored value.
                """
                return self._value

            def set(self, value):
                """Store a new value.

                Args:
                    value (object): New value.
                """
                self._value = value

        self.seq = Var(0)
        self.shot = Var("0")
        self.start_frame = Var(1001)
        self.end_frame = Var(1001)
        self.inc_frame = Var(1)
        self.asset_type = Var("Chara")
        self.custom_path = Var("")

        # ----- Internal state -----
        self.file_vars: Dict[Path, bool] = {}
        self.asset_paths: Dict[str, Path] = {}  # Store asset name to path mapping

        # ----- RenderManager initialization -----
        self.render_manager = render.RenderManager(husk_path=utils.husk_path(), renderer=utils.renderer_variable())

        # ----- UI Build -----
        self._create_widgets()
        self.render_finished_signal.connect(self._show_render_success_dialog)

        # ----- Print log -----
        QtCore.QTimer.singleShot(100, lambda: self.log("Console ready.\n"))

    @staticmethod
    def _bind_lineedit(line_edit, var_obj):
        """Bind a QLineEdit to a variable-like object.

        The variable is updated each time the text changes. A variable holding an
        integer only accepts valid integers.

        Args:
            line_edit (QLineEdit): Line edit to bind.
            var_obj (Var): Object exposing get() and set().
        """

        def on_change():
            """Update the bound variable from the line edit text."""
            try:
                text = line_edit.text()
                # Handle conversion based on current value type
                current = var_obj.get()
                if isinstance(current, int):
                    try:
                        var_obj.set(int(text))
                    except ValueError:
                        pass
                else:
                    var_obj.set(text)
            except Exception as e:
                print(f"Binding error: {e}")

        line_edit.textChanged.connect(on_change)

    def _create_widgets(self):

        """Build the main widgets.

        Creates the Directory group (type, sequence, shot or asset, custom path), the
        USD Files list with the frame range controls, the Render group (progress bar,
        local render, Tractor, stop), the Render List tree and the Console.
        """
        self.root = self
        # ----- Main widget -----
        main = QWidget()
        main_layout = QHBoxLayout(main)
        self.root.setCentralWidget(main)
        # -----------------------

        # ----- Left side -----
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        main_layout.addWidget(left_panel, 2)
        # ---------------------

        # ----- Directory group -----
        rep_box = QGroupBox("Directory")
        self.dir_grid = QGridLayout(rep_box)

        # --- Type combo ---
        self.dir_grid.addWidget(QLabel("Type :"), 0, 0)

        self.type_combo = QComboBox()
        # load sequence
        type_list = ["Lookdev", "Shot", "Custom"]
        self.type_combo.addItem(type_list[0])
        self.type_combo.addItem(type_list[1])
        self.type_combo.addItem(type_list[2])
        # update model when changed
        self.type_combo.currentTextChanged.connect(self._on_type_changed)

        self.dir_grid.addWidget(self.type_combo, 0, 1)

        # --- Create widgets for all three modes (we'll show/hide as needed) ---

        # LOOKDEV MODE widgets
        self.asset_type_label = QLabel("Asset Type :")
        self.asset_type_combo = QComboBox()
        self.asset_type_combo.addItems(["Chara", "Prop", "Set"])
        self.asset_type_combo.currentTextChanged.connect(self._on_asset_type_changed)

        # SHOT MODE widgets
        self.seq_label = QLabel("Sequence :")
        self.seq_combo = QComboBox()

        # Load sequences for shot mode
        try:
            result = utils.sequences()
            if result:
                seq_names, seq_paths = result
                self.sequences = dict(zip(seq_names, seq_paths))
                self.seq_combo.addItems(seq_names)
                if seq_names:
                    self.seq_combo.setCurrentText(str(seq_names[0]))
            else:
                self.sequences = {}
                self.seq_combo.addItem("No sequences found")
        except Exception as e:
            self.sequences = {}
            self.seq_combo.addItem("Error loading sequences")
            QtCore.QTimer.singleShot(200, lambda: self.log(
                f"⚠ Unable to load sequences: {repr(e)}\nCheck your network path in Settings.\n"))

        self.seq_combo.currentTextChanged.connect(self._on_sequence_changed)

        # CUSTOM MODE widgets
        self.custom_label = QLabel("Custom Path :")
        self.custom_path_edit = QLineEdit()
        self._bind_lineedit(self.custom_path_edit, self.custom_path)

        self.custom_browse_btn = QPushButton("Browse...")
        self.custom_browse_btn.clicked.connect(self._browse_custom_path)

        # SHARED: Shot/Asset combo (used in both Lookdev and Shot modes)
        self.shot_label = QLabel("Shot :")
        self.shot_combo = QComboBox()
        self.shot_combo.currentTextChanged.connect(lambda v: self.shot.set(v))

        # Add all widgets to grid (they'll be shown/hidden based on mode)
        # Row 1: Second label column
        self.dir_grid.addWidget(self.asset_type_label, 0, 2)
        self.dir_grid.addWidget(self.seq_label, 0, 2)
        self.dir_grid.addWidget(self.custom_label, 0, 2)

        # Row 1: Second combo/widget column
        self.dir_grid.addWidget(self.asset_type_combo, 0, 3)
        self.dir_grid.addWidget(self.seq_combo, 0, 3)
        self.dir_grid.addWidget(self.custom_path_edit, 0, 3)

        # Row 1: Third label column (Shot label)
        self.dir_grid.addWidget(self.shot_label, 0, 4)

        # Row 1: Third combo column (Shot combo)
        self.dir_grid.addWidget(self.shot_combo, 0, 5)

        # Row 1: Browse button for custom mode
        self.dir_grid.addWidget(self.custom_browse_btn, 0, 4, 1, 2)

        left_layout.addWidget(rep_box)

        # Initialize to Shot mode by default
        self._on_type_changed("Lookdev")
        # ---------------------------

        # ----- Main Action Widget -----
        btn_row = QHBoxLayout()
        left_layout.addLayout(btn_row)

        def B(text, func):
            """Create a push button connected to a callback.

            Args:
                text (str): Button label.
                func (Callable): Function called when the button is clicked.

            Returns:
                QPushButton: The created button.
            """
            b = QPushButton(text)
            b.clicked.connect(func)
            return b

        btn_row.addWidget(B("List USD", self.list_aov_usd))
        btn_row.addWidget(B("Remove Selected USD", self.remove_selected_usd))
        btn_row.addWidget(B("Clear USD List", self.clear_usd_list))
        # ------------------------------

        # -----------------------------------------------------
        #              SCROLLABLE USD FILE LIST
        # -----------------------------------------------------
        usd_box = QGroupBox("USD Files")
        usd_layout = QVBoxLayout(usd_box)

        self.usd_list = QtWidgets.QListWidget()
        self.usd_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        usd_layout.addWidget(self.usd_list)

        left_layout.addWidget(usd_box, 1)

        # -----------------------------------------------------
        #       FRAME RANGE + SELECT ALL
        # -----------------------------------------------------
        range_row = QHBoxLayout()
        left_layout.addLayout(range_row)

        range_row.addWidget(QLabel("Start Frame :"))
        start = QLineEdit(str(self.start_frame.get()))
        self._bind_lineedit(start, self.start_frame)
        range_row.addWidget(start)

        range_row.addWidget(QLabel("End Frame :"))
        end = QLineEdit(str(self.end_frame.get()))
        self._bind_lineedit(end, self.end_frame)
        range_row.addWidget(end)

        range_row.addWidget(QLabel("Inc Frame :"))
        inc = QLineEdit(str(self.inc_frame.get()))
        self._bind_lineedit(inc, self.inc_frame)
        range_row.addWidget(inc)

        range_row.addWidget(B("Set Mid Frame", self.set_mid_frame))
        range_row.addWidget(B("Reset Mid Frame", self.reset_mid_frame))

        # -----------------------------------------------------
        #      ACTIONS ON USD LIST
        # -----------------------------------------------------
        usd_action = QHBoxLayout()
        left_layout.addLayout(usd_action)

        usd_action.addWidget(B("Add to Render List", self.add_to_render_list))
        usd_action.addWidget(B("Add FML to Render List", self.add_fml_to_render_list))

        # -----------------------------------------------------
        #            LOCAL RENDER CONTROLS
        # -----------------------------------------------------
        render_box = QGroupBox("Render")
        render_layout = QVBoxLayout(render_box)

        self.progress = QProgressBar()
        self.progress.setMaximum(100)
        self.progress.setValue(0)
        self.progress.setStyleSheet("QProgressBar { height: 18px; }")
        render_layout.addWidget(self.progress)

        btns = QHBoxLayout()
        btns.addWidget(B("Local Render", self.start_render_thread))
        btns.addWidget(B("Tractor", self._open_tractor_window))
        btns.addWidget(B("Stop", self.cancel_render_process))
        render_layout.addLayout(btns)

        left_layout.addWidget(render_box)

        # =====================================================
        # ===================== RIGHT SIDE ====================
        # =====================================================
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        main_layout.addWidget(right_panel, 1)

        # -----------------------------------------------------
        #          RENDER LIST TREEVIEW
        # -----------------------------------------------------
        rl_box = QGroupBox("Render List")
        rl_layout = QVBoxLayout(rl_box)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Shot / File", "Frames"])
        self.tree.setColumnWidth(0, 250)
        rl_layout.addWidget(self.tree)

        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)

        button_rl_widget = QWidget()
        button_rl_layout = QHBoxLayout(button_rl_widget)
        button_rl_layout.addWidget(B("Delete Selection", self.delete_selection_from_render_list), 2)
        button_rl_layout.addWidget(B("Clear", self.clear_from_render_list), 1)

        rl_layout.addWidget(button_rl_widget)
        right_layout.addWidget(rl_box, 1)

        # -----------------------------------------------------
        #                   CONSOLE
        # -----------------------------------------------------
        console_box = QGroupBox("Console")
        console_layout = QVBoxLayout(console_box)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        console_layout.addWidget(self.log_text)

        right_layout.addWidget(console_box)

    def _on_type_changed(self, type_name):
        """Show the widgets matching the selected type.

        Args:
            type_name (str): Selected type, 'Lookdev', 'Shot' or 'Custom'.
        """

        # Hide all mode-specific widgets first
        self.asset_type_label.hide()
        self.asset_type_combo.hide()
        self.seq_label.hide()
        self.seq_combo.hide()
        self.custom_label.hide()
        self.custom_path_edit.hide()
        self.custom_browse_btn.hide()
        self.shot_label.hide()
        self.shot_combo.hide()

        if type_name == "Lookdev":
            # Show: Asset Type combo and Shot combo (for assets)
            self.asset_type_label.show()
            self.asset_type_combo.show()
            self.shot_label.setText("Asset :")
            self.shot_label.show()
            self.shot_combo.show()

            # Load assets based on current asset type
            self._on_asset_type_changed(self.asset_type_combo.currentText())

        elif type_name == "Shot":
            # Show: Sequence combo and Shot combo
            self.seq_label.show()
            self.seq_combo.show()
            self.shot_label.setText("Shot :")
            self.shot_label.show()
            self.shot_combo.show()

            # Initialize shot mode
            if self.sequences:
                self._on_sequence_changed(self.seq_combo.currentText())

        elif type_name == "Custom":
            # Show: Path line edit and Browse button
            self.custom_label.show()
            self.custom_path_edit.show()
            self.custom_browse_btn.show()

    def _on_asset_type_changed(self, asset_type):
        """Update the asset list when an asset type is selected (Lookdev mode).

        Args:
            asset_type (str): Selected asset type, 'Chara', 'Prop' or 'Set'.
        """
        self.asset_type.set(asset_type)

        # Clear old list
        self.shot_combo.clear()

        try:
            # Use the new assets() function from utils to get assets with 'rdr' folders
            result = utils.assets(asset_type)

            if result:
                asset_names, asset_paths = result

                # Store the asset paths for later use
                self.asset_paths = dict(zip(asset_names, asset_paths))

                # Fill combo with asset names
                self.shot_combo.addItems(asset_names)

                # Auto-select first asset
                if asset_names:
                    self.shot.set(asset_names[0])
                    self.shot_combo.setCurrentText(asset_names[0])
                    self.log(f"Loaded {len(asset_names)} {asset_type} asset(s)\n")
            else:
                self.asset_paths = {}
                self.shot_combo.addItem("No assets found")
                self.log(f"No {asset_type} assets with 'rdr' folder found\n")

        except Exception as e:
            self.asset_paths = {}
            self.shot_combo.addItem("Error loading assets")
            self.log(f"Error loading assets for {asset_type}: {repr(e)}\n")

    def _browse_custom_path(self):
        """Open a folder dialog to select the custom path."""
        file_dialog = QFileDialog(self)
        file_dialog.setFileMode(QFileDialog.Directory)
        file_dialog.setOption(QFileDialog.ShowDirsOnly, True)

        if file_dialog.exec():
            selected_path = file_dialog.selectedFiles()[0]
            self.custom_path.set(selected_path)
            self.custom_path_edit.setText(selected_path)
            self.log(f"Custom path set to: {selected_path}\n")

    def _on_sequence_changed(self, sequence_name):
        """Update the shot list when a sequence is selected.

        Args:
            sequence_name (str): Selected sequence name.
        """
        self.seq.set(sequence_name)

        # clear old list
        self.shot_combo.clear()

        sequence_path = self.sequences.get(sequence_name)

        # Check if sequence_path exists and is valid
        if not sequence_path or not Path(sequence_path).exists():
            self.log(f"Sequence path not found: {sequence_path}\n")
            return

        # Get shots using your function
        try:
            result = utils.shots(sequence_path)
            if not result:
                return

            shot_list, shot_paths = result

            # Fill shot combo
            self.shot_combo.addItems(shot_list)

            # Auto-select first shot
            if shot_list:
                self.shot.set(shot_list[0])
                self.shot_combo.setCurrentText(shot_list[0])
        except Exception as e:
            self.log(f"Error loading shots for {sequence_name}: {repr(e)}\n")

    # ---------------- Logging ----------------
    def log(self, txt: str) -> None:
        """Append a message to the console in a thread-safe way.

        Falls back to print if the console does not exist yet.

        Args:
            txt (str): Message to display.
        """
        if not hasattr(self, "log_text") or self.log_text is None:
            print(txt, end="")
            return

        message = txt.rstrip("\n")

        # Always use invokeMethod for thread safety
        QtCore.QMetaObject.invokeMethod(
            self.log_text,
            "append",
            QtCore.Qt.QueuedConnection,
            QtCore.Q_ARG(str, message)
        )

    # ---------------- File listing ----------------
    def list_aov_usd(self) -> None:
        """List the USD files of the current selection in the USD list.

        The folder depends on the type: custom folder, lookdev asset or shot.
        """
        self.usd_list.clear()

        current_type = self.type_combo.currentText()

        if current_type == "Custom":
            custom_path = self.custom_path.get()
            if not custom_path:
                QMessageBox.warning(self, "No Path", "Please select a custom path first.")
                return

            # List USD files in custom path
            custom_dir = Path(custom_path)
            if not custom_dir.exists():
                self.log(f"Custom path does not exist: {custom_path}\n")
                return

            usd_files = list(custom_dir.glob("*.usd")) + list(custom_dir.glob("*.usda"))

            for f in usd_files:
                item = QtWidgets.QListWidgetItem(f.name)
                item.setData(QtCore.Qt.UserRole, f)
                self.usd_list.addItem(item)

            self.log(f"{len(usd_files)} USD files listed from custom path\n")

        elif current_type == "Lookdev":
            asset_name = self.shot_combo.currentText()

            # Get the asset path from stored dictionary
            asset_path = self.asset_paths.get(asset_name)

            if not asset_path:
                self.log(f"Asset path not found for: {asset_name}\n")
                return

            # Use the new usd_path_lookdev function
            try:
                result = utils.usd_path_lookdev(asset_path)

                if result:
                    usd_names, usd_paths = result

                    for f in usd_paths:
                        item = QtWidgets.QListWidgetItem(f.name)
                        item.setData(QtCore.Qt.UserRole, f)
                        self.usd_list.addItem(item)

                    self.log(f"{len(usd_paths)} USD files listed for {asset_name}\n")
                else:
                    self.log(f"No USD files found in rdr folder for {asset_name}\n")

            except Exception as e:
                self.log(f"Error listing USD files: {repr(e)}\n")

        else:  # Shot mode
            sequence_name = self.seq_combo.currentText()
            shot_name = self.shot_combo.currentText()

            usd_list, usd_path_list = utils.usd_path(sequence_name, shot_name)

            for f in usd_path_list:
                f = Path(f)
                item = QtWidgets.QListWidgetItem(f.name)
                item.setData(QtCore.Qt.UserRole, f)
                self.usd_list.addItem(item)

            self.log(f"{len(usd_path_list)} USD files listed\n")


    def clear_usd_list(self) -> None:
        """Clear the USD list and reset the tracking variables."""
        self.usd_list.clear()  # Remove all items from the list

        self.file_vars.clear()
        self.current_folder = None
        self.log("List deleted files.\n")

    # ---------------- Render List management ----------------
    def set_mid_frame(self) -> None:
        """Open the dialog that sets a custom middle frame."""
        start = self.start_frame.get()
        end = self.end_frame.get()

        result = show_mid_frame_dialog(self, start, end)

        if result is not None:
            self.custom_mid_frame = result
            if result:
                self.log(f"Middle frame set to: {result}\n")
            else:
                self.log("Middle frame set to automatic calculation\n")

    def reset_mid_frame(self) -> None:
        """Reset the middle frame to the automatic calculation."""
        self.custom_mid_frame = None
        self.log("Middle frame reset to automatic calculation.\n")
        QMessageBox.information(
            self,
            "Middle Frame Reset",
            "Middle frame has been reset to automatic calculation."
        )

    def get_usd_list(self):
        """Return the USD files of the USD list.

        Returns:
            List[Path] | None: USD paths, or None (after a warning) if the list is empty.
        """
        paths = []

        for i in range(self.usd_list.count()):
            item = self.usd_list.item(i)
            if not item:
                continue
            path_str = item.data(QtCore.Qt.UserRole)
            if path_str:
                paths.append(Path(path_str))

        if not paths:
            QMessageBox.warning(self, "No files", "No USD in the list.")
            return
        else:
            return paths

    def add_to_render_list(self):
        """Add the USD files of the list to the render list with the current frame range."""
        paths = self.get_usd_list()
        if not paths:
            return

        current_type = self.type_combo.currentText()

        if current_type == "Custom":
            custom_path = self.custom_path.get()
            shot_key = f"CUSTOM: {custom_path}"
        elif current_type == "Lookdev":
            asset_type = self.asset_type_combo.currentText()
            asset_name = self.shot_combo.currentText()
            shot_key = f"LOOKDEV: {asset_type} / {asset_name}"
        else:  # Shot mode
            sequence_name = self.seq_combo.currentText()
            shot_name = self.shot_combo.currentText()
            shot_key = f"SEQUENCE: {sequence_name} / SHOT: {shot_name}"

        start = self.start_frame.get()
        end = self.end_frame.get()
        inc = self.inc_frame.get()

        new, merged, skipped = self.render_manager.add_to_render_list(
            shot_key, paths, start, end, inc
        )

        if new:
            self.log(f"{new} file(s) added.\n")
        if merged:
            self.log(f"{merged} merged.\n")
        if skipped:
            self.log(f"{skipped} skipped.\n")

        self.refresh_render_window_tree()

    def add_fml_to_render_list(self):
        """Add the first, middle and last frames of the USD files to the render list."""
        paths = self.get_usd_list()
        if not paths:
            return

        current_type = self.type_combo.currentText()

        if current_type == "Custom":
            custom_path = self.custom_path.get()
            shot_key = f"CUSTOM: {custom_path}"
        elif current_type == "Lookdev":
            asset_type = self.asset_type_combo.currentText()
            asset_name = self.shot_combo.currentText()
            shot_key = f"LOOKDEV: {asset_type} / {asset_name}"
        else:  # Shot mode
            sequence_name = self.seq_combo.currentText()
            shot_name = self.shot_combo.currentText()
            shot_key = f"SEQUENCE: {sequence_name} / SHOT: {shot_name}"

        start = self.start_frame.get()
        end = self.end_frame.get()
        inc = self.inc_frame.get()

        new, merged, skipped, error = self.render_manager.add_fml_to_render_list(
            shot_key, paths, start, end, self.custom_mid_frame, inc
        )

        if error:
            QMessageBox.warning(self, "Invalid Middle Frame", error)
            return

        if new:
            self.log(f"{new} file(s) added.\n")
        if merged:
            self.log(f"{merged} merged.\n")
        if skipped:
            self.log(f"{skipped} skipped.\n")

        self.refresh_render_window_tree()

    def remove_selected_usd(self):
        """Remove the selected files from the USD list."""
        selected_items = self.usd_list.selectedItems()  # Get selected QListWidgetItems
        count = len(selected_items)

        for item in selected_items:
            path = item.data(QtCore.Qt.UserRole)  # Retrieve stored Path object
            row = self.usd_list.row(item)
            self.usd_list.takeItem(row)  # Remove item from list

            # Also remove from file_vars if needed
            if path in self.file_vars:
                del self.file_vars[path]

        self.log(f"Deleted {count} USD files\n")

    def refresh_render_window_tree(self) -> None:
        """Rebuild the render list tree from the render manager."""
        self.tree.clear()

        sorted_list = self.render_manager.get_render_list_sorted()

        for shot_key, entries in sorted_list.items():
            shot_node = QTreeWidgetItem(self.tree)
            shot_node.setText(0, shot_key)
            shot_node.setExpanded(True)

            for entry in entries:
                frame_str = f"{entry.start}-{entry.end} / {entry.inc}"
                file_item = QTreeWidgetItem(shot_node)
                file_item.setText(0, entry.path.name)
                file_item.setText(1, frame_str)

    def delete_selection_from_render_list(self) -> None:
        """Remove the selected tree items from the render list."""
        selected = self.tree.selectedItems()
        removed = 0

        for item in selected:
            parent = item.parent()
            if parent:
                shot_key = parent.text(0)
                filename = item.text(0)
                frame_range = item.text(1)

                if self.render_manager.remove_from_render_list(shot_key, filename, frame_range):
                    removed += 1

        self.refresh_render_window_tree()
        self.log(f"{removed} file(s) removed from render list.\n")

    def clear_from_render_list(self) -> None:
        """Clear the whole render list."""
        self.render_manager.clear_render_list()
        self.tree.clear()
        self.log("All items cleared from render list.\n")

    # ---------------- Rendering ----------------
    def start_render_thread(self) -> None:
        """Start the local render in a background thread."""
        t = threading.Thread(target=self.render_files, daemon=True)
        t.start()

    def cancel_render_process(self) -> None:
        """Request the cancellation of the current local render."""
        self.render_manager.cancel_current_render()
        self.log("Render cancellation requested.\n")

    def render_files(self) -> None:
        """Render all the entries of the render list locally.

        The output folder depends on the type: <custom path>/renders, the renders
        folder inside the rdr folder of the asset, or the render folder of the shot.
        Runs in a background thread.
        """
        current_type = self.type_combo.currentText()

        if current_type == "Custom":
            custom_path = self.custom_path.get()
            render_path = Path(custom_path) / "renders"
        elif current_type == "Lookdev":
            # Define render path for lookdev assets
            asset_type = self.asset_type_combo.currentText()
            asset_name = self.shot_combo.currentText()
            asset_path = self.asset_paths.get(asset_name)

            if asset_path:
                # Render in a 'renders' subfolder within the asset's rdr folder
                render_path = asset_path / "rdr" / "renders"
            else:
                self.log(f"Cannot determine render path for asset: {asset_name}\n")
                return
        else:  # Shot mode
            sequence_name = self.seq_combo.currentText()
            shot_name = self.shot_combo.currentText()
            render_path = Path(utils.render_path(sequence_name, shot_name))

        # Ensure render directory exists
        render_path.mkdir(parents=True, exist_ok=True)
        self.log(f"Rendering to: {render_path}\n")

        # Progress callback
        def update_progress(current: int, total: int):
            """Update the progress bar from the render thread.

            Args:
                current (int): Index of the entry being rendered.
                total (int): Total number of entries.
            """
            QtCore.QMetaObject.invokeMethod(
                self.progress,
                "setMaximum",
                QtCore.Qt.QueuedConnection,
                QtCore.Q_ARG(int, total)
            )
            QtCore.QMetaObject.invokeMethod(
                self.progress,
                "setValue",
                QtCore.Qt.QueuedConnection,
                QtCore.Q_ARG(int, current)
            )

        # Render all
        success, message = self.render_manager.render_all(
            render_output_dir=render_path,
            progress_callback=update_progress,
            log_callback=self.log
        )

        if success:
            self.log("✓ All renders completed successfully.\n")
            self.render_finished_signal.emit()
        else:
            self.log(f"✗ Render failed: {message}\n")

    @QtCore.Slot()
    def _show_render_success_dialog(self):
        """Show the render success dialog and reset the progress bar.

        Must run on the main thread.
        """
        self.log("DEBUG: _show_render_success_dialog CALLED!\n")

        QMessageBox.information(
            self,
            "Render Success",
            "USD have been successfully rendered."
        )

        self.log("DEBUG: Dialog closed by user\n")

        # Reset progress bar to 0
        self.progress.setValue(0)

    # ---------------- Tractor Integration ----------------
    def _open_tractor_window(self) -> None:
        """Open the Tractor submission dialog for the current render list."""
        current_type = self.type_combo.currentText()

        if current_type == "Custom":
            custom_path = self.custom_path.get()
            render_path = Path(custom_path) / "renders"
        elif current_type == "Lookdev":
            asset_type = self.asset_type_combo.currentText()
            asset_name = self.shot_combo.currentText()
            asset_path = self.asset_paths.get(asset_name)

            if asset_path:
                render_path = asset_path / "rdr" / "renders"
            else:
                QMessageBox.warning(self, "Invalid Asset", f"Cannot find path for asset: {asset_name}")
                return
        else:  # Shot mode
            sequence_name = self.seq_combo.currentText()
            shot_name = self.shot_combo.currentText()
            render_path = Path(utils.render_path(sequence_name, shot_name))

        render_list = self.render_manager.get_render_list_sorted()

        # Create and show dialog
        dialog = TractorDialog(
            parent=self,
            render_list=render_list,
            husk_path=Path(utils.husk_path()),
            renderer=utils.renderer_variable(),
            render_dir=render_path,
            log_callback=self.log
        )

        dialog.exec()

# endregion

# ==========

# region Module API Helpers

def main():
    """Launch the Atlas Batcher UI outside Houdini.

    Closes any existing Atlas Batcher window, then creates and shows a new one.
    """
    try:
        app = QtWidgets.QApplication.instance()
        if not app:
            app = QtWidgets.QApplication(sys.argv)

        # Close any existing instance
        for widget in app.topLevelWidgets():
            if widget.objectName() == "AtlasBatcher":
                widget.close()
                widget.deleteLater()

        # Create window without Houdini parent
        win = AtlasBatcher(parent=None)
        win.setObjectName("AtlasBatcher")
        win.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        win.show()


    except Exception as e:
        import traceback
        print(f"Error launching AtlasBatcher: {e}")
        print(traceback.format_exc())
        raise

# endregion

# ==========

# region Standalone Entry Point

# Only needed if running standalone
if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    win = AtlasBatcher()

    win.show()
    sys.exit(app.exec())

# endregion
