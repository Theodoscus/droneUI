import sys
import os
import datetime
import random
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QProgressBar, QMessageBox, QGroupBox, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeyEvent, QImage, QPixmap
import pygame
import threading
import cv2  # OpenCV for video capture/display

# Your imports for report, shared, etc.
from report_gen import DroneReportApp
from video_process import run
from shared import open_homepage, open_full_screen

from djitellopy import Tello, TelloException

# ---------------------------------------------------------------------
# RealTello: a wrapper for djitellopy Tello
# ---------------------------------------------------------------------
class RealTello:
    def __init__(self):
        self.tello = Tello()
        self.is_flying = False
        self.stream_on = False
        self.connected = False

    def connect(self):
        self.tello.connect()
        self.connected = True
        print("Drone connected")

    def disconnect(self):
        try:
            self.tello.end()
            print("Drone disconnected")
        except TelloException as e:
            print(f"Failed to properly disconnect: {e}")
        finally:
            self.connected = False
            self.is_flying = False
            self.stream_on = False

    def takeoff(self):
        if not self.connected:
            print("Cannot take off: not connected.")
            return
        if self.is_flying:
            print("Already flying!")
            return
        try:
            self.tello.takeoff()
            self.is_flying = True
            print("Takeoff successful")
        except TelloException as e:
            print(f"Takeoff failed: {e}")

    def land(self):
        if not self.connected:
            print("Cannot land: not connected.")
            return
        if not self.is_flying:
            print("Already landed!")
            return
        try:
            self.tello.land()
            self.is_flying = False
            print("Landing successful")
        except TelloException as e:
            print(f"Landing failed: {e}")

    def streamon(self):
        if not self.connected:
            print("Cannot stream on: not connected.")
            return
        try:
            self.tello.streamon()
            self.stream_on = True
            print("Video stream started")
        except TelloException as e:
            print(f"Failed to start video stream: {e}")

    def streamoff(self):
        try:
            self.tello.streamoff()
            self.stream_on = False
            print("Video stream stopped")
        except TelloException as e:
            print(f"Failed to stop video stream: {e}")

    # ------------------
    # Movement Methods
    # ------------------
    def move_forward(self):
        if not self.connected or not self.is_flying:
            print("Cannot move forward: not connected or not flying.")
            return
        try:
            self.tello.move_forward(30)
        except TelloException as e:
            print(f"Failed to move forward: {e}")

    def move_backward(self):
        if not self.connected or not self.is_flying:
            print("Cannot move backward: not connected or not flying.")
            return
        try:
            self.tello.move_back(30)
        except TelloException as e:
            print(f"Failed to move back: {e}")

    def move_left(self):
        if not self.connected or not self.is_flying:
            print("Cannot move left: not connected or not flying.")
            return
        try:
            self.tello.move_left(30)
        except TelloException as e:
            print(f"Failed to move left: {e}")

    def move_right(self):
        if not self.connected or not self.is_flying:
            print("Cannot move right: not connected or not flying.")
            return
        try:
            self.tello.move_right(30)
        except TelloException as e:
            print(f"Failed to move right: {e}")

    def move_up(self):
        if not self.connected or not self.is_flying:
            print("Cannot move up: not connected or not flying.")
            return
        try:
            self.tello.move_up(20)
        except TelloException as e:
            print(f"Failed to move up: {e}")

    def move_down(self):
        if not self.connected or not self.is_flying:
            print("Cannot move down: not connected or not flying.")
            return
        try:
            self.tello.move_down(20)
        except TelloException as e:
            print(f"Failed to move down: {e}")

    def rotate_left(self):
        if not self.connected or not self.is_flying:
            print("Cannot rotate left: not connected or not flying.")
            return
        try:
            self.tello.rotate_counter_clockwise(30)
        except TelloException as e:
            print(f"Failed to rotate left: {e}")

    def rotate_right(self):
        if not self.connected or not self.is_flying:
            print("Cannot rotate right: not connected or not flying.")
            return
        try:
            self.tello.rotate_clockwise(30)
        except TelloException as e:
            print(f"Failed to rotate right: {e}")

    def flip_left(self):
        if not self.connected or not self.is_flying:
            print("Cannot flip left: not connected or not flying.")
            return
        try:
            self.tello.flip('l')
        except TelloException as e:
            print(f"Failed to flip left: {e}")

    def flip_right(self):
        if not self.connected or not self.is_flying:
            print("Cannot flip right: not connected or not flying.")
            return
        try:
            self.tello.flip('r')
        except TelloException as e:
            print(f"Failed to flip right: {e}")

    def flip_forward(self):
        if not self.connected or not self.is_flying:
            print("Cannot flip forward: not connected or not flying.")
            return
        try:
            self.tello.flip('f')
        except TelloException as e:
            print(f"Failed to flip forward: {e}")

    def flip_back(self):
        if not self.connected or not self.is_flying:
            print("Cannot flip back: not connected or not flying.")
            return
        try:
            self.tello.flip('b')
        except TelloException as e:
            print(f"Failed to flip back: {e}")


# ---------------------------------------------------------------------
# DroneControlApp
# ---------------------------------------------------------------------
class DroneControlApp(QMainWindow):
    def __init__(self, field_path):
        super().__init__()
        self.setWindowTitle("Drone Control (Full Screen)")
        # We do NOT set a normal geometry since we'll go full screen

        self.field_path = field_path
        self.flights_folder = os.path.join(self.field_path, "flights")
        os.makedirs(self.flights_folder, exist_ok=True)

        self.drone = RealTello()
        self.flight_duration = 0
        self.battery_level = 100
        self.fly_height = 0
        self.speed = 0
        self.temperature = 0
        self.current_flight_folder = None

        # Attempt to connect
        try:
            self.drone.connect()
        except TelloException:
            print("Could not connect to Tello. DISCONNECTED mode.")

        # Timers
        self.flight_timer = QTimer()
        self.flight_timer.timeout.connect(self.update_flight_duration)

        self.ui_timer = QTimer()
        self.ui_timer.timeout.connect(self.update_ui_stats)
        self.ui_timer.start(2000)

        # Pygame
        pygame.init()
        pygame.joystick.init()
        self.controller = None
        self.controller_timer = QTimer()
        self.controller_timer.timeout.connect(self.poll_controller_input)
        self.controller_timer.start(20)

        # Keyboard mapping
        self.key_pressed_mapping = {
            Qt.Key.Key_W: self.drone.move_forward,
            Qt.Key.Key_S: self.drone.move_backward,
            Qt.Key.Key_A: self.drone.move_left,
            Qt.Key.Key_D: self.drone.move_right,
            Qt.Key.Key_Q: self.drone.flip_left,
            Qt.Key.Key_E: self.drone.flip_right,
            Qt.Key.Key_Return: self.take_off,
            Qt.Key.Key_P: self.land,
            Qt.Key.Key_Up: self.drone.move_up,
            Qt.Key.Key_Down: self.drone.move_down,
            Qt.Key.Key_Left: self.drone.rotate_left,
            Qt.Key.Key_Right: self.drone.rotate_right,
        }
        self.keyboard_control_enabled = True
        self.control_buttons = {}

        # Video
        self.frame_read = None
        self.video_writer = None
        self.is_recording = False
        self.video_thread = None
        self.video_thread_running = False

        # Build UI
        self.init_ui()
        self.update_connection_status_ui()
        self.update_controller_status()

        # If connected, start the video stream
        if self.drone.connected:
            self.start_video_stream()

        # Full screen (prevents user from resizing)
        self.showFullScreen()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)

        # Connection Status
        self.connection_status = QLabel()
        self.connection_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.connection_status.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.connection_status.setStyleSheet("font-size: 18px; font-weight: bold; border: 2px solid #555;")
        main_layout.addWidget(self.connection_status)

        # Connect/Disconnect
        self.connect_button = QPushButton("Connect/Disconnect Drone")
        self.connect_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: #FF9900; color: black;")
        self.connect_button.clicked.connect(self.toggle_drone_connection)
        main_layout.addWidget(self.connect_button)

        # Notification label
        self.notification_label = QLabel("")
        self.notification_label.setStyleSheet("color: red; font-size: 16px; font-weight: bold;")
        self.notification_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.notification_label.setVisible(False)
        main_layout.addWidget(self.notification_label)

        # Content layout (side panel + video feed)
        content_layout = QHBoxLayout()
        main_layout.addLayout(content_layout)

        # Left panel
        left_panel = QVBoxLayout()
        battery_box = QGroupBox("Battery")
        battery_layout = QVBoxLayout()
        self.battery_bar = QProgressBar()
        self.battery_bar.setValue(self.battery_level)
        self.battery_bar.setStyleSheet("QProgressBar::chunk { background-color: green; }")
        battery_layout.addWidget(self.battery_bar)
        battery_box.setLayout(battery_layout)
        battery_box.setFixedHeight(60)
        left_panel.addWidget(battery_box)

        controller_status_box = QGroupBox("Controller Status")
        controller_layout = QVBoxLayout()
        self.controller_status_label = QLabel("No Controller Connected")
        self.controller_status_label.setStyleSheet("color: red; font-size: 14px; font-weight: bold;")
        controller_layout.addWidget(self.controller_status_label)
        controller_status_box.setLayout(controller_layout)
        controller_status_box.setFixedHeight(60)
        left_panel.addWidget(controller_status_box)

        info_box = QGroupBox("Drone Info")
        info_layout = QVBoxLayout()
        self.info_labels = {
            "Temperature": QLabel("0°C"),
            "Height": QLabel("0 cm"),
            "Speed": QLabel("0 cm/s"),
            "Data Transmitted": QLabel("0 MB"),
            "Flight Duration": QLabel("0 sec"),
        }
        for key, lbl in self.info_labels.items():
            row = QHBoxLayout()
            row.addWidget(QLabel(f"{key}:"))
            row.addWidget(lbl)
            info_layout.addLayout(row)
        info_box.setLayout(info_layout)
        info_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        left_panel.addWidget(info_box, stretch=1)

        left_panel_widget = QWidget()
        left_panel_widget.setLayout(left_panel)
        left_panel_widget.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        left_panel_widget.setMaximumWidth(300)

        # Make the drone stream bigger: ratio side=1, stream=4
        content_layout.addWidget(left_panel_widget, stretch=1)

        # VIDEO LABEL FIXES
        self.stream_label = QLabel("Drone Stream Placeholder")
        self.stream_label.setStyleSheet("background-color: #000; color: white; font-size: 14px; border: 1px solid #555;")
        self.stream_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # No label-based resizing
        self.stream_label.setScaledContents(False)
        # Let the layout decide
        self.stream_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Use 'stretch=4' so it takes more space relative to the side panel's 'stretch=1'
        content_layout.addWidget(self.stream_label, stretch=4)

        # Control buttons
        controls_layout = QVBoxLayout()
        control_buttons = [
            [("Q", "Flip Left"), ("W", "Forward"), ("E", "Flip Right"), ("R", "Flip Forward")],
            [("A", "Left"), ("S", "Backward"), ("D", "Right"), ("F", "Flip Back")],
            [("Enter", "Take Off", "green"), ("Space", "Land", "red")],
            [("Up Arrow", "Up"), ("Down Arrow", "Down"), ("Left Arrow", "Rotate Left"), ("Right Arrow", "Rotate Right")],
        ]
        for row in control_buttons:
            row_layout = QHBoxLayout()
            for button_spec in row:
                if len(button_spec) == 3:
                    btn = self.create_control_button(button_spec[0], button_spec[1], button_spec[2])
                else:
                    btn = self.create_control_button(button_spec[0], button_spec[1])
                row_layout.addWidget(btn)
            controls_layout.addLayout(row_layout)
        main_layout.addLayout(controls_layout)

        # Footer
        self.history_button = QPushButton("View Flight History")
        self.history_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: #007BFF; color: white;")
        self.history_button.clicked.connect(self.view_flight_history)
        main_layout.addWidget(self.history_button)

        self.home_button = QPushButton("Αρχική Σελίδα")
        self.home_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: #007BFF; color: white;")
        self.home_button.clicked.connect(self.go_to_homepage)
        main_layout.addWidget(self.home_button)

        self.fullscreen_button = QPushButton("Full Screen Drone Operation")
        self.fullscreen_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: #007BFF; color: white;")
        self.fullscreen_button.setEnabled(True)
        self.fullscreen_button.clicked.connect(self.launch_fullscreen)
        main_layout.addWidget(self.fullscreen_button)

    # ---------------------------------------------------------------------
    # Connect/Disconnect
    # ---------------------------------------------------------------------
    def toggle_drone_connection(self):
        if self.drone.connected:
            self.stop_video_stream()
            self.drone.disconnect()
            self.update_connection_status_ui()
        else:
            try:
                self.drone.connect()
                self.update_connection_status_ui()
                self.start_video_stream()
            except TelloException:
                QMessageBox.critical(self, "Connection Error", "Could not connect to Tello drone.")
                self.update_connection_status_ui()

    def update_connection_status_ui(self):
        if self.drone.connected:
            self.connection_status.setText("CONNECTED")
            self.connection_status.setStyleSheet(
                "background-color: green; color: white; font-size: 18px; font-weight: bold; border: 2px solid #555;"
            )
            self.set_controls_enabled(True)
        else:
            self.connection_status.setText("DISCONNECTED")
            self.connection_status.setStyleSheet(
                "background-color: red; color: white; font-size: 18px; font-weight: bold; border: 2px solid #555;"
            )
            self.set_controls_enabled(False)

    # ---------------------------------------------------------------------
    # Start/Stop Video Stream
    # ---------------------------------------------------------------------
    def start_video_stream(self):
        if not self.drone.connected:
            return
        if not self.drone.stream_on:
            self.drone.streamon()

        self.frame_read = self.drone.tello.get_frame_read()
        if not self.frame_read:
            print("Failed to get frame_read object from Tello.")
            return

        self.video_thread_running = True
        self.video_thread = threading.Thread(target=self.video_loop, daemon=True)
        self.video_thread.start()

    def stop_video_stream(self):
        self.video_thread_running = False
        if self.drone.stream_on:
            self.drone.streamoff()

    def video_loop(self):
        """
        Continuously read frames, convert them to QPixmap,
        scale with aspect ratio, and display in self.stream_label.
        """
        while self.video_thread_running:
            frame = self.frame_read.frame
            if frame is not None:
                rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb_image.shape
                bytes_per_line = ch * w
                qt_img = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
                pixmap = QPixmap.fromImage(qt_img)

                label_width = self.stream_label.width()
                label_height = self.stream_label.height()

                scaled_pix = pixmap.scaled(
                    label_width,
                    label_height,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self.stream_label.setPixmap(scaled_pix)

                if self.is_recording and self.video_writer is not None:
                    self.video_writer.write(frame)

            cv2.waitKey(33)

    # ---------------------------------------------------------------------
    # Threads & Windows
    # ---------------------------------------------------------------------
    def launch_fullscreen(self):
        self.flight_timer.stop()
        self.ui_timer.stop()
        self.controller_timer.stop()
        pygame.joystick.quit()
        pygame.quit()
        self.stop_video_stream()

        self.fullscreen_window = open_full_screen(self.field_path)
        self.fullscreen_window.show()
        self.close()

    # ---------------------------------------------------------------------
    # Controller Management
    # ---------------------------------------------------------------------
    def update_controller_status(self):
        if pygame.joystick.get_count() > 0:
            if not self.controller:
                self.controller = pygame.joystick.Joystick(0)
                self.controller.init()
            self.controller_status_label.setText("Controller Connected")
            self.controller_status_label.setStyleSheet("color: green; font-size: 14px; font-weight: bold;")
            self.set_controls_enabled(False)
        else:
            self.controller = None
            self.controller_status_label.setText("No Controller Connected")
            self.controller_status_label.setStyleSheet("color: red; font-size: 14px; font-weight: bold;")
            self.set_controls_enabled(self.drone.connected)

    def set_controls_enabled(self, enabled: bool):
        for button in self.control_buttons.values():
            button.setEnabled(enabled)
        self.keyboard_control_enabled = enabled

    def poll_controller_input(self):
        pygame.event.pump()
        controller_count = pygame.joystick.get_count()
        if (self.controller and controller_count == 0) or (not self.controller and controller_count > 0):
            self.update_controller_status()

        if self.controller:
            for event in pygame.event.get():
                if event.type == pygame.JOYBUTTONDOWN:
                    self.handle_button_press(event.button)
                elif event.type == pygame.JOYAXISMOTION:
                    self.handle_axis_motion(event.axis, event.value)

    def handle_button_press(self, button):
        if not self.drone.connected:
            return
        if button == 0:  # A
            self.take_off()
        elif button == 1:  # B
            self.land()
        elif button == 2:  # X
            self.drone.flip_left()
        elif button == 3:  # Y
            self.drone.flip_right()

    def handle_axis_motion(self, axis, value):
        if not self.drone.connected:
            return
        if axis == 0:  # Left horizontal
            if value < -0.5:
                self.drone.move_left()
            elif value > 0.5:
                self.drone.move_right()
        elif axis == 1:  # Left vertical
            if value < -0.5:
                self.drone.move_forward()
            elif value > 0.5:
                self.drone.move_backward()
        elif axis == 2:  # Right horizontal
            if value < -0.5:
                self.drone.rotate_left()
            elif value > 0.5:
                self.drone.rotate_right()
        elif axis == 3:  # Right vertical
            if value < -0.5:
                self.drone.move_up()
            elif value > 0.5:
                self.drone.move_down()

    # ---------------------------------------------------------------------
    # Control Buttons (GUI)
    # ---------------------------------------------------------------------
    def create_control_button(self, key: str, action: str, color=None) -> QPushButton:
        btn = QPushButton(f"{key}\n({action})")
        if color:
            btn.setStyleSheet(f"background-color: {color}; color: white; font-weight: bold;")
        btn.clicked.connect(self.create_button_handler(action))
        self.control_buttons[action] = btn
        return btn

    def create_button_handler(self, action: str):
        def handler():
            action_mapping = {
                "Flip Left": "flip_left",
                "Forward": "move_forward",
                "Flip Right": "flip_right",
                "Flip Forward": "flip_forward",
                "Left": "move_left",
                "Backward": "move_backward",
                "Right": "move_right",
                "Flip Back": "flip_back",
                "Take Off": "take_off",
                "Land": "land",
                "Up": "move_up",
                "Down": "move_down",
                "Rotate Left": "rotate_left",
                "Rotate Right": "rotate_right",
            }
            method_name = action_mapping.get(action)
            if method_name:
                method = getattr(self, method_name, None)
                if callable(method):
                    method()
        return handler

    # ---------------------------------------------------------------------
    # Keyboard Events
    # ---------------------------------------------------------------------
    def keyPressEvent(self, event: QKeyEvent):
        if not self.keyboard_control_enabled:
            return
        if event.key() in self.key_pressed_mapping:
            self.key_pressed_mapping[event.key()]()

    # ---------------------------------------------------------------------
    # Flight Duration & Stats
    # ---------------------------------------------------------------------
    def update_flight_duration(self):
        self.flight_duration += 1
        self.info_labels["Flight Duration"].setText(f"{self.flight_duration} sec")

    def update_ui_stats(self):
        if not self.drone.connected:
            return
        try:
            self.battery_level = self.drone.tello.get_battery()
            self.battery_bar.setValue(self.battery_level)

            self.fly_height = self.drone.tello.get_height()
            self.info_labels["Height"].setText(f"{self.fly_height} cm")

            self.temperature = self.drone.tello.get_temperature()
            self.info_labels["Temperature"].setText(f"{self.temperature}°C")

            self.speed = self.drone.tello.get_speed_z()
            self.info_labels["Speed"].setText(f"{self.speed} cm/s")

            if self.battery_level < 20:
                self.notification_label.setText("Warning: Battery level is critically low!")
                self.notification_label.setVisible(True)
            else:
                self.notification_label.setVisible(False)
        except TelloException as e:
            print(f"Failed to get drone stats: {e}")

    # ---------------------------------------------------------------------
    # Flight Operations
    # ---------------------------------------------------------------------
    def take_off(self):
        if not self.drone.connected:
            print("Cannot take off: Drone not connected.")
            return

        self.history_button.setEnabled(False)
        self.home_button.setEnabled(False)
        self.fullscreen_button.setEnabled(False)
        self.home_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: lightgray; color: gray;")
        self.fullscreen_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: lightgray; color: gray;")

        if not self.drone.is_flying:
            self.drone.takeoff()
            if self.drone.is_flying:
                self.flight_timer.start(1000)
                self.flight_start_time = datetime.datetime.now()

                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                self.current_flight_folder = os.path.join(self.flights_folder, f"flight_{timestamp}")
                os.makedirs(self.current_flight_folder, exist_ok=True)
                print(f"Flight folder created: {self.current_flight_folder}")

                self.start_recording()

    def land(self):
        if not self.drone.is_flying:
            print("Not flying or not connected.")
            return
        self.drone.land()
        if not self.drone.is_flying:
            self.flight_timer.stop()
            self.stop_recording()

            self.home_button.setEnabled(True)
            self.fullscreen_button.setEnabled(True)
            self.home_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: #007BFF; color: white;")
            self.fullscreen_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: #007BFF; color: white;")

            self.flight_end_time = datetime.datetime.now()
            duration = self.flight_end_time - self.flight_start_time
            QMessageBox.information(self, "Flight Completed", f"Flight duration: {duration}")
            print(f"Flight data saved in: {self.current_flight_folder}")

            self.process_flight_video(duration)
            self.update_history_button()

    def start_recording(self):
        if not self.frame_read or self.frame_read.frame is None:
            print("No frame to record from.")
            return
        frame = self.frame_read.frame
        video_filename = os.path.join(self.current_flight_folder, "flight_video.avi")
        fourcc = cv2.VideoWriter_fourcc(*'XVID')
        height, width, _ = frame.shape
        self.video_writer = cv2.VideoWriter(video_filename, fourcc, 30.0, (width, height))
        self.is_recording = True
        print(f"Recording started: {video_filename}")

    def stop_recording(self):
        if self.is_recording and self.video_writer:
            self.is_recording = False
            self.video_writer.release()
            self.video_writer = None
            print("Recording stopped.")

    def process_flight_video(self, duration):
        video_formats = [".mp4", ".mov", ".avi"]
        video_path = None
        for fmt in video_formats:
            potential_path = os.path.join(self.current_flight_folder, f"flight_video{fmt}")
            if os.path.exists(potential_path):
                video_path = potential_path
                break
        if video_path:
            try:
                run(video_path, duration, self.field_path)
            except Exception as e:
                QMessageBox.critical(self, "Processing Error", f"Error processing video: {e}")
        else:
            QMessageBox.warning(self, "Video Missing", "No flight video found for processing!")

    def update_history_button(self):
        runs_dir = os.path.join(self.field_path, "runs")
        if os.path.exists(runs_dir) and os.listdir(runs_dir):
            self.history_button.setEnabled(True)
        else:
            self.history_button.setEnabled(False)

    # ---------------------------------------------------------------------
    # Navigation
    # ---------------------------------------------------------------------
    def go_to_homepage(self):
        self.flight_timer.stop()
        self.ui_timer.stop()
        self.controller_timer.stop()
        self.stop_video_stream()

        self.home_page = open_homepage()
        self.home_page.show()
        self.close()

    def view_flight_history(self):
        self.report_app = DroneReportApp(self.field_path)
        self.report_app.show()


# -------------------------
# Optional main
# -------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    field_directory_path = "fields"
    window = DroneControlApp(field_directory_path)
    sys.exit(app.exec())
