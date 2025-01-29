import sys
import os
import datetime
import random
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QProgressBar, QMessageBox, QGroupBox, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeyEvent
from report_gen import DroneReportApp
from video_process import run
import pygame
from shared import open_homepage, open_full_screen
import threading


# ---------------------------------------------------------------------
# MockTello: A Simulated Drone Class
# ---------------------------------------------------------------------
class MockTello:
    """
    Simulates basic drone behavior such as takeoff, land, move, stream on/off.
    """

    def __init__(self):
        """
        Initializes internal states:
          - is_flying: Whether the drone is in-flight
          - stream_on: Whether the video stream is active
        """
        self.is_flying = False
        self.stream_on = False

    def connect(self):
        """Simulates a connection to the drone."""
        print("Mock: Drone connected")

    def takeoff(self):
        """Simulates takeoff if not already flying."""
        if self.is_flying:
            print("Mock: Already flying!")
        else:
            print("Mock: Taking off...")
            self.is_flying = True

    def land(self):
        """Simulates landing if currently flying."""
        if not self.is_flying:
            print("Mock: Already landed!")
        else:
            print("Mock: Landing...")
            self.is_flying = False

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
# DroneControlApp: Main Window for Drone Control
# ---------------------------------------------------------------------
class DroneControlApp(QMainWindow):
    """
    A main window providing controls and status for a mock drone:
      - Connects to a MockTello instance
      - Keyboard/Xbox controller input
      - Flight stats (battery, duration, height, speed)
      - Video stream placeholder
      - PDF/History/Fullscreen transitions
    """

    def __init__(self, field_path):
        """
        Constructor:
          field_path: Path to the field directory where flight data is saved.
        """
        super().__init__()
        self.setWindowTitle("Drone Control")
        self.setGeometry(100, 100, 1200, 800)

        # Setup references
        self.field_path = field_path
        self.flights_folder = os.path.join(self.field_path, "flights")
        os.makedirs(self.flights_folder, exist_ok=True)

        # Initialize mock drone
        self.drone = MockTello()
        self.drone.connect()
        self.drone.is_flying = False

        # Flight/data states
        self.flight_duration = 0
        self.battery_level = 100
        self.fly_height = 0
        self.speed = 0
        self.current_flight_folder = None

        # Timers
        self.flight_timer = QTimer()
        self.flight_timer.timeout.connect(self.update_flight_duration)

        self.ui_timer = QTimer()
        self.ui_timer.timeout.connect(self.update_ui_stats)
        self.ui_timer.start(2000)  # Update stats every 2 seconds

        # For controlling the drone via an Xbox controller
        pygame.init()
        pygame.joystick.init()
        self.controller = None

        # Timer to poll the controller
        self.controller_timer = QTimer()
        self.controller_timer.timeout.connect(self.poll_controller_input)
        self.controller_timer.start(20)  # Poll every 20ms

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

        # Whether keyboard input is enabled or disabled
        self.keyboard_control_enabled = True

        # Dictionary for control buttons in the UI
        self.control_buttons = {}

        # Build the UI
        self.init_ui()

        # Check if a controller is connected
        self.update_controller_status()

    # ---------------------------------------------------------------------
    # UI Setup
    # ---------------------------------------------------------------------

    def init_ui(self):
        """
        Builds the layout:
          - Connection status, notification label
          - Left panel (battery, controller, info)
          - Stream placeholder
          - Control buttons
          - Buttons for flight history, homepage, fullscreen
        """
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)

        # Connection Status Label
        self.connection_status = QLabel("CONNECTED")
        self.connection_status.setStyleSheet(
            "background-color: green; color: white; font-size: 18px; font-weight: bold; border: 2px solid #555;"
        )
        self.connection_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.connection_status.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        main_layout.addWidget(self.connection_status)

        # Notification Label (hidden by default)
        self.notification_label = QLabel("")
        self.notification_label.setStyleSheet("color: red; font-size: 16px; font-weight: bold;")
        self.notification_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.notification_label.setVisible(False)
        main_layout.addWidget(self.notification_label)

        # Content Layout (Left panel + Stream)
        content_layout = QHBoxLayout()
        main_layout.addLayout(content_layout)

        left_panel = QVBoxLayout()

        # ------------------
        # Battery GroupBox
        # ------------------
        battery_box = QGroupBox("Battery")
        battery_layout = QVBoxLayout()
        self.battery_bar = QProgressBar()
        self.battery_bar.setValue(self.battery_level)
        self.battery_bar.setStyleSheet("QProgressBar::chunk { background-color: green; }")
        self.battery_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        battery_layout.addWidget(self.battery_bar)
        battery_box.setLayout(battery_layout)
        battery_box.setFixedHeight(60)
        left_panel.addWidget(battery_box)

        # ------------------
        # Controller Status
        # ------------------
        controller_status_box = QGroupBox("Controller Status")
        controller_layout = QVBoxLayout()
        self.controller_status_label = QLabel("No Controller Connected")
        self.controller_status_label.setStyleSheet("color: red; font-size: 14px; font-weight: bold;")
        controller_layout.addWidget(self.controller_status_label)
        controller_status_box.setLayout(controller_layout)
        controller_status_box.setFixedHeight(60)
        left_panel.addWidget(controller_status_box)

        # ------------------
        # Drone Info Box
        # ------------------
        info_box = QGroupBox("Drone Info")
        info_layout = QVBoxLayout()
        self.info_labels = {
            "Temperature": QLabel("20°C"),
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

        # ------------------
        # Stream Placeholder
        # ------------------
        self.stream_label = QLabel("Drone Stream Placeholder")
        self.stream_label.setStyleSheet("background-color: #000; color: white; font-size: 14px; border: 1px solid #555;")
        self.stream_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stream_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        content_layout.addWidget(self.stream_label, stretch=3)

        # ------------------
        # Control Buttons
        # ------------------
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

        # ------------------
        # Footer Buttons (History, Home, Fullscreen)
        # ------------------
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
    # Threads & Windows
    # ---------------------------------------------------------------------

    def debug_active_threads(self):
        """Prints all active Python threads to console for debugging."""
        print("Active threads:")
        for thread in threading.enumerate():
            print(thread.name)

    def launch_fullscreen(self):
        """
        Closes this window and opens a fullscreen drone operation window,
        stopping relevant timers and releasing pygame resources.
        """
        self.flight_timer.stop()
        self.ui_timer.stop()
        self.controller_timer.stop()
        pygame.joystick.quit()
        pygame.quit()

        self.fullscreen_window = open_full_screen(self.field_path)
        self.fullscreen_window.show()
        self.close()

    def center_window(self):
        """
        Centers this window on the screen.
        (Not currently called, but can be uncommented if needed.)
        """
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
        """
        Checks if a controller is connected. If so, disable keyboard/GUI controls
        and use controller exclusively. Otherwise, re-enable them.
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
        Enables or disables all GUI control buttons and toggles keyboard control
        based on the 'enabled' parameter.
        """
        for button in self.control_buttons.values():
            button.setEnabled(enabled)
        self.keyboard_control_enabled = enabled

    def poll_controller_input(self):
        """
        Periodically reads events from the Xbox controller. If a controller
        is connected, handles button presses and axis motions.
        """
        pygame.event.pump()
        controller_count = pygame.joystick.get_count()

        # If the controller state changed (connected/disconnected), re-check
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
        Maps specific controller buttons to certain drone actions.
        Example: A->Take Off, B->Land, etc.
        """
        if button == 0:  # Button A
            print("here")
            self.take_off()
        elif button == 1:  # Button B
            self.land()
        elif button == 2:  # Button X
            self.drone.flip_left()
        elif button == 3:  # Button Y
            self.drone.flip_right()

    def handle_axis_motion(self, axis, value):
        """
        Maps joystick axis movement to drone motion.
        Left joystick for directional, right joystick for rotation/up/down.
        """
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
        """
        Creates a QPushButton for a given action, optionally with a background color.
        The label is f"{key}\n({action})".
        """
        btn = QPushButton(f"{key}\n({action})")
        if color:
            btn.setStyleSheet(f"background-color: {color}; color: white; font-weight: bold;")
        btn.clicked.connect(self.create_button_handler(action))
        self.control_buttons[action] = btn
        return btn

    def create_button_handler(self, action: str):
        """
        Returns a function that, when called, maps the textual action (e.g., "Forward")
        to an actual drone or local method (e.g., self.drone.move_forward).
        """
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
                else:
                    print(f"Warning: Method '{method_name}' not found for action '{action}'")
            else:
                print(f"Warning: Action '{action}' not mapped to any method")
        return handler

    # ---------------------------------------------------------------------
    # Keyboard Events
    # ---------------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent):
        """
        Intercepts keyboard presses; if keyboard control is enabled,
        maps them to drone actions.
        """
        if not self.keyboard_control_enabled:
            return
        if event.key() in self.key_pressed_mapping:
            self.key_pressed_mapping[event.key()]()

    # ---------------------------------------------------------------------
    # Flight Duration & Stats
    # ---------------------------------------------------------------------

    def update_flight_duration(self):
        """
        Increments flight_duration each second and updates the label.
        Called by flight_timer.
        """
        self.flight_duration += 1
        self.info_labels["Flight Duration"].setText(f"{self.flight_duration} sec")

    def update_ui_stats(self):
        """
        Simulates battery drain, random height/speed if flying, updates the
        progress bar, and displays a low-battery warning if <20%.
        """
        self.battery_level = max(0, self.battery_level - random.randint(0, 2))
        self.fly_height = random.randint(0, 500) if self.drone.is_flying else 0
        self.speed = random.uniform(0, 10) if self.drone.is_flying else 0

        self.battery_bar.setValue(self.battery_level)

        if self.battery_level < 20:
            self.notification_label.setText("Warning: Battery level is critically low!")
            self.notification_label.setVisible(True)
        else:
            self.notification_label.setVisible(False)

        self.info_labels["Height"].setText(f"{self.fly_height} cm")
        self.info_labels["Speed"].setText(f"{self.speed:.2f} cm/s")

    # ---------------------------------------------------------------------
    # Flight Operations
    # ---------------------------------------------------------------------

    def take_off(self):
        """
        Sets is_flying to True if not already, starts flight timer,
        creates a flight folder, and turns on the mock stream.
        Disables certain UI buttons while flying.
        """
        self.history_button.setEnabled(False)
        self.home_button.setEnabled(False)
        self.fullscreen_button.setEnabled(False)
        self.home_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: lightgray; color: gray;")
        self.fullscreen_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: lightgray; color: gray;")

        if not self.drone.is_flying:
            self.drone.is_flying = True
            self.flight_timer.start(1000)
            self.flight_start_time = datetime.datetime.now()

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self.current_flight_folder = os.path.join(self.flights_folder, f"flight_{timestamp}")
            os.makedirs(self.current_flight_folder, exist_ok=True)
            print(f"Flight folder created: {self.current_flight_folder}")

            self.stream_label.setText("Stream On")
            self.drone.streamon()
            print("Take off successful")

    def land(self):
        """
        Simulates drone landing if flying, stops flight timer, stops stream,
        then processes the flight video and re-enables UI buttons.
        """
        if self.drone.is_flying:
            self.drone.is_flying = False
            self.flight_timer.stop()
            self.stream_label.setText("Stream Off")
            self.drone.streamoff()

            self.home_button.setEnabled(True)
            self.fullscreen_button.setEnabled(True)
            self.home_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: #007BFF; color: white;")
            self.fullscreen_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: #007BFF; color: white;")

            print("Landing successful")
            self.flight_end_time = datetime.datetime.now()
            duration = self.flight_end_time - self.flight_start_time

            QMessageBox.information(self, "Flight Completed", f"Flight duration: {duration}")
            print(f"Flight data saved in: {self.current_flight_folder}")

            self.process_flight_video(duration)
            self.update_history_button()

    def process_flight_video(self, duration):
        """
        Checks for a flight video in the current_flight_folder, processes it with
        video_process.run, and logs or shows errors if missing or if processing fails.
        """
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
        """
        If the runs folder in field_path has content, enable 'View Flight History' button.
        Otherwise, disable it.
        """
        runs_dir = os.path.join(self.field_path, "runs")
        if os.path.exists(runs_dir) and os.listdir(runs_dir):
            self.history_button.setEnabled(True)
        else:
            self.history_button.setEnabled(False)

    # ---------------------------------------------------------------------
    # Navigation to Other Pages
    # ---------------------------------------------------------------------

    def go_to_homepage(self):
        """
        Stops timers, closes this window, and opens the home page.
        """
        self.flight_timer.stop()
        self.ui_timer.stop()
        self.controller_timer.stop()

        self.home_page = open_homepage()
        self.home_page.show()
        self.close()

    def view_flight_history(self):
        """
        Opens DroneReportApp with the current field path to show flight histories.
        """
        self.report_app = DroneReportApp(self.field_path)
        self.report_app.show()


# if __name__ == "__main__":
#     app = QApplication(sys.argv)
#     window = DroneControlApp()
#     window.show()
#     sys.exit(app.exec())
