import sys
import os
import datetime
import logging
import subprocess
import platform
import queue
import threading
import time

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

# Import the drone classes from drone_functions.py.
# DroneController handles drone operations (including continuous control),
# DroneConnectWorker handles asynchronous connection, and ConnectingDialog shows a modal dialog.
from drone_functions import DroneController, DroneConnectWorker, ConnectingDialog

# External modules for video processing and shared UI functionality.
from video_process import run
from shared import open_real_drone_control  # Function to open the windowed drone control UI


# -----------------------------------------------------------------------------
# Global exception hook
# -----------------------------------------------------------------------------
def log_uncaught_exceptions(exctype, value, traceback):
    """
    This function is used as a global exception hook.
    It logs any uncaught exceptions with their type, value, and traceback.
    """
    logging.critical("Uncaught exception", exc_info=(exctype, value, traceback))

# Set the global exception hook so that any exceptions that are not caught will be logged.
sys.excepthook = log_uncaught_exceptions


# =============================================================================
# Utility function: ping_drone
# =============================================================================
def ping_drone(ip="192.168.10.1", count=1, timeout=1) -> bool:
    """
    Uses the system ping command to check connectivity with the drone.
    
    Parameters:
      ip: The IP address of the drone.
      count: The number of ping packets to send.
      timeout: The timeout (in seconds) for each ping.
    
    Returns:
      True if the ping command succeeds, False otherwise.
    """
    # Choose ping parameter based on the OS.
    param = "-n" if platform.system().lower() == "windows" else "-c"
    if platform.system().lower() == "windows":
        command = ["ping", param, str(count), "-w", str(timeout * 1000), ip]
    else:
        command = ["ping", param, str(count), "-W", str(timeout), ip]

    try:
        # Execute the ping command.
        subprocess.check_output(command, stderr=subprocess.STDOUT, universal_newlines=True)
        return True
    except subprocess.CalledProcessError:
        return False





# =============================================================================
# DroneOperatingPage Class (Full-Screen UI)
# =============================================================================
class DroneOperatingPage(QWidget):
    """
    This is the main full-screen UI for controlling a real drone.
    It uses an ExtendedDroneController to manage the drone's commands, video streaming,
    and flight data recording. The UI incorporates:
      - A video stream display.
      - Buttons for emergency landing, toggling fullscreen, and switching to windowed mode.
      - A status display (including battery, connection, and drone state).
      - Joystick overlays for manual control.
      
    Continuous movement is handled using a QTimer (firing every 100ms). The latest joystick
    axis values are stored in self.last_joystick, and these values are used to compute velocities
    (vx, vy, vz, yaw) which are sent to the drone via the send_continious_control method.
    
    Commands are executed asynchronously using a command queue and worker thread.
    """
    def __init__(self, field_path):
        super().__init__()
        self.field_path = field_path
        # Create a folder for storing flight data if it doesn't already exist.
        self.flights_folder = os.path.join(self.field_path, "flights")
        os.makedirs(self.flights_folder, exist_ok=True)
        # Create a Tello drone instance and wrap it with our DroneController for easier management.
        self.tello = Tello()
        self.drone_controller = DroneController(self.tello, self.flights_folder)

        

        # Initialize state variables for flight duration and battery level.
        self.flight_duration = 0
        self.battery_level = 0

        # Dictionary to store button states for debouncing joystick inputs.
        self.button_states = {}

        # ----------------------------
        # Timers for periodic tasks
        # ----------------------------
        # Timer to update flight duration every second.
        self.flight_timer = QTimer()
        self.flight_timer.timeout.connect(self.update_flight_duration)

        # Timer to update UI statistics (battery, height, temperature, speed) every 2 seconds.
        self.ui_timer = QTimer()
        self.ui_timer.timeout.connect(self.update_ui_stats)
        self.ui_timer.start(2000)

        # Initialize Pygame and its joystick support.
        pygame.init()
        pygame.joystick.init()

        # Timer to poll joystick inputs and update the controller state (every 20ms).
        self.joystick_timer = QTimer()
        self.joystick_timer.timeout.connect(self.update_joystick_inputs)
        self.joystick_timer.timeout.connect(self.setup_controller)
        self.joystick_timer.start(20)

        # Timer for updating the video stream display (will start once connected).
        self.stream_timer = QTimer()
        self.stream_timer.timeout.connect(self.update_video_stream)

        # Timer to periodically ping the drone and verify connectivity (every 2 seconds).
        self.connection_check_timer = QTimer()
        self.connection_check_timer.timeout.connect(self.check_drone_connection)
        self.connection_check_timer.start(2000)

        # Counter to keep track of consecutive ping failures.
        self.consecutive_ping_failures = 0

        # ----------------------------
        # Command Queue and Worker Thread
        # ----------------------------
        # Create a command queue to handle both discrete commands (e.g. takeoff, land)
        # and continuous movement commands.
        self.command_queue = queue.Queue(maxsize=1)
        self.command_worker = threading.Thread(target=self.process_commands, daemon=True)
        self.command_worker.start()

        # ----------------------------
        # Continuous Movement Setup
        # ----------------------------
        # Define a speed factor for scaling joystick input to drone velocity.
        self.speed = 30
        # Store the latest joystick axis values; these will be updated continuously.
        self.last_joystick = {'left_x': 0.0, 'left_y': 0.0, 'right_x': 0.0, 'right_y': 0.0}
        # Flag to avoid sending duplicate stop commands when joystick inputs are near zero.
        self.last_stop_sent = False
        # Timer to process continuous movement commands every 100ms.
        self.continuous_timer = QTimer()
        self.continuous_timer.timeout.connect(self.process_continuous_commands)
        self.continuous_timer.start(100)

        # Set the window to full-screen mode.
        self.setWindowState(Qt.WindowState.WindowFullScreen)
        # Initialize all UI elements.
        self.init_ui()
        # Set up the controller (if any joystick is connected).
        self.setup_controller()

        # Begin connecting to the drone asynchronously.
        self.connecting_dialog = None
        self.connect_drone_async()

    # -------------------------------------------------------------------------
    # Command Queue and Worker Thread Methods
    # -------------------------------------------------------------------------
    def process_commands(self):
        """
        Continuously retrieves and executes commands from the command queue.
        This runs in a separate thread so that UI responsiveness is maintained.
        """
        while True:
            try:
                command, args, kwargs = self.command_queue.get()
                command(*args, **kwargs)
            except Exception as e:
                logging.error("Error executing command: %s", e)
            finally:
                self.command_queue.task_done()

    def execute_command(self, command_func, *args, **kwargs):
        """
        Adds a command to the command queue for asynchronous execution.
        If the queue is full, the oldest command is discarded to make room.
        
        :param command_func: The function representing the drone command.
        """
        try:
            if self.command_queue.full():
                try:
                    self.command_queue.get(block=False)
                    self.command_queue.task_done()
                except queue.Empty:
                    pass
            self.command_queue.put((command_func, args, kwargs), block=False)
        except queue.Full:
            logging.error("Command queue is unexpectedly full.")

    # -------------------------------------------------------------------------
    # Continuous Movement Processing
    # -------------------------------------------------------------------------
    def process_continuous_commands(self):
        """
        Calculates the drone's movement velocities based on the latest joystick values.
        If the calculated velocities (vx, vy, vz, yaw) are nearly zero, a stop command
        is sent only once. Otherwise, the continuous control command is sent.
        """
        # Calculate the desired velocities from joystick input.
        # Adjust the signs as needed based on how your joystick axes map to drone movement.
        vx = self.last_joystick['left_x'] * self.speed    # For example, left_x controls forward/backward
        vy = -self.last_joystick['left_y'] * self.speed   # Invert so that pushing up means forward
        vz = -self.last_joystick['right_y'] * self.speed   # Up/down control (inverted so pushing up means ascend)
        yaw = self.last_joystick['right_x'] * self.speed   # Rotation

        # Check if all velocities are near zero (i.e. joystick in dead zone).
        if abs(vx) < 1 and abs(vy) < 1 and abs(vz) < 1 and abs(yaw) < 1:
            # If not already sent, send a stop command.
            if not self.last_stop_sent:
                self.execute_command(self.drone_controller.send_continuous_control, 0, 0, 0, 0)
                self.last_stop_sent = True
            return
        else:
            # Reset the flag if any movement is detected.
            self.last_stop_sent = False
        # Send the continuous movement command with computed velocities.
        # Velocities are cast to integers.
        self.execute_command(self.drone_controller.send_continuous_control, int(vx), int(vy), int(vz), int(yaw))

    # -------------------------------------------------------------------------
    # UI Initialization and Layout
    # -------------------------------------------------------------------------
    def init_ui(self):
        """
        Sets up the full-screen UI layout including the video stream display,
        status labels, control buttons, and joystick overlays.
        """
        try:
            self.setWindowTitle("Real Drone Controller - Full Screen")

            # Create a QLabel to display the drone video stream.
            self.stream_label = QLabel(self)
            self.stream_label.setGeometry(0, 0, self.width(), self.height())
            self.stream_label.setStyleSheet("background-color: black;")
            self.stream_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

            # Label for displaying notifications (e.g., errors, warnings).
            self.notification_label = QLabel("", self)
            self.notification_label.setStyleSheet("color: red; font-size: 16px; font-weight: bold;")
            self.notification_label.setGeometry(10, 450, 400, 50)
            self.notification_label.setVisible(False)

            # Emergency landing button.
            self.emergency_button = QPushButton("EMERGENCY", self)
            self.emergency_button.setGeometry(self.width() // 2 - 100, 10, 200, 50)
            self.emergency_button.setStyleSheet(
                "background-color: red; color: white; font-size: 18px; font-weight: bold; border: 2px solid white;"
            )
            self.emergency_button.clicked.connect(self.emergency_landing)

            # Button to toggle full-screen mode.
            self.toggle_fullscreen_button = QPushButton("Exit Full Screen", self)
            self.toggle_fullscreen_button.setStyleSheet(
                "background-color: #007BFF; color: white; font-size: 16px; font-weight: bold; border: 2px solid white;"
            )
            self.toggle_fullscreen_button.adjustSize()
            self.toggle_fullscreen_button.setGeometry(10, 10, 200, 50)
            self.toggle_fullscreen_button.clicked.connect(self.toggle_fullscreen)

            # Button to switch to windowed mode.
            self.close_button = QPushButton("Windowed Mode", self)
            self.close_button.setStyleSheet(
                "background-color: #007BFF; color: white; font-size: 16px; font-weight: bold; border: 2px solid white;"
            )
            self.close_button.adjustSize()
            self.close_button.setGeometry(self.width() - 210, 10, 200, 50)
            self.close_button.clicked.connect(self.launch_windowed)

            # Status label for displaying Wi-Fi signal strength and connection status.
            self.status_label = QLabel("Signal: ??? | Connection: ???", self)
            self.status_label.setStyleSheet(
                "background-color: rgba(0, 0, 0, 0.5); color: white; font-size: 18px; padding: 10px; border: 2px solid white;"
            )
            self.status_label.setGeometry(10, 70, 400, 50)

            # Label showing controller connection status.
            self.controller_status_label = QLabel("No Controller Connected", self)
            self.controller_status_label.setStyleSheet(
                "color: red; font-size: 14px; font-weight: bold; border: 2px solid white; padding: 2px;"
            )
            self.controller_status_label.setGeometry(10, 130, 400, 50)

            # Progress bar to display the drone's battery level.
            self.battery_bar = QProgressBar(self)
            self.battery_bar.setGeometry(10, 190, 400, 50)
            self.battery_bar.setValue(self.battery_level)
            self.battery_bar.setTextVisible(True)
            self.battery_bar.setFormat("  %p%")
            self.battery_bar.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.battery_bar.setStyleSheet(
                """
                QProgressBar {
                    border: 2px solid white;
                    text-align: left;
                    padding-left: 5px;
                }
                QProgressBar::chunk {
                    background-color: green;
                }
                """
            )

            # Info box containing labels for temperature, height, speed, and flight duration.
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
            # Create rows for each piece of drone information.
            for key, lbl in self.info_labels.items():
                row = QHBoxLayout()
                row.addWidget(QLabel(f"{key}:", self))
                row.addWidget(lbl)
                info_layout.addLayout(row)
            self.info_box.setLayout(info_layout)

            # Create joystick overlay widgets.
            self.joystick_left = DirectionalJoystick(self, "Left Joystick")
            self.joystick_left.setGeometry(50, self.height() - 250, 200, 200)

            self.joystick_right = CircularJoystick(self, "Right Joystick")
            self.joystick_right.setGeometry(self.width() - 250, self.height() - 250, 200, 200)

            # Label to display the current drone state (e.g., "Landed", "On Air").
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
        """
        Handles resizing of the window by adjusting the positions and sizes
        of UI elements so that they adapt to the new window dimensions.
        """
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
        """
        Initiates a connection to the drone in a background thread.
        Displays a modal ConnectingDialog while attempting to connect.
        """
        self.connecting_dialog = ConnectingDialog()
        self.connecting_dialog.show()

        self.connection_thread = QThread()
        self.connection_worker = DroneConnectWorker(self.drone_controller)
        self.connection_worker.moveToThread(self.connection_thread)

        # When the thread starts, attempt to connect.
        self.connection_thread.started.connect(self.connection_worker.run)
        # Connect success and error signals to respective handlers.
        self.connection_worker.connect_success.connect(self.handle_connect_success)
        self.connection_worker.connect_error.connect(self.handle_connect_error)

        # Quit and cleanup the thread when done.
        self.connection_worker.connect_success.connect(self.connection_thread.quit)
        self.connection_worker.connect_error.connect(self.connection_thread.quit)
        self.connection_thread.finished.connect(self.connection_thread.deleteLater)

        self.connection_thread.start()

    def handle_connect_success(self):
        """
        Called when the drone connection is successful.
        Starts the video stream timer and closes the connecting dialog.
        """
        print("[UI] Drone connected successfully!")
        self.stream_timer.start(33)
        self.connecting_dialog.close()

    def handle_connect_error(self, error_message):
        """
        Called if the connection fails.
        Displays an error message and switches to windowed mode.
        """
        print("Connection error:", error_message)
        QMessageBox.critical(self, "Connection Error", f"Could not connect:\n{error_message}")
        self.connecting_dialog.close()
        self.launch_windowed()

    def check_drone_connection(self):
        """
        Periodically checks the drone connection:
          - Retrieves Wi-Fi signal strength (if available).
          - Performs a ping test.
          If multiple ping failures occur, the drone is marked as disconnected.
        """
        if not self.drone_controller.is_connected:
            return

        wifi_signal = self.drone_controller.get_wifi_signal()
        if wifi_signal is not None:
            self.status_label.setText(f"Signal: {wifi_signal} | Connection: OK")
        else:
            self.status_label.setText(f"Signal: N/A | Connection: OK")

        if not ping_drone("192.168.10.1"):
            self.consecutive_ping_failures += 1
            print(f"Ping failed. Consecutive failures: {self.consecutive_ping_failures}")
            if self.consecutive_ping_failures >= 3:
                print("[UI] Drone lost connection after multiple ping failures.")
                self.drone_controller.is_connected = False
                QMessageBox.warning(self, "Drone Disconnected", "Lost connection to drone!")
                self.launch_windowed()
        else:
            self.consecutive_ping_failures = 0

    # -------------------------------------------------------------------------
    # Windowed Mode and Fullscreen Toggling
    # -------------------------------------------------------------------------
    def launch_windowed(self):
        """
        Switches from full-screen to windowed mode by:
          - Stopping all timers.
          - Quitting joystick support.
          - Disconnecting from the drone.
          - Opening the windowed UI.
        """
        self.flight_timer.stop()
        self.ui_timer.stop()
        self.joystick_timer.stop()
        self.continuous_timer.stop()
        self.stream_timer.stop()
        pygame.joystick.quit()
        pygame.quit()

        if self.drone_controller.is_connected:
            self.drone_controller.streamoff()
            self.drone_controller.disconnect()
        
        time.sleep(2)

        self.windowed_ui = open_real_drone_control(self.field_path)
        self.windowed_ui.show()
        self.close()

    def toggle_fullscreen(self):
        """
        Toggles between full-screen and windowed modes.
        Changes the button text accordingly.
        """
        if self.isFullScreen():
            self.showNormal()
            self.toggle_fullscreen_button.setText("Enter Full Screen")
        else:
            self.showFullScreen()
            self.toggle_fullscreen_button.setText("Exit Full Screen")

    # -------------------------------------------------------------------------
    # Flight Duration and UI Statistics Updates
    # -------------------------------------------------------------------------
    def update_flight_duration(self):
        """
        Increments the flight duration counter every second and updates the UI label.
        """
        self.flight_duration += 1
        self.info_labels["Flight Duration"].setText(f"{self.flight_duration} sec")

    def update_ui_stats(self):
        """
        Retrieves the latest drone statistics (battery, height, temperature, speed)
        and updates the corresponding UI elements.
        """
        try:
            battery = self.drone_controller.get_battery()
            height = self.drone_controller.get_height()
            temp = self.drone_controller.get_temperature()

            self.battery_bar.setValue(battery)
            self.info_labels["Height"].setText(f"{height} cm")
            self.info_labels["Temperature"].setText(f"{temp}°C")
            speed = self.drone_controller.get_speed_x()
            self.info_labels["Speed"].setText(f"{speed} cm/s")
        except Exception as e:
            print("[UI] Failed to get drone state:", e)

    # -------------------------------------------------------------------------
    # Video Stream Handling
    # -------------------------------------------------------------------------
    def update_video_stream(self):
        """
        Retrieves the latest video frame from the drone, converts it to a QImage,
        scales it to fit the stream label, and displays it.
        If recording is active, the frame is also saved.
        """
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
    # Flight Control Methods (Takeoff, Landing, Emergency Landing)
    # -------------------------------------------------------------------------
    def start_recording(self):
        """Starts recording the video stream."""
        self.drone_controller.start_recording()

    def stop_recording(self):
        """Stops recording the video stream."""
        self.drone_controller.stop_recording()

    def take_off(self):
        """
        Initiates drone takeoff:
          - Updates the UI to reflect the takeoff state.
          - Sends the takeoff command asynchronously via the command queue.
          - Starts the flight timer and video recording.
        """
        if not self.drone_controller.is_flying:
            self.drone_state_label.setText("Taking Off...")
            self.drone_state_label.adjustSize()
            self.close_button.setEnabled(False)
            self.close_button.setStyleSheet(
                "font-size: 16px; padding: 10px; background-color: lightgray; color: gray; border: 2px solid white;"
            )
            try:
                self.execute_command(self.drone_controller.takeoff)
                self.flight_timer.start(1000)
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
        Initiates landing with a 5-second delay.
        The landing command is executed via the command queue.
        """
        if self.drone_controller.is_flying:
            self.drone_state_label.setText("Landing...")
            self.drone_state_label.adjustSize()
            self.close_button.setEnabled(True)
            self.close_button.setStyleSheet(
                "font-size: 16px; padding: 10px; background-color: #007BFF; color: white; border: 2px solid white;"
            )
            QTimer.singleShot(5000, self._perform_landing)

    def _perform_landing(self):
        """
        Finalizes landing:
          - Executes the landing command via the command queue.
          - Stops timers and video recording.
          - Calculates and displays flight duration.
          - Initiates flight video processing.
        """
        try:
            self.execute_command(self.drone_controller.land)
            print("Landing successful")
        except Exception as e:
            QMessageBox.critical(self, "Land Error", str(e))

        self.flight_timer.stop()
        self.stream_label.setText("Stream Off")
        self.stop_recording()

        self.drone_controller.flight_end_time = datetime.datetime.now()
        duration = self.drone_controller.flight_end_time - self.drone_controller.flight_start_time
        QMessageBox.information(self, "Drone Status", f"Flight completed!\nDuration: {duration}")

        self.process_flight_video(duration)

        self.flight_duration = 0
        self.info_labels["Flight Duration"].setText("0 sec")
        self.drone_state_label.setText("Landed.")
        self.drone_state_label.adjustSize()

    def emergency_landing(self):
        """
        Immediately performs an emergency landing:
          - Sends the landing command via the command queue.
          - Stops timers and video recording.
          - Processes flight video after landing.
        """
        if not self.drone_controller.is_flying:
            logging.info("Drone is already landed; cannot perform emergency landing.")
            return

        logging.info("Emergency landing initiated!")
        self.update_drone_state("Emergency Landing")

        try:
            self.execute_command(self.drone_controller.land)
            print("Emergency landing successful")
        except Exception as e:
            logging.error("Emergency landing failed: %s", e)

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

        self.flight_duration = 0
        self.info_labels["Flight Duration"].setText("0 sec")
        self.drone_state_label.setText("Emergency Landed.")
        self.drone_state_label.adjustSize()

        self.close_button.setEnabled(True)
        self.close_button.setStyleSheet(
            "font-size: 16px; padding: 10px; background-color: #007BFF; color: white; border: 2px solid white;"
        )

    def update_drone_state(self, state: str):
        """
        Updates the drone state label on the UI.
        
        :param state: A string describing the current state (e.g., "On Air", "Landed").
        """
        self.drone_state_label.setText(state)
        self.drone_state_label.adjustSize()
        self.drone_state_label.move(
            self.width() // 2 - self.drone_state_label.width() // 2, self.height() - 100
        )

    def process_flight_video(self, duration):
        """
        Processes the flight video by:
          - Ensuring a flight folder exists.
          - Creating a new run folder based on the current timestamp.
          - Determining the video file format and processing the video.
        
        :param duration: The duration of the flight.
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
        """
        Checks if a joystick is connected.
        If so, initializes it and updates the controller status label.
        Otherwise, sets the status to indicate no controller.
        """
        try:
            if pygame.joystick.get_count() > 0:
                self.controller = pygame.joystick.Joystick(0)
                self.controller.init()
                self.controller_status_label.setText("Controller Connected")
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
        """
        Polls joystick inputs:
          - Retrieves axis values for both joysticks.
          - Updates the on-screen joystick overlays.
          - Stores the latest axis values for continuous control.
          - Processes discrete button presses (e.g., takeoff and land).
        """
        if not hasattr(self, "controller") or self.controller is None:
            return

        try:
            pygame.event.pump()
            # Retrieve joystick axis values.
            left_x = self.controller.get_axis(0)
            left_y = self.controller.get_axis(1)
            right_x = self.controller.get_axis(2)
            right_y = self.controller.get_axis(3)

            # Apply smoothing to reduce noise.
            left_x = self.smooth_input(left_x)
            left_y = self.smooth_input(left_y)
            right_x = self.smooth_input(right_x)
            right_y = self.smooth_input(right_y)

            # Update joystick overlay positions.
            self.joystick_left.update_position(left_x, -left_y)
            self.joystick_right.update_position(right_x, -right_y)

            # Save the latest joystick values for continuous control.
            self.last_joystick = {
                'left_x': left_x,
                'left_y': left_y,
                'right_x': right_x,
                'right_y': right_y
            }

            # Process discrete joystick buttons.
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

    def smooth_input(self, value, threshold=0.1):
        """
        Applies a deadzone to joystick inputs: values below the threshold are set to zero.
        
        :param value: The raw joystick input value.
        :param threshold: The deadzone threshold.
        :return: Smoothed joystick value.
        """
        if abs(value) < threshold:
            return 0.0
        return round(value, 2)

# -------------------------------------------------------------------------
# Joystick Overlay Classes
# -------------------------------------------------------------------------
class DirectionalJoystick(QWidget):
        """
        A simple joystick overlay that draws a circular background,
        directional arrows, and a movable knob indicating the joystick position.
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
            # Draw the circular background.
            painter.setBrush(QColor(50, 50, 50, 150))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(0, 0, 200, 200)

            # Draw directional arrows.
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

            # Draw the movable knob.
            knob_x = int(100 + self.x_pos * 75)
            knob_y = int(100 - self.y_pos * 75)
            painter.setBrush(QColor(200, 0, 0, 200))
            painter.drawEllipse(knob_x - 10, knob_y - 10, 20, 20)

        def update_position(self, x: float, y: float):
            """
            Updates the knob position and repaints the widget.
            """
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
            """
            Updates the knob position and repaints the widget.
            """
            self.x_pos = x
            self.y_pos = y
            self.update()


# =============================================================================
# Main entry point
# =============================================================================
# if __name__ == "__main__":
#     # Create the QApplication.
#     app = QApplication(sys.argv)
#     # Define the field path where flight data is stored.
#     field_path = "fields"  # Or wherever you store flight data
#     # Instantiate the full-screen Drone Operating Page.
#     window = DroneOperatingPage(field_path)
#     window.show()
#     # Start the event loop.
#     sys.exit(app.exec())
