import sys
import os
import datetime
import logging
import subprocess
import platform

# Pygame is used for joystick/keyboard inputs and OpenCV for image/video processing.
import pygame
import cv2
from djitellopy import Tello

# PyQt6 modules for creating the graphical user interface.
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QGroupBox, QVBoxLayout,
    QHBoxLayout, QMessageBox, QProgressBar
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QPoint
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor, QPolygon

# Import your existing drone classes from dronefunctions.py
from drone_functions import DroneController, DroneConnectWorker, ConnectingDialog

# External modules for video processing and shared UI functionality.
from video_process import run
from shared import open_real_drone_control  # Opens the windowed drone control UI


# -----------------------------------------------------------------------------
# Global exception hook to log any uncaught exceptions.
# -----------------------------------------------------------------------------
def log_uncaught_exceptions(exctype, value, traceback):
    logging.critical("Uncaught exception", exc_info=(exctype, value, traceback))

sys.excepthook = log_uncaught_exceptions


# =============================================================================
# Utility function to ping the drone's IP to verify connectivity
# =============================================================================
def ping_drone(ip="192.168.10.1", count=1, timeout=1) -> bool:
    """
    Ping the drone using its IP address. Returns True if successful, otherwise False.
    """
    param = "-n" if platform.system().lower() == "windows" else "-c"
    if platform.system().lower() == "windows":
        command = ["ping", param, str(count), "-w", str(timeout * 1000), ip]
    else:
        command = ["ping", param, str(count), "-W", str(timeout), ip]

    try:
        subprocess.check_output(command, stderr=subprocess.STDOUT, universal_newlines=True)
        return True
    except subprocess.CalledProcessError:
        return False


# =============================================================================
# Extend DroneController to expose signal strength (if supported)
# =============================================================================
class ExtendedDroneController(DroneController):
    """Subclass that adds a get_wifi_signal() method if Tello supports get_wifi()."""

    def get_wifi_signal(self):
        """
        Retrieve the Wi-Fi signal strength (if supported by djitellopy).
        Returns None if not supported or if any error occurs.
        """
        try:
            # Tello.get_wifi() typically returns a string like "90%"
            # or an integer. We'll just return the raw string for display.
            val = self.tello.get_wifi()
            return val
        except:
            return None


# =============================================================================
# Fullscreen Drone Operating Page (UI)
# =============================================================================
class DroneOperatingPage(QWidget):
    """
    This QWidget provides a full-screen user interface for controlling
    a real drone. It uses DroneController for commands, streaming, and recording.
    The UI includes live video, control buttons, status displays, joystick overlays,
    and mode toggling.
    """
    def __init__(self, field_path):
        super().__init__()
        self.field_path = field_path
        # Create the folder for storing flights if it doesn't exist.
        self.flights_folder = os.path.join(self.field_path, "flights")
        os.makedirs(self.flights_folder, exist_ok=True)

        # Use our ExtendedDroneController that can retrieve Wi-Fi signal
        self.drone_controller = ExtendedDroneController(Tello(), self.flights_folder)

        # State variables for flight duration and battery.
        self.flight_duration = 0
        self.battery_level = 100

        # Button state dictionary for joystick debouncing.
        self.button_states = {}

        # Timers ---------------------------------------------------------------
        self.flight_timer = QTimer()
        self.flight_timer.timeout.connect(self.update_flight_duration)

        self.ui_timer = QTimer()
        self.ui_timer.timeout.connect(self.update_ui_stats)
        self.ui_timer.start(2000)  # Update UI stats every 2 seconds

        # Joystick checking
        pygame.init()
        pygame.joystick.init()

        self.joystick_timer = QTimer()
        self.joystick_timer.timeout.connect(self.update_joystick_inputs)
        self.joystick_timer.timeout.connect(self.setup_controller)
        self.joystick_timer.start(20)  # Poll joystick inputs every 20ms

        # Video stream timer (will start after successful connection)
        self.stream_timer = QTimer()
        self.stream_timer.timeout.connect(self.update_video_stream)

        # Timer to ping the drone and check connectivity
        self.connection_check_timer = QTimer()
        self.connection_check_timer.timeout.connect(self.check_drone_connection)
        self.connection_check_timer.start(2000)  # every 2s

        self.consecutive_ping_failures = 0

        # Start in full screen mode.
        self.setWindowState(Qt.WindowState.WindowFullScreen)
        # Build the UI elements.
        self.init_ui()
        # Setup controller (if connected).
        self.setup_controller()

        # Try to connect asynchronously (no blocking in __init__).
        self.connecting_dialog = None
        self.connect_drone_async()

    # -------------------------------------------------------------------------
    # UI Initialization
    # -------------------------------------------------------------------------
    def init_ui(self):
        try:
            self.setWindowTitle("Real Drone Controller - Full Screen")

            # Video stream background
            self.stream_label = QLabel(self)
            self.stream_label.setGeometry(0, 0, self.width(), self.height())
            self.stream_label.setStyleSheet("background-color: black;")
            self.stream_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

            # Notification label (hidden by default)
            self.notification_label = QLabel("", self)
            self.notification_label.setStyleSheet("color: red; font-size: 16px; font-weight: bold;")
            self.notification_label.setGeometry(10, 450, 400, 50)
            self.notification_label.setVisible(False)

            # Emergency button
            self.emergency_button = QPushButton("EMERGENCY", self)
            self.emergency_button.setGeometry(self.width() // 2 - 100, 10, 200, 50)
            self.emergency_button.setStyleSheet(
                "background-color: red; color: white; font-size: 18px; font-weight: bold; border: 2px solid white;"
            )
            self.emergency_button.clicked.connect(self.emergency_landing)

            # Toggle Full Screen
            self.toggle_fullscreen_button = QPushButton("Exit Full Screen", self)
            self.toggle_fullscreen_button.setStyleSheet(
                "background-color: #007BFF; color: white; font-size: 16px; font-weight: bold; border: 2px solid white;"
            )
            self.toggle_fullscreen_button.adjustSize()
            self.toggle_fullscreen_button.setGeometry(10, 10, 200, 50)
            self.toggle_fullscreen_button.clicked.connect(self.toggle_fullscreen)

            # Windowed Mode button
            self.close_button = QPushButton("Windowed Mode", self)
            self.close_button.setStyleSheet(
                "background-color: #007BFF; color: white; font-size: 16px; font-weight: bold; border: 2px solid white;"
            )
            self.close_button.adjustSize()
            self.close_button.setGeometry(self.width() - 210, 10, 200, 50)
            self.close_button.clicked.connect(self.launch_windowed)

            # Status label (2px white border)
            self.status_label = QLabel("Signal: ??? | Connection: ???", self)
            self.status_label.setStyleSheet(
                "background-color: rgba(0, 0, 0, 0.5); color: white; font-size: 18px; padding: 10px;"
                "border: 2px solid white;"
            )
            self.status_label.setGeometry(10, 70, 400, 50)

            # Controller Status label (2px white border)
            self.controller_status_label = QLabel("No Controller Connected", self)
            self.controller_status_label.setStyleSheet(
                "color: red; font-size: 14px; font-weight: bold; border: 2px solid white; padding: 2px;"
            )
            self.controller_status_label.setGeometry(10, 130, 400, 50)

            # Battery bar (2px white border), with left-aligned text inside
            self.battery_bar = QProgressBar(self)
            self.battery_bar.setGeometry(10, 190, 400, 50)
            self.battery_bar.setValue(self.battery_level)
            self.battery_bar.setTextVisible(True)
            self.battery_bar.setFormat("  %p%")  # e.g., "85%"
            self.battery_bar.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.battery_bar.setStyleSheet(
                """
                QProgressBar {
                    border: 2px solid white;
                    text-align: left;
                    padding-left: 5px; /* Additional left padding so text won't overlap border */
                }
                QProgressBar::chunk {
                    background-color: green;
                }
                """
            )

            # Info box (2px white border) with temperature, height, speed, flight duration
            self.info_box = QGroupBox("Drone Info", self)
            self.info_box.setStyleSheet("QGroupBox { border: 2px solid white; }")
            self.info_box.setGeometry(10, 250, 400, 250)
            info_layout = QVBoxLayout()
            self.info_labels = {
                "Temperature": QLabel("0°C", self),
                "Height": QLabel("0 cm", self),
                "Speed": QLabel("0 cm/s", self),
                "Flight Duration": QLabel("0 sec", self),
            }
            for key, lbl in self.info_labels.items():
                row = QHBoxLayout()
                row.addWidget(QLabel(f"{key}:", self))
                row.addWidget(lbl)
                info_layout.addLayout(row)
            self.info_box.setLayout(info_layout)

            # Joystick overlays
            self.joystick_left = DirectionalJoystick(self, "Left Joystick")
            self.joystick_left.setGeometry(50, self.height() - 250, 200, 200)

            self.joystick_right = CircularJoystick(self, "Right Joystick")
            self.joystick_right.setGeometry(self.width() - 250, self.height() - 250, 200, 200)

            # Drone state label (e.g., "Landed", "On Air", etc.) with 2px white border
            self.drone_state_label = QLabel("Landed", self)
            self.drone_state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.drone_state_label.setStyleSheet(
                "background-color: rgba(200, 200, 200, 0.7); color: black; font-size: 18px; font-weight: bold; padding: 5px; border: 2px solid white;"
            )
            self.drone_state_label.move(self.width() // 2 - 50, self.height() - 100)
            self.drone_state_label.adjustSize()

        except Exception as e:
            logging.error(f"Error initializing DroneOperatingPage: {e}")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.stream_label.setGeometry(0, 0, self.width(), self.height())
        self.emergency_button.setGeometry(self.width() // 2 - 100, 10, 200, 50)
        self.close_button.setGeometry(self.width() - 210, 10, 200, 50)
        self.toggle_fullscreen_button.setGeometry(10, 10, 200, 50)
        self.joystick_left.setGeometry(50, self.height() - 250, 200, 200)
        self.joystick_right.setGeometry(self.width() - 250, self.height() - 250, 200, 200)
        self.drone_state_label.move(
            self.width() // 2 - self.drone_state_label.width() // 2,
            self.height() - 100,
        )

    # -------------------------------------------------------------------------
    # Asynchronous Drone Connection
    # -------------------------------------------------------------------------
    def connect_drone_async(self):
        """Connect to the drone in a background thread; show a 'Connecting...' dialog."""
        self.connecting_dialog = ConnectingDialog()
        self.connecting_dialog.show()

        self.connection_thread = QThread()
        self.connection_worker = DroneConnectWorker(self.drone_controller)
        self.connection_worker.moveToThread(self.connection_thread)

        self.connection_thread.started.connect(self.connection_worker.run)
        self.connection_worker.connect_success.connect(self.handle_connect_success)
        self.connection_worker.connect_error.connect(self.handle_connect_error)

        self.connection_worker.connect_success.connect(self.connection_thread.quit)
        self.connection_worker.connect_error.connect(self.connection_thread.quit)
        self.connection_thread.finished.connect(self.connection_thread.deleteLater)

        self.connection_thread.start()

    def handle_connect_success(self):
        print("[UI] Drone connected successfully!")
        self.stream_timer.start(50)
        self.connecting_dialog.close()

    def handle_connect_error(self, error_message):
        """
        If we fail to connect at all, we show an error and return to windowed mode.
        """
        print("Connection error:", error_message)
        QMessageBox.critical(self, "Connection Error", f"Could not connect:\n{error_message}")
        self.connecting_dialog.close()
        self.launch_windowed()  # Immediately return to windowed mode on connect fail.

    def check_drone_connection(self):
        if not self.drone_controller.is_connected:
            return

        # Attempt to retrieve Wi-Fi signal (if available), else show N/A
        wifi_signal = self.drone_controller.get_wifi_signal()
        if wifi_signal is not None:
            # Example: Tello might return "70%"
            self.status_label.setText(f"Signal: {wifi_signal} | Connection: OK")
        else:
            self.status_label.setText(f"Signal: N/A | Connection: OK")

        # Also do a ping check
        if not ping_drone("192.168.10.1"):
            self.consecutive_ping_failures += 1
            print(f"Ping failed. Consecutive failures: {self.consecutive_ping_failures}")
            if self.consecutive_ping_failures >= 3:
                print("[UI] Drone lost connection after multiple ping failures.")
                self.drone_controller.is_connected = False
                QMessageBox.warning(self, "Drone Disconnected", "Lost connection to drone!")
                # Immediately return to windowed mode on lost connection
                self.launch_windowed()
        else:
            self.consecutive_ping_failures = 0

    # -------------------------------------------------------------------------
    # Windowed Mode
    # -------------------------------------------------------------------------
    def launch_windowed(self):
        """
        Switch from full-screen to windowed mode, stopping all timers,
        quitting joystick, and disconnecting from the drone if needed.
        """
        self.flight_timer.stop()
        self.ui_timer.stop()
        self.joystick_timer.stop()
        self.stream_timer.stop()
        pygame.joystick.quit()
        pygame.quit()

        if self.drone_controller.is_connected:
            self.drone_controller.streamoff()
            self.drone_controller.disconnect()

        self.windowed_ui = open_real_drone_control(self.field_path)
        self.windowed_ui.show()
        self.close()

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            self.toggle_fullscreen_button.setText("Enter Full Screen")
        else:
            self.showFullScreen()
            self.toggle_fullscreen_button.setText("Exit Full Screen")

    # -------------------------------------------------------------------------
    # Flight Duration & UI Stats
    # -------------------------------------------------------------------------
    def update_flight_duration(self):
        self.flight_duration += 1
        self.info_labels["Flight Duration"].setText(f"{self.flight_duration} sec")

    def update_ui_stats(self):
        try:
            battery = self.drone_controller.get_battery()
            height = self.drone_controller.get_height()
            temp = self.drone_controller.get_temperature()

            # Update the battery bar value
            self.battery_bar.setValue(battery)

            # Update other labels
            self.info_labels["Height"].setText(f"{height} cm")
            self.info_labels["Temperature"].setText(f"{temp}°C")
            speed = self.drone_controller.get_speed_x()
            self.info_labels["Speed"].setText(f"{speed} cm/s")

        except Exception as e:
            print("[UI] Failed to get drone state:", e)

    # -------------------------------------------------------------------------
    # Video Stream
    # -------------------------------------------------------------------------
    def update_video_stream(self):
        frame = self.drone_controller.get_frame()
        if frame is None:
            return

        h, w, ch = frame.shape
        bytes_per_line = ch * w
        q_img = QImage(frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(q_img)
        scaled_pixmap = pixmap.scaled(
            self.stream_label.width(),
            self.stream_label.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.stream_label.setPixmap(scaled_pixmap)

        if self.drone_controller.is_recording:
            self.drone_controller.record_frame(frame)

    # -------------------------------------------------------------------------
    # Flight Control
    # -------------------------------------------------------------------------
    def start_recording(self):
        self.drone_controller.start_recording()

    def stop_recording(self):
        self.drone_controller.stop_recording()

    def take_off(self):
        if not self.drone_controller.is_flying:
            self.drone_state_label.setText("Taking Off...")
            self.drone_state_label.adjustSize()
            self.close_button.setEnabled(False)
            self.close_button.setStyleSheet(
                "font-size: 16px; padding: 10px; background-color: lightgray; color: gray; border: 2px solid white;"
            )
            try:
                self.drone_controller.takeoff()
                self.flight_timer.start(1000)  # Start flight duration timer
                self.drone_controller.flight_start_time = datetime.datetime.now()
                self.drone_state_label.setText("On Air.")
                self.drone_state_label.adjustSize()
                self.stream_label.setText("Stream On")
                self.start_recording()
                print("Take off successful")
            except Exception as e:
                QMessageBox.critical(self, "Takeoff Error", str(e))

    def land(self):
        """
        Normal landing with a 5-second delay before performing the final landing steps.
        """
        if self.drone_controller.is_flying:
            self.drone_state_label.setText("Landing...")
            self.drone_state_label.adjustSize()
            self.close_button.setEnabled(True)
            self.close_button.setStyleSheet(
                "font-size: 16px; padding: 10px; background-color: #007BFF; color: white; border: 2px solid white;"
            )

            # After 5 seconds, call _perform_landing to finalize.
            QTimer.singleShot(5000, self._perform_landing)

    def _perform_landing(self):
        """Actually land the drone and finalize the flight."""
        try:
            self.drone_controller.land()
            print("Landing successful")
        except Exception as e:
            QMessageBox.critical(self, "Land Error", str(e))

        # Now do the post-landing steps
        self.flight_timer.stop()
        self.stream_label.setText("Stream Off")
        self.stop_recording()

        self.drone_controller.flight_end_time = datetime.datetime.now()
        duration = self.drone_controller.flight_end_time - self.drone_controller.flight_start_time
        QMessageBox.information(self, "Drone Status", f"Flight completed!\nDuration: {duration}")

        # Process flight video
        self.process_flight_video(duration)

        # Reset flight duration
        self.flight_duration = 0
        self.info_labels["Flight Duration"].setText("0 sec")

        # Update label
        self.drone_state_label.setText("Landed.")
        self.drone_state_label.adjustSize()

    def emergency_landing(self):
        """
        Emergency landing performs immediate landing only if the drone is flying.
        Otherwise, it does nothing.
        Video saving/processing should still occur, same as a normal flight end.
        """
        if not self.drone_controller.is_flying:
            logging.info("Drone is already landed; cannot perform emergency landing.")
            return

        logging.info("Emergency landing initiated!")
        self.update_drone_state("Emergency Landing")

        try:
            self.drone_controller.land()
            print("Emergency landing successful")
        except Exception as e:
            logging.error("Emergency landing failed: %s", e)

        # Now finalize flight
        self.flight_timer.stop()
        self.stream_label.setText("Stream Off")
        self.stop_recording()

        self.drone_controller.flight_end_time = datetime.datetime.now()
        duration = self.drone_controller.flight_end_time - self.drone_controller.flight_start_time

        QMessageBox.information(
            self,
            "Drone Status",
            f"Emergency landing performed!\nFlight duration: {duration}",
        )

        self.process_flight_video(duration)

        # Reset flight duration
        self.flight_duration = 0
        self.info_labels["Flight Duration"].setText("0 sec")

        # Update label
        self.drone_state_label.setText("Emergency Landed.")
        self.drone_state_label.adjustSize()

        # Re-enable the close_button if needed
        self.close_button.setEnabled(True)
        self.close_button.setStyleSheet(
            "font-size: 16px; padding: 10px; background-color: #007BFF; color: white; border: 2px solid white;"
        )

    def update_drone_state(self, state: str):
        self.drone_state_label.setText(state)
        self.drone_state_label.adjustSize()
        self.drone_state_label.move(
            self.width() // 2 - self.drone_state_label.width() // 2, self.height() - 100
        )

    def process_flight_video(self, duration):
        if not self.drone_controller.current_flight_folder:
            QMessageBox.warning(self, "Error", "Flight folder not set. Cannot process video.")
            return
        runs_folder = os.path.join(self.field_path, "runs")
        os.makedirs(runs_folder, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        run_folder = os.path.join(runs_folder, f"run_{timestamp}")
        os.makedirs(run_folder, exist_ok=True)

        video_formats = [".mp4", ".mov", ".avi"]
        video_path = None
        for fmt in video_formats:
            potential_path = os.path.join(
                self.drone_controller.current_flight_folder, f"flight_video{fmt}"
            )
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

    # -------------------------------------------------------------------------
    # Joystick Functions
    # -------------------------------------------------------------------------
    def setup_controller(self):
        try:
            if pygame.joystick.get_count() > 0:
                self.controller = pygame.joystick.Joystick(0)
                self.controller.init()
                self.controller_status_label.setText("Controller Connected")
                # Use white border for the controller label
                self.controller_status_label.setStyleSheet(
                    "color: green; font-size: 14px; font-weight: bold; border: 2px solid white; padding: 2px;"
                )
            else:
                self.controller_status_label.setText("No Controller Connected")
                self.controller_status_label.setStyleSheet(
                    "color: red; font-size: 14px; font-weight: bold; border: 2px solid white; padding: 2px;"
                )
                self.controller = None
        except Exception as e:
            logging.error(f"Error setting up controller: {e}")

    def update_joystick_inputs(self):
        if not hasattr(self, "controller") or self.controller is None:
            return

        try:
            pygame.event.pump()
            left_x = self.controller.get_axis(0)
            left_y = self.controller.get_axis(1)
            right_x = self.controller.get_axis(2)
            right_y = self.controller.get_axis(3)

            left_x = self.smooth_input(left_x)
            left_y = self.smooth_input(left_y)
            right_x = self.smooth_input(right_x)
            right_y = self.smooth_input(right_y)

            self.joystick_left.update_position(left_x, -left_y)
            self.joystick_right.update_position(right_x, -right_y)

            self.map_joystick_to_drone(left_x, left_y, right_x, right_y)

            for button_id, action in [(0, self.take_off), (1, self.land)]:
                button_pressed = self.controller.get_button(button_id)
                previously_pressed = self.button_states.get(button_id, False)
                if button_pressed and not previously_pressed:
                    action()
                    self.button_states[button_id] = True
                elif not button_pressed:
                    self.button_states[button_id] = False

        except Exception as e:
            logging.error(f"Error updating joystick inputs: {e}")

    def map_joystick_to_drone(self, left_x, left_y, right_x, right_y):
        try:
            if left_y < -0.5:
                self.drone_controller.move_forward()
            elif left_y > 0.5:
                self.drone_controller.move_backward()

            if left_x < -0.5:
                self.drone_controller.move_left()
            elif left_x > 0.5:
                self.drone_controller.move_right()

            if right_y < -0.5:
                self.drone_controller.move_up()
            elif right_y > 0.5:
                self.drone_controller.move_down()

            if right_x < -0.5:
                self.drone_controller.rotate_left()
            elif right_x > 0.5:
                self.drone_controller.rotate_right()

        except Exception as e:
            logging.error(f"Error mapping joystick inputs to drone: {e}")

    def smooth_input(self, value, threshold=0.1):
        if abs(value) < threshold:
            return 0.0
        return round(value, 2)


# =============================================================================
# Joystick Overlay Classes
# =============================================================================
class DirectionalJoystick(QWidget):
    """
    A simple directional joystick overlay: draws a circle background,
    arrows for direction, and a movable knob representing the joystick position.
    """
    def __init__(self, parent, label):
        super().__init__(parent)
        self.setFixedSize(200, 200)
        self.label = label
        self.x_pos = 0.0
        self.y_pos = 0.0

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(50, 50, 50, 150))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, 200, 200)

        arrow_color = QColor(255, 255, 255, 200)
        painter.setBrush(arrow_color)
        up_arrow = QPolygon([QPoint(100, 10), QPoint(90, 40), QPoint(110, 40)])
        painter.drawPolygon(up_arrow)
        down_arrow = QPolygon([QPoint(100, 190), QPoint(90, 160), QPoint(110, 160)])
        painter.drawPolygon(down_arrow)
        left_arrow = QPolygon([QPoint(10, 100), QPoint(40, 90), QPoint(40, 110)])
        painter.drawPolygon(left_arrow)
        right_arrow = QPolygon([QPoint(190, 100), QPoint(160, 90), QPoint(160, 110)])
        painter.drawPolygon(right_arrow)

        knob_x = int(100 + self.x_pos * 75)
        knob_y = int(100 - self.y_pos * 75)
        painter.setBrush(QColor(200, 0, 0, 200))
        painter.drawEllipse(knob_x - 10, knob_y - 10, 20, 20)

    def update_position(self, x: float, y: float):
        self.x_pos = x
        self.y_pos = y
        self.update()


class CircularJoystick(QWidget):
    """
    A circular joystick overlay with concentric circles and a movable knob.
    """
    def __init__(self, parent, label):
        super().__init__(parent)
        self.setFixedSize(200, 200)
        self.label = label
        self.x_pos = 0.0
        self.y_pos = 0.0

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Draw concentric circles
        for radius in range(30, 121, 30):
            painter.setPen(QColor(255, 255, 255, 100))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(100 - radius, 100 - radius, radius * 2, radius * 2)

        # Draw the knob
        knob_x = int(100 + self.x_pos * 75)
        knob_y = int(100 - self.y_pos * 75)
        painter.setBrush(QColor(200, 0, 0, 200))
        painter.drawEllipse(knob_x - 10, knob_y - 10, 20, 20)

    def update_position(self, x: float, y: float):
        self.x_pos = x
        self.y_pos = y
        self.update()


# =============================================================================
# Main entry point
# =============================================================================
# if __name__ == "__main__":
#     app = QApplication(sys.argv)
#     field_path = "fields"  # or wherever you store flight data
#     window = DroneOperatingPage(field_path)
#     window.show()
#     sys.exit(app.exec())
