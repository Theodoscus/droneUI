import os
import datetime
import threading
import platform
import subprocess

import pygame
import cv2
from djitellopy import Tello

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QProgressBar, QMessageBox, QGroupBox, QSizePolicy, QDialog
)
from PyQt6.QtCore import Qt, QTimer, QThread, QObject, pyqtSignal
from PyQt6.QtGui import QKeyEvent, QImage, QPixmap

from report_gen import DroneReportApp
from video_process import run
from shared import open_homepage, open_full_screen


# ---------------------------------------------------------------------
# 1) Worker + Dialog Classes
# ---------------------------------------------------------------------
import re
from djitellopy import Tello
from PyQt6.QtCore import QObject, pyqtSignal

class DroneConnectWorker(QObject):
    connect_success = pyqtSignal()
    connect_error = pyqtSignal(str)

    def __init__(self, drone: Tello):
        super().__init__()
        self.drone = drone

    import re
from djitellopy import Tello
from PyQt6.QtCore import QObject, pyqtSignal

class DroneConnectWorker(QObject):
    connect_success = pyqtSignal()
    connect_error = pyqtSignal(str)

    def __init__(self, drone: Tello):
        super().__init__()
        self.drone = drone

    def run(self):
        """
        Attempt to connect to the drone and start video streaming.
        Some firmware versions (or library versions) return the drone’s IP address
        (or a tuple containing it) instead of "ok". This version checks if the raw
        response is a tuple and extracts the first element before sanitizing.
        """
        try:
            # Attempt to call connect(); if it raises an exception, capture its message.
            try:
                raw_response = self.drone.connect()
            except Exception as e:
                raw_response = str(e)
            
            # If raw_response is a tuple (or list), take its first element.
            if isinstance(raw_response, (tuple, list)):
                print("Raw response is a tuple/list; extracting first element.")
                raw_response = raw_response[0]
            
            # Log the raw response (using repr to show quotes and extra characters)
            print("Raw response from drone.connect():", repr(raw_response))
            
            # If raw_response is None, treat it as success.
            if raw_response is None:
                print("Received None from drone.connect(); treating as successful connection.")
            else:
                # If raw_response is bytes, decode it.
                if isinstance(raw_response, bytes):
                    raw_response = raw_response.decode("utf-8")
                # Sanitize the response: remove extra whitespace and any wrapping quotes.
                response_str = str(raw_response).strip().strip('"').strip("'")
                print("Sanitized response:", repr(response_str))
                # Accept the response if it is "ok" or "192.168.10.1".
                if response_str not in ["ok", "192.168.10.1"]:
                    raise Exception(response_str)
                else:
                    print("Accepted response:", response_str)
            
            # Start video streaming and emit success.
            self.drone.streamon()
            self.connect_success.emit()
        except Exception as e:
            self.connect_error.emit(str(e))




class ConnectingDialog(QDialog):
    """
    A modal dialog showing "Connecting..." with an indeterminate progress bar.
    The close button is removed so the user cannot dismiss it prematurely.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Connecting to Drone")

        # Remove the close button from the title bar
        self.setWindowFlags(self.windowFlags())
        self.setModal(True)

        layout = QVBoxLayout()

        title_label = QLabel("<h2>Connecting to Tello Drone</h2>")
        info_label = QLabel("Please wait while we establish a connection...")

        # Indeterminate progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # "Marquee" / Busy mode
        self.progress_bar.setTextVisible(False)

        layout.addWidget(title_label)
        layout.addWidget(info_label)
        layout.addWidget(self.progress_bar)

        self.setLayout(layout)


class DroneControlApp(QMainWindow):
    def __init__(self, field_path):
        super().__init__()
        self.setWindowTitle("Drone Control")
        self.setGeometry(100, 100, 1200, 800)

        self.field_path = field_path
        self.flights_folder = os.path.join(self.field_path, "flights")
        os.makedirs(self.flights_folder, exist_ok=True)

        # --------------------------------------------------
        # 1) Create Tello instance (but do NOT block here!)
        # --------------------------------------------------
        self.drone = Tello()
        self.is_connected = False  # We will do asynchronous connection below.

        # Flight/data states
        self.flight_duration = 0
        self.current_flight_folder = None
        self.flight_start_time = None
        self.is_recording = False
        self.video_writer = None
        # Initialize a counter for consecutive ping failures.
        self.consecutive_ping_failures = 0


        # Timers
        self.flight_timer = QTimer()
        self.flight_timer.timeout.connect(self.update_flight_duration)

        self.ui_timer = QTimer()
        self.ui_timer.timeout.connect(self.update_ui_stats)
        self.ui_timer.start(3000)  # Every 3 seconds instead of 2


        pygame.init()
        pygame.joystick.init()
        self.controller = None

        self.controller_timer = QTimer()
        self.controller_timer.timeout.connect(self.poll_controller_input)
        self.controller_timer.start(20)
        
        # Check the drone connection every 5 seconds
        self.connection_check_timer = QTimer()
        self.connection_check_timer.timeout.connect(self.check_drone_connection)
        self.connection_check_timer.start(2000)  


        self.key_pressed_mapping = {
            Qt.Key.Key_W: self.move_forward,
            Qt.Key.Key_S: self.move_backward,
            Qt.Key.Key_A: self.move_left,
            Qt.Key.Key_D: self.move_right,
            Qt.Key.Key_Q: self.flip_left,
            Qt.Key.Key_E: self.flip_right,
            Qt.Key.Key_Return: self.take_off,
            Qt.Key.Key_P: self.land,
            Qt.Key.Key_Up: self.move_up,
            Qt.Key.Key_Down: self.move_down,
            Qt.Key.Key_Left: self.rotate_left,
            Qt.Key.Key_Right: self.rotate_right,
        }

        self.keyboard_control_enabled = True
        self.control_buttons = {}

        self.stream_timer = QTimer()
        self.stream_timer.timeout.connect(self.update_video_stream)
        # We'll start stream_timer in handle_connect_success() once connected.

        # 2) Build the UI
        self.init_ui()
        self.update_controller_status()

        # 3) Immediately attempt to connect asynchronously
        self.connect_drone_async()

    # ---------------------------------------------------------------------
    # UI Setup
    # ---------------------------------------------------------------------
    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)

        # --------------------------------------------------------------------
        # 1) TOP AREA (3/4 of total height)
        # --------------------------------------------------------------------
        top_area_widget = QWidget()
        top_area_layout = QVBoxLayout(top_area_widget)

        # Connection Status
        self.connection_status = QLabel()
        self.connection_status.setText("DISCONNECTED")
        self.connection_status.setStyleSheet(
            "background-color: red; color: white; font-size: 18px; font-weight: bold; border: 2px solid #555;"
        )
        self.connection_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.connection_status.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        top_area_layout.addWidget(self.connection_status)

        self.notification_label = QLabel("")
        self.notification_label.setStyleSheet("color: red; font-size: 16px; font-weight: bold;")
        self.notification_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.notification_label.setVisible(False)
        top_area_layout.addWidget(self.notification_label)
        
        # Wi-Fi Connection Warning Label (new)
        self.connection_notification_label = QLabel("")
        self.connection_notification_label.setStyleSheet("color: orange; font-size: 16px; font-weight: bold;")
        self.connection_notification_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.connection_notification_label.setVisible(False)
        top_area_layout.addWidget(self.connection_notification_label)

        # Content Layout (Left panel + Stream)
        content_layout = QHBoxLayout()
        top_area_layout.addLayout(content_layout)

        left_panel = QVBoxLayout()

        # Battery
        battery_box = QGroupBox("Battery")
        battery_layout = QVBoxLayout()
        self.battery_bar = QProgressBar()
        self.battery_bar.setValue(0)  # Initially unknown
        self.battery_bar.setStyleSheet("QProgressBar::chunk { background-color: green; }")
        self.battery_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        battery_layout.addWidget(self.battery_bar)
        battery_box.setLayout(battery_layout)
        battery_box.setFixedHeight(60)
        left_panel.addWidget(battery_box)

        # Controller Status
        controller_status_box = QGroupBox("Controller Status")
        controller_layout = QVBoxLayout()
        self.controller_status_label = QLabel("No Controller Connected")
        self.controller_status_label.setStyleSheet("color: red; font-size: 14px; font-weight: bold;")
        controller_layout.addWidget(self.controller_status_label)
        controller_status_box.setLayout(controller_layout)
        controller_status_box.setFixedHeight(60)
        left_panel.addWidget(controller_status_box)

        # Drone Info
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
        content_layout.addWidget(left_panel_widget, stretch=1)

        # STREAM LABEL
        self.stream_label = QLabel("Drone Stream")
        self.stream_label.setStyleSheet(
            "background-color: #000; color: white; font-size: 14px; border: 1px solid #555;"
        )
        self.stream_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stream_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.stream_label.setScaledContents(True)
        content_layout.addWidget(self.stream_label, stretch=3)

        main_layout.addWidget(top_area_widget, stretch=3)

        # --------------------------------------------------------------------
        # 2) BOTTOM AREA (1/4 of total height)
        # --------------------------------------------------------------------
        bottom_area_widget = QWidget()
        bottom_area_layout = QVBoxLayout(bottom_area_widget)

        # CONTROL BUTTONS
        controls_layout = QVBoxLayout()
        control_buttons = [
            [("Q", "Flip Left"), ("W", "Forward"), ("E", "Flip Right")],
            [("A", "Left"), ("S", "Backward"), ("D", "Right")],
            [("Enter", "Take Off", "green"), ("P", "Land", "red")],
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

        bottom_area_layout.addLayout(controls_layout)

        self.history_button = QPushButton("View Flight History")
        self.history_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: #007BFF; color: white;")
        self.history_button.clicked.connect(self.view_flight_history)
        self.history_button.setEnabled(False)
        bottom_area_layout.addWidget(self.history_button)

        self.home_button = QPushButton("Αρχική Σελίδα")
        self.home_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: #007BFF; color: white;")
        self.home_button.clicked.connect(self.go_to_homepage)
        bottom_area_layout.addWidget(self.home_button)

        self.fullscreen_button = QPushButton("Full Screen Drone Operation")
        self.fullscreen_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: #007BFF; color: white;")
        self.fullscreen_button.setEnabled(True)
        self.fullscreen_button.clicked.connect(self.launch_fullscreen)
        bottom_area_layout.addWidget(self.fullscreen_button)

        # Connect/Disconnect toggle button
        self.connect_toggle_button = QPushButton("Connect")
        self.connect_toggle_button.setStyleSheet(
            "font-size: 16px; padding: 10px; background-color: green; color: white;"
        )
        self.connect_toggle_button.clicked.connect(self.toggle_connection)
        bottom_area_layout.addWidget(self.connect_toggle_button)

        main_layout.addWidget(bottom_area_widget, stretch=1)

    # ---------------------------------------------------------------------
    # Toggle Connection
    # ---------------------------------------------------------------------
    def toggle_connection(self):
        """If connected, disconnect. If disconnected, reconnect (async)."""
        if self.is_connected:
            self.disconnect_drone()
        else:
            self.connect_drone_async()
            
    

    def disconnect_drone(self):
        """
        Disconnect from the drone without permanently shutting down the instance.
        Instead of calling self.drone.end(), we simply turn off the stream.
        """
        if self.is_connected and self.drone:
            try:
                self.drone.streamoff()  # Only turn off the stream.
                print("Drone stream turned off.")
            except Exception as e:
                print("Error turning off drone stream:", e)
            self.is_connected = False
            self.stream_timer.stop()
            self.connection_status.setText("DISCONNECTED")
            self.connection_status.setStyleSheet(
                "background-color: red; color: white; font-size: 18px; font-weight: bold; border: 2px solid #555;"
            )
            self.connect_toggle_button.setText("Connect")
            self.connect_toggle_button.setStyleSheet(
                "font-size: 16px; padding: 10px; background-color: green; color: white;"
            )
        else:
            print("Drone already disconnected.")



    # ---------------------------------------------------------------------
    # 2) Asynchronous Connection
    # ---------------------------------------------------------------------
    def connect_drone_async(self):
        """
        Attempt to connect using the existing Tello instance.
        Use a QThread and a DroneConnectWorker to avoid blocking the UI.
        """
        # Do not reinitialize self.drone here—reuse the existing instance.
        self.connecting_dialog = ConnectingDialog()
        self.connecting_dialog.show()

        self.connection_thread = QThread()
        self.connection_worker = DroneConnectWorker(self.drone)
        self.connection_worker.moveToThread(self.connection_thread)
        self.connection_thread.started.connect(self.connection_worker.run)
        self.connection_worker.connect_success.connect(self.handle_connect_success)
        self.connection_worker.connect_error.connect(self.handle_connect_error)
        self.connection_worker.connect_success.connect(self.connection_thread.quit)
        self.connection_worker.connect_error.connect(self.connection_thread.quit)
        self.connection_thread.finished.connect(self.connection_thread.deleteLater)
        self.connection_thread.start()

    def handle_connect_success(self):
        """
        Called when the connection worker signals success.
        Update the UI to reflect that the drone is now connected.
        """
        self.is_connected = True
        self.connection_status.setText("CONNECTED")
        self.connection_status.setStyleSheet(
            "background-color: green; color: white; font-size: 18px; font-weight: bold; border: 2px solid #555;"
        )
        self.connect_toggle_button.setText("Disconnect")
        self.connect_toggle_button.setStyleSheet(
            "font-size: 16px; padding: 10px; background-color: red; color: white;"
        )
        # Start the timer that updates the video stream.
        self.stream_timer.start(50)
        self.connecting_dialog.close()
        print("Drone connected successfully and stream is ON.")

    def handle_connect_error(self, error_message):
        """
        Called when the connection worker signals an error.
        Display an error message and update the UI accordingly.
        """
        print("Error connecting to drone:", error_message)
        QMessageBox.critical(self, "Connection Error", f"Could not connect:\n{error_message}")
        self.is_connected = False
        self.connection_status.setText("DISCONNECTED")
        self.connection_status.setStyleSheet(
            "background-color: red; color: white; font-size: 18px; font-weight: bold; border: 2px solid #555;"
        )
        self.connect_toggle_button.setText("Connect")
        self.connect_toggle_button.setStyleSheet(
            "font-size: 16px; padding: 10px; background-color: green; color: white;"
        )
        self.connecting_dialog.close()
        
    def check_drone_connection(self):
        """Periodically check if the drone is still reachable via ping."""
        if not self.is_connected:
            return

        if not self.ping_drone("192.168.10.1"):
            self.consecutive_ping_failures += 1
            print(f"Ping failed ({self.consecutive_ping_failures} consecutive failure(s)).")
            # After 3 consecutive failures, update the UI/state but do not call disconnect_drone()
            if self.consecutive_ping_failures >= 3:
                print("Multiple ping failures: Drone not reachable. Marking as disconnected in UI.")
                # Update internal state without sending any commands to the drone.
                self.is_connected = False
                # Update the connection status label.
                self.connection_status.setText("DISCONNECTED")
                self.connection_status.setStyleSheet(
                    "background-color: red; color: white; font-size: 18px; font-weight: bold; border: 2px solid #555;"
                )
                # Change the toggle button to "Connect"
                self.connect_toggle_button.setText("Connect")
                self.connect_toggle_button.setStyleSheet(
                    "font-size: 16px; padding: 10px; background-color: green; color: white;"
                )
                # Show a warning that the drone has been lost.
                self.connection_notification_label.setText("Drone disconnected from WiFi!")
                self.connection_notification_label.setVisible(True)
        else:
            # If the ping succeeds, reset the failure counter.
            if self.consecutive_ping_failures > 0:
                print("Ping succeeded. Resetting failure counter.")
            self.consecutive_ping_failures = 0
            # Hide the WiFi warning if it is visible.
            if self.connection_notification_label.isVisible():
                self.connection_notification_label.setVisible(False)






    def ping_drone(self, ip="192.168.10.1", count=1, timeout=1):
        """
        Ping the given IP address.
        Returns True if the ping is successful, False otherwise.
        """
        # Choose the correct parameter based on OS.
        param = '-n' if platform.system().lower() == 'windows' else '-c'
        # Build the command list using the provided ip (not self).
        if platform.system().lower() == "windows":
            command = ["ping", param, str(count), "-w", str(timeout * 1000), ip]
        else:
            command = ["ping", param, str(count), "-W", str(timeout), ip]
        try:
            subprocess.check_output(command, stderr=subprocess.STDOUT, universal_newlines=True)
            return True
        except subprocess.CalledProcessError:
            return False


    # ---------------------------------------------------------------------
    # Other Windows / Threads
    # ---------------------------------------------------------------------
    

    def launch_fullscreen(self):
        self.stop_all_timers()
        pygame.joystick.quit()
        pygame.quit()
        self.disconnect_drone()
        self.fullscreen_window = open_full_screen(self.field_path)
        self.fullscreen_window.show()
        self.close()

    def center_window(self):
        self.show()
        self.updateGeometry()
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        center_x = screen_geometry.x() + (screen_geometry.width() - self.width()) // 2
        center_y = screen_geometry.y() + (screen_geometry.height() - self.height()) // 2
        self.move(center_x, center_y)

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
            self.set_controls_enabled(True)

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
        if button == 0:  # A
            self.take_off()
        elif button == 1:  # B
            self.land()
        elif button == 2:  # X
            self.flip_left()
        elif button == 3:  # Y
            self.flip_right()

    def handle_axis_motion(self, axis, value):
        # Basic threshold-based controls
        if axis == 0:  # Left horizontal
            if value < -0.5:
                self.move_left()
            elif value > 0.5:
                self.move_right()
        elif axis == 1:  # Left vertical
            if value < -0.5:
                self.move_forward()
            elif value > 0.5:
                self.move_backward()
        elif axis == 2:  # Right horizontal
            if value < -0.5:
                self.rotate_left()
            elif value > 0.5:
                self.rotate_right()
        elif axis == 3:  # Right vertical
            if value < -0.5:
                self.move_up()
            elif value > 0.5:
                self.move_down()

    # ---------------------------------------------------------------------
    # Control Buttons
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
            action_methods = {
                "Flip Left": self.flip_left,
                "Forward": self.move_forward,
                "Flip Right": self.flip_right,
                "Left": self.move_left,
                "Backward": self.move_backward,
                "Right": self.move_right,
                "Take Off": self.take_off,
                "Land": self.land,
                "Up": self.move_up,
                "Down": self.move_down,
                "Rotate Left": self.rotate_left,
                "Rotate Right": self.rotate_right,
            }
            method = action_methods.get(action)
            if callable(method):
                method()
            else:
                print(f"Warning: No method mapped for '{action}'")
        return handler

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
        if not self.is_connected:
            return
        try:
            battery_level = self.drone.get_battery()
            temperature = self.drone.get_temperature()
            height = self.drone.get_height()
            speed = self.drone.get_speed_x()

            self.battery_bar.setValue(battery_level)
            if battery_level < 90:
                self.notification_label.setText("Warning: Battery level is critically low!")
                self.notification_label.setVisible(True)
            else:
                self.notification_label.setVisible(False)

            self.info_labels["Temperature"].setText(f"{temperature}°C")
            self.info_labels["Height"].setText(f"{height} cm")
            self.info_labels["Speed"].setText(f"{speed} cm/s")
            self.info_labels["Data Transmitted"].setText("0 MB")
        except Exception as e:
            print("Failed to get Tello state:", e)

    # ---------------------------------------------------------------------
    # Flight Operations
    # ---------------------------------------------------------------------
    def take_off(self):
        if not self.is_connected:
            QMessageBox.warning(self, "Drone Disconnected", "Cannot take off because the drone is not connected.")
            return

        self.history_button.setEnabled(False)
        self.home_button.setEnabled(False)
        self.fullscreen_button.setEnabled(False)
        self.home_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: lightgray; color: gray;")
        self.fullscreen_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: lightgray; color: gray;")

        try:
            self.drone.takeoff()
            print("Drone takeoff successful.")

            self.flight_timer.start(1000)
            self.flight_duration = 0
            self.flight_start_time = datetime.datetime.now()

            timestamp = self.flight_start_time.strftime("%Y%m%d_%H%M%S")
            self.current_flight_folder = os.path.join(self.flights_folder, f"flight_{timestamp}")
            os.makedirs(self.current_flight_folder, exist_ok=True)
            print(f"Flight folder created: {self.current_flight_folder}")

            self.start_recording()
        except Exception as e:
            QMessageBox.critical(self, "Take Off Error", f"Unable to take off: {e}")

    def land(self):
        if not self.is_connected:
            QMessageBox.warning(self, "Drone Disconnected", "Cannot land because the drone is not connected.")
            return

        try:
            self.drone.land()
            print("Drone landing...")

            self.flight_timer.stop()
            self.flight_end_time = datetime.datetime.now()
            duration = self.flight_end_time - self.flight_start_time

            QMessageBox.information(self, "Flight Completed", f"Flight duration: {duration}")
            print(f"Flight data saved in: {self.current_flight_folder}")

            self.stop_recording()
            self.home_button.setEnabled(True)
            self.fullscreen_button.setEnabled(True)
            self.home_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: #007BFF; color: white;")
            self.fullscreen_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: #007BFF; color: white;")

            self.process_flight_video(duration)
            self.update_history_button()
        except Exception as e:
            QMessageBox.critical(self, "Land Error", f"Unable to land: {e}")

    def start_recording(self):
        if not self.is_connected:
            return
        self.is_recording = True
        self.frame_width = 960
        self.frame_height = 720
        output_path = os.path.join(self.current_flight_folder, "flight_video.mp4")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self.video_writer = cv2.VideoWriter(output_path, fourcc, 20.0, (self.frame_width, self.frame_height))
        print(f"Recording started: {output_path}")

    def stop_recording(self):
        if self.is_recording and self.video_writer is not None:
            self.is_recording = False
            self.video_writer.release()
            self.video_writer = None
            print("Recording stopped and VideoWriter released.")

    def process_flight_video(self, duration):
        video_path = os.path.join(self.current_flight_folder, "flight_video.mp4")
        if os.path.exists(video_path):
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
    # Video Stream
    # ---------------------------------------------------------------------
    def update_video_stream(self):
        if not self.is_connected:
            return
        frame_read = self.drone.get_frame_read()
        frame = frame_read.frame
        if frame is None:
            return

        image_rgb = frame
        height, width, channels = image_rgb.shape
        bytes_per_line = channels * width
        q_img = QImage(
            image_rgb.data,
            width,
            height,
            bytes_per_line,
            QImage.Format.Format_RGB888
        )
        pixmap = QPixmap.fromImage(q_img)
        self.stream_label.setPixmap(pixmap)

        if self.is_recording and self.video_writer is not None:
            self.video_writer.write(frame)

    # ---------------------------------------------------------------------
    # Movement
    # ---------------------------------------------------------------------
    def move_forward(self):
        if not self.is_connected:
            return
        try:
            self.drone.move_forward(30)
        except Exception as e:
            print(f"Failed to move forward: {e}")

    def move_backward(self):
        if not self.is_connected:
            return
        try:
            self.drone.move_back(30)
        except Exception as e:
            print(f"Failed to move backward: {e}")

    def move_left(self):
        if not self.is_connected:
            return
        try:
            self.drone.move_left(30)
        except Exception as e:
            print(f"Failed to move left: {e}")

    def move_right(self):
        if not self.is_connected:
            return
        try:
            self.drone.move_right(30)
        except Exception as e:
            print(f"Failed to move right: {e}")

    def move_up(self):
        if not self.is_connected:
            return
        try:
            self.drone.move_up(30)
        except Exception as e:
            print(f"Failed to move up: {e}")

    def move_down(self):
        if not self.is_connected:
            return
        try:
            self.drone.move_down(30)
        except Exception as e:
            print(f"Failed to move down: {e}")

    def rotate_left(self):
        if not self.is_connected:
            return
        try:
            self.drone.rotate_counter_clockwise(30)
        except Exception as e:
            print(f"Failed to rotate left: {e}")

    def rotate_right(self):
        if not self.is_connected:
            return
        try:
            self.drone.rotate_clockwise(30)
        except Exception as e:
            print(f"Failed to rotate right: {e}")

    def flip_left(self):
        if not self.is_connected:
            return
        try:
            self.drone.flip_left()
        except Exception as e:
            print(f"Failed to flip left: {e}")

    def flip_right(self):
        if not self.is_connected:
            return
        try:
            self.drone.flip_right()
        except Exception as e:
            print(f"Failed to flip right: {e}")

    # ---------------------------------------------------------------------
    # Navigation to Other Pages
    # ---------------------------------------------------------------------
    def go_to_homepage(self):
        self.stop_all_timers()
        self.home_page = open_homepage()
        self.home_page.show()
        self.close()

    def view_flight_history(self):
        self.report_app = DroneReportApp(self.field_path)
        self.report_app.show()

    def stop_all_timers(self):
        self.flight_timer.stop()
        self.ui_timer.stop()
        self.controller_timer.stop()
        self.stream_timer.stop()
        self.stop_recording()

        if self.is_connected:
            try:
                self.drone.streamoff()
                print("Tello stream is OFF.")
            except Exception as e:
                print(f"Error turning stream off: {e}")


