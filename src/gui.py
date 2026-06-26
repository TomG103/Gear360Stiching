import sys
import os
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
            for i, file_path in enumerate(self.files):
                if not file_path.lower().endswith(('.jpg', '.jpeg', '.png')):
                    self.log.emit(f"Skipping {os.path.basename(file_path)} (not an image).")
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
            self.log.emit(f"Error: {str(e)}")

        self.log.emit("Processing complete.")
        self.finished.emit()

class DropListWidget(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

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
        top_layout.addWidget(QLabel("Camera Model:"))
        top_layout.addWidget(self.camera_combo)

        top_layout.addStretch()

        self.scale_spin = QSpinBox()
        self.scale_spin.setRange(10, 100)
        self.scale_spin.setValue(100)
        self.scale_spin.setSuffix("%")
        top_layout.addWidget(QLabel("Output Scale:"))
        top_layout.addWidget(self.scale_spin)

        layout.addLayout(top_layout)

        # Mode selection
        mode_layout = QHBoxLayout()
        self.mode_group = QButtonGroup(self)

        self.radio_simple = QRadioButton("Simple Mode (Use Saved Calibration)")
        self.radio_simple.setChecked(True)
        self.mode_group.addButton(self.radio_simple, 1)

        self.radio_adv = QRadioButton("Advanced Mode (Dynamic Alignment per Image)")
        self.mode_group.addButton(self.radio_adv, 2)

        mode_layout.addWidget(self.radio_simple)
        mode_layout.addWidget(self.radio_adv)
        layout.addLayout(mode_layout)

        # File list
        layout.addWidget(QLabel("Drag and Drop Images or Folders here:"))
        self.file_list = DropListWidget()
        layout.addWidget(self.file_list)

        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_clear = QPushButton("Clear List")
        self.btn_clear.clicked.connect(self.file_list.clear)
        self.btn_process = QPushButton("Start Processing")
        self.btn_process.clicked.connect(self.start_processing)

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
        self.log_text.append(msg)

    def on_processing_finished(self):
        self.btn_process.setEnabled(True)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    # sys.exit(app.exec_()) # Commented out for headless test
    print("GUI initialized successfully.")
