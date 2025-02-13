import os 
import datetime
import threading
import platform
import subprocess

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
from report_gen import DroneReportApp
from video_process import run
from shared import open_homepage, open_full_screen
# Import our separated drone-related functions (connection, control, etc.)
from drone_functions import DroneController, DroneConnectWorker, ConnectingDialog


# =============================================================================
# Main Drone Control Application (UI remains unchanged)
# =============================================================================
class DroneControlApp(QMainWindow):
    def __init__(self, field_path):
        """
        Initialize the DroneControlApp by setting up the window,
        creating directories for flight data, initializing the drone,
        setting up timers, and building the user interface.
        """
        super().__init__()
        self.setWindowTitle("Drone Control")
        self.setGeometry(100, 100, 1200, 800)  # Set the window position and size

        # Save the path to the field where flight data will be stored.
        self.field_path = field_path
        self.flights_folder = os.path.join(self.field_path, "flights")
        os.makedirs(self.flights_folder, exist_ok=True)  # Ensure the flights folder exists

        # Create an instance of the Tello drone and wrap it with our DroneController
        self.tello = Tello()
        self.drone_controller = DroneController(self.tello, self.flights_folder)

        # Initialize flight and data states for UI tracking.
        self.flight_duration = 0         # Total flight duration in seconds
        self.flight_start_time = None    # Timestamp when the flight started
        self.consecutive_ping_failures = 0  # Counter for consecutive ping failures (used to check connection health)

        # ---------------------------------------------------------------------
        # Timers Setup
        # ---------------------------------------------------------------------
        # Timer to update the flight duration every second.
        self.flight_timer = QTimer()
        self.flight_timer.timeout.connect(self.update_flight_duration)

        # Timer to update UI statistics (battery, etc.) every 3 seconds.
        self.ui_timer = QTimer()
        self.ui_timer.timeout.connect(self.update_ui_stats)
        self.ui_timer.start(3000)  # 3000 milliseconds = 3 seconds

        # Initialize pygame for controller (joystick) support.
        pygame.init()
        pygame.joystick.init()
        self.controller = None  # This will hold the joystick/controller instance if connected

        # Timer to poll the controller input frequently (every 20ms) for smooth responsiveness.
        self.controller_timer = QTimer()
        self.controller_timer.timeout.connect(self.poll_controller_input)
        self.controller_timer.start(20)

        # Timer to check the drone connection status every 2 seconds.
        self.connection_check_timer = QTimer()
        self.connection_check_timer.timeout.connect(self.check_drone_connection)
        self.connection_check_timer.start(2000)
        
        self.history_timer = QTimer()
        self.history_timer.timeout.connect(self.update_history_button)
        self.history_timer.start(2000)

        # Mapping of keyboard keys to their corresponding drone control methods.
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

        # Flag to enable/disable keyboard control.
        self.keyboard_control_enabled = True
        # Dictionary to store control buttons for later reference.
        self.control_buttons = {}

        # Timer to update the video stream (drone camera feed) on the UI.
        self.stream_timer = QTimer()
        self.stream_timer.timeout.connect(self.update_video_stream)
        # Note: stream_timer is started after a successful connection.

        # Build the user interface (UI layout, widgets, etc.)
        self.init_ui()
        # Check if any controller is connected and update UI accordingly.
        self.update_controller_status()

        # Immediately try to connect to the drone asynchronously.
        self.connect_drone_async()

    # ---------------------------------------------------------------------
    # UI Setup (Layout and Widgets)
    # ---------------------------------------------------------------------
    def init_ui(self):
        """
        Create and configure the main UI layout, including the top area
        (connection status, battery, stream) and bottom area (control buttons).
        """
        # Create the main widget and set it as the central widget of the window.
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)

        # -------------------------------
        # TOP AREA: Status and Stream
        # -------------------------------
        top_area_widget = QWidget()
        top_area_layout = QVBoxLayout(top_area_widget)

        # Connection Status label: shows whether the drone is connected.
        self.connection_status = QLabel("DISCONNECTED")
        self.connection_status.setStyleSheet(
            "background-color: red; color: white; font-size: 18px; font-weight: bold; border: 2px solid #555;"
        )
        self.connection_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.connection_status.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        top_area_layout.addWidget(self.connection_status)

        # Notification label for critical warnings (e.g., low battery).
        self.notification_label = QLabel("")
        self.notification_label.setStyleSheet("color: red; font-size: 16px; font-weight: bold;")
        self.notification_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.notification_label.setVisible(False)
        top_area_layout.addWidget(self.notification_label)
        
        # Wi-Fi Connection Warning Label (new): alerts if the drone disconnects from WiFi.
        self.connection_notification_label = QLabel("")
        self.connection_notification_label.setStyleSheet("color: orange; font-size: 16px; font-weight: bold;")
        self.connection_notification_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.connection_notification_label.setVisible(False)
        top_area_layout.addWidget(self.connection_notification_label)

        # Content Layout: Divides the top area into a left panel (controls/info) and the stream area.
        content_layout = QHBoxLayout()
        top_area_layout.addLayout(content_layout)

        # Left panel layout for battery, controller status, and drone info.
        left_panel = QVBoxLayout()

        # Battery box: shows current battery level.
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

        # Controller Status box: shows if a joystick/controller is connected.
        controller_status_box = QGroupBox("Controller Status")
        controller_layout = QVBoxLayout()
        self.controller_status_label = QLabel("No Controller Connected")
        self.controller_status_label.setStyleSheet("color: red; font-size: 14px; font-weight: bold;")
        controller_layout.addWidget(self.controller_status_label)
        controller_status_box.setLayout(controller_layout)
        controller_status_box.setFixedHeight(60)
        left_panel.addWidget(controller_status_box)

        # Drone Info box: displays information like temperature, height, speed, etc.
        info_box = QGroupBox("Drone Info")
        info_layout = QVBoxLayout()
        self.info_labels = {
            "Temperature": QLabel("0°C"),
            "Height": QLabel("0 cm"),
            "Speed": QLabel("0 cm/s"),
            "Data Transmitted": QLabel("0 MB"),
            "Flight Duration": QLabel("0 sec"),
        }
        # Create a row for each piece of info.
        for key, lbl in self.info_labels.items():
            row = QHBoxLayout()
            row.addWidget(QLabel(f"{key}:"))
            row.addWidget(lbl)
            info_layout.addLayout(row)
        info_box.setLayout(info_layout)
        info_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        left_panel.addWidget(info_box, stretch=1)

        # Wrap left panel in a widget and add to the content layout.
        left_panel_widget = QWidget()
        left_panel_widget.setLayout(left_panel)
        left_panel_widget.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        left_panel_widget.setMaximumWidth(300)
        content_layout.addWidget(left_panel_widget, stretch=1)

        # Stream Label: displays the video feed from the drone.
        self.stream_label = QLabel("Drone Stream")
        self.stream_label.setStyleSheet(
            "background-color: #000; color: white; font-size: 14px; border: 1px solid #555;"
        )
        self.stream_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stream_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.stream_label.setScaledContents(True)
        content_layout.addWidget(self.stream_label, stretch=3)

        main_layout.addWidget(top_area_widget, stretch=3)

        # -------------------------------
        # BOTTOM AREA: Control Buttons & Navigation
        # -------------------------------
        bottom_area_widget = QWidget()
        bottom_area_layout = QVBoxLayout(bottom_area_widget)

        # Layout for control buttons (for various drone operations).
        controls_layout = QVBoxLayout()
        control_buttons = [
            [("Q", "Flip Left"), ("W", "Forward"), ("E", "Flip Right")],
            [("A", "Left"), ("S", "Backward"), ("D", "Right")],
            [("Enter", "Take Off", "green"), ("P", "Land", "red")],
            [("Up Arrow", "Up"), ("Down Arrow", "Down"), ("Left Arrow", "Rotate Left"), ("Right Arrow", "Rotate Right")],
        ]
        # Create buttons row-by-row.
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

        # Button to view flight history; initially disabled.
        self.history_button = QPushButton("View Flight History")
        self.history_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: #007BFF; color: white;")
        self.history_button.clicked.connect(self.view_flight_history)
        self.history_button.setEnabled(True)
        bottom_area_layout.addWidget(self.history_button)

        # Button to navigate to the homepage.
        self.home_button = QPushButton("Αρχική Σελίδα")
        self.home_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: #007BFF; color: white;")
        self.home_button.clicked.connect(self.go_to_homepage)
        bottom_area_layout.addWidget(self.home_button)

        # Button for full screen drone operation.
        self.fullscreen_button = QPushButton("Full Screen Drone Operation")
        self.fullscreen_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: #007BFF; color: white;")
        self.fullscreen_button.setEnabled(True)
        self.fullscreen_button.clicked.connect(self.launch_fullscreen)
        bottom_area_layout.addWidget(self.fullscreen_button)

        # Connect/Disconnect toggle button.
        self.connect_toggle_button = QPushButton("Connect")
        self.connect_toggle_button.setStyleSheet(
            "font-size: 16px; padding: 10px; background-color: green; color: white;"
        )
        self.connect_toggle_button.clicked.connect(self.toggle_connection)
        bottom_area_layout.addWidget(self.connect_toggle_button)

        main_layout.addWidget(bottom_area_widget, stretch=1)

    # ---------------------------------------------------------------------
    # Toggle Connection: Connect or disconnect the drone.
    # ---------------------------------------------------------------------
    def toggle_connection(self):
        """If connected, disconnect. If disconnected, reconnect asynchronously."""
        if self.drone_controller.is_connected:
            self.disconnect_drone()
        else:
            self.connect_drone_async()
            
    def disconnect_drone(self):
        """
        Disconnect from the drone and update the UI.
        This stops the video stream and resets connection status.
        """
        if self.drone_controller.is_connected:
            try:
                self.drone_controller.disconnect()
                print("Drone stream turned off.")
            except Exception as e:
                print("Error turning off drone stream:", e)
            self.stream_timer.stop()  # Stop updating the video stream.
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
    # Asynchronous Drone Connection: Runs in a separate thread.
    # ---------------------------------------------------------------------
    def connect_drone_async(self):
        """
        Attempt to connect to the drone asynchronously using a separate QThread.
        This ensures that the UI remains responsive during the connection process.
        """
        # Display a dialog to inform the user that connection is in progress.
        self.connecting_dialog = ConnectingDialog()
        self.connecting_dialog.show()

        # Create a QThread and a worker to handle the connection process.
        self.connection_thread = QThread()
        self.connection_worker = DroneConnectWorker(self.drone_controller)
        self.connection_worker.moveToThread(self.connection_thread)
        self.connection_thread.started.connect(self.connection_worker.run)
        # Connect signals for success and error handling.
        self.connection_worker.connect_success.connect(self.handle_connect_success)
        self.connection_worker.connect_error.connect(self.handle_connect_error)
        # Also quit the thread when connection is done (either success or error).
        self.connection_worker.connect_success.connect(self.connection_thread.quit)
        self.connection_worker.connect_error.connect(self.connection_thread.quit)
        self.connection_thread.finished.connect(self.connection_thread.deleteLater)
        self.connection_thread.start()

    def handle_connect_success(self):
        """
        Callback function executed when the drone connects successfully.
        Updates the UI elements and starts the video stream.
        """
        self.connection_status.setText("CONNECTED")
        self.connection_status.setStyleSheet(
            "background-color: green; color: white; font-size: 18px; font-weight: bold; border: 2px solid #555;"
        )
        self.connect_toggle_button.setText("Disconnect")
        self.connect_toggle_button.setStyleSheet(
            "font-size: 16px; padding: 10px; background-color: red; color: white;"
        )
        # Start the timer to update the video stream every 50ms.
        self.stream_timer.start(50)
        self.connecting_dialog.close()
        print("Drone connected successfully and stream is ON.")

    def handle_connect_error(self, error_message):
        """
        Callback function executed when there is an error connecting to the drone.
        Displays an error message and resets the UI.
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
    # Check Drone Connection: Uses ping to verify if the drone is still reachable.
    # ---------------------------------------------------------------------
    def check_drone_connection(self):
        """Periodically ping the drone to verify connection status."""
        if not self.drone_controller.is_connected:
            return

        # Use the ping_drone method to check connectivity.
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
            # Reset the failure counter if the ping succeeds.
            if self.consecutive_ping_failures > 0:
                print("Ping succeeded. Resetting failure counter.")
            self.consecutive_ping_failures = 0
            if self.connection_notification_label.isVisible():
                self.connection_notification_label.setVisible(False)

    def ping_drone(self, ip="192.168.10.1", count=1, timeout=1):
        """
        Ping the drone using its IP address.
        Returns True if the ping is successful, otherwise False.
        """
        # Determine the correct ping command parameter based on the operating system.
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
        Stop all current timers, clean up pygame resources,
        disconnect the drone, and open the full-screen drone operation window.
        """
        self.stop_all_timers()
        pygame.joystick.quit()
        pygame.quit()
        self.disconnect_drone()
        self.fullscreen_window = open_full_screen(self.field_path)
        self.fullscreen_window.show()
        self.close()

    def center_window(self):
        """
        Center the window on the screen.
        """
        self.show()
        self.updateGeometry()
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        center_x = screen_geometry.x() + (screen_geometry.width() - self.width()) // 2
        center_y = screen_geometry.y() + (screen_geometry.height() - self.height()) // 2
        self.move(center_x, center_y)

    # ---------------------------------------------------------------------
    # Controller Management: Handling joystick/controller inputs.
    # ---------------------------------------------------------------------
    def update_controller_status(self):
        """
        Check if a joystick/controller is connected.
        Update the UI and enable/disable keyboard controls accordingly.
        """
        if pygame.joystick.get_count() > 0:
            if not self.controller:
                self.controller = pygame.joystick.Joystick(0)
                self.controller.init()
            self.controller_status_label.setText("Controller Connected")
            self.controller_status_label.setStyleSheet("color: green; font-size: 14px; font-weight: bold;")
            # Disable on-screen control buttons when a physical controller is connected.
            self.set_controls_enabled(False)
        else:
            self.controller = None
            self.controller_status_label.setText("No Controller Connected")
            self.controller_status_label.setStyleSheet("color: red; font-size: 14px; font-weight: bold;")
            self.set_controls_enabled(True)

    def set_controls_enabled(self, enabled: bool):
        """
        Enable or disable all control buttons on the UI.
        Also sets whether keyboard controls are active.
        """
        for button in self.control_buttons.values():
            button.setEnabled(enabled)
        self.keyboard_control_enabled = enabled

    def poll_controller_input(self):
        """
        Poll for controller events (button presses or joystick movements)
        and handle them appropriately.
        """
        pygame.event.pump()
        controller_count = pygame.joystick.get_count()
        # Update controller status if there's a change in connection.
        if (self.controller and controller_count == 0) or (not self.controller and controller_count > 0):
            self.update_controller_status()

        if self.controller:
            # Process each event from the controller.
            for event in pygame.event.get():
                if event.type == pygame.JOYBUTTONDOWN:
                    self.handle_button_press(event.button)
                elif event.type == pygame.JOYAXISMOTION:
                    self.handle_axis_motion(event.axis, event.value)

    def handle_button_press(self, button):
        """
        Map joystick button presses to drone commands.
        Button mappings:
            0: Take Off
            1: Land
            2: Flip Left
            3: Flip Right
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
        Map joystick axis movements to drone movement commands.
        Axis mappings:
            0: Left horizontal (move left/right)
            1: Left vertical (move forward/backward)
            2: Right horizontal (rotate left/right)
            3: Right vertical (move up/down)
        """
        if axis == 0:  # Left horizontal axis
            if value < -0.5:
                self.move_left()
            elif value > 0.5:
                self.move_right()
        elif axis == 1:  # Left vertical axis
            if value < -0.5:
                self.move_forward()
            elif value > 0.5:
                self.move_backward()
        elif axis == 2:  # Right horizontal axis
            if value < -0.5:
                self.rotate_left()
            elif value > 0.5:
                self.rotate_right()
        elif axis == 3:  # Right vertical axis
            if value < -0.5:
                self.move_up()
            elif value > 0.5:
                self.move_down()

    # ---------------------------------------------------------------------
    # Control Buttons: Creating and handling on-screen control buttons.
    # ---------------------------------------------------------------------
    def create_control_button(self, key: str, action: str, color=None) -> QPushButton:
        """
        Create a QPushButton for a specific drone action.
        The button displays the key and the action. An optional color can be specified.
        """
        btn = QPushButton(f"{key}\n({action})")
        if color:
            btn.setStyleSheet(f"background-color: {color}; color: white; font-weight: bold;")
        # Connect the button click to the corresponding action method.
        btn.clicked.connect(self.create_button_handler(action))
        # Save the button in a dictionary for later reference.
        self.control_buttons[action] = btn
        return btn

    def create_button_handler(self, action: str):
        """
        Return a handler function that calls the appropriate drone command based on the action.
        """
        def handler():
            # Map action text to the corresponding method.
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
        """
        Overridden method to handle keyboard events.
        Executes a mapped action if the pressed key exists in key_pressed_mapping.
        """
        if not self.keyboard_control_enabled:
            return
        if event.key() in self.key_pressed_mapping:
            self.key_pressed_mapping[event.key()]()

    # ---------------------------------------------------------------------
    # Flight Duration & Stats Updates
    # ---------------------------------------------------------------------
    def update_flight_duration(self):
        """
        Increment the flight duration counter by one second.
        Also update the flight duration label on the UI.
        """
        self.flight_duration += 1
        self.info_labels["Flight Duration"].setText(f"{self.flight_duration} sec")

    def update_ui_stats(self):
        """
        Update various UI elements such as battery level, temperature, height, and speed.
        This method is called periodically by ui_timer.
        """
        if not self.drone_controller.is_connected:
            return
        try:
            battery_level = self.drone_controller.get_battery()
            temperature = self.drone_controller.get_temperature()
            height = self.drone_controller.get_height()
            speed = self.drone_controller.get_speed_x()
            self.update_history_button()
            # Update the battery progress bar.
            self.battery_bar.setValue(battery_level)
            # Show a warning if the battery level is critically low.
            if battery_level < 20:
                self.notification_label.setText("Warning: Battery level is critically low!")
                self.notification_label.setVisible(True)
            else:
                self.notification_label.setVisible(False)

            # Update the info labels with current drone stats.
            self.info_labels["Temperature"].setText(f"{temperature}°C")
            self.info_labels["Height"].setText(f"{height} cm")
            self.info_labels["Speed"].setText(f"{speed} cm/s")
            self.info_labels["Data Transmitted"].setText("0 MB")
        except Exception as e:
            print("Failed to get Tello state:", e)

    # ---------------------------------------------------------------------
    # Flight Operations: Commands to take off, land, and process flight data.
    # ---------------------------------------------------------------------
    def take_off(self):
        """
        Command the drone to take off.
        Disables some buttons during flight and starts tracking flight duration.
        """
        if not self.drone_controller.is_connected:
            QMessageBox.warning(self, "Drone Disconnected", "Cannot take off because the drone is not connected.")
            return

        # Disable buttons during flight to prevent conflicting commands.
        self.history_button.setEnabled(False)
        self.home_button.setEnabled(False)
        self.fullscreen_button.setEnabled(False)
        self.home_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: lightgray; color: gray;")
        self.fullscreen_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: lightgray; color: gray;")
        self.history_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: lightgray; color: gray;")
        try:
            self.drone_controller.takeoff()
            print("Drone takeoff successful.")

            self.flight_timer.start(1000)  # Start tracking flight duration (every second).
            self.flight_duration = 0
            self.flight_start_time = datetime.datetime.now()
        except Exception as e:
            QMessageBox.critical(self, "Take Off Error", f"Unable to take off: {e}")

    def land(self):
        """
        Command the drone to land.
        Stops flight duration tracking and processes the flight video.
        """
        if not self.drone_controller.is_connected:
            QMessageBox.warning(self, "Drone Disconnected", "Cannot land because the drone is not connected.")
            return

        try:
            self.drone_controller.land()
            print("Drone landing...")

            self.flight_timer.stop()  # Stop the flight duration timer.
            self.flight_end_time = datetime.datetime.now()
            duration = self.flight_end_time - self.flight_start_time

            # Inform the user about the completed flight duration.
            QMessageBox.information(self, "Flight Completed", f"Flight duration: {duration}")
            print(f"Flight data saved in: {self.drone_controller.current_flight_folder}")

            # Re-enable navigation buttons.
            self.home_button.setEnabled(True)
            self.fullscreen_button.setEnabled(True)
            self.home_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: #007BFF; color: white;")
            self.fullscreen_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: #007BFF; color: white;")

            # Process the flight video and update flight history.
            self.process_flight_video(duration)
            self.update_history_button()
            self.history_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: #007BFF; color: white;")
        except Exception as e:
            QMessageBox.critical(self, "Land Error", f"Unable to land: {e}")

    def process_flight_video(self, duration):
        """
        Process the flight video using the external video processing function.
        If processing is successful, disconnect the drone and close the app.
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
        Enable the 'View Flight History' button if there is flight history available.
        """
        runs_dir = os.path.join(self.field_path, "runs")
        if os.path.exists(runs_dir) and os.listdir(runs_dir):
            self.history_button.setEnabled(True)
            self.history_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: #007BFF; color: white;")
        else:
            self.history_button.setEnabled(False)
            self.history_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: lightgray; color: gray;")

    def closeEvent(self, event):
        """Ensure all timers are stopped and drone is disconnected on close."""
        self.stop_all_timers()
        self.disconnect_drone()
        super().closeEvent(event)
    
    # ---------------------------------------------------------------------
    # Video Stream: Fetch and display the video feed from the drone.
    # ---------------------------------------------------------------------
    def update_video_stream(self):
        """
        Get the latest frame from the drone and display it on the stream label.
        Also, record the frame if recording is active.
        """
        if not self.drone_controller.is_connected:
            return
        frame = self.drone_controller.get_frame()
        if frame is None:
            return

        # Convert the raw frame (assumed RGB) to a QImage, then to a QPixmap for display.
        height, width, channels = frame.shape
        bytes_per_line = channels * width
        q_img = QImage(
            frame.data,
            width,
            height,
            bytes_per_line,
            QImage.Format.Format_RGB888
        )
        pixmap = QPixmap.fromImage(q_img)
        self.stream_label.setPixmap(pixmap)

        # If recording is enabled, record the frame.
        self.drone_controller.record_frame(frame)

    # ---------------------------------------------------------------------
    # Movement Commands: Forward, backward, left, right, up, down, rotate, flip.
    # ---------------------------------------------------------------------
    def move_forward(self):
        if self.drone_controller.is_connected:
            try:
                self.drone_controller.move_forward()
            except Exception as e:
                print(f"Failed to move forward: {e}")

    def move_backward(self):
        if self.drone_controller.is_connected:
            try:
                self.drone_controller.move_backward()
            except Exception as e:
                print(f"Failed to move backward: {e}")

    def move_left(self):
        if self.drone_controller.is_connected:
            try:
                self.drone_controller.move_left()
            except Exception as e:
                print(f"Failed to move left: {e}")

    def move_right(self):
        if self.drone_controller.is_connected:
            try:
                self.drone_controller.move_right()
            except Exception as e:
                print(f"Failed to move right: {e}")

    def move_up(self):
        if self.drone_controller.is_connected:
            try:
                self.drone_controller.move_up()
            except Exception as e:
                print(f"Failed to move up: {e}")

    def move_down(self):
        if self.drone_controller.is_connected:
            try:
                self.drone_controller.move_down()
            except Exception as e:
                print(f"Failed to move down: {e}")

    def rotate_left(self):
        if self.drone_controller.is_connected:
            try:
                self.drone_controller.rotate_left()
            except Exception as e:
                print(f"Failed to rotate left: {e}")

    def rotate_right(self):
        if self.drone_controller.is_connected:
            try:
                self.drone_controller.rotate_right()
            except Exception as e:
                print(f"Failed to rotate right: {e}")

    def flip_left(self):
        if self.drone_controller.is_connected:
            try:
                self.drone_controller.flip_left()
            except Exception as e:
                print(f"Failed to flip left: {e}")

    def flip_right(self):
        if self.drone_controller.is_connected:
            try:
                self.drone_controller.flip_right()
            except Exception as e:
                print(f"Failed to flip right: {e}")

    # ---------------------------------------------------------------------
    # Navigation to Other Pages: Homepage and Flight History.
    # ---------------------------------------------------------------------
    def go_to_homepage(self):
        """
        Stop all timers and open the homepage.
        """
        self.stop_all_timers()
        self.home_page = open_homepage()
        self.home_page.show()
        self.close()

    def view_flight_history(self):
        """
        Open the flight history report window.
        """
        self.report_app = DroneReportApp(self.field_path)
        self.report_app.show()
        self.stop_all_timers()
        self.disconnect()
        self.close()
        

    def stop_all_timers(self):
        """
        Stop all active timers and recording processes.
        Also, attempt to turn off the Tello stream if connected.
        """
        self.flight_timer.stop()
        self.ui_timer.stop()
        self.controller_timer.stop()
        self.stream_timer.stop()
        self.drone_controller.stop_recording()
        self.history_timer.stop()

        if self.drone_controller.is_connected:
            try:
                self.drone_controller.tello.streamoff()
                print("Tello stream is OFF.")
            except Exception as e:
                print(f"Error turning stream off: {e}")


# =============================================================================
# Main entry point (for testing)
# =============================================================================
# if __name__ == "__main__":
#     import sys
#     # Create the QApplication instance.
#     app = QApplication(sys.argv)
#     # Define the field path where flight data will be stored (adjust as necessary).
#     field_path = os.path.abspath("fields/field1")
#     # Create the main DroneControlApp window.
#     window = DroneControlApp(field_path)
#     window.show()
#     # Start the event loop.
#     sys.exit(app.exec())
