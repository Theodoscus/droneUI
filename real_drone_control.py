import os 
import datetime
import threading
import platform
import subprocess
import queue
import time
import logging

# Pygame is used for joystick/controller support; OpenCV is used for image processing.
import pygame
import cv2
from djitellopy import Tello  # Library to control Tello drones

# PyQt6 modules for building the GUI
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QProgressBar, QMessageBox, QGroupBox, QSizePolicy, QDialog
)
from PyQt6.QtCore import Qt, QTimer, QThread, QObject, pyqtSignal
from PyQt6.QtGui import QKeyEvent, QImage, QPixmap

# Import additional modules for reporting, video processing, and shared functionality.
from report_gen import DroneReportApp  # Module to generate flight reports
from video_process import run         # Function to process the recorded flight video
from shared import open_homepage, open_full_screen  # Shared functions for navigation

# Import our separated drone-related functions (connection, control, etc.)
from drone_functions import DroneController, DroneConnectWorker, ConnectingDialog


# =============================================================================
# Main Drone Control Application (UI)
# =============================================================================
class DroneControlApp(QMainWindow):
    def __init__(self, field_path):
        """
        Initializes the DroneControlApp:
          - Sets up the main window properties and UI components.
          - Creates folders to store flight data.
          - Instantiates the drone and its controller.
          - Sets up timers for flight duration, UI updates, controller input, and connection checks.
          - Configures both keyboard and joystick controls.
          
        :param field_path: Base path for storing flight data and related files.
        """
        super().__init__()
        # Set window title and dimensions.
        self.setWindowTitle("Drone Control")
        self.setGeometry(100, 100, 1200, 800)

        # Save the field path and create a folder for flights if it doesn't exist.
        self.field_path = field_path
        self.flights_folder = os.path.join(self.field_path, "flights")
        os.makedirs(self.flights_folder, exist_ok=True)
        

        # Create a Tello drone instance and wrap it with our DroneController for easier management.
        self.tello = Tello()
        self.drone_controller = DroneController(self.tello, self.flights_folder)

        # Initialize flight tracking variables.
        
        self.flight_duration = 0          # How long the flight has been in progress.
        self.flight_start_time = None     # Timestamp for when the flight started.
        self.consecutive_ping_failures = 0  # Counter for monitoring connection stability.
        self.wifi_signal = "N/A"
        self.wifi_thread = threading.Thread(target=self.poll_wifi_signal, daemon=True)
        self.wifi_thread.start()

        # ---------------------------------------------------------------------
        # Timers Setup
        # ---------------------------------------------------------------------
        # Timer to update flight duration (once per second).
        self.flight_timer = QTimer()
        self.flight_timer.timeout.connect(self.update_flight_duration)

        # Timer to update UI stats (e.g., battery level, temperature) every 3 seconds.
        self.ui_timer = QTimer()
        self.ui_timer.timeout.connect(self.update_ui_stats)
        self.ui_timer.start(3000)

        # Initialize Pygame to support joystick/controller input.
        pygame.init()
        pygame.joystick.init()
        self.controller = None  # This will hold our joystick if one is connected.

        # Timer for polling joystick inputs (every 20 ms).
        self.controller_timer = QTimer()
        self.controller_timer.timeout.connect(self.poll_controller_input)
        self.controller_timer.start(20)

        # Timer to periodically check the drone connection (every 2 seconds).
        self.connection_check_timer = QTimer()
        self.connection_check_timer.timeout.connect(self.check_drone_connection)
        self.connection_check_timer.start(2000)

        # Timer to update the flight history button status (every 2 seconds).
        self.history_timer = QTimer()
        self.history_timer.timeout.connect(self.update_history_button)
        self.history_timer.start(2000)

        # Map keyboard keys to drone actions.
        # Continuous actions (such as movement) are separate from discrete commands.
        self.key_to_action = {
            Qt.Key.Key_W: "Forward",
            Qt.Key.Key_S: "Backward",
            Qt.Key.Key_A: "Left",
            Qt.Key.Key_D: "Right",
            Qt.Key.Key_Up: "Up",
            Qt.Key.Key_Down: "Down",
            Qt.Key.Key_Left: "Rotate Left",
            Qt.Key.Key_Right: "Rotate Right",
            # Discrete commands:
            Qt.Key.Key_Q: "Flip Left",
            Qt.Key.Key_E: "Flip Right",
            Qt.Key.Key_T: "Take Off",
            Qt.Key.Key_L: "Land"
        }

        # Enable keyboard control by default; also prepare a container for control buttons.
        self.keyboard_control_enabled = True
        self.control_buttons = {}

        # Timer to update the video stream display (frequency set later).
        self.stream_timer = QTimer()
        self.stream_timer.timeout.connect(self.update_video_stream)

        # Set up a dedicated command queue and worker thread for discrete commands
        # (commands like takeoff, landing, flips, etc.).
        self.command_queue = queue.Queue(maxsize=1)
        self.command_worker = threading.Thread(target=self.process_commands, daemon=True)
        self.command_worker.start()

        # ---------------------------------------------------------------------
        # Continuous Movement Setup:
        # Define continuous movement commands with preset speed values.
        # ---------------------------------------------------------------------
        self.speed = 30  # Speed value used for continuous control commands.
        self.movement_actions = {
            "Forward": lambda: self.drone_controller.send_continuous_control(0, self.speed, 0, 0),
            "Backward": lambda: self.drone_controller.send_continuous_control(0, -self.speed, 0, 0),
            "Left": lambda: self.drone_controller.send_continuous_control(-self.speed, 0, 0, 0),
            "Right": lambda: self.drone_controller.send_continuous_control(self.speed, 0, 0, 0),
            "Up": lambda: self.drone_controller.send_continuous_control(0, 0, self.speed, 0),
            "Down": lambda: self.drone_controller.send_continuous_control(0, 0, -self.speed, 0),
            "Rotate Left": lambda: self.drone_controller.send_continuous_control(0, 0, 0, -self.speed),
            "Rotate Right": lambda: self.drone_controller.send_continuous_control(0, 0, 0, self.speed),
        }
        # A set of keys representing continuous actions.
        self.continuous_actions = set(self.movement_actions.keys())
        self.last_stop_sent = False  # Flag to ensure a stop command is sent only once.
        self.active_movement = {}     # Dictionary to track which movement actions are active.
        # Timer to process continuous movement commands every 100 ms.
        self.continuous_timer = QTimer()
        self.continuous_timer.timeout.connect(self.process_continuous_commands)
        self.continuous_timer.start(100)

        # Flag to lock new commands (used after takeoff or landing).
        self.commands_locked = False
        
        # Initialize the UI, update controller status, and start connecting to the drone.
        self.init_ui()
        self.update_controller_status()
        self.connect_drone_async()

    # ---------------------------------------------------------------------
    # Command Queue and Executor Thread (for discrete commands)
    # ---------------------------------------------------------------------
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

    # ---------------------------------------------------------------------
    # Continuous Movement Processing
    # ---------------------------------------------------------------------
    def process_continuous_commands(self):
        """
        Combines the active movement commands and sends a single continuous control command.
        This allows, for example, moving forward and rotating simultaneously.
        """
        # Calculate combined velocities.
        lr = 0      # Left/Right
        fb = 0      # Forward/Backward
        ud = 0      # Up/Down
        yaw = 0     # Rotation

        if self.active_movement.get("Left", False):
            lr -= self.speed
        if self.active_movement.get("Right", False):
            lr += self.speed
        if self.active_movement.get("Forward", False):
            fb += self.speed
        if self.active_movement.get("Backward", False):
            fb -= self.speed
        if self.active_movement.get("Up", False):
            ud += self.speed
        if self.active_movement.get("Down", False):
            ud -= self.speed
        if self.active_movement.get("Rotate Left", False):
            yaw -= self.speed
        if self.active_movement.get("Rotate Right", False):
            yaw += self.speed

        # Always send the combined command, even if it is (0,0,0,0).
        # This keeps the drone in hover mode.
        self.execute_command(
            self.drone_controller.send_continuous_control,
            int(lr), int(fb), int(ud), int(yaw)
        )


    def set_active_movement(self, action, state: bool):
        """
        Updates the active/inactive state for a given movement command.
        
        :param action: The movement action name (e.g., "Forward").
        :param state: True if the movement is active, False if inactive.
        """
        self.active_movement[action] = state

    # ---------------------------------------------------------------------
    # UI Setup (Layout and Widgets)
    # ---------------------------------------------------------------------
    def init_ui(self):
        """
        Constructs the user interface including layouts, labels, buttons, and panels.
        """
        # Create the main widget and set it as the central widget.
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)

        # --------------------------
        # TOP AREA: Status and Video Stream
        # --------------------------
        top_area_widget = QWidget()
        top_area_layout = QVBoxLayout(top_area_widget)

        # Label to display the connection status (e.g., CONNECTED, DISCONNECTED).
        self.connection_status = QLabel("DISCONNECTED")
        self.connection_status.setStyleSheet(
            "background-color: red; color: white; font-size: 18px; font-weight: bold; border: 2px solid #555;"
        )
        self.connection_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.connection_status.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        top_area_layout.addWidget(self.connection_status)

        # Label for notifications such as battery warnings.
        self.notification_label = QLabel("")
        self.notification_label.setStyleSheet("color: red; font-size: 16px; font-weight: bold;")
        self.notification_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.notification_label.setVisible(False)
        top_area_layout.addWidget(self.notification_label)

        # Label to show connection-specific messages (e.g., drone disconnected from WiFi).
        self.connection_notification_label = QLabel("")
        self.connection_notification_label.setStyleSheet("color: orange; font-size: 16px; font-weight: bold;")
        self.connection_notification_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.connection_notification_label.setVisible(False)
        top_area_layout.addWidget(self.connection_notification_label)

        # Create a horizontal layout to house the left panel and the video stream.
        content_layout = QHBoxLayout()
        top_area_layout.addLayout(content_layout)

        # --------------------------
        # Left Panel: Drone Information
        # --------------------------
        left_panel = QVBoxLayout()
        # Battery GroupBox and progress bar.
        battery_box = QGroupBox("Battery")
        battery_layout = QVBoxLayout()
        self.battery_bar = QProgressBar()
        self.battery_bar.setValue(0)
        self.battery_bar.setStyleSheet("QProgressBar::chunk { background-color: green; }")
        self.battery_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        battery_layout.addWidget(self.battery_bar)
        battery_box.setLayout(battery_layout)
        battery_box.setFixedHeight(60)
        left_panel.addWidget(battery_box)

        # Controller Status GroupBox.
        controller_status_box = QGroupBox("Controller Status")
        controller_layout = QVBoxLayout()
        self.controller_status_label = QLabel("No Controller Connected")
        self.controller_status_label.setStyleSheet("color: red; font-size: 14px; font-weight: bold;")
        controller_layout.addWidget(self.controller_status_label)
        controller_status_box.setLayout(controller_layout)
        controller_status_box.setFixedHeight(60)
        left_panel.addWidget(controller_status_box)

        # Drone Information GroupBox: Temperature, Height, Speed, etc.
        info_box = QGroupBox("Drone Info")
        info_layout = QVBoxLayout()
        self.info_labels = {
            "Temperature": QLabel("0°C"),
            "Height": QLabel("0 cm"),
            "Speed": QLabel("0 cm/s"),
            "Signal Strength": QLabel("N/A"),
            "Flight Duration": QLabel("0 sec"),
        }
        # Add each information row to the layout.
        for key, lbl in self.info_labels.items():
            row = QHBoxLayout()
            row.addWidget(QLabel(f"{key}:"))
            row.addWidget(lbl)
            info_layout.addLayout(row)
        info_box.setLayout(info_layout)
        info_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        left_panel.addWidget(info_box, stretch=1)

        # Wrap the left panel in its own widget and set size constraints.
        left_panel_widget = QWidget()
        left_panel_widget.setLayout(left_panel)
        left_panel_widget.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        left_panel_widget.setMaximumWidth(300)
        content_layout.addWidget(left_panel_widget, stretch=1)

        # --------------------------
        # Right Panel: Video Stream Display
        # --------------------------
        self.stream_label = QLabel("Drone Stream")
        self.stream_label.setStyleSheet(
            "background-color: #000; color: white; font-size: 14px; border: 1px solid #555;"
        )
        self.stream_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stream_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.stream_label.setScaledContents(True)
        content_layout.addWidget(self.stream_label, stretch=3)

        # Add the top area to the main layout.
        main_layout.addWidget(top_area_widget, stretch=3)

        # --------------------------
        # BOTTOM AREA: Control Buttons & Navigation
        # --------------------------
        bottom_area_widget = QWidget()
        bottom_area_layout = QVBoxLayout(bottom_area_widget)

        # Layout for the control buttons.
        controls_layout = QVBoxLayout()
        # Define rows of control buttons with key labels, associated actions, and optional colors.
        control_buttons = [
            [("Q", "Flip Left"), ("W", "Forward"), ("E", "Flip Right")],
            [("A", "Left"), ("S", "Backward"), ("D", "Right")],
            [("T", "Take Off", "green"), ("L", "Land", "red")],
            [("Up Arrow", "Up"), ("Down Arrow", "Down"), ("Left Arrow", "Rotate Left"), ("Right Arrow", "Rotate Right")],
        ]
        # Create buttons for each row and add them to the layout.
        for row in control_buttons:
            row_layout = QHBoxLayout()
            for button_spec in row:
                if len(button_spec) == 3:
                    btn = self.create_control_button(button_spec[0], button_spec[1], button_spec[2])
                else:
                    btn = self.create_control_button(button_spec[0], button_spec[1])
                row_layout.addWidget(btn)
            controls_layout.addLayout(row_layout)

        # Add the controls layout to the bottom area.
        bottom_area_layout.addLayout(controls_layout)

        # Flight History Button.
        self.history_button = QPushButton("View Flight History")
        self.history_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: #007BFF; color: white;")
        self.history_button.clicked.connect(self.view_flight_history)
        self.history_button.setEnabled(True)
        bottom_area_layout.addWidget(self.history_button)

        # Home Button.
        self.home_button = QPushButton("Αρχική Σελίδα")
        self.home_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: #007BFF; color: white;")
        self.home_button.clicked.connect(self.go_to_homepage)
        bottom_area_layout.addWidget(self.home_button)

        # Full Screen Drone Operation Button.
        self.fullscreen_button = QPushButton("Full Screen Drone Operation")
        self.fullscreen_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: #007BFF; color: white;")
        self.fullscreen_button.setEnabled(True)
        self.fullscreen_button.clicked.connect(self.launch_fullscreen)
        bottom_area_layout.addWidget(self.fullscreen_button)

        # Connect/Disconnect Button.
        self.connect_toggle_button = QPushButton("Connect")
        self.connect_toggle_button.setStyleSheet(
            "font-size: 16px; padding: 10px; background-color: green; color: white;"
        )
        self.connect_toggle_button.clicked.connect(self.toggle_connection)
        bottom_area_layout.addWidget(self.connect_toggle_button)

        # Add the bottom area to the main layout.
        main_layout.addWidget(bottom_area_widget, stretch=1)

    # ---------------------------------------------------------------------
    # Toggle Connection (Connect/Disconnect Drone)
    # ---------------------------------------------------------------------
    def toggle_connection(self):
        """
        Toggles the connection state: if the drone is connected, disconnect it;
        otherwise, initiate a connection.
        """
        if self.drone_controller.is_connected:
            self.disconnect_drone()
        else:
            self.connect_drone_async()

    def disconnect_drone(self):
        """
        Disconnects the drone, stops video streaming, and updates the UI to reflect a disconnected state.
        """
        if self.drone_controller.is_connected:
            try:
                self.drone_controller.disconnect()
                print("Drone stream turned off.")
            except Exception as e:
                print("Error turning off drone stream:", e)
            # Stop the video stream timer.
            self.stream_timer.stop()
            # Update the connection status label.
            self.connection_status.setText("DISCONNECTED")
            self.connection_status.setStyleSheet(
                "background-color: red; color: white; font-size: 18px; font-weight: bold; border: 2px solid #555;"
            )
            # Reset the connect toggle button.
            self.connect_toggle_button.setText("Connect")
            self.connect_toggle_button.setStyleSheet(
                "font-size: 16px; padding: 10px; background-color: green; color: white;"
            )
            # Clear any active continuous movement flags.
            for act in self.continuous_actions:
                self.set_active_movement(act, False)
        else:
            print("Drone already disconnected.")

    # ---------------------------------------------------------------------
    # Asynchronous Drone Connection
    # ---------------------------------------------------------------------
    def connect_drone_async(self):
        """
        Initiates an asynchronous connection to the drone using a QThread.
        A connecting dialog is shown while the connection is being established.
        """
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
        """
        Called when the drone is connected successfully.
        Updates the UI to show connected status, starts video streaming, and closes the connecting dialog.
        """
        self.connection_status.setText("CONNECTED")
        self.connection_status.setStyleSheet(
            "background-color: green; color: white; font-size: 18px; font-weight: bold; border: 2px solid #555;"
        )
        self.connect_toggle_button.setText("Disconnect")
        self.connect_toggle_button.setStyleSheet(
            "font-size: 16px; padding: 10px; background-color: red; color: white;"
        )
        self.stream_timer.start(33)  # Start the video stream update timer.
        self.connecting_dialog.close()
        print("Drone connected successfully and stream is ON.")

    def handle_connect_error(self, error_message):
        """
        Called if the drone connection fails.
        Displays an error message and resets UI elements to reflect the disconnected state.
        
        :param error_message: The error message to display.
        """
        print("Error connecting to drone:", error_message)
        QMessageBox.critical(self, "Connection Error", f"Could not connect:\n{error_message}")
        self.connection_status.setText("DISCONNECTED")
        self.connection_status.setStyleSheet(
            "background-color: red; color: white; font-size: 18px; font-weight: bold; border: 2px solid #555;"
        )
        self.connect_toggle_button.setText("Connect")
        self.connect_toggle_button.setStyleSheet(
            "font-size: 16px; padding: 10px; background-color: green; color: white;"
        )
        self.connecting_dialog.close()

    # ---------------------------------------------------------------------
    # Check Drone Connection (Ping Test)
    # ---------------------------------------------------------------------
    def check_drone_connection(self):
        """
        Periodically pings the drone's IP to check connectivity.
        If multiple consecutive pings fail, updates the UI to show the drone as disconnected.
        """
        if not self.drone_controller.is_connected:
            return
        if not self.ping_drone("192.168.10.1"):
            self.consecutive_ping_failures += 1
            print(f"Ping failed ({self.consecutive_ping_failures} consecutive failure(s)).")
            if self.consecutive_ping_failures >= 3:
                print("Multiple ping failures: Drone not reachable. Marking as disconnected in UI.")
                self.drone_controller.is_connected = False
                self.connection_status.setText("DISCONNECTED")
                self.connection_status.setStyleSheet(
                    "background-color: red; color: white; font-size: 18px; font-weight: bold; border: 2px solid #555;"
                )
                self.connect_toggle_button.setText("Connect")
                self.connect_toggle_button.setStyleSheet(
                    "font-size: 16px; padding: 10px; background-color: green; color: white;"
                )
                self.connection_notification_label.setText("Drone disconnected from WiFi!")
                self.connection_notification_label.setVisible(True)
        else:
            if self.consecutive_ping_failures > 0:
                print("Ping succeeded. Resetting failure counter.")
            self.consecutive_ping_failures = 0
            if self.connection_notification_label.isVisible():
                self.connection_notification_label.setVisible(False)
                
    def poll_wifi_signal(self):
        """
        Continuously polls the drone for its Wi-Fi signal strength.
        This runs in a separate thread so that it doesn't block the UI.
        """
        while True:
            if self.drone_controller.is_connected:
                try:
                    signal = self.drone_controller.get_wifi_signal()
                    self.wifi_signal = signal
                except Exception as e:
                    logging.error("Error querying Wi-Fi signal: %s", e)
                    self.wifi_signal = "N/A"
            else:
                self.wifi_signal = "N/A"
            time.sleep(1)  # poll every second


    def ping_drone(self, ip="192.168.10.1", count=1, timeout=1):
        """
        Pings the drone to verify connectivity.
        
        :param ip: Drone's IP address.
        :param count: Number of ping packets to send.
        :param timeout: Timeout for each ping.
        :return: True if ping is successful, otherwise False.
        """
        param = '-n' if platform.system().lower() == 'windows' else '-c'
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
        """
        Launches a full-screen drone operation window.
        Stops all timers and disconnects the drone before transitioning.
        """
        self.stop_all_timers()
        pygame.joystick.quit()
        pygame.quit()
        self.disconnect_drone()
        time.sleep(2)
        
        
        self.fullscreen_window = open_full_screen(self.field_path)
        self.fullscreen_window.show()
        self.close()

    def center_window(self):
        """
        Centers the main window on the primary screen.
        """
        self.show()
        self.updateGeometry()
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        center_x = screen_geometry.x() + (screen_geometry.width() - self.width()) // 2
        center_y = screen_geometry.y() + (screen_geometry.height() - self.height()) // 2
        self.move(center_x, center_y)

    # ---------------------------------------------------------------------
    # Controller Management (Joystick/Keyboard)
    # ---------------------------------------------------------------------
    def update_controller_status(self):
        """
        Checks whether a joystick/controller is connected.
        Updates the controller status label and disables keyboard controls if a controller is present.
        """
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
        """
        Enables or disables the control buttons and keyboard input.
        
        :param enabled: True to enable controls; False to disable.
        """
        for button in self.control_buttons.values():
            button.setEnabled(enabled)
        self.keyboard_control_enabled = enabled

    def poll_controller_input(self):
        """
        Polls for joystick/controller events and processes them.
        """
        pygame.event.pump()  # Process internal events.
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
        """
        Maps joystick button presses to drone actions.
        
        :param button: The index of the button pressed.
        """
        if button == 0:  # A button
            self.take_off()
        elif button == 1:  # B button
            self.land()
        elif button == 2:  # X button
            self.flip_left()
        elif button == 3:  # Y button
            self.flip_right()

    def handle_axis_motion(self, axis, value):
        """
        Processes joystick axis movements to update continuous movement states.
        
        :param axis: The axis index.
        :param value: The value from the axis (typically between -1 and 1).
        """
        if axis == 1:
            if value < -0.5:
                self.set_active_movement("Forward", True)
                self.set_active_movement("Backward", False)
            elif value > 0.5:
                self.set_active_movement("Backward", True)
                self.set_active_movement("Forward", False)
            else:
                self.set_active_movement("Forward", False)
                self.set_active_movement("Backward", False)
        elif axis == 0:
            if value < -0.5:
                self.set_active_movement("Left", True)
                self.set_active_movement("Right", False)
            elif value > 0.5:
                self.set_active_movement("Right", True)
                self.set_active_movement("Left", False)
            else:
                self.set_active_movement("Left", False)
                self.set_active_movement("Right", False)
        elif axis == 2:
            if value < -0.5:
                self.set_active_movement("Rotate Left", True)
                self.set_active_movement("Rotate Right", False)
            elif value > 0.5:
                self.set_active_movement("Rotate Right", True)
                self.set_active_movement("Rotate Left", False)
            else:
                self.set_active_movement("Rotate Left", False)
                self.set_active_movement("Rotate Right", False)
        elif axis == 3:
            if value < -0.5:
                self.set_active_movement("Up", True)
                self.set_active_movement("Down", False)
            elif value > 0.5:
                self.set_active_movement("Down", True)
                self.set_active_movement("Up", False)
            else:
                self.set_active_movement("Up", False)
                self.set_active_movement("Down", False)

    # ---------------------------------------------------------------------
    # Control Buttons
    # ---------------------------------------------------------------------
    def create_control_button(self, key: str, action: str, color=None) -> QPushButton:
        """
        Creates a button for controlling the drone with a specified key, action, and optional color.
        
        :param key: The keyboard key representation (e.g., "W").
        :param action: The associated action (e.g., "Forward").
        :param color: Optional background color for the button.
        :return: The created QPushButton.
        """
        btn = QPushButton(f"{key}\n({action})")
        if color:
            btn.setStyleSheet(f"background-color: {color}; color: white; font-weight: bold;")
        # If this is a continuous action, bind press and release events.
        if action in self.continuous_actions:
            btn.pressed.connect(lambda act=action: self.set_active_movement(act, True))
            btn.released.connect(lambda act=action: self.set_active_movement(act, False))
        else:
            # For discrete actions, connect the button click to the appropriate handler.
            btn.clicked.connect(self.create_button_handler(action))
        self.control_buttons[action] = btn
        return btn

    def create_button_handler(self, action: str):
        """
        Returns a function that handles button clicks for discrete actions.
        
        :param action: The action name (e.g., "Take Off").
        :return: A function that calls the associated command.
        """
        def handler():
            discrete_actions = {
                "Flip Left": self.flip_left,
                "Flip Right": self.flip_right,
                "Take Off": self.take_off,
                "Land": self.land,
            }
            if action in discrete_actions:
                discrete_actions[action]()
            else:
                # For actions that are not explicitly discrete, simulate a quick activation.
                self.set_active_movement(action, True)
                QTimer.singleShot(200, lambda: self.set_active_movement(action, False))
        return handler

    def keyPressEvent(self, event: QKeyEvent):
        """
        Processes key press events for keyboard control.
        
        :param event: The QKeyEvent instance.
        """
        if self.commands_locked:
            return
        if not self.keyboard_control_enabled:
            return
        if event.isAutoRepeat():
            return
        key = event.key()
        if key in self.key_to_action:
            action = self.key_to_action[key]
            if action in self.continuous_actions:
                self.set_active_movement(action, True)
            else:
                if action == "Flip Left":
                    self.flip_left()
                elif action == "Flip Right":
                    self.flip_right()
                elif action == "Take Off":
                    self.take_off()
                elif action == "Land":
                    self.land()

    def keyReleaseEvent(self, event: QKeyEvent):
        """
        Processes key release events to stop continuous actions.
        
        :param event: The QKeyEvent instance.
        """
        if not self.keyboard_control_enabled:
            return
        if event.isAutoRepeat():
            return
        key = event.key()
        if key in self.key_to_action:
            action = self.key_to_action[key]
            if action in self.continuous_actions:
                self.set_active_movement(action, False)

    # ---------------------------------------------------------------------
    # Flight Duration & Stats Updates
    # ---------------------------------------------------------------------
    def update_flight_duration(self):
        """
        Increments the flight duration counter and updates the associated UI label.
        """
        self.flight_duration += 1
        self.info_labels["Flight Duration"].setText(f"{self.flight_duration} sec")

    def update_ui_stats(self):
        """
        Retrieves the latest statistics from the drone and updates the UI accordingly.
        """
        if not self.drone_controller.is_connected:
            return
        try:
            battery_level = self.drone_controller.get_battery()
            temperature = self.drone_controller.get_temperature()
            height = self.drone_controller.get_height()
            speed = self.drone_controller.get_speed_x()
            self.update_history_button()
            self.battery_bar.setValue(battery_level)
            if battery_level < 20:
                self.notification_label.setText("Warning: Battery level is critically low!")
                self.notification_label.setVisible(True)
            else:
                self.notification_label.setVisible(False)
            self.info_labels["Temperature"].setText(f"{temperature}°C")
            self.info_labels["Height"].setText(f"{height} cm")
            self.info_labels["Speed"].setText(f"{speed} cm/s")
            # Update the signal strength (polled in a separate thread)
            self.info_labels["Signal Strength"].setText(f"{self.wifi_signal}")
        except Exception as e:
            print("Failed to get Tello state:", e)


    # ---------------------------------------------------------------------
    # Flight Operations (Take Off, Land, etc.)
    # ---------------------------------------------------------------------
    def take_off(self):
        """
        Handles the drone's takeoff sequence:
          - Checks if the drone is connected.
          - Clears active movement flags.
          - Disables navigation buttons.
          - Sends the takeoff command.
          - Locks further commands for 5 seconds to allow the drone to initialize.
          - Starts flight duration tracking.
        """
        if not self.drone_controller.is_connected:
            QMessageBox.warning(self, "Drone Disconnected", "Cannot take off because the drone is not connected.")
            return
        if self.commands_locked:
            return  # Ignore input if commands are locked

        # Clear any active continuous movement commands.
        for act in self.continuous_actions:
            self.set_active_movement(act, False)
        # Disable navigation and history buttons during takeoff.
        self.history_button.setEnabled(False)
        self.home_button.setEnabled(False)
        self.fullscreen_button.setEnabled(False)
        self.home_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: lightgray; color: gray;")
        self.fullscreen_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: lightgray; color: gray;")
        self.history_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: lightgray; color: gray;")
        
        # Send the takeoff command to the drone.
        self.execute_command(self.drone_controller.takeoff)
        self.commands_locked = True  # Lock commands to prevent additional input during initialization
        print("Drone takeoff command sent.")
        self.flight_timer.start(1000)  # Start the flight duration timer
        self.flight_duration = 0  # Reset the flight duration counter
        self.flight_start_time = datetime.datetime.now()  # Record the start time of the flight
        # Re-enable commands after a 5-second delay.
        QTimer.singleShot(5000, self.unlock_commands)

    def land(self):
        """
        Handles the drone's landing sequence:
          - Checks if the drone is connected.
          - Sends the landing command.
          - Locks commands for 5 seconds to allow the drone to finalize landing.
          - Stops the flight duration timer.
          - Calculates flight duration and displays it.
          - Initiates flight video processing.
          - Re-enables navigation buttons.
        """
        if not self.drone_controller.is_connected:
            QMessageBox.warning(self, "Drone Disconnected", "Cannot land because the drone is not connected.")
            return
        if self.commands_locked:
            return  # Prevent further input if commands are locked

        self.execute_command(self.drone_controller.land)
        self.commands_locked = True  # Lock commands during landing finalization
        print("Drone landing command sent.")
        self.flight_timer.stop()  # Stop the flight duration timer
        self.flight_end_time = datetime.datetime.now()  # Record the end time
        duration = self.flight_end_time - self.flight_start_time  # Calculate flight duration
        QMessageBox.information(self, "Flight Completed", f"Flight duration: {duration}")
        print(f"Flight data saved in: {self.drone_controller.current_flight_folder}")
        # Re-enable navigation buttons.
        self.home_button.setEnabled(True)
        self.fullscreen_button.setEnabled(True)
        self.home_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: #007BFF; color: white;")
        self.fullscreen_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: #007BFF; color: white;")
        # Start processing the flight video.
        self.process_flight_video(duration)
        self.update_history_button()
        self.history_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: #007BFF; color: white;")
        # Clear any active continuous movement commands.
        for act in self.continuous_actions:
            self.set_active_movement(act, False)
        # Re-enable commands after a 5-second delay.
        QTimer.singleShot(5000, self.unlock_commands)

    def unlock_commands(self):
        """
        Unlocks the command input, allowing new commands to be processed.
        """
        self.commands_locked = False
        print("Commands unlocked after delay.")

    def process_flight_video(self, duration):
        """
        Initiates processing of the flight video:
          - Stops recording to ensure the video file is properly finalized.
          - After a 1-second delay (to allow file release), starts the video processing routine.
          
        :param duration: Duration of the flight.
        """
        # Stop recording to release the VideoWriter.
        self.drone_controller.stop_recording()
        
        # Wait 1 second to ensure the VideoWriter is fully released.
        QTimer.singleShot(1000, lambda: self.start_video_processing(duration))

    def start_video_processing(self, duration):
        """
        Processes the flight video file.
        If the video file exists, it runs the processing function,
        then disconnects the drone and closes the UI.
        
        :param duration: Duration of the flight.
        """
        video_path = os.path.join(self.drone_controller.current_flight_folder, "flight_video.mp4")
        if os.path.exists(video_path):
            try:
                run(video_path, duration, self.field_path)
                self.disconnect_drone()
                self.close()
            except Exception as e:
                QMessageBox.critical(self, "Processing Error", f"Error processing video: {e}")
        else:
            QMessageBox.warning(self, "Video Missing", "No flight video found for processing!")

    def update_history_button(self):
        """
        Updates the flight history button's enabled state and appearance based on whether there are stored flight runs.
        """
        runs_dir = os.path.join(self.field_path, "runs")
        if os.path.exists(runs_dir) and os.listdir(runs_dir):
            self.history_button.setEnabled(True)
            self.history_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: #007BFF; color: white;")
        else:
            self.history_button.setEnabled(False)
            self.history_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: lightgray; color: gray;")

    def closeEvent(self, event):
        """
        Handles the window close event:
          - Stops all timers.
          - Disconnects the drone.
          - Calls the superclass's closeEvent.
        """
        self.stop_all_timers()
        
        if self.drone_controller.is_connected:
            try:
                self.disconnect_drone()
            except Exception as e:
                print(f"Error turning stream off: {e}")
        super().closeEvent(event)
    
    # ---------------------------------------------------------------------
    # Video Stream Handling
    # ---------------------------------------------------------------------
    def update_video_stream(self):
        """
        Retrieves a frame from the drone's video stream, converts it to a QImage,
        displays it in the UI, and records it for later video processing.
        """
        if not self.drone_controller.is_connected:
            return
        frame = self.drone_controller.get_frame()
        if frame is None:
            return
        # Convert the frame (numpy array) to a QImage.
        height, width, channels = frame.shape
        bytes_per_line = channels * width
        q_img = QImage(frame.data, width, height, bytes_per_line, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(q_img)
        self.stream_label.setPixmap(pixmap)
        # Save the frame for the flight video.
        self.drone_controller.record_frame(frame)

    # --- Non-continuous movement methods (for discrete triggers) ---
    def flip_left(self):
        """
        Executes the drone's flip left maneuver if connected.
        """
        if self.drone_controller.is_connected:
            self.execute_command(self.drone_controller.flip_left)

    def flip_right(self):
        """
        Executes the drone's flip right maneuver if connected.
        """
        if self.drone_controller.is_connected:
            self.execute_command(self.drone_controller.flip_right)

    # ---------------------------------------------------------------------
    # Navigation to Other Pages
    # ---------------------------------------------------------------------
    def go_to_homepage(self):
        """
        Navigates to the home page:
          - Stops all timers.
          - Opens the homepage.
          - Closes the current drone control UI.
        """
        self.stop_all_timers()
        self.home_page = open_homepage()
        self.home_page.show()
        self.close()

    def view_flight_history(self):
        """
        Opens the flight history/report application:
          - Shows the report window.
          - Stops all timers.
          - Disconnects the drone.
          - Closes the current UI.
        """
        self.report_app = DroneReportApp(self.field_path)
        self.report_app.show()
        self.stop_all_timers()
        self.disconnect_drone()
        self.close()
        
    def stop_all_timers(self):
        """
        Stops all running timers and halts video recording.
        Also attempts to turn off the drone's video stream.
        """
        self.flight_timer.stop()
        self.ui_timer.stop()
        self.controller_timer.stop()
        self.stream_timer.stop()
        # self.drone_controller.stop_recording()
        self.history_timer.stop()
        # if self.drone_controller.is_connected:
        #     try:
        #         self.drone_controller.tello.streamoff()
        #         print("Tello stream is OFF.")
        #     except Exception as e:
        #         print(f"Error turning stream off: {e}")
