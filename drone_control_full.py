import sys
import os
import datetime
import logging
import subprocess
import platform

import pygame
import cv2
from djitellopy import Tello

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QGroupBox, QVBoxLayout, QProgressBar,
    QHBoxLayout, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QPoint
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor, QPolygon

from video_process import run
from shared import open_real_drone_control  # Opens the windowed UI

# Global exception hook
def log_uncaught_exceptions(exctype, value, traceback):
    logging.critical("Uncaught exception", exc_info=(exctype, value, traceback))
sys.excepthook = log_uncaught_exceptions

# =============================================================================
# RealDroneController: Separates real-drone logic from the UI
# =============================================================================
class RealDroneController:
    """
    Encapsulates all real drone control functionality.
    Wraps djitellopy.Tello and provides methods for connection,
    flight commands, video streaming, and video recording.
    """
    def __init__(self, flights_folder):
        self.flights_folder = flights_folder
        self.tello = Tello()
        self.is_flying = False
        self.frame_read = None
        self.is_recording = False
        self.video_writer = None
        self.flight_start_time = None
        self.current_flight_folder = None
        self.frame_width = 960
        self.frame_height = 720

    def connect(self):
        """Connect to the real drone and start video streaming."""
        self.tello.connect()
        self.tello.streamon()
        self.frame_read = self.tello.get_frame_read()
        battery = self.tello.get_battery()
        print(f"Real Drone connected. Battery: {battery}%")

    def streamon(self):
        self.tello.streamon()
        print("Real drone stream started")

    def streamoff(self):
        self.tello.streamoff()
        print("Real drone stream stopped")

    def end(self):
        self.tello.end()
        print("Real drone disconnected")

    # --- Basic Drone Movement Commands ---
    def takeoff(self):
        if self.is_flying:
            print("Drone is already in flight.")
        else:
            self.tello.takeoff()
            self.is_flying = True
            print("Taking off...")

    def land(self):
        if not self.is_flying:
            print("Drone is already landed.")
        else:
            self.tello.land()
            self.is_flying = False
            print("Landing...")

    def move_forward(self, distance=30):
        if not self.is_flying:
            print("Cannot move. Drone not in flight.")
            return
        self.tello.move_forward(distance)
        print("Moving forward...")

    def move_backward(self, distance=30):
        if not self.is_flying:
            print("Cannot move. Drone not in flight.")
            return
        self.tello.move_back(distance)
        print("Moving backward...")

    def move_left(self, distance=30):
        if not self.is_flying:
            print("Cannot move. Drone not in flight.")
            return
        self.tello.move_left(distance)
        print("Moving left...")

    def move_right(self, distance=30):
        if not self.is_flying:
            print("Cannot move. Drone not in flight.")
            return
        self.tello.move_right(distance)
        print("Moving right...")

    def move_up(self, distance=30):
        if not self.is_flying:
            print("Cannot move. Drone not in flight.")
            return
        self.tello.move_up(distance)
        print("Moving up...")

    def move_down(self, distance=30):
        if not self.is_flying:
            print("Cannot move. Drone not in flight.")
            return
        self.tello.move_down(distance)
        print("Moving down...")

    def rotate_left(self, angle=30):
        if not self.is_flying:
            print("Cannot rotate. Drone not in flight.")
            return
        self.tello.rotate_counter_clockwise(angle)
        print("Rotating left...")

    def rotate_right(self, angle=30):
        if not self.is_flying:
            print("Cannot rotate. Drone not in flight.")
            return
        self.tello.rotate_clockwise(angle)
        print("Rotating right...")

    def flip_left(self):
        if not self.is_flying:
            print("Cannot flip. Drone not in flight.")
            return
        self.tello.flip_left()
        print("Flipping left...")

    def flip_right(self):
        if not self.is_flying:
            print("Cannot flip. Drone not in flight.")
            return
        self.tello.flip_right()
        print("Flipping right...")

    # --- Helper Methods for Drone State ---
    def get_battery(self):
        return self.tello.get_battery()

    def get_height(self):
        return self.tello.get_height()

    def get_speed_x(self):
        return self.tello.get_speed_x()

    # --- Video Recording Methods ---
    def start_recording(self):
        if self.current_flight_folder is None:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self.current_flight_folder = os.path.join(self.flights_folder, f"flight_{timestamp}")
            os.makedirs(self.current_flight_folder, exist_ok=True)
        self.is_recording = True
        output_path = os.path.join(self.current_flight_folder, "flight_video.mp4")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self.video_writer = cv2.VideoWriter(output_path, fourcc, 20.0, (self.frame_width, self.frame_height))
        print(f"Recording started: {output_path}")

    def stop_recording(self):
        if self.is_recording and self.video_writer is not None:
            self.is_recording = False
            self.video_writer.release()
            self.video_writer = None
            print("Recording stopped.")

    def record_frame(self, frame):
        if self.is_recording and self.video_writer is not None:
            self.video_writer.write(frame)


# =============================================================================
# Fullscreen Drone Operating Page (UI remains unchanged)
# =============================================================================
class DroneOperatingPage(QWidget):
    """
    Fullscreen UI for real drone operation.
    Uses the RealDroneController for all drone commands and recording.
    Provides live video stream, control buttons, stats, joystick overlays,
    and full screen/windowed mode toggling.
    """
    def __init__(self, field_path):
        super().__init__()
        self.field_path = field_path
        self.flights_folder = os.path.join(self.field_path, "flights")
        os.makedirs(self.flights_folder, exist_ok=True)

        # Initialize the real drone controller
        self.drone_controller = RealDroneController(self.flights_folder)
        self.drone_controller.connect()
        self.drone_controller.streamon()
        # For convenience, also keep a local reference to the frame reader:
        self.frame_read = self.drone_controller.frame_read

        # States
        self.flight_duration = 0
        self.battery_level = 100

        # Video recording state is now managed by the controller

        # Button state for joystick debouncing
        self.button_states = {}

        # Timers
        self.flight_timer = QTimer()
        self.flight_timer.timeout.connect(self.update_flight_duration)

        self.ui_timer = QTimer()
        self.ui_timer.timeout.connect(self.update_ui_stats)
        self.ui_timer.start(2000)

        self.joystick_timer = QTimer()
        self.joystick_timer.timeout.connect(self.update_joystick_inputs)
        self.joystick_timer.timeout.connect(self.setup_controller)
        self.joystick_timer.start(20)

        self.stream_timer = QTimer()
        self.stream_timer.timeout.connect(self.update_video_stream)
        self.stream_timer.start(50)

        pygame.init()
        pygame.joystick.init()
        self.controller = None

        # Start in full screen mode
        self.setWindowState(Qt.WindowState.WindowFullScreen)
        self.init_ui()
        self.setup_controller()

    def init_ui(self):
        try:
            self.setWindowTitle("Real Drone Controller - Full Screen")
            # Video stream label fills the background
            self.stream_label = QLabel(self)
            self.stream_label.setGeometry(0, 0, self.width(), self.height())
            self.stream_label.setStyleSheet("background-color: black;")
            self.stream_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

            # Notification label (for warnings)
            self.notification_label = QLabel("", self)
            self.notification_label.setStyleSheet("color: red; font-size: 16px; font-weight: bold;")
            self.notification_label.setGeometry(10, 450, 400, 50)
            self.notification_label.setVisible(False)

            # Emergency Button
            self.emergency_button = QPushButton("EMERGENCY", self)
            self.emergency_button.setGeometry(self.width() // 2 - 100, 10, 200, 50)
            self.emergency_button.setStyleSheet("background-color: red; color: white; font-size: 18px; font-weight: bold;")
            self.emergency_button.clicked.connect(self.emergency_landing)

            # Toggle Full Screen Button
            self.toggle_fullscreen_button = QPushButton("Exit Full Screen", self)
            self.toggle_fullscreen_button.setStyleSheet("background-color: blue; color: white; font-size: 16px; font-weight: bold;")
            self.toggle_fullscreen_button.clicked.connect(self.toggle_fullscreen)
            self.toggle_fullscreen_button.adjustSize()
            self.toggle_fullscreen_button.setGeometry(10, 10, 200, 50)

            # Windowed Mode Button
            self.close_button = QPushButton("Windowed Mode", self)
            self.close_button.setStyleSheet("background-color: blue; color: white; font-size: 16px; font-weight: bold;")
            self.close_button.clicked.connect(self.launch_windowed)
            self.close_button.adjustSize()
            self.close_button.setGeometry(self.width() - 210, 10, 200, 50)

            # Status Label
            self.status_label = QLabel("Signal: Strong | Connection: Stable", self)
            self.status_label.setStyleSheet("background-color: rgba(0, 0, 0, 0.5); color: white; font-size: 18px; padding: 10px;")
            self.status_label.setGeometry(10, 70, 400, 50)

            # Controller Status Label
            self.controller_status_label = QLabel("No Controller Connected", self)
            self.controller_status_label.setStyleSheet("color: red; font-size: 14px; font-weight: bold;")
            self.controller_status_label.setGeometry(10, 130, 400, 50)

            # Battery Bar
            self.battery_bar = QProgressBar(self)
            self.battery_bar.setGeometry(10, 190, 400, 50)
            self.battery_bar.setValue(self.battery_level)
            self.battery_bar.setStyleSheet("QProgressBar::chunk { background-color: green; }")

            # Drone Info Box (for stats)
            self.info_box = QGroupBox("Drone Info", self)
            self.info_box.setGeometry(10, 250, 400, 250)
            info_layout = QVBoxLayout()
            self.info_labels = {
                "Temperature": QLabel("20°C", self),
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

            # Joystick Overlays
            self.joystick_left = DirectionalJoystick(self, "Left Joystick")
            self.joystick_left.setGeometry(50, self.height() - 250, 200, 200)

            self.joystick_right = CircularJoystick(self, "Right Joystick")
            self.joystick_right.setGeometry(self.width() - 250, self.height() - 250, 200, 200)

            # Drone State Label
            self.drone_state_label = QLabel("Landed", self)
            self.drone_state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.drone_state_label.setStyleSheet("background-color: rgba(200, 200, 200, 0.7); color: black; font-size: 18px; font-weight: bold; padding: 5px;")
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
        self.drone_state_label.move(self.width() // 2 - self.drone_state_label.width() // 2, self.height() - 100)

    def toggle_fullscreen(self):
        """Toggle between full screen and windowed mode."""
        if self.isFullScreen():
            self.showNormal()
            self.toggle_fullscreen_button.setText("Enter Full Screen")
        else:
            self.showFullScreen()
            self.toggle_fullscreen_button.setText("Exit Full Screen")

    def launch_windowed(self):
        """Switch to the windowed drone control UI."""
        self.flight_timer.stop()
        self.ui_timer.stop()
        self.joystick_timer.stop()
        pygame.joystick.quit()
        pygame.quit()
        self.drone_controller.end()
        self.windowed_ui = open_real_drone_control(self.field_path)
        self.windowed_ui.show()
        self.close()

    def update_flight_duration(self):
        self.flight_duration += 1
        self.info_labels["Flight Duration"].setText(f"{self.flight_duration} sec")

    def update_ui_stats(self):
        try:
            battery = self.drone_controller.get_battery()
            height = self.drone_controller.get_height()
            self.battery_bar.setValue(battery)
            self.info_labels["Height"].setText(f"{height} cm")
            speed = self.drone_controller.get_speed_x()
            self.info_labels["Speed"].setText(f"{speed} cm/s")
        except Exception as e:
            print("Failed to get drone state:", e)

    def update_video_stream(self):
        frame = self.frame_read.frame
        if frame is None:
            return
        # Use the drone’s RGB frame directly for display.
        h, w, ch = frame.shape
        bytes_per_line = ch * w
        q_img = QImage(frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(q_img)
        scaled_pixmap = pixmap.scaled(self.stream_label.width(), self.stream_label.height(),
                                       Qt.AspectRatioMode.KeepAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation)
        self.stream_label.setPixmap(scaled_pixmap)
        if self.drone_controller.is_recording and self.drone_controller.video_writer is not None:
            self.drone_controller.record_frame(frame)

    # --- Video Recording and Flight Control (auto-record on takeoff/land) ---
    def start_recording(self):
        self.drone_controller.start_recording()

    def stop_recording(self):
        self.drone_controller.stop_recording()

    
    
    def take_off(self):
        if not self.drone_controller.is_flying:
            self.drone_state_label.setText("Taking Off...")
            self.drone_state_label.adjustSize()
            self.close_button.setEnabled(False)
            self.close_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: lightgray; color: gray;")
            QTimer.singleShot(5000, self._perform_take_off)

    def _perform_take_off(self):
        self.drone_state_label.setText("On Air.")
        self.drone_state_label.adjustSize()
        self.drone_controller.takeoff()
        self.flight_timer.start(1000)
        self.drone_controller.flight_start_time = datetime.datetime.now()
        # Reset the flight folder and start recording
        self.drone_controller.current_flight_folder = None
        self.stream_label.setText("Stream On")
        self.start_recording()
        print("Take off successful")

    def land(self):
        if self.drone_controller.is_flying:
            self.drone_state_label.setText("Landing...")
            self.drone_state_label.adjustSize()
            self.close_button.setEnabled(True)
            self.close_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: #007BFF; color: white;")
            QTimer.singleShot(5000, self._perform_landing)

    def _perform_landing(self):
        self.drone_state_label.setText("Landed.")
        self.drone_state_label.adjustSize()
        self.drone_controller.land()
        self.flight_timer.stop()
        self.stream_label.setText("Stream Off")
        print("Landing successful")
        self.stop_recording()
        self.drone_controller.flight_end_time = datetime.datetime.now()
        duration = self.drone_controller.flight_end_time - self.drone_controller.flight_start_time
        QMessageBox.information(self, "Drone Status", f"Flight completed!\nDuration: {duration}")
        self.process_flight_video(duration)

    def emergency_landing(self):
        logging.info("Emergency landing initiated!")
        self.update_drone_state("Emergency Landing")
        self.drone_controller.land()

    def update_drone_state(self, state: str):
        self.drone_state_label.setText(state)
        self.drone_state_label.adjustSize()
        self.drone_state_label.move(self.width() // 2 - self.drone_state_label.width() // 2, self.height() - 100)

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
            potential_path = os.path.join(self.drone_controller.current_flight_folder, f"flight_video{fmt}")
            if os.path.exists(potential_path):
                video_path = potential_path
                break
        if video_path:
            try:
                run(video_path, duration, self.field_path)
                QMessageBox.information(self, "Video Processing", f"Video processed successfully!\nResults in:\n{run_folder}")
            except Exception as e:
                QMessageBox.critical(self, "Processing Error", f"Error processing video: {e}")
        else:
            QMessageBox.warning(self, "Video Missing", "No flight video found for processing!")

    # --- Controller & Joystick Functions ---
    def setup_controller(self):
        try:
            if pygame.joystick.get_count() > 0:
                self.controller = pygame.joystick.Joystick(0)
                self.controller.init()
                self.controller_status_label.setText("Controller Connected")
                self.controller_status_label.setStyleSheet("color: green; font-size: 14px; font-weight: bold;")
            else:
                self.controller_status_label.setText("No Controller Connected")
                self.controller_status_label.setStyleSheet("color: red; font-size: 14px; font-weight: bold;")
                self.controller = None
        except Exception as e:
            logging.error(f"Error setting up controller: {e}")

    def update_joystick_inputs(self):
        if self.controller:
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

    def launch_windowed(self):
        self.flight_timer.stop()
        self.ui_timer.stop()
        self.joystick_timer.stop()
        pygame.joystick.quit()
        pygame.quit()
        self.drone_controller.end()
        self.windowed_ui = open_real_drone_control(self.field_path)
        self.windowed_ui.show()
        self.close()

# =============================================================================
# Joystick Overlay Classes (unchanged)
# =============================================================================
class DirectionalJoystick(QWidget):
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
    def __init__(self, parent, label):
        super().__init__(parent)
        self.setFixedSize(200, 200)
        self.label = label
        self.x_pos = 0.0
        self.y_pos = 0.0

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for radius in range(30, 121, 30):
            painter.setPen(QColor(255, 255, 255, 100))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(100 - radius, 100 - radius, radius * 2, radius * 2)
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
if __name__ == "__main__":
    app = QApplication(sys.argv)
    field_path = "fields"  # or adjust as needed
    window = DroneOperatingPage(field_path)
    window.show()
    sys.exit(app.exec())
