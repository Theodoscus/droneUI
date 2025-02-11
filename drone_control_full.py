import sys
import os
import datetime
import logging
import subprocess
import platform

# Pygame is used for joystick/keyboard inputs and OpenCV for image/video processing.
import pygame
import cv2
from djitellopy import Tello  # Library to control Tello drones

# PyQt6 modules for creating the graphical user interface.
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QGroupBox, QVBoxLayout, QProgressBar,
    QHBoxLayout, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QPoint
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor, QPolygon

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
# RealDroneController: Encapsulates real drone logic separate from UI code.
# =============================================================================
class RealDroneController:
    """
    This class wraps the djitellopy.Tello drone functionality to provide
    a set of methods for connecting, commanding, streaming video, and recording.
    It manages flight state and video recording using OpenCV.
    """
    def __init__(self, flights_folder):
        # Store the folder where flight data will be saved.
        self.flights_folder = flights_folder
        # Create a Tello drone instance.
        self.tello = Tello()
        self.is_flying = False
        self.frame_read = None  # Will hold the video stream frame reader.
        self.is_recording = False
        self.video_writer = None
        self.flight_start_time = None
        self.current_flight_folder = None
        # Set default dimensions for video frames.
        self.frame_width = 960
        self.frame_height = 720

    def connect(self):
        """Connect to the real drone and start the video stream."""
        self.tello.connect()
        self.tello.streamon()
        self.frame_read = self.tello.get_frame_read()
        battery = self.tello.get_battery()
        print(f"Real Drone connected. Battery: {battery}%")

    def streamon(self):
        """Start the video stream from the drone."""
        self.tello.streamon()
        print("Real drone stream started")

    def streamoff(self):
        """Stop the video stream from the drone."""
        self.tello.streamoff()
        print("Real drone stream stopped")

    def end(self):
        """Disconnect from the drone and clean up resources."""
        self.tello.end()
        print("Real drone disconnected")

    # --- Basic Drone Movement Commands ---
    def takeoff(self):
        """Command the drone to take off if it isn't already flying."""
        if self.is_flying:
            print("Drone is already in flight.")
        else:
            self.tello.takeoff()
            self.is_flying = True
            print("Taking off...")

    def land(self):
        """Command the drone to land if it is currently flying."""
        if not self.is_flying:
            print("Drone is already landed.")
        else:
            self.tello.land()
            self.is_flying = False
            print("Landing...")

    def move_forward(self, distance=30):
        """Move the drone forward by a specified distance (in centimeters)."""
        if not self.is_flying:
            print("Cannot move. Drone not in flight.")
            return
        self.tello.move_forward(distance)
        print("Moving forward...")

    def move_backward(self, distance=30):
        """Move the drone backward by a specified distance (in centimeters)."""
        if not self.is_flying:
            print("Cannot move. Drone not in flight.")
            return
        self.tello.move_back(distance)
        print("Moving backward...")

    def move_left(self, distance=30):
        """Move the drone left by a specified distance (in centimeters)."""
        if not self.is_flying:
            print("Cannot move. Drone not in flight.")
            return
        self.tello.move_left(distance)
        print("Moving left...")

    def move_right(self, distance=30):
        """Move the drone right by a specified distance (in centimeters)."""
        if not self.is_flying:
            print("Cannot move. Drone not in flight.")
            return
        self.tello.move_right(distance)
        print("Moving right...")

    def move_up(self, distance=30):
        """Move the drone upward by a specified distance (in centimeters)."""
        if not self.is_flying:
            print("Cannot move. Drone not in flight.")
            return
        self.tello.move_up(distance)
        print("Moving up...")

    def move_down(self, distance=30):
        """Move the drone downward by a specified distance (in centimeters)."""
        if not self.is_flying:
            print("Cannot move. Drone not in flight.")
            return
        self.tello.move_down(distance)
        print("Moving down...")

    def rotate_left(self, angle=30):
        """Rotate the drone counter-clockwise by a given angle (in degrees)."""
        if not self.is_flying:
            print("Cannot rotate. Drone not in flight.")
            return
        self.tello.rotate_counter_clockwise(angle)
        print("Rotating left...")

    def rotate_right(self, angle=30):
        """Rotate the drone clockwise by a given angle (in degrees)."""
        if not self.is_flying:
            print("Cannot rotate. Drone not in flight.")
            return
        self.tello.rotate_clockwise(angle)
        print("Rotating right...")

    def flip_left(self):
        """Command the drone to perform a left flip."""
        if not self.is_flying:
            print("Cannot flip. Drone not in flight.")
            return
        self.tello.flip_left()
        print("Flipping left...")

    def flip_right(self):
        """Command the drone to perform a right flip."""
        if not self.is_flying:
            print("Cannot flip. Drone not in flight.")
            return
        self.tello.flip_right()
        print("Flipping right...")

    # --- Helper Methods for Drone State ---
    def get_battery(self):
        """Return the current battery level of the drone."""
        return self.tello.get_battery()

    def get_height(self):
        """Return the current height of the drone."""
        return self.tello.get_height()

    def get_speed_x(self):
        """Return the current horizontal speed of the drone."""
        return self.tello.get_speed_x()

    # --- Video Recording Methods ---
    def start_recording(self):
        """
        Begin recording the drone's video stream.
        Creates a new flight folder (if not already created) and initializes
        an OpenCV VideoWriter to save the stream.
        """
        if self.current_flight_folder is None:
            # Create a unique folder based on the current timestamp.
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self.current_flight_folder = os.path.join(self.flights_folder, f"flight_{timestamp}")
            os.makedirs(self.current_flight_folder, exist_ok=True)
        self.is_recording = True
        output_path = os.path.join(self.current_flight_folder, "flight_video.mp4")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self.video_writer = cv2.VideoWriter(output_path, fourcc, 20.0, (self.frame_width, self.frame_height))
        print(f"Recording started: {output_path}")

    def stop_recording(self):
        """Stop recording the video stream and release the VideoWriter."""
        if self.is_recording and self.video_writer is not None:
            self.is_recording = False
            self.video_writer.release()
            self.video_writer = None
            print("Recording stopped.")

    def record_frame(self, frame):
        """
        Write a single frame to the video file if recording is active.
        This method is typically called on each new video frame.
        """
        if self.is_recording and self.video_writer is not None:
            self.video_writer.write(frame)

# =============================================================================
# Fullscreen Drone Operating Page: The main UI for real drone control.
# =============================================================================
class DroneOperatingPage(QWidget):
    """
    This QWidget provides a full-screen user interface for controlling
    a real drone. It uses the RealDroneController for issuing commands,
    streaming video, and recording. The UI includes live video, control
    buttons, status displays, joystick overlays, and mode toggling.
    """
    def __init__(self, field_path):
        super().__init__()
        self.field_path = field_path
        # Create the folder for storing flights if it doesn't exist.
        self.flights_folder = os.path.join(self.field_path, "flights")
        os.makedirs(self.flights_folder, exist_ok=True)

        # Initialize the real drone controller and connect to the drone.
        self.drone_controller = RealDroneController(self.flights_folder)
        self.drone_controller.connect()
        self.drone_controller.streamon()
        # Keep a local reference to the frame reader for the video stream.
        self.frame_read = self.drone_controller.frame_read

        # Initialize state variables for flight duration and battery.
        self.flight_duration = 0
        self.battery_level = 100

        # Button state dictionary for joystick debouncing.
        self.button_states = {}

        # -----------------------------------------------------------------------------
        # Timers for updating flight duration, UI stats, joystick inputs, and video stream.
        # -----------------------------------------------------------------------------
        self.flight_timer = QTimer()
        self.flight_timer.timeout.connect(self.update_flight_duration)

        self.ui_timer = QTimer()
        self.ui_timer.timeout.connect(self.update_ui_stats)
        self.ui_timer.start(2000)  # Update UI stats every 2 seconds

        self.joystick_timer = QTimer()
        self.joystick_timer.timeout.connect(self.update_joystick_inputs)
        self.joystick_timer.timeout.connect(self.setup_controller)
        self.joystick_timer.start(20)  # Poll joystick inputs every 20ms

        self.stream_timer = QTimer()
        self.stream_timer.timeout.connect(self.update_video_stream)
        self.stream_timer.start(50)  # Update video stream every 50ms

        # Initialize pygame for joystick support.
        pygame.init()
        pygame.joystick.init()
        self.controller = None

        # Start in full screen mode.
        self.setWindowState(Qt.WindowState.WindowFullScreen)
        # Build the UI elements.
        self.init_ui()
        # Set up the controller (if connected).
        self.setup_controller()

    def init_ui(self):
        """Initialize and layout all UI components on the full-screen page."""
        try:
            self.setWindowTitle("Real Drone Controller - Full Screen")
            # The video stream label fills the background.
            self.stream_label = QLabel(self)
            self.stream_label.setGeometry(0, 0, self.width(), self.height())
            self.stream_label.setStyleSheet("background-color: black;")
            self.stream_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

            # Notification label for warnings (e.g., low battery or connection issues).
            self.notification_label = QLabel("", self)
            self.notification_label.setStyleSheet("color: red; font-size: 16px; font-weight: bold;")
            self.notification_label.setGeometry(10, 450, 400, 50)
            self.notification_label.setVisible(False)

            # Emergency landing button.
            self.emergency_button = QPushButton("EMERGENCY", self)
            self.emergency_button.setGeometry(self.width() // 2 - 100, 10, 200, 50)
            self.emergency_button.setStyleSheet("background-color: red; color: white; font-size: 18px; font-weight: bold;")
            self.emergency_button.clicked.connect(self.emergency_landing)

            # Button to toggle full screen mode.
            self.toggle_fullscreen_button = QPushButton("Exit Full Screen", self)
            self.toggle_fullscreen_button.setStyleSheet("background-color: blue; color: white; font-size: 16px; font-weight: bold;")
            self.toggle_fullscreen_button.clicked.connect(self.toggle_fullscreen)
            self.toggle_fullscreen_button.adjustSize()
            self.toggle_fullscreen_button.setGeometry(10, 10, 200, 50)

            # Button to switch to windowed mode.
            self.close_button = QPushButton("Windowed Mode", self)
            self.close_button.setStyleSheet("background-color: blue; color: white; font-size: 16px; font-weight: bold;")
            self.close_button.clicked.connect(self.launch_windowed)
            self.close_button.adjustSize()
            self.close_button.setGeometry(self.width() - 210, 10, 200, 50)

            # Status label showing signal strength and connection stability.
            self.status_label = QLabel("Signal: Strong | Connection: Stable", self)
            self.status_label.setStyleSheet("background-color: rgba(0, 0, 0, 0.5); color: white; font-size: 18px; padding: 10px;")
            self.status_label.setGeometry(10, 70, 400, 50)

            # Controller status label.
            self.controller_status_label = QLabel("No Controller Connected", self)
            self.controller_status_label.setStyleSheet("color: red; font-size: 14px; font-weight: bold;")
            self.controller_status_label.setGeometry(10, 130, 400, 50)

            # Battery progress bar.
            self.battery_bar = QProgressBar(self)
            self.battery_bar.setGeometry(10, 190, 400, 50)
            self.battery_bar.setValue(self.battery_level)
            self.battery_bar.setStyleSheet("QProgressBar::chunk { background-color: green; }")

            # Drone info box to display stats (temperature, height, speed, flight duration).
            self.info_box = QGroupBox("Drone Info", self)
            self.info_box.setGeometry(10, 250, 400, 250)
            info_layout = QVBoxLayout()
            self.info_labels = {
                "Temperature": QLabel("20°C", self),
                "Height": QLabel("0 cm", self),
                "Speed": QLabel("0 cm/s", self),
                "Flight Duration": QLabel("0 sec", self),
            }
            # Create rows for each info item.
            for key, lbl in self.info_labels.items():
                row = QHBoxLayout()
                row.addWidget(QLabel(f"{key}:", self))
                row.addWidget(lbl)
                info_layout.addLayout(row)
            self.info_box.setLayout(info_layout)

            # Joystick overlay widgets for visual feedback.
            self.joystick_left = DirectionalJoystick(self, "Left Joystick")
            self.joystick_left.setGeometry(50, self.height() - 250, 200, 200)

            self.joystick_right = CircularJoystick(self, "Right Joystick")
            self.joystick_right.setGeometry(self.width() - 250, self.height() - 250, 200, 200)

            # Drone state label to display current state (e.g., "Landed", "On Air").
            self.drone_state_label = QLabel("Landed", self)
            self.drone_state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.drone_state_label.setStyleSheet("background-color: rgba(200, 200, 200, 0.7); color: black; font-size: 18px; font-weight: bold; padding: 5px;")
            self.drone_state_label.move(self.width() // 2 - 50, self.height() - 100)
            self.drone_state_label.adjustSize()

        except Exception as e:
            logging.error(f"Error initializing DroneOperatingPage: {e}")

    def resizeEvent(self, event):
        """
        Overridden to handle window resizing.
        Repositions and resizes UI components to match the new window dimensions.
        """
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
        """
        Switch from full screen to windowed mode.
        Stops timers, quits joystick support, disconnects the drone,
        and opens the windowed UI.
        """
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
        """Increment the flight duration counter and update the display."""
        self.flight_duration += 1
        self.info_labels["Flight Duration"].setText(f"{self.flight_duration} sec")

    def update_ui_stats(self):
        """
        Update UI statistics such as battery level, height, and speed.
        This method is called periodically.
        """
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
        """
        Fetch the latest frame from the drone's video stream,
        convert it for display, and update the stream label.
        If recording is active, record the frame.
        """
        frame = self.frame_read.frame
        if frame is None:
            return
        # Convert the raw RGB frame to a QImage.
        h, w, ch = frame.shape
        bytes_per_line = ch * w
        q_img = QImage(frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(q_img)
        # Scale the pixmap to fit the stream label while keeping the aspect ratio.
        scaled_pixmap = pixmap.scaled(self.stream_label.width(), self.stream_label.height(),
                                       Qt.AspectRatioMode.KeepAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation)
        self.stream_label.setPixmap(scaled_pixmap)
        # If recording is active, write the frame to the video file.
        if self.drone_controller.is_recording and self.drone_controller.video_writer is not None:
            self.drone_controller.record_frame(frame)

    # --- Video Recording and Flight Control (auto-record on takeoff/land) ---
    def start_recording(self):
        """Start video recording by delegating to the drone controller."""
        self.drone_controller.start_recording()

    def stop_recording(self):
        """Stop video recording by delegating to the drone controller."""
        self.drone_controller.stop_recording()

    def take_off(self):
        """
        Initiate drone takeoff.
        Updates the UI to reflect that takeoff is in progress and disables certain buttons.
        """
        if not self.drone_controller.is_flying:
            self.drone_state_label.setText("Taking Off...")
            self.drone_state_label.adjustSize()
            self.close_button.setEnabled(False)
            self.close_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: lightgray; color: gray;")
            # Use a single-shot timer to delay the actual takeoff command (simulate a takeoff delay).
            QTimer.singleShot(5000, self._perform_take_off)

    def _perform_take_off(self):
        """
        Perform the actual takeoff after a delay.
        Updates the drone state, starts flight duration tracking, and begins video recording.
        """
        self.drone_state_label.setText("On Air.")
        self.drone_state_label.adjustSize()
        self.drone_controller.takeoff()
        self.flight_timer.start(1000)
        self.drone_controller.flight_start_time = datetime.datetime.now()
        # Reset the flight folder and start recording.
        self.drone_controller.current_flight_folder = None
        self.stream_label.setText("Stream On")
        self.start_recording()
        print("Take off successful")

    def land(self):
        """
        Initiate drone landing.
        Updates the UI to show landing state and re-enables buttons.
        """
        if self.drone_controller.is_flying:
            self.drone_state_label.setText("Landing...")
            self.drone_state_label.adjustSize()
            self.close_button.setEnabled(True)
            self.close_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: #007BFF; color: white;")
            # Use a single-shot timer to delay the landing command.
            QTimer.singleShot(5000, self._perform_landing)

    def _perform_landing(self):
        """
        Perform the actual landing.
        Stops flight duration tracking, stops recording, and processes the flight video.
        """
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
        """
        Immediately initiate an emergency landing.
        Updates the UI and logs the emergency action.
        """
        logging.info("Emergency landing initiated!")
        self.update_drone_state("Emergency Landing")
        self.drone_controller.land()

    def update_drone_state(self, state: str):
        """
        Update the drone state label with the given state string.
        Centers the label horizontally.
        """
        self.drone_state_label.setText(state)
        self.drone_state_label.adjustSize()
        self.drone_state_label.move(self.width() // 2 - self.drone_state_label.width() // 2, self.height() - 100)

    def process_flight_video(self, duration):
        """
        Process the recorded flight video.
        Creates a unique folder for the processed run and calls an external function to process the video.
        """
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
        # Try to find the recorded video file among common formats.
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
        """
        Check for a connected joystick/controller using pygame.
        Update the controller status label accordingly.
        """
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
        """
        Poll the joystick for input and update the on-screen joystick overlays.
        Map joystick inputs to drone commands.
        """
        if self.controller:
            try:
                pygame.event.pump()
                # Get axis values for left and right joysticks.
                left_x = self.controller.get_axis(0)
                left_y = self.controller.get_axis(1)
                right_x = self.controller.get_axis(2)
                right_y = self.controller.get_axis(3)
                # Smooth the inputs to filter out small fluctuations.
                left_x = self.smooth_input(left_x)
                left_y = self.smooth_input(left_y)
                right_x = self.smooth_input(right_x)
                right_y = self.smooth_input(right_y)
                # Update the visual position of the joystick overlays.
                self.joystick_left.update_position(left_x, -left_y)
                self.joystick_right.update_position(right_x, -right_y)
                # Map the joystick inputs to drone movement commands.
                self.map_joystick_to_drone(left_x, left_y, right_x, right_y)
                # Handle joystick button presses (using button IDs 0 and 1).
                for button_id, action in [(0, self.take_off), (1, self.land)]:
                    button_pressed = self.controller.get_button(button_id)
                    previously_pressed = self.button_states.get(button_id, False)
                    # Trigger the action only when the button is pressed (debounce logic).
                    if button_pressed and not previously_pressed:
                        action()
                        self.button_states[button_id] = True
                    elif not button_pressed:
                        self.button_states[button_id] = False
            except Exception as e:
                logging.error(f"Error updating joystick inputs: {e}")

    def map_joystick_to_drone(self, left_x, left_y, right_x, right_y):
        """
        Map joystick axis values to drone movement commands.
        For example, pushing the left joystick forward moves the drone forward.
        """
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
        """
        Apply a dead zone threshold to joystick input.
        Values within the threshold are treated as zero.
        """
        if abs(value) < threshold:
            return 0.0
        return round(value, 2)

    def launch_windowed(self):
        """
        Switch to the windowed drone control UI.
        Stops timers, quits joystick support, disconnects the drone,
        and opens the windowed UI.
        """
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
# Joystick Overlay Classes: Provide on-screen visualizations of joystick inputs.
# =============================================================================
class DirectionalJoystick(QWidget):
    """
    A simple directional joystick overlay that shows a fixed background
    with arrows and a movable knob representing the joystick's current position.
    """
    def __init__(self, parent, label):
        super().__init__(parent)
        self.setFixedSize(200, 200)
        self.label = label
        self.x_pos = 0.0
        self.y_pos = 0.0

    def paintEvent(self, event):
        """
        Custom paint event to draw the joystick overlay.
        Draws a circle background, arrows for direction, and the knob.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Draw the background circle with semi-transparency.
        painter.setBrush(QColor(50, 50, 50, 150))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, 200, 200)
        # Draw directional arrows in white.
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
        # Draw the movable knob based on the current joystick input.
        knob_x = int(100 + self.x_pos * 75)
        knob_y = int(100 - self.y_pos * 75)
        painter.setBrush(QColor(200, 0, 0, 200))
        painter.drawEllipse(knob_x - 10, knob_y - 10, 20, 20)

    def update_position(self, x: float, y: float):
        """Update the knob position and trigger a repaint."""
        self.x_pos = x
        self.y_pos = y
        self.update()

class CircularJoystick(QWidget):
    """
    A circular joystick overlay with concentric circles to indicate magnitude,
    and a movable knob representing the joystick's current position.
    """
    def __init__(self, parent, label):
        super().__init__(parent)
        self.setFixedSize(200, 200)
        self.label = label
        self.x_pos = 0.0
        self.y_pos = 0.0

    def paintEvent(self, event):
        """
        Custom paint event to draw the circular joystick overlay.
        Draws concentric circles and a movable knob.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Draw concentric circles.
        for radius in range(30, 121, 30):
            painter.setPen(QColor(255, 255, 255, 100))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(100 - radius, 100 - radius, radius * 2, radius * 2)
        # Draw the movable knob.
        knob_x = int(100 + self.x_pos * 75)
        knob_y = int(100 - self.y_pos * 75)
        painter.setBrush(QColor(200, 0, 0, 200))
        painter.drawEllipse(knob_x - 10, knob_y - 10, 20, 20)

    def update_position(self, x: float, y: float):
        """Update the knob position and trigger a repaint."""
        self.x_pos = x
        self.y_pos = y
        self.update()

# =============================================================================
# Main entry point: Start the application.
# =============================================================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    # Set the field path (directory for storing flight data).
    field_path = "fields"  # Adjust as needed.
    # Create and show the full-screen drone operating page.
    window = DroneOperatingPage(field_path)
    window.show()
    sys.exit(app.exec())
