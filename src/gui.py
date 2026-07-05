import sys
import os
import html
import cv2
import logging
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QPushButton, QComboBox,
                             QRadioButton, QButtonGroup, QFileDialog, QListWidget,
                             QProgressBar, QTextEdit, QSpinBox, QCheckBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from stitcher import Gear360Stitcher
from metadata import MetadataHandler

class Worker(QThread):
    progress = pyqtSignal(int)
    log = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, files, camera_model, mode, scale_factor, output_dir=None):
        super().__init__()
        self.files = files
        self.camera_model = camera_model
        self.mode = mode # 'simple' or 'advanced'
        self.scale_factor = scale_factor
        self.output_dir = output_dir

    def run(self):
        try:
            stitcher = Gear360Stitcher(self.camera_model)
            meta_handler = MetadataHandler()

            total = len(self.files)
            # Security: Maximum allowed file size to prevent memory exhaustion (DoS)
            MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024 # 100 MB

            for i, file_path in enumerate(self.files):
                if not file_path.lower().endswith(('.jpg', '.jpeg', '.png')):
                    self.log.emit(f"Skipping {os.path.basename(file_path)} (not an image).")
                    continue

                try:
                    file_size = os.path.getsize(file_path)
                    if file_size > MAX_FILE_SIZE_BYTES:
                        self.log.emit(f"Skipping {os.path.basename(file_path)} (file too large, exceeds 100MB limit).")
                        continue
                except OSError as e:
                    logging.error(f"Failed to check file size for {file_path}: {e}")
                    self.log.emit(f"Skipping {os.path.basename(file_path)} (error accessing file).")
                    continue

                self.log.emit(f"Processing {os.path.basename(file_path)}...")

                img = cv2.imread(file_path)
                if img is None:
                    self.log.emit(f"Failed to load {os.path.basename(file_path)}")
                    continue

                # Setup output dimensions
                out_w = int(stitcher.src_width * self.scale_factor)
                out_h = out_w // 2

                # Check alignment mode
                if self.mode == "advanced":
                    self.log.emit("Attempting dynamic alignment...")
                    success = stitcher.find_misalignment(img)
                    if success:
                        self.log.emit("Dynamic alignment successful.")
                        stitcher.save_calibration() # Save as new default
                    else:
                        self.log.emit("Dynamic alignment failed. Falling back to saved calibration.")
                        stitcher.load_calibration()
                        stitcher.update_maps(out_w, out_h)
                else:
                    stitcher.update_maps(out_w, out_h)

                # Stitch
                self.log.emit("Stitching image...")
                out_img = stitcher.stitch(img)

                # Save
                filename = os.path.basename(file_path)
                name, ext = os.path.splitext(filename)
                out_name = f"{name}_stitched{ext}"

                if self.output_dir:
                    out_path = os.path.join(self.output_dir, out_name)
                else:
                    out_path = os.path.join(os.path.dirname(file_path), out_name)

                cv2.imwrite(out_path, out_img)

                # Metadata
                self.log.emit("Applying metadata...")
                meta_handler.process_metadata(file_path, out_path, out_w, out_h)

                self.log.emit(f"Saved to {out_path}")
                self.progress.emit(int((i+1)/total * 100))

        except Exception as e:
            # Security: Avoid leaking stack trace or sensitive paths to UI
            logging.error(f"Unexpected error during processing: {e}", exc_info=True)
            self.log.emit("An unexpected error occurred during processing.")

        self.log.emit("Processing complete.")
        self.finished.emit()

class DropListWidget(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setSelectionMode(QListWidget.ExtendedSelection)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            for item in self.selectedItems():
                self.takeItem(self.row(item))
        else:
            super().keyPressEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if os.path.isdir(path):
                    for root, _, files in os.walk(path):
                        for file in files:
                            if file.lower().endswith(('.jpg', '.jpeg', '.png')):
                                self.addItem(os.path.join(root, file))
                elif os.path.isfile(path) and path.lower().endswith(('.jpg', '.jpeg', '.png')):
                    self.addItem(path)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gear 360 Auto Stitcher")
        self.resize(600, 500)

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # Top controls
        top_layout = QHBoxLayout()

        self.camera_combo = QComboBox()
        self.camera_combo.addItems(["Gear 360 (2017)", "Gear 360 (2016)"])
        self.camera_combo.setToolTip("Select the Gear 360 camera model used to capture the images")

        lbl_camera = QLabel("&Camera Model:")
        lbl_camera.setBuddy(self.camera_combo)
        top_layout.addWidget(lbl_camera)
        top_layout.addWidget(self.camera_combo)

        top_layout.addStretch()

        self.scale_spin = QSpinBox()
        self.scale_spin.setRange(10, 100)
        self.scale_spin.setValue(100)
        self.scale_spin.setSuffix("%")
        self.scale_spin.setToolTip("Set the output image resolution scale")

        lbl_scale = QLabel("Output &Scale:")
        lbl_scale.setBuddy(self.scale_spin)
        top_layout.addWidget(lbl_scale)
        top_layout.addWidget(self.scale_spin)

        layout.addLayout(top_layout)

        # Mode selection
        mode_layout = QHBoxLayout()
        self.mode_group = QButtonGroup(self)

        self.radio_simple = QRadioButton("Si&mple Mode (Use Saved Calibration)")
        self.radio_simple.setChecked(True)
        self.radio_simple.setToolTip("Faster. Uses previously saved calibration data for stitching.")
        self.mode_group.addButton(self.radio_simple, 1)

        self.radio_adv = QRadioButton("&Advanced Mode (Dynamic Alignment per Image)")
        self.radio_adv.setToolTip("Slower. Attempts to dynamically calculate the best alignment for every single image.")
        self.mode_group.addButton(self.radio_adv, 2)

        mode_layout.addWidget(self.radio_simple)
        mode_layout.addWidget(self.radio_adv)
        layout.addLayout(mode_layout)

        # File list
        lbl_drag = QLabel("&Drag and Drop Images/Folders here, or use Add Files:")
        layout.addWidget(lbl_drag)
        self.file_list = DropListWidget()
        self.file_list.setToolTip("List of files to process. Drag and drop files, use Add Files button, and press Delete to remove selected.")
        lbl_drag.setBuddy(self.file_list)
        layout.addWidget(self.file_list)

        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_add = QPushButton("&Add Files...")
        self.btn_add.clicked.connect(self.browse_files)
        self.btn_add.setToolTip("Browse and add image files to the list")
        self.btn_clear = QPushButton("C&lear List")
        self.btn_clear.clicked.connect(self.file_list.clear)
        self.btn_process = QPushButton("S&tart Processing")
        self.btn_process.clicked.connect(self.start_processing)

        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_clear)
        btn_layout.addWidget(self.btn_process)
        layout.addLayout(btn_layout)

        # Progress and Log
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text)

        self.worker = None

        # Update button states based on list content
        self.file_list.model().rowsInserted.connect(self.update_button_states)
        self.file_list.model().rowsRemoved.connect(self.update_button_states)
        self.file_list.model().modelReset.connect(self.update_button_states)
        self.update_button_states()

    def browse_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Images",
            "",
            "Images (*.png *.jpg *.jpeg)"
        )
        if files:
            self.file_list.addItems(files)

    def update_button_states(self):
        has_files = self.file_list.count() > 0
        self.btn_clear.setEnabled(has_files)
        self.btn_process.setEnabled(has_files)
        if has_files:
            self.btn_process.setToolTip("Begin stitching process")
            self.btn_clear.setToolTip("Clear the list of files")
        else:
            self.btn_process.setToolTip("Add files to begin stitching")
            self.btn_clear.setToolTip("No files to clear")

    def start_processing(self):
        files = [self.file_list.item(i).text() for i in range(self.file_list.count())]
        if not files:
            self.log("No files to process.")
            return

        camera_model = self.camera_combo.currentText()
        mode = "simple" if self.radio_simple.isChecked() else "advanced"
        scale = self.scale_spin.value() / 100.0

        self.btn_process.setEnabled(False)
        self.progress_bar.setValue(0)
        self.log_text.clear()

        self.worker = Worker(files, camera_model, mode, scale)
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.log.connect(self.log)
        self.worker.finished.connect(self.on_processing_finished)
        self.worker.start()

    def log(self, msg):
        # Escape HTML to prevent injection, wrap in span so Qt parses it as rich text properly
        safe_msg = f"<span>{html.escape(msg)}</span>"
        self.log_text.append(safe_msg)

    def on_processing_finished(self):
        self.btn_process.setEnabled(True)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
