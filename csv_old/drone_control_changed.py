import os
import cv2
import sys
import datetime
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget, QMessageBox, QFileDialog, QProgressBar, QGridLayout
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap, QImage
from djitellopy import Tello
from report_gen import DroneReportApp
from video_process import run



FLIGHTS_FOLDER = "flights"
if not os.path.exists(FLIGHTS_FOLDER):
    os.makedirs(FLIGHTS_FOLDER)

class MockTello:
    def __init__(self):
        self.is_flying = False
        self.stream_on = False

    def connect(self):
        print("Mock: Drone connected")

    def takeoff(self):
        if self.is_flying:
            print("Mock: Already flying!")
        else:
            print("Mock: Taking off...")
            self.is_flying = True

    def land(self):
        if not self.is_flying:
            print("Mock: Already landed!")
        else:
            print("Mock: Landing...")
            self.is_flying = False

    def streamon(self):
        self.stream_on = True
        print("Mock: Video stream started")

    def streamoff(self):
        self.stream_on = False
        print("Mock: Video stream stopped")

    def end(self):
        print("Mock: Drone disconnected")

class DroneControlApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Drone Control Panel")
        self.setGeometry(100, 100, 1000, 700)

        # Initialize Tello Drone
        self.drone = MockTello()
        self.drone.connect()
        self.is_flying = False
        self.recording = False
        self.flight_start_time = None
        self.flight_folder = None

        # Video Capture Variables
        self.video_stream_active = False
        self.video_capture = None
        
        # UI Layout
        self.init_ui()
        self.update_history_button()
        

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)

        # Connection status
        self.connection_status = QLabel("CONNECTED")
        self.connection_status.setStyleSheet("background-color: green; color: white; font-size: 18px; font-weight: bold;")
        self.connection_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.connection_status)

        # Content layout
        content_layout = QHBoxLayout()
        main_layout.addLayout(content_layout)

        # Left Panel
        left_panel = QVBoxLayout()

        # Battery Progress Bar
        self.battery_bar = QProgressBar()
        #self.battery_bar.setValue(self.battery_level)
        self.battery_bar.setStyleSheet("QProgressBar::chunk { background-color: green; }")
        left_panel.addWidget(QLabel("Battery:"))
        left_panel.addWidget(self.battery_bar)

        # Info Labels
        self.info_labels = {
            "Temperature": QLabel("20°C"),
            "Height": QLabel("0 cm"),
            "Speed": QLabel("0 cm/s"),
            "Data Transmitted": QLabel("0 MB"),
            "Flight Duration": QLabel("0 sec"),
        }
        for key, label in self.info_labels.items():
            left_panel.addWidget(QLabel(key + ":"))
            left_panel.addWidget(label)

        content_layout.addLayout(left_panel)

        # Center Panel (Live Stream)
        self.stream_label = QLabel("Drone Stream Placeholder")
        self.stream_label.setStyleSheet("background-color: #000; color: white; font-size: 14px; border: 1px solid #555;")
        self.stream_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stream_label.setFixedSize(800, 600)
        content_layout.addWidget(self.stream_label)

        # Bottom Controls
        controls_layout = QGridLayout()
        controls_layout.setSpacing(5)

        control_buttons = [
            ("Q", "Flip Left"), ("W", "Forward"), ("E", "Flip Right"), ("R", "Flip Forward"),
            ("A", "Left"), ("S", "Backward"), ("D", "Right"), ("F", "Flip Back"),
            ("Enter", "Take Off"), ("Space", "Land"),
            ("Up Arrow", "Up"), ("Down Arrow", "Down"),
            ("Left Arrow", "Rotate Left"), ("Right Arrow", "Rotate Right")
        ]

        positions = [
            (0, 0), (0, 1), (0, 2), (0, 3),
            (1, 0), (1, 1), (1, 2), (1, 3),
            (2, 0), (2, 1), (2, 2), (2, 3),
            (3, 0), (3, 1), (3, 2), (3, 3)
        ]

        for i, (key, action) in enumerate(control_buttons):
            button = QPushButton(f"{key}\n({action})")
            button.setFixedSize(150, 60)
            controls_layout.addWidget(button, *positions[i])

        main_layout.addLayout(controls_layout)

        # View Flight History Button
        history_button = QPushButton("View Flight History")
        history_button.setStyleSheet("font-size: 14px; padding: 10px;")
        history_button.clicked.connect(self.view_flight_history)
        main_layout.addWidget(history_button)
        
    def view_flight_history(self):
        """Open the report window to view flight history."""
        # Open the flight history report
        report_window = DroneReportApp()
        report_window.show()

        
    def keyPressEvent(self, event):
            if not self.is_flying:
                QMessageBox.warning(self, "Drone Status", "Το drone δεν είναι στον αέρα! Παρακαλώ απογειώστε το drone πρώτα.")
                return

            key = event.key()

            if key == Qt.Key.Key_W:
                print("Mock: Drone moving forward")
            elif key == Qt.Key.Key_S:
                print("Mock: Drone moving backward")
            elif key == Qt.Key.Key_A:
                print("Mock: Drone moving left")
            elif key == Qt.Key.Key_D:
                print("Mock: Drone moving right")
            elif key == Qt.Key.Key_Q:
                print("Mock: Drone rotating left")
            elif key == Qt.Key.Key_E:
                print("Mock: Drone rotating right")
            elif key == Qt.Key.Key_Up:
                print("Mock: Drone moving up")
            elif key == Qt.Key.Key_Down:
                print("Mock: Drone moving down")
            else:
                print("Key not mapped")

    # def start_video_stream(self):
    #     if not self.video_stream_active:
    #         self.drone.streamon()
    #         self.video_stream_active = True
    #         self.video_capture = cv2.VideoCapture('udp://0.0.0.0:11111')
    #         self.timer.start(30)

    # def stop_video_stream(self):
    #     if self.video_stream_active:
    #         self.timer.stop()
    #         self.video_stream_active = False
    #         self.drone.streamoff()
    #         if self.video_capture:
    #             self.video_capture.release()
    
    # def update_video_feed(self):
    #     if self.video_capture:
    #         ret, frame = self.video_capture.read()
    #         if ret:
    #             rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    #             height, width, channel = rgb_image.shape
    #             bytes_per_line = channel * width
    #             q_image = QImage(rgb_image.data, width, height, bytes_per_line, QImage.Format.Format_RGB888)
    #             self.video_label.setPixmap(QPixmap.fromImage(q_image))

    #             if self.recording:
    #                 self.video_writer.write(frame)

    def start_video_stream(self):
        if not self.video_stream_active:
            self.video_stream_active = True
            self.timer.start(30)

    def stop_video_stream(self):
        if self.video_stream_active:
            self.timer.stop()
            self.video_stream_active = False

    def update_video_feed(self):
        # Simulate video feed with a placeholder image
        placeholder_image = QImage(800, 400, QImage.Format.Format_RGB888)
        placeholder_image.fill(Qt.GlobalColor.lightGray)
        self.video_label.setPixmap(QPixmap.fromImage(placeholder_image))

    

    
    def takeoff(self):
        if self.is_flying:
            QMessageBox.warning(self, "Drone Status", "Το drone είναι ήδη στον αέρα!")
            return

        self.drone.takeoff()
        self.is_flying = True
        self.flight_start_time = datetime.datetime.now()

        # Create a folder for the flight
        self.flight_folder = os.path.join(FLIGHTS_FOLDER, f"Flight_{self.flight_start_time.strftime('%Y%m%d_%H%M%S')}")
        os.makedirs(self.flight_folder, exist_ok=True)

        self.start_video_stream()

    def land(self):
        if not self.is_flying:
            QMessageBox.warning(self, "Drone Status", "Το drone δεν είναι στον αέρα!")
            return

        self.drone.land()
        self.is_flying = False
        self.stop_video_stream()

        # Calculate flight duration
        flight_end_time = datetime.datetime.now()
        duration = flight_end_time - self.flight_start_time

        QMessageBox.information(self, "Drone Status", f"Η πτήση ολοκληρώθηκε!\nΔιάρκεια: {duration}")

        # Process the flight video
        self.process_flight_video(duration)

    def process_flight_video(self, duration):
        """Process the flight video using video_process.py."""
        # Supported video formats
        video_formats = [".mp4", ".mov", ".avi"]
        
        # Search for a video file in the flight folder
        video_path = None
        for fmt in video_formats:
            potential_path = os.path.join(self.flight_folder, f"flight_video{fmt}")
            if os.path.exists(potential_path):
                video_path = potential_path
                break

        if video_path:
            # Process the video using video_process.py
            try:
                run(video_path, duration)
                self.update_history_button()
            except Exception as e:
                QMessageBox.critical(self, "Processing Error", f"Σφάλμα κατά την επεξεργασία του βίντεο: {e}")
        else:
            # Show warning if no video is found
            QMessageBox.warning(self, "Video Missing", "Δεν βρέθηκε βίντεο πτήσης για επεξεργασία!")
        


    def update_history_button(self):
        """Enable the history button if runs folder has content."""
        runs_dir = "runs"
        if os.path.exists(runs_dir) and os.listdir(runs_dir):
            self.history_button.setEnabled(True)
        else:
            self.history_button.setEnabled(False)

    
    
        
    # def toggle_recording(self):
    #     if not self.is_flying:
    #         QMessageBox.warning(self, "Drone Status", "Το drone πρέπει να είναι στον αέρα για να γίνει εγγραφή βίντεο!")
    #         return

    #     if not self.recording:
    #         video_file = os.path.join(self.flight_folder, "flight_video.avi")
    #         fourcc = cv2.VideoWriter_fourcc(*"XVID")
    #         self.video_writer = cv2.VideoWriter(video_file, fourcc, 30.0, (640, 480))
    #         self.recording = True
    #         self.record_button.setText("Διακοπή Εγγραφής")
    #     else:
    #         self.recording = False
    #         self.video_writer.release()
    #         self.record_button.setText("Έναρξη Εγγραφής")

    # def capture_photo(self):
    #     if not self.is_flying:
    #         QMessageBox.warning(self, "Drone Status", "Το drone πρέπει να είναι στον αέρα για να τραβήξετε φωτογραφία!")
    #         return

    #     ret, frame = self.video_capture.read()
    #     if ret:
    #         photo_file = os.path.join(self.flight_folder, f"photo_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
    #         cv2.imwrite(photo_file, frame)
    #         QMessageBox.information(self, "Drone Status", f"Η φωτογραφία αποθηκεύτηκε: {photo_file}")
    
    def capture_photo(self):
        if not self.is_flying:
            QMessageBox.warning(self, "Drone Status", "Το drone πρέπει να είναι στον αέρα για να τραβήξετε φωτογραφία!")
            return

        print("Mock: Capturing photo...")
        QMessageBox.information(self, "Drone Status", "Mock photo captured successfully!")

    def toggle_recording(self):
        if not self.is_flying:
            QMessageBox.warning(self, "Drone Status", "Το drone πρέπει να είναι στον αέρα για να γίνει εγγραφή βίντεο!")
            return

        if not self.recording:
            print("Mock: Video recording started")
            self.recording = True
            self.record_button.setText("Διακοπή Εγγραφής")
        else:
            print("Mock: Video recording stopped")
            self.recording = False
            self.record_button.setText("Έναρξη Εγγραφής")

    
    def closeEvent(self, event):
        self.stop_video_stream()
        self.drone.end()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication([])
    window = DroneControlApp()
    window.show()
    sys.exit(app.exec())
