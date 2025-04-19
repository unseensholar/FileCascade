import sys
import os
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path
import pickle
import math
import re


from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QFileDialog, QListWidget, QListWidgetItem,
    QAbstractItemView, QTextEdit, QProgressBar, QScrollArea, QFrame,
    QSizePolicy, QSpinBox, QCheckBox, QMessageBox,
)
from PySide6.QtCore import (
    Qt, QThread, Signal, Slot, QMimeData, QByteArray, QTimer, QPoint
)
from PySide6.QtGui import QDrag, QIcon, QPixmap, QPainter, QColor, QLinearGradient

# --- Configuration ---
DEFAULT_TIME_THRESHOLD_MINUTES = 5
DEFAULT_MANUAL_GROUP_COUNT = 5
DEFAULT_FOLDER_NAME_PATTERN = "Run_{num}"
DEFAULT_GROUP_TITLE_PREFIX = "Group"
DEFAULT_EXTENSIONS = ".csv"
CUSTOM_MIME_TYPE = "application/x-sorterapp-filelist"
# --- End Configuration --

def create_icon(shape, color="black"):
    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QColor(color))
    if shape == '+':
        painter.drawLine(4, 8, 12, 8)
        painter.drawLine(8, 4, 8, 12)
    elif shape == 'x':
        painter.drawLine(4, 4, 12, 12)
        painter.drawLine(4, 12, 12, 4)
    painter.end()
    return QIcon(pixmap)


def create_app_icon():
    pixmap = QPixmap(256, 256)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    bg_gradient = QLinearGradient(0, 0, 0, 256)
    bg_gradient.setColorAt(0, QColor("#fefefe"))
    bg_gradient.setColorAt(1, QColor("#e0e0e0"))
    painter.setBrush(bg_gradient)
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(0, 0, 256, 256, 30, 30)

    shadow_color = QColor(0, 0, 0, 40)
    bar_width = 160
    bar_height = 24
    spacing = 40

    start_x = 30
    start_y = 60

    for i in range(3):
        y = start_y + i * (bar_height + spacing)
        painter.setBrush(shadow_color)
        painter.drawRoundedRect(start_x + 4, y + 4, bar_width, bar_height, 12, 12)

    for i in range(3):
        y = start_y + i * (bar_height + spacing)
        bar_gradient = QLinearGradient(start_x, y, start_x + bar_width, y + bar_height)
        bar_gradient.setColorAt(0, QColor("#6BA8FF"))
        bar_gradient.setColorAt(1, QColor("#3A70E0"))

        painter.setBrush(bar_gradient)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(start_x, y, bar_width, bar_height, 12, 12)

    arrow_color = QColor("#3A70E0") 
    painter.setBrush(arrow_color)
    painter.setPen(Qt.NoPen)

    center_x = start_x + bar_width + 30
    center_y = 138  

    arrow_width = 30    
    arrow_height = 28  
    bar_thickness = 10   
    bar_length = 100    

    top_arrow = [
        QPoint(center_x, center_y - bar_length // 2 - arrow_height),  
        QPoint(center_x - arrow_width // 2, center_y - bar_length // 2),  
        QPoint(center_x + arrow_width // 2, center_y - bar_length // 2),  
    ]
    painter.drawPolygon(top_arrow)

    
    painter.drawRect(center_x - bar_thickness // 2, center_y - bar_length // 2, bar_thickness, bar_length)

    
    bottom_arrow = [
        QPoint(center_x, center_y + bar_length // 2 + arrow_height),  
        QPoint(center_x - arrow_width // 2, center_y + bar_length // 2),  
        QPoint(center_x + arrow_width // 2, center_y + bar_length // 2),  
    ]
    painter.drawPolygon(bottom_arrow)

    painter.end()
    
    return QIcon(pixmap)

# --- FileScannerWorker ---
class FileScannerWorker(QThread):
    progress = Signal(str)
    result = Signal(list)
    finished = Signal()

    def __init__(self, source_dir, extensions): 
        super().__init__()
        self.source_dir = source_dir
        self.extensions = [ext.strip().lower() for ext in extensions if ext.strip()] 
        self.files_data = []

    def run(self):
        if not self.extensions:
            self.progress.emit("Error: No valid file extensions specified.")
            self.result.emit([])
            self.finished.emit()
            return

        ext_str = ', '.join(self.extensions)
        self.progress.emit(f"Scanning '{self.source_dir}' for files matching: {ext_str}...")
        try:
            source_path = Path(self.source_dir)
            count = 0
            # Iterate through all files and filter by extension
            for file_path in source_path.rglob('*'):
                if file_path.is_file() and file_path.suffix.lower() in self.extensions:
                    try:
                        mod_ts = os.path.getmtime(file_path)
                        mod_dt = datetime.fromtimestamp(mod_ts)
                        self.files_data.append({
                           'path': file_path,
                            'mod_time_ts': mod_ts,
                            'mod_time_dt': mod_dt
                        })
                        count += 1
                        if count % 100 == 0:
                            self.progress.emit(f"Scanned {count} matching files...")
                    except Exception as e:
                        self.progress.emit(f"Error accessing {file_path}: {e}")

            self.files_data.sort(key=lambda x: x['mod_time_ts'])
            self.progress.emit(f"Scan complete. Found {len(self.files_data)} files matching {ext_str}.")
            self.result.emit(self.files_data)
        except Exception as e:
            self.progress.emit(f"Error during scanning: {e}")
            self.result.emit([])
        finally:
            self.finished.emit()

# --- FileCopyWorker --- 
class FileCopyWorker(QThread):
    progress = Signal(int, int, str)
    finished = Signal(bool, str)

    def __init__(self, groups_data, dest_dir,
group_folder_names):
        super().__init__()
        self.groups_data = groups_data
        self.dest_dir = Path(dest_dir)
        self.group_folder_names = group_folder_names

    def sanitize_folder_name(self, name):
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', name)
        name = name.strip('. ')
        return name or "Invalid_Name"

    def run(self):
        total_files = sum(len(g) for g in self.groups_data)
        copied = 0
        errors = 0
        if len(self.groups_data) != len(self.group_folder_names):
            msg = f"Mismatch between group data ({len(self.groups_data)}) and folder names ({len(self.group_folder_names)})."
            self.progress.emit(0, total_files, f"ERROR: {msg}")
            self.finished.emit(False, msg)
            return
        self.progress.emit(copied, total_files, "Starting copy process...")
        try:
            for idx, group in enumerate(self.groups_data):
                if not group:
                   continue
                raw_name = self.group_folder_names[idx]
                folder_name = self.sanitize_folder_name(raw_name)
                target = self.dest_dir / folder_name
                try:
                    target.mkdir(parents=True, exist_ok=True)
                    log_name = f"'{raw_name}'" if raw_name == folder_name else f"'{raw_name}' (sanitized to '{folder_name}')"
                    self.progress.emit(copied, total_files, f"Using folder: {log_name}")
                except Exception as e:
                    self.progress.emit(copied, total_files, f"ERROR creating folder '{folder_name}': {e}")
                    errors += len(group)
                    continue
                for fpath in group:
                    if not isinstance(fpath, Path):
                       self.progress.emit(copied, total_files, f"Skipping invalid item: {type(fpath)}")
                       errors += 1
                       continue
                    dest = target / fpath.name
                    try:
                        if not fpath.exists():
                            self.progress.emit(copied, total_files, f"ERROR missing '{fpath.name}'")
                            errors += 1
                            continue
                        shutil.copy2(fpath, dest)
                        copied += 1
                        if copied % 10 == 0 or \
                           copied == total_files:
                            self.progress.emit(copied, total_files, f"Copied {copied}/{total_files} files...")
                    except Exception as e:
                        self.progress.emit(copied, total_files, f"ERROR copying '{fpath.name}': {e}")
                        errors += 1
            final = f"Copy finished. "
            final += f"{copied}/{total_files} files copied."
            if errors:
                final += f" {errors} errors."
                self.finished.emit(False, final)
            else:
                self.finished.emit(True, final)
        except Exception as e:
            self.finished.emit(False, f"Critical error: {e}")


# --- DraggableListWidget --- 
class DraggableListWidget(QListWidget):
    item_dropped = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)

    def startDrag(self, supportedActions):
        items = self.selectedItems()
        if not items:
            return
        mime = QMimeData()
        paths = [it.data(Qt.UserRole) for it in items if isinstance(it.data(Qt.UserRole), Path)]
        if not paths:
            return
        try:
            data = pickle.dumps(paths)
            mime.setData(CUSTOM_MIME_TYPE, QByteArray(data))
        except Exception as e:
            print(f"Drag serialize error: {e}")
            return
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.MoveAction | Qt.CopyAction, Qt.MoveAction)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(CUSTOM_MIME_TYPE):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(CUSTOM_MIME_TYPE):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if not event.mimeData().hasFormat(CUSTOM_MIME_TYPE):
            event.ignore()
            return
        src = event.source()
        if not isinstance(src, QListWidget):
            event.ignore()
            return
        data = event.mimeData().data(CUSTOM_MIME_TYPE)
        try:
            paths = pickle.loads(bytes(data))
        except Exception as e:
            print(f"Drop deserialize error: {e}")
            event.ignore()
            return
        if not isinstance(paths, list):
            event.ignore()
            return
        pt = event.position().toPoint()
        target_item = self.itemAt(pt)
        row = self.row(target_item) if target_item else self.count()
        added = []
        for p in paths:
            if isinstance(p, Path):
                text = p.name
                try:
                    ts = os.path.getmtime(p)
                    ts_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
                    text = f"{p.name} ({ts_str})"
                except:
                    text = f"{p.name} (time unavailable)"
                itm = QListWidgetItem(text)
                itm.setData(Qt.UserRole, p)
                itm.setToolTip(str(p))
                self.insertItem(row, itm)
                added.append(p)
                row += 1
        external = (src is not self) and (event.proposedAction() == Qt.MoveAction)
        if external:
            to_remove = [src.item(i) for i in range(src.count()) if src.item(i).data(Qt.UserRole) in added]
            for itm in to_remove:
                r = src.row(itm)
                if r != -1:
                    src.takeItem(r)
            event.setDropAction(Qt.MoveAction)
            event.accept()
        else:
            event.acceptProposedAction()
        self.item_dropped.emit()


# --- Main Application ---
class FileCascadeApp(QWidget):
    EDITABLE_TITLE_STYLE_READONLY = """
        QLineEdit {
            background-color: transparent;
            border: none;
            font-weight: bold; padding: 2px;
        }
    """
    EDITABLE_TITLE_STYLE_EDITING = """
        QLineEdit {
            border: 1px solid #cccccc; font-weight: normal;
            padding: 1px;
        }
    """

    def __init__(self):
        super().__init__()
        self.setWindowIcon(create_app_icon())
        self.setWindowTitle("File Cascade v1.3.0")
        self.setMinimumSize(800, 600)

        self.source_dir = ""
        self.dest_dir = ""
        self.original_scanned_files = []
        self.groups_widgets = []
        self.group_ui_elements = []

        # Settings
        self.time_threshold_minutes = DEFAULT_TIME_THRESHOLD_MINUTES
        self.manual_grouping_enabled = False
        self.manual_group_count = DEFAULT_MANUAL_GROUP_COUNT
        self.folder_name_pattern = DEFAULT_FOLDER_NAME_PATTERN
        self.group_title_editing_enabled = False
        self.file_extensions = DEFAULT_EXTENSIONS # New state variable

        # Icons
        self.add_icon = create_icon('+')
        self.remove_icon = create_icon('x', color="red")

        # Layouts
        self.main_layout = QVBoxLayout(self)
        self.top_layout = QHBoxLayout()
        self.settings_layout_top_row = QHBoxLayout() # Renamed for clarity
        self.settings_layout_mid_row = QHBoxLayout() # Renamed for clarity
        self.settings_layout_bottom_row = QHBoxLayout() # New row for extensions
        self.groups_area_layout = QVBoxLayout()
        self.bottom_layout = QVBoxLayout()

        # Source/Dest Widgets
        self.source_label = QLabel("Source:")
        self.source_entry = QLineEdit(); self.source_entry.setReadOnly(True)
        self.source_button = QPushButton("Browse..."); self.source_button.clicked.connect(self.select_source_directory)
        self.dest_label = QLabel("Destination:")
        self.dest_entry = QLineEdit(); self.dest_entry.setReadOnly(True)
        self.dest_button = QPushButton("Browse..."); self.dest_button.clicked.connect(self.select_dest_directory)

        # Grouping Settings Row 1 (settings_layout_top_row)
        self.threshold_label = QLabel("Time Threshold (min):")
        self.threshold_spinbox = QSpinBox(); self.threshold_spinbox.setRange(1,1440)
        self.threshold_spinbox.setValue(self.time_threshold_minutes)
        self.threshold_spinbox.valueChanged.connect(self._on_threshold_changed)
        self.manual_group_checkbox = QCheckBox("Manual Group Count:")
        self.manual_group_checkbox.stateChanged.connect(self._on_manual_toggle)
        self.manual_group_count_spinbox = QSpinBox(); self.manual_group_count_spinbox.setRange(1,1000)
        self.manual_group_count_spinbox.setValue(self.manual_group_count)
        self.manual_group_count_spinbox.setEnabled(self.manual_grouping_enabled)
        self.manual_group_count_spinbox.valueChanged.connect(self._on_manual_count_changed)
        self.regroup_button = QPushButton("Apply Grouping Settings")
        self.regroup_button.clicked.connect(self.regroup_files); self.regroup_button.setEnabled(False)

        # Naming/Editing Settings Row 2 (settings_layout_mid_row)
        self.folder_pattern_label = QLabel("Default Folder Pattern:")
        self.folder_pattern_input = QLineEdit(); self.folder_pattern_input.setText(self.folder_name_pattern)
        self.folder_pattern_input.setToolTip("Pattern for destination folders (use {num})")
        self.folder_pattern_input.textChanged.connect(self._on_folder_pattern_changed)
        self.title_edit_checkbox = QCheckBox("Enable Group Title Editing")
        self.title_edit_checkbox.setToolTip("Toggle manual group title editing.")
        self.title_edit_checkbox.stateChanged.connect(self._on_title_edit_toggle)

        # Extension Settings Row 3 (settings_layout_bottom_row) - New
        self.extensions_label = QLabel("File Extensions:")
        self.extensions_input = QLineEdit()
        self.extensions_input.setText(self.file_extensions)
        self.extensions_input.setToolTip("Comma-separated list of extensions (e.g., .csv, .txt, .log)")
        self.extensions_input.textChanged.connect(self._on_extensions_changed)

        # Groups Scroll Area
        self.groups_scroll_area = QScrollArea(); self.groups_scroll_area.setWidgetResizable(True)
        self.groups_widget_container = QWidget(); self.groups_widget_container.setLayout(self.groups_area_layout)
        self.groups_widget_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.groups_scroll_area.setWidget(self.groups_widget_container)
        self.placeholder_label = QLabel("1. Select Source Directory to scan for files.")
        self.groups_area_layout.addWidget(self.placeholder_label, 0, Qt.AlignTop)

        # Copy & Log
        self.copy_button = QPushButton("Copy Files to Destination"); self.copy_button.clicked.connect(self.start_copy)
        self.copy_button.setEnabled(False)
        self.progress_bar = QProgressBar(); self.progress_bar.setVisible(False)
        self.log_label = QLabel("Process Log:")
        self.log_area = QTextEdit(); self.log_area.setObjectName("log_area")
        self.log_area.setReadOnly(True); self.log_area.setMinimumHeight(100)
        self.log_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)

        # Assemble Layouts
        top_frame = QFrame(); top_frame.setLayout(self.top_layout)
        self.top_layout.addWidget(self.source_label); self.top_layout.addWidget(self.source_entry,1)
        self.top_layout.addWidget(self.source_button);
        self.top_layout.addSpacing(20)
        self.top_layout.addWidget(self.dest_label); self.top_layout.addWidget(self.dest_entry,1)
        self.top_layout.addWidget(self.dest_button)

        settings_frame_top = QFrame(); settings_frame_top.setLayout(self.settings_layout_top_row)
        self.settings_layout_top_row.addWidget(self.threshold_label); self.settings_layout_top_row.addWidget(self.threshold_spinbox)
        self.settings_layout_top_row.addSpacing(15);
        self.settings_layout_top_row.addWidget(self.manual_group_checkbox)
        self.settings_layout_top_row.addWidget(self.manual_group_count_spinbox); self.settings_layout_top_row.addStretch(1)
        self.settings_layout_top_row.addWidget(self.regroup_button)

        settings_frame_mid = QFrame(); settings_frame_mid.setLayout(self.settings_layout_mid_row)
        self.settings_layout_mid_row.addWidget(self.folder_pattern_label); self.settings_layout_mid_row.addWidget(self.folder_pattern_input,1)
        self.settings_layout_mid_row.addSpacing(15);
        self.settings_layout_mid_row.addWidget(self.title_edit_checkbox)
        self.settings_layout_mid_row.addStretch(1)

        # New layout for extensions
        settings_frame_bottom = QFrame(); settings_frame_bottom.setLayout(self.settings_layout_bottom_row)
        self.settings_layout_bottom_row.addWidget(self.extensions_label)
        self.settings_layout_bottom_row.addWidget(self.extensions_input, 1) # Make it stretch

        bottom_frame = QFrame(); bottom_frame.setLayout(self.bottom_layout)
        bottom_frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.bottom_layout.addWidget(self.copy_button);
        self.bottom_layout.addWidget(self.progress_bar)
        self.bottom_layout.addWidget(self.log_label); self.bottom_layout.addWidget(self.log_area)

        self.main_layout.addWidget(top_frame)
        self.main_layout.addWidget(settings_frame_top) # Add the rows
        self.main_layout.addWidget(settings_frame_mid)
        self.main_layout.addWidget(settings_frame_bottom) # Add the new extensions row
        self.main_layout.addWidget(self.groups_scroll_area,1)
        self.main_layout.addWidget(bottom_frame)

        self._apply_title_editing_state()
        self.log("Application started. Select source directory.")
        self.main_layout.addWidget(bottom_frame)
        separator_line = QFrame()
        separator_line.setFrameShape(QFrame.HLine)
        separator_line.setFrameShadow(QFrame.Sunken)
        self.main_layout.addWidget(separator_line)
        
        footer_label = QLabel("Copyright © 2025 | License: MIT | Creator: UnseenScholar")
        footer_label.setAlignment(Qt.AlignCenter)
        footer_label.setStyleSheet("color: gray; font-size: 10px; padding: 5px;")
        self.main_layout.addWidget(footer_label)
    # --- Settings Handlers ---
    def _set_settings_enabled(self, enabled):
        self.threshold_spinbox.setEnabled(enabled and not self.manual_grouping_enabled)
        self.manual_group_checkbox.setEnabled(enabled)
        self.manual_group_count_spinbox.setEnabled(enabled and self.manual_grouping_enabled)
        self.folder_pattern_input.setEnabled(enabled)
        self.title_edit_checkbox.setEnabled(enabled)
        self.extensions_input.setEnabled(enabled) # Enable/disable extension input
        self.log(f"Setting UI enabled={enabled}, title_editing_enabled={self.group_title_editing_enabled}")
        for ui in self.group_ui_elements:
            
            current_readonly = ui['title_edit'].isReadOnly()
            desired_readonly = not (enabled and self.group_title_editing_enabled)
            if current_readonly != desired_readonly:
                ui['title_edit'].setReadOnly(desired_readonly)
                ui['title_edit'].update()  # Force UI refresh
                self.log(f"Group {ui['title_edit'].objectName()}: readOnly set to {desired_readonly}")
        self.regroup_button.setEnabled(enabled and bool(self.original_scanned_files))

    def _on_threshold_changed(self, value):
        self.time_threshold_minutes = value
        self.log(f"Time threshold set to {value} minutes.")

    def _on_manual_toggle(self, state):
        self.manual_grouping_enabled = (state == Qt.Checked)
        self.manual_group_count_spinbox.setEnabled(self.manual_grouping_enabled)
        self.threshold_spinbox.setEnabled(not self.manual_grouping_enabled)
        self.log(f"Manual grouping {'enabled' if self.manual_grouping_enabled else 'disabled'}.")

    def _on_manual_count_changed(self, value):
        self.manual_group_count = value
        self.log(f"Manual group count set to {value}.")

    def _on_folder_pattern_changed(self, text):
        self.folder_name_pattern = text
        self.log(f"Folder name pattern set to: {text}")

    
    def _on_extensions_changed(self, text):
        self.file_extensions = text
        # Trigger a rescan here or just log
        self.log(f"File extensions set to: {text}. Re-scan source to apply.")
        # If you want automatic rescan on change:
        # if self.source_dir:
        #     self.log("Extensions changed. Re-scanning source directory...")
        #     self.start_file_scan()


    def _on_title_edit_toggle(self, state):
        print(f"DEBUG: Title edit toggle called with state={state}")
        if not self.title_edit_checkbox:
            print("ERROR: title_edit_checkbox is None!")
            return 
        print(f"DEBUG: Checkbox state: {self.title_edit_checkbox.checkState()}")
        self.group_title_editing_enabled = (self.title_edit_checkbox.isChecked())
        self.log(f"Group title editing {'enabled' if self.group_title_editing_enabled else 'disabled'}.")
        self._apply_title_editing_state()
        
        if not self.group_title_editing_enabled:
            self.update_all_group_labels()

    def _apply_title_editing_state(self):
        editing = self.group_title_editing_enabled
        style = self.EDITABLE_TITLE_STYLE_EDITING if editing else self.EDITABLE_TITLE_STYLE_READONLY
        self.log(f"Applying title editing state: {'enabled' if editing else 'disabled'}")
        for ui in self.group_ui_elements:
            if not ui or not ui['title_edit']:
                print("ERROR: Invalid UI element in group_ui_elements!")
                continue  
            te = ui['title_edit']
            te.setReadOnly(not editing)
            te.setStyleSheet(style)
            te.update()  # Force UI refresh
            self.log(f"Group {ui['title_edit'].objectName()}: readOnly={te.isReadOnly()}, style applied")
        if not editing:
            for i, ui in enumerate(self.group_ui_elements):
                 ui['title_edit'].setText(f"{DEFAULT_GROUP_TITLE_PREFIX} {i+1}")
        QApplication.processEvents()

    # --- Display & Manage Groups --- 
    def clear_groups_display(self):
        self.groups_widgets.clear()
        self.group_ui_elements.clear()
        while self.groups_area_layout.count():
            it = self.groups_area_layout.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
            del it
        self.placeholder_label = None

    def display_groups(self, groups):
        self.clear_groups_display()
        if not groups:
            lbl = QLabel("No file groups to display (check source/extensions).") 
            self.groups_area_layout.addWidget(lbl,0,Qt.AlignTop)
            self.check_copy_button_state()
            return
        widgets = []
        for idx, grp in enumerate(groups):
            hl = QHBoxLayout()
            te = QLineEdit(); te.setObjectName(f"group_title_{idx+1}")
            te.setText(f"{DEFAULT_GROUP_TITLE_PREFIX} {idx+1}")
            te.setReadOnly(not self.group_title_editing_enabled)
            te.setStyleSheet(self.EDITABLE_TITLE_STYLE_READONLY if not self.group_title_editing_enabled else self.EDITABLE_TITLE_STYLE_EDITING)
            add = QPushButton(self.add_icon,""); rm = QPushButton(self.remove_icon,"")
            add.setToolTip("Add group below"); rm.setToolTip("Remove this group")
            add.setFixedSize(20,20); rm.setFixedSize(20,20)
            hl.addWidget(te,1); hl.addWidget(add); hl.addWidget(rm)
            hdr = QWidget(); hdr.setLayout(hl)
            lw = DraggableListWidget(); lw.setObjectName(f"group_list_{idx+1}"); lw.setMinimumHeight(80)
            lw.item_dropped.connect(self.on_item_dropped)
            self.group_ui_elements.append({'header_widget': hdr, 'title_edit': te, 'add_btn': add, 'remove_btn': rm, 'list_widget': lw})
            self.groups_widgets.append(lw)
            for fi in grp:
                ts = fi['mod_time_dt'].strftime('%Y-%m-%d %H:%M:%S')
                txt = f"{fi['path'].name} ({ts})"
                itm = QListWidgetItem(txt); itm.setData(Qt.UserRole, fi['path']);
                itm.setToolTip(str(fi['path']))
                lw.addItem(itm)
            if idx>0:
                sep = QFrame(); sep.setFrameShape(QFrame.HLine); sep.setFrameShadow(QFrame.Sunken)
                widgets.append(sep)
            widgets.extend([hdr, lw])
            add.clicked.connect(lambda _,i=idx: self.add_group_below(i))
            rm.clicked.connect(lambda _,i=idx: self.remove_group(i))
        for w in widgets:
            self.groups_area_layout.addWidget(w)
        self.groups_area_layout.addStretch(1)
        self.update_all_group_labels()
        self.log(f"Displayed {len(self.groups_widgets)} groups.")
        self.check_copy_button_state()

    def add_group_below(self, above):
        self.log(f"Adding new group below {above+1}")
        idx = above+1
        hl = QHBoxLayout(); te=QLineEdit(); add=QPushButton(self.add_icon,""); rm=QPushButton(self.remove_icon,"")
        te.setText(f"{DEFAULT_GROUP_TITLE_PREFIX} {idx+1}"); te.setReadOnly(not self.group_title_editing_enabled)
        te.setStyleSheet(self.EDITABLE_TITLE_STYLE_READONLY if not self.group_title_editing_enabled else self.EDITABLE_TITLE_STYLE_EDITING)
        add.setToolTip("Add group below"); rm.setToolTip("Remove this group"); add.setFixedSize(20,20); rm.setFixedSize(20,20)
        hl.addWidget(te,1); hl.addWidget(add); hl.addWidget(rm)
        hdr=QWidget(); hdr.setLayout(hl)
        lw=DraggableListWidget(); lw.setMinimumHeight(80); lw.item_dropped.connect(self.on_item_dropped)
        new_ui={'header_widget':hdr,'title_edit':te,'add_btn':add,'remove_btn':rm,'list_widget':lw}
        self.group_ui_elements.insert(idx,new_ui); self.groups_widgets.insert(idx,lw)
        above_widget=self.group_ui_elements[above]['list_widget']
        pos=self.groups_area_layout.indexOf(above_widget)+1
        if idx>0:
            sep=QFrame(); sep.setFrameShape(QFrame.HLine); sep.setFrameShadow(QFrame.Sunken)
            self.groups_area_layout.insertWidget(pos,sep); pos+=1
        self.groups_area_layout.insertWidget(pos,hdr); pos+=1
        self.groups_area_layout.insertWidget(pos,lw)
        self._reconnect_group_buttons(); self.update_all_group_labels(); self.check_copy_button_state()

    def remove_group(self, i):
        if not(0<=i<len(self.group_ui_elements)): return
        if len(self.group_ui_elements)<=1:
            QMessageBox.warning(self,"Cannot Remove","Cannot remove the last group.");
            return
        self.log(f"Removing group {i+1}")
        ui=self.group_ui_elements[i]
        hdr, lw = ui['header_widget'], ui['list_widget']
        idx = self.groups_area_layout.indexOf(hdr)
        sep=None
        if idx>0:
            prev=self.groups_area_layout.itemAt(idx-1).widget()
            if isinstance(prev,QFrame): sep=prev
        self.groups_area_layout.removeWidget(hdr); hdr.deleteLater()
        self.groups_area_layout.removeWidget(lw); lw.deleteLater()
        if sep: self.groups_area_layout.removeWidget(sep); sep.deleteLater()
        del self.group_ui_elements[i]; del self.groups_widgets[i]
        self._reconnect_group_buttons(); self.update_all_group_labels(); self.check_copy_button_state()

    def _reconnect_group_buttons(self):
        for idx, ui in enumerate(self.group_ui_elements):
            try:
                ui['add_btn'].clicked.disconnect(); ui['remove_btn'].clicked.disconnect()
            except RuntimeError:
                pass
            ui['add_btn'].clicked.connect(lambda _,i=idx: self.add_group_below(i))
            ui['remove_btn'].clicked.connect(lambda _,i=idx: self.remove_group(i))

    def update_single_group_label(self, gi):
        ui = self.group_ui_elements[gi]
        te = ui['title_edit']
        lw = ui['list_widget']
        cnt = lw.count()
        if self.group_title_editing_enabled:
            txt = te.text().strip()
            if not txt:
                te.setText(f"{DEFAULT_GROUP_TITLE_PREFIX} {gi+1}")
        else:
            st, et = "N/A", "N/A"
            if cnt > 0 and self.original_scanned_files:
                paths = [lw.item(i).data(Qt.UserRole) for i in range(cnt)]
                od = {str(f['path']): f for f in self.original_scanned_files}
                infos = [od[str(p)] for p in paths if str(p) in od]
                if infos:
                    infos.sort(key=lambda x: x['mod_time_ts'])
                    st = infos[0]['mod_time_dt'].strftime('%H:%M:%S')
                    et = infos[-1]['mod_time_dt'].strftime('%H:%M:%S')
            new = f"{DEFAULT_GROUP_TITLE_PREFIX} {gi+1} ({cnt} files) [{st} - {et}]"
            if te.text() != new:
                te.setText(new)
                te.update()  # Force UI refresh

    def update_all_group_labels(self):
        for i in range(len(self.group_ui_elements)):
            self.update_single_group_label(i)

    # --- Copy Handlers --- 
    @Slot(int,int,str)
    def update_copy_progress(self, cur, tot, msg):
        self.progress_bar.setValue(cur)
        self.log(msg)

    @Slot(bool,str)
    def on_copy_finished(self, success, msg):
        self.log(msg)
        self.source_button.setEnabled(True)
        self.dest_button.setEnabled(True)
        self._set_settings_enabled(True)
        for ui in self.group_ui_elements:
            ui['list_widget'].setEnabled(True)
            ui['add_btn'].setEnabled(True)
            ui['remove_btn'].setEnabled(True)
        self.copy_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        if success:
            QMessageBox.information(self,"Copy Complete",msg)
        else:
            QMessageBox.critical(self,"Copy Errors",msg)

    # --- Drag/Drop Handler --- 
    @Slot()
    def on_item_dropped(self):
        self.log("Group modified via drag and drop.")
        self.update_all_group_labels()
        self.check_copy_button_state()

    # --- File Copy Trigger --- 
    def start_copy(self):
        if not self.dest_dir:
            QMessageBox.warning(self,"Destination Missing","Select destination directory.")
            return
        destp=Path(self.dest_dir)
        if not destp.is_dir():
            reply=QMessageBox.question(self,"Create Directory?",
                f"Destination '{self.dest_dir}' does not exist. Create?",
                QMessageBox.Yes|QMessageBox.No, QMessageBox.No)
            if reply==QMessageBox.No: return
            try:
                destp.mkdir(parents=True,exist_ok=True)
                self.log(f"Destination created: {self.dest_dir}")
            except Exception as e:
                QMessageBox.critical(self,"Error",f"Could not create destination: {e}")
                return
        final_groups=[]; names=[]; total=0
        for idx, ui in enumerate(self.group_ui_elements):
            lw=ui['list_widget']; files=[]
            for i in range(lw.count()):
                it=lw.item(i); p=it.data(Qt.UserRole)
                if isinstance(p,Path): files.append(p); total+=1
                else: self.log(f"Invalid item skipped: {it.text()}")
            if files:
                final_groups.append(files)
                if self.group_title_editing_enabled:
                    nm=ui['title_edit'].text().strip() or f"{DEFAULT_GROUP_TITLE_PREFIX}_{idx+1}_Untitled"
                else:
                    pat=self.folder_pattern_input.text()
                    if "{num}" not in pat: pat=DEFAULT_FOLDER_NAME_PATTERN
                    nm=pat.replace("{num}",str(idx+1))
                names.append(nm)
            else:
                self.log(f"Skipping empty group {idx+1}")
        if total==0:
            QMessageBox.information(self,"Empty Groups","All groups are empty.")
            return
        # disable UI
        self.source_button.setEnabled(False); self.dest_button.setEnabled(False)
        self.copy_button.setEnabled(False); self._set_settings_enabled(False); self.regroup_button.setEnabled(False)
        for ui in self.group_ui_elements:
            ui['list_widget'].setEnabled(False); ui['add_btn'].setEnabled(False); ui['remove_btn'].setEnabled(False)
        self.progress_bar.setVisible(True); self.progress_bar.setRange(0,total); self.progress_bar.setValue(0)
        self.log(f"Starting copy: {len(final_groups)} groups, {total} files...")
        self.copy_thread = FileCopyWorker(final_groups, self.dest_dir, names)
        self.copy_thread.progress.connect(self.update_copy_progress)
        self.copy_thread.finished.connect(self.on_copy_finished)
        self.copy_thread.start()

    # --- Logging --- 
    def log(self, message):
        ts=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_area.append(f"[{ts}] {message}")
        QApplication.processEvents()
        self.log_area.verticalScrollBar().setValue(self.log_area.verticalScrollBar().maximum())


    # --- Directory Selection ---
    def select_source_directory(self):
        d=QFileDialog.getExistingDirectory(self,"Select Source Directory")
        if d:
            self.source_dir=d;
            self.source_entry.setText(d)
            self.log(f"Source directory selected: {d}")
            self.clear_groups_display();
            self.original_scanned_files.clear(); self.regroup_button.setEnabled(False)
            self.placeholder_label = QLabel("Scanning... Please wait.")
            self.groups_area_layout.addWidget(self.placeholder_label,0,Qt.AlignTop)
            QApplication.processEvents();
            self.start_file_scan(); self.check_copy_button_state()

    def select_dest_directory(self):
        d=QFileDialog.getExistingDirectory(self,"Select Destination Directory")
        if d:
            self.dest_dir=d;
            self.dest_entry.setText(d)
            self.log(f"Destination directory selected: {d}")
            self.check_copy_button_state()

    # --- Button State Checks --- 
    def check_copy_button_state(self):
        en=bool(self.source_dir and self.dest_dir and self.groups_widgets)
        if en:
            cnt=sum(lw.count() for lw in self.groups_widgets)
            if cnt==0: en=False
        self.copy_button.setEnabled(en)

    def check_regroup_button_state(self):
        self.regroup_button.setEnabled(bool(self.original_scanned_files))

    # --- File Scanning ---
    def start_file_scan(self):
        if not self.source_dir:
            self.log("Error: Source directory not set.")
            self.clear_groups_display()
            lbl=QLabel("1. Select Source Directory to scan for files.")
            self.groups_area_layout.addWidget(lbl,0,Qt.AlignTop)
            return

        # Get extensions from input field
        extensions_text = self.extensions_input.text()
        extensions_list = [ext.strip() for ext in extensions_text.split(',') if ext.strip()]
        if not extensions_list:
             QMessageBox.warning(self, "Missing Extensions", "Please enter at least one file extension (e.g., .csv).")
             self.log("Scan cancelled: No extensions provided.")
             # Re-enable source/dest buttons if needed
             self.source_button.setEnabled(True); self.dest_button.setEnabled(True)
             return

        self.log(f"Starting scan with extensions: {', '.join(extensions_list)}")

        self.source_button.setEnabled(False); self.dest_button.setEnabled(False);
        self.copy_button.setEnabled(False)
        self._set_settings_enabled(False); self.regroup_button.setEnabled(False)
        for ui in self.group_ui_elements:
            ui['list_widget'].setEnabled(False); ui['add_btn'].setEnabled(False); ui['remove_btn'].setEnabled(False)
        self.progress_bar.setVisible(True); self.progress_bar.setRange(0,0) 

        # Pass extensions to the worker
        self.scanner_thread = FileScannerWorker(self.source_dir, extensions_list)
        self.scanner_thread.progress.connect(self.log)
        self.scanner_thread.result.connect(self.process_scan_results)
        self.scanner_thread.finished.connect(self.on_scan_finished)
        self.scanner_thread.start()

    @Slot(list)
    def process_scan_results(self, files_data):
        self.original_scanned_files = files_data
        if self.placeholder_label:
            self.placeholder_label.deleteLater(); self.placeholder_label=None
            QApplication.processEvents()
        if not files_data:
            self.log("No matching files found or error during scan.")
            lbl=QLabel("No matching files found in the selected directory for the specified extensions.") 
            self.groups_area_layout.addWidget(lbl,0,Qt.AlignTop)
            return
        self.log(f"Scan found {len(files_data)} files. Applying grouping...")
        self.apply_grouping(files_data)

    @Slot()
    def on_scan_finished(self):
        self.source_button.setEnabled(True); self.dest_button.setEnabled(True)
        self._set_settings_enabled(True)
        for ui in self.group_ui_elements:
            ui['list_widget'].setEnabled(True); ui['add_btn'].setEnabled(True); ui['remove_btn'].setEnabled(True)
        self.progress_bar.setVisible(False); self.progress_bar.setRange(0,100) # Reset progress bar
        self.log("Scan finished.")
        self.check_copy_button_state();
        self.check_regroup_button_state()

    # --- Grouping Logic --- 
    def regroup_files(self):
        if not self.original_scanned_files:
            self.log("No scanned files available to regroup.")
            QMessageBox.information(self,"No Files","Scan for files first.")
            return
        self.log("Re-applying grouping settings...")
        self.apply_grouping(self.original_scanned_files)

    def apply_grouping(self, files):
        if self.manual_grouping_enabled:
            grps=self.group_files_manually(files,self.manual_group_count)
        else:
            grps=self.group_files_by_time(files,self.time_threshold_minutes)
        self.display_groups(grps)

    def group_files_by_time(self, files, th):
        self.log(f"Grouping by time ({th} min)...")
        if not files: return []
        groups=[]; cur=[files[0]]; last=files[0]['mod_time_ts']
        for fi in files[1:]:
            if fi['mod_time_ts'] - last <= timedelta(minutes=th).total_seconds():
                cur.append(fi); last=fi['mod_time_ts']
            else:
                groups.append(cur); cur=[fi]; last=fi['mod_time_ts']
        if cur: groups.append(cur)
        self.log(f"{len(groups)} groups formed.")
        return groups

    def group_files_manually(self, files, n):
        self.log(f"Grouping manually into {n} groups...")
        if not files or n<=0: return []
        per=math.ceil(len(files)/n) or 1
        grps=[[] for _ in range(n)]
        for i,fi in enumerate(files):
            idx=min(i//per, n-1)
            grps[idx].append(fi)
        self.log(f"{len(grps)} manual groups created.")
        return [g for g in grps if g]

# --- Application ---
if __name__ == '__main__':
    app = QApplication(sys.argv)
    sorter = FileCascadeApp()
    sorter.show()
    sys.exit(app.exec())