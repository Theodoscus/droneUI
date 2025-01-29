import sys
import pygame
import cv2
import os
import random
import logging
import datetime

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QGroupBox, QVBoxLayout, QProgressBar,
    QHBoxLayout, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor, QPolygon
from PyQt6.QtCore import QPoint

from video_process import run
from shared import open_drone_control


def log_uncaught_exceptions(exctype, value, traceback):
    """
    Global exception handler to log uncaught exceptions at CRITICAL level.
    """
    logging.critical("Uncaught exception", exc_info=(exctype, value, traceback))

sys.excepthook = log_uncaught_exceptions


# ---------------------------------------------------------------------
# MockPTello: A Mock Drone Class
# ---------------------------------------------------------------------

class MockPTello:
    """
    Simulates some drone-like behaviors (flying, streaming video).
    No hardware communication is done.
    """

    def __init__(self):
        self.is_flying = False
        self.stream_on = False

    def connect(self):
        """Simulates connecting to the drone."""
        print("Mock: Drone connected")

    def streamon(self):
        """Simulates starting the video stream."""
        self.stream_on = True
        print("Mock: Video stream started")

    def streamoff(self):
        """Simulates stopping the video stream."""
        self.stream_on = False
        print("Mock: Video stream stopped")

    def end(self):
        """Simulates fully disconnecting from the drone."""
        print("Mock: Drone disconnected")

    # ------------------
    # Movement Methods
    # ------------------
    def move_forward(self):
        if not self.is_flying:
            print("Drone cannot move because it has not taken off.")
            return
        print("Moving forward...")

    def move_backward(self):
        if not self.is_flying:
            print("Drone cannot move because it has not taken off.")
            return
        print("Moving backward...")

    def move_left(self):
        if not self.is_flying:
            print("Drone cannot move because it has not taken off.")
            return
        print("Moving left...")

    def move_right(self):
        if not self.is_flying:
            print("Drone cannot move because it has not taken off.")
            return
        print("Moving right...")

    def move_up(self):
        if not self.is_flying:
            print("Drone cannot move because it has not taken off.")
            return
        print("Moving up...")

    def move_down(self):
        if not self.is_flying:
            print("Drone cannot move because it has not taken off.")
            return
        print("Moving down...")

    def rotate_left(self):
        if not self.is_flying:
            print("Drone cannot move because it has not taken off.")
            return
        print("Rotating left...")

    def rotate_right(self):
        if not self.is_flying:
            print("Drone cannot move because it has not taken off.")
            return
        print("Rotating right...")

    def flip_left(self):
        if not self.is_flying:
            print("Drone cannot move because it has not taken off.")
            return
        print("Flipping left...")

    def flip_right(self):
        if not self.is_flying:
            print("Drone cannot move because it has not taken off.")
            return
        print("Flipping right...")


# ---------------------------------------------------------------------
# DroneOperatingPage: Full-Screen Drone Operation UI
# ---------------------------------------------------------------------

class DroneOperatingPage(QWidget):
    """
    A fullscreen-like UI that displays:
      - Mock drone video stream placeholder
      - Joystick overlays for left and right sticks
      - Buttons for takeoff, land, emergency
      - Drone stats (battery, height, speed, flight duration)
      - Integration with 'video_process.run' for flight video after landing
    """

    def __init__(self, field_path):
        """
        Constructor for DroneOperatingPage.
          field_path: The folder path for the current field, used for saving flight data.
        """
        super().__init__()

        # Mock drone initialization
        self.drone = MockPTello()
        self.drone.connect()

        # Internal states
        self.is_flying = False
        self.flight_duration = 0
        self.battery_level = 100
        self.fly_height = 0
        self.speed = 0
        self.current_flight_folder = None
        self.field_path = field_path
        self.flights_folder = os.path.join(self.field_path, "flights")
        os.makedirs(self.flights_folder, exist_ok=True)

        # Button states to handle single-press logic
        self.button_states = {}

        # Timer for flight duration
        self.flight_timer = QTimer()
        self.flight_timer.timeout.connect(self.update_flight_duration)

        # Timer to periodically update UI stats
        self.ui_timer = QTimer()
        self.ui_timer.timeout.connect(self.update_ui_stats)
        self.ui_timer.start(2000)  # every 2 seconds

        # Timer for joystick overlays & controller setup
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_joystick_inputs)
        self.timer.timeout.connect(self.setup_controller)
        self.timer.start(20)  # every 20ms for smoother polling

        # Initialize PyGame for controller input
        pygame.init()
        pygame.joystick.init()
        self.controller = None

        # Build the UI
        self.init_ui()
        self.setup_controller()

    # ---------------------------------------------------------------------
    # UI Setup
    # ---------------------------------------------------------------------

    def init_ui(self):
        """
        Sets up the fullscreen-like UI:
          - Stream label (full background)
          - Emergency + Close/Windowed buttons
          - Status label
          - Battery/Drone info
          - Joystick overlays
        """
        try:
            self.setWindowTitle("Drone Controller")
            self.setGeometry(100, 100, 1024, 768)

            # Video Stream Placeholder
            self.stream_label = QLabel(self)
            self.stream_label.setGeometry(0, 0, self.width(), self.height())
            self.stream_label.setStyleSheet("background-color: black;")
            self.stream_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

            # Emergency Button
            self.emergency_button = QPushButton("EMERGENCY", self)
            self.emergency_button.setGeometry(self.width() // 2 - 100, 10, 200, 50)
            self.emergency_button.setStyleSheet("background-color: red; color: white; font-size: 18px; font-weight: bold;")
            self.emergency_button.clicked.connect(self.emergency_landing)

            # Close/Windowed Button
            self.close_button = QPushButton("Λειτουργία Παραθύρου", self)
            self.close_button.setStyleSheet("background-color: blue; color: white; font-size: 16px; font-weight: bold;")
            self.close_button.clicked.connect(self.launch_windowed)
            self.close_button.adjustSize()
            button_width = self.close_button.width()
            self.close_button.setGeometry(self.width() - button_width - 10, 10, 200, 50)

            # Connection Status Label
            self.status_label = QLabel("Signal: Strong | Connection: Stable", self)
            self.status_label.setStyleSheet(
                "background-color: rgba(0, 0, 0, 0.5); color: white; font-size: 18px; padding: 10px;"
            )
            self.status_label.setGeometry(10, 10, 400, 50)

            # Controller Status
            controller_status_box = QGroupBox("Controller Status", self)
            controller_layout = QVBoxLayout()
            self.controller_status_label = QLabel("No Controller Connected")
            self.controller_status_label.setStyleSheet("color: red; font-size: 14px; font-weight: bold;")
            controller_layout.addWidget(self.controller_status_label)
            controller_status_box.setLayout(controller_layout)
            controller_status_box.setGeometry(10, 70, 400, 50)

            # Battery Box
            battery_box = QGroupBox("Battery", self)
            battery_layout = QVBoxLayout()
            battery_box.setGeometry(10, 130, 400, 50)
            self.battery_bar = QProgressBar()
            self.battery_bar.setValue(self.battery_level)
            self.battery_bar.setStyleSheet("QProgressBar::chunk { background-color: green; }")
            battery_layout.addWidget(self.battery_bar)
            battery_box.setLayout(battery_layout)

            # Drone Info Box
            info_box = QGroupBox("Drone Info", self)
            info_layout = QVBoxLayout()
            info_box.setGeometry(10, 190, 400, 250)
            self.info_labels = {
                "Temperature": QLabel("20°C"),
                "Height": QLabel("0 cm"),
                "Speed": QLabel("0 cm/s"),
                "Data Transmitted": QLabel("0 MB"),
                "Flight Duration": QLabel("0 sec"),
            }
            for key, label in self.info_labels.items():
                row = QHBoxLayout()
                row.addWidget(QLabel(f"{key}:"))
                row.addWidget(label)
                info_layout.addLayout(row)
            info_box.setLayout(info_layout)

            # Joystick Overlays
            self.joystick_left = DirectionalJoystick(self, "Left Joystick")
            self.joystick_left.setGeometry(50, self.height() - 250, 200, 200)

            self.joystick_right = CircularJoystick(self, "Right Joystick")
            self.joystick_right.setGeometry(self.width() - 250, self.height() - 250, 200, 200)

            # Drone State Label
            self.drone_state_label = QLabel("Landed", self)
            self.drone_state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.drone_state_label.setStyleSheet(
                "background-color: rgba(200, 200, 200, 0.7); color: black; font-size: 18px; font-weight: bold; padding: 5px;"
            )
            self.drone_state_label.move(self.width() // 2 - 50, self.height() - 100)
            self.drone_state_label.adjustSize()

        except Exception as e:
            logging.error(f"Error initializing DroneOperatingPage: {e}")

    # ---------------------------------------------------------------------
    # Window Resizing
    # ---------------------------------------------------------------------

    def resizeEvent(self, event):
        """
        Adjusts positions/sizes of UI elements when the window is resized.
        """
        super().resizeEvent(event)

        # Resize stream label to fill the background
        self.stream_label.setGeometry(0, 0, self.width(), self.height())

        # Reposition emergency and close buttons
        self.emergency_button.setGeometry(self.width() // 2 - 100, 10, 200, 50)
        self.close_button.setGeometry(self.width() - 210, 10, 200, 50)

        # Joystick overlays
        self.joystick_left.setGeometry(50, self.height() - 250, 200, 200)
        self.joystick_right.setGeometry(self.width() - 250, self.height() - 250, 200, 200)

        # Drone state label near bottom center
        self.drone_state_label.move(
            self.width() // 2 - self.drone_state_label.width() // 2,
            self.height() - 100
        )

    # ---------------------------------------------------------------------
    # Flight Timers & Stats
    # ---------------------------------------------------------------------

    def update_flight_duration(self):
        """Increments flight duration every second."""
        self.flight_duration += 1
        self.info_labels["Flight Duration"].setText(f"{self.flight_duration} sec")

    def update_ui_stats(self):
        """
        Simulates random battery drain, height, speed
        and updates the battery bar + drone info labels.
        """
        self.battery_level = max(0, self.battery_level - random.randint(0, 2))
        self.fly_height = random.randint(0, 500) if self.drone.is_flying else 0
        self.speed = random.uniform(0, 10) if self.drone.is_flying else 0

        self.battery_bar.setValue(self.battery_level)
        self.info_labels["Height"].setText(f"{self.fly_height} cm")
        self.info_labels["Speed"].setText(f"{self.speed:.2f} cm/s")

    # ---------------------------------------------------------------------
    # Take Off & Land
    # ---------------------------------------------------------------------

    def take_off(self):
        """
        Initiates a delayed takeoff sequence if the drone isn't flying.
        Disables the close_button until takeoff is complete.
        """
        if not self.drone.is_flying:
            self.drone_state_label.setText("Taking Off...")
            self.drone_state_label.adjustSize()
            self.close_button.setEnabled(False)
            self.close_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: lightgray; color: gray;")

            # Delay the actual takeoff steps by 5 seconds
            QTimer.singleShot(5000, self._perform_take_off)

    def _perform_take_off(self):
        """Called after the 5-second delay, finalizing the takeoff state."""
        self.drone_state_label.setText("On Air.")
        self.drone_state_label.adjustSize()
        self.drone.is_flying = True

        self.flight_timer.start(1000)
        self.flight_start_time = datetime.datetime.now()

        # Create a folder for this flight
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.current_flight_folder = os.path.join(self.flights_folder, f"flight_{timestamp}")
        os.makedirs(self.current_flight_folder, exist_ok=True)

        self.stream_label.setText("Stream On")
        # self.drone.streamon()  # Mock stream
        print("Take off successful")

    def land(self):
        """
        Initiates a delayed landing sequence if the drone is flying.
        Re-enables the close_button after landing completes.
        """
        if self.drone.is_flying:
            self.drone_state_label.setText("Landing...")
            self.drone_state_label.adjustSize()
            self.close_button.setEnabled(True)
            self.close_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: #007BFF; color: white;")

            # Delay the actual landing steps by 5 seconds
            QTimer.singleShot(5000, self._perform_landing)

    def _perform_landing(self):
        """Called after the 5-second delay, finalizing the landing state."""
        self.drone_state_label.setText("Landed.")
        self.drone_state_label.adjustSize()
        self.drone.is_flying = False

        self.flight_timer.stop()
        self.stream_label.setText("Stream Off")
        # self.drone.streamoff()
        print("Landing successful")

        # Calculate final flight duration
        self.flight_end_time = datetime.datetime.now()
        duration = self.flight_end_time - self.flight_start_time

        QMessageBox.information(self, "Drone Status", f"Η πτήση ολοκληρώθηκε!\nΔιάρκεια: {duration}")

        # Process flight video
        self.process_flight_video(duration)

    def emergency_landing(self):
        """
        Immediately sets the drone state to an 'emergency landing'.
        Could be expanded for real failsafe logic.
        """
        logging.info("Emergency landing initiated!")
        self.update_drone_state("Emergency Landing")

    def update_drone_state(self, state: str):
        """
        Updates the label indicating the drone's current state.
        (e.g., Landing, Landed, Taking Off, Emergency, etc.)
        """
        self.drone_state_label.setText(state)
        self.drone_state_label.adjustSize()
        self.drone_state_label.move(self.width() // 2 - self.drone_state_label.width() // 2, self.height() - 100)

    # ---------------------------------------------------------------------
    # Video Processing
    # ---------------------------------------------------------------------

    def process_flight_video(self, duration):
        """
        Searches for a flight video in self.current_flight_folder and processes it
        using 'video_process.run', saving results into 'runs' folder of the field.
        """
        if not self.current_flight_folder:
            QMessageBox.warning(self, "Error", "Flight folder not set. Cannot process video.")
            return

        runs_folder = os.path.join(self.field_path, "runs")
        os.makedirs(runs_folder, exist_ok=True)

        # Create a new run folder for the processed results
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        run_folder = os.path.join(runs_folder, f"run_{timestamp}")
        os.makedirs(run_folder, exist_ok=True)

        # Check for a flight video
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
                QMessageBox.information(
                    self,
                    "Video Processing",
                    f"Η επεξεργασία του βίντεο ολοκληρώθηκε επιτυχώς!\nΑποτελέσματα στον φάκελο:\n{run_folder}"
                )
            except Exception as e:
                QMessageBox.critical(self, "Processing Error", f"Σφάλμα κατά την επεξεργασία του βίντεο: {e}")
        else:
            QMessageBox.warning(self, "Video Missing", "Δεν βρέθηκε βίντεο πτήσης για επεξεργασία!")

    # ---------------------------------------------------------------------
    # Controller & Joystick Inputs
    # ---------------------------------------------------------------------

    def setup_controller(self):
        """
        Detects if a joystick controller (e.g. Xbox) is present.
        Updates the controller_status_label accordingly.
        """
        try:
            if pygame.joystick.get_count() > 0:
                self.controller = pygame.joystick.Joystick(0)
                self.controller.init()
                self.controller_status_label.setText("Controller Connected")
                self.controller_status_label.setStyleSheet("color: green; font-size: 14px; font-weight: bold;")
                logging.info("Xbox Controller connected.")
            else:
                logging.warning("No controller detected.")
                self.controller_status_label.setText("No Controller Connected")
                self.controller_status_label.setStyleSheet("color: red; font-size: 14px; font-weight: bold;")
        except Exception as e:
            logging.error(f"Error setting up controller: {e}")

    def update_joystick_inputs(self):
        """
        Polls joystick input to update overlays and move the drone.
        Called every 20ms by a QTimer.
        """
        if self.controller:
            try:
                pygame.event.pump()
                left_x = self.controller.get_axis(0)
                left_y = self.controller.get_axis(1)
                right_x = self.controller.get_axis(2)
                right_y = self.controller.get_axis(3)

                # Apply small deadzone
                left_x = self.smooth_input(left_x)
                left_y = self.smooth_input(left_y)
                right_x = self.smooth_input(right_x)
                right_y = self.smooth_input(right_y)

                # Update Joystick Overlays
                self.joystick_left.update_position(left_x, -left_y)   # Invert Y
                self.joystick_right.update_position(right_x, -right_y)

                # Map axes to drone moves
                self.map_joystick_to_drone(left_x, left_y, right_x, right_y)

                # Button checks (e.g., button 0 -> takeoff, 1 -> land)
                for button_id, action in [(0, self.take_off), (1, self.land)]:
                    button_pressed = self.controller.get_button(button_id)
                    previously_pressed = self.button_states.get(button_id, False)

                    # If pressed now but wasn't pressed before => initial press
                    if button_pressed and not previously_pressed:
                        action()
                        self.button_states[button_id] = True
                    elif not button_pressed:
                        self.button_states[button_id] = False
            except Exception as e:
                logging.error(f"Error updating joystick inputs: {e}")

    def map_joystick_to_drone(self, left_x, left_y, right_x, right_y):
        """
        Maps joystick axis values to corresponding drone actions.
        - left_x, left_y: Movement in horizontal/vertical plane
        - right_x, right_y: Rotation, up/down
        """
        try:
            # Vertical motion on left Y
            if left_y < -0.5:
                self.drone.move_forward()
            elif left_y > 0.5:
                self.drone.move_backward()

            # Horizontal motion on left X
            if left_x < -0.5:
                self.drone.move_left()
            elif left_x > 0.5:
                self.drone.move_right()

            # Vertical motion on right Y
            if right_y < -0.5:
                self.drone.move_up()
            elif right_y > 0.5:
                self.drone.move_down()

            # Rotation on right X
            if right_x < -0.5:
                self.drone.rotate_left()
            elif right_x > 0.5:
                self.drone.rotate_right()
        except Exception as e:
            logging.error(f"Error mapping joystick inputs to drone: {e}")

    def smooth_input(self, value, threshold=0.1):
        """
        Applies a deadzone threshold and rounds joystick input for smoother movement.
        Returns 0 if |value| < threshold.
        """
        if abs(value) < threshold:
            return 0.0
        return round(value, 2)

    # ---------------------------------------------------------------------
    # Switching to Windowed Mode
    # ---------------------------------------------------------------------

    def launch_windowed(self):
        """
        Closes this fullscreen UI and reopens the DroneControlApp in a windowed mode.
        """
        self.flight_timer.stop()
        self.ui_timer.stop()
        self.timer.stop()

        # Quit PyGame to free resources
        pygame.joystick.quit()
        pygame.quit()

        # Open the windowed control
        self.fullscreen_window = open_drone_control(self.field_path)
        self.fullscreen_window.show()
        self.close()

# ---------------------------------------------------------------------
# Joystick Overlay Classes
# ---------------------------------------------------------------------

class DirectionalJoystick(QWidget):
    """
    A widget displaying a directional pad style joystick with up/down/left/right arrows.
    x_pos, y_pos in range [-1, 1].
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

        # Background circle
        painter.setBrush(QColor(50, 50, 50, 150))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, 200, 200)

        # Draw directional arrows (up, down, left, right)
        arrow_color = QColor(255, 255, 255, 200)
        painter.setBrush(arrow_color)

        # Up arrow
        up_arrow = QPolygon([QPoint(100, 10), QPoint(90, 40), QPoint(110, 40)])
        painter.drawPolygon(up_arrow)

        # Down arrow
        down_arrow = QPolygon([QPoint(100, 190), QPoint(90, 160), QPoint(110, 160)])
        painter.drawPolygon(down_arrow)

        # Left arrow
        left_arrow = QPolygon([QPoint(10, 100), QPoint(40, 90), QPoint(40, 110)])
        painter.drawPolygon(left_arrow)

        # Right arrow
        right_arrow = QPolygon([QPoint(190, 100), QPoint(160, 90), QPoint(160, 110)])
        painter.drawPolygon(right_arrow)

        # Draw joystick 'knob'
        knob_x = int(100 + self.x_pos * 75)
        knob_y = int(100 - self.y_pos * 75)
        painter.setBrush(QColor(200, 0, 0, 200))
        painter.drawEllipse(knob_x - 10, knob_y - 10, 20, 20)

    def update_position(self, x: float, y: float):
        """Sets joystick knob position in [-1, 1] for x,y."""
        self.x_pos = x
        self.y_pos = y
        self.update()


class CircularJoystick(QWidget):
    """
    A widget displaying a circular joystick with concentric rings.
    x_pos, y_pos in range [-1, 1].
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

        # Draw joystick knob
        knob_x = int(100 + self.x_pos * 75)
        knob_y = int(100 - self.y_pos * 75)
        painter.setBrush(QColor(200, 0, 0, 200))
        painter.drawEllipse(knob_x - 10, knob_y - 10, 20, 20)

    def update_position(self, x: float, y: float):
        """Sets joystick knob position in [-1, 1] for x,y."""
        self.x_pos = x
        self.y_pos = y
        self.update()


# ---------------------------------------------------------------------
# Example main guard
# ---------------------------------------------------------------------
# if __name__ == "__main__":
#     try:
#         logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
#         app = QApplication(sys.argv)
#         window = DroneOperatingPage('fields')
#         window.show()
#         sys.exit(app.exec())
#     except Exception as e:
#         logging.critical(f"Unhandled exception in main: {e}")
