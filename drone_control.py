import sys
import os
import datetime
import random
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QProgressBar, QGridLayout, QMessageBox, QGroupBox
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeyEvent
from report_gen import DroneReportApp
from video_process import run
import pygame
from PyQt6.QtCore import QTimer

FLIGHTS_FOLDER = "flights"
if not os.path.exists(FLIGHTS_FOLDER):
    os.makedirs(FLIGHTS_FOLDER)

class MockTello:
    def __init__(self):
        self.is_flying = False
        self.stream_on = False

    def connect(self):
        print("Mock: Drone connected")

    def takeoff(self):
        if self.is_flying:
            print("Mock: Already flying!")
        else:
            print("Mock: Taking off...")
            self.is_flying = True

    def land(self):
        if not self.is_flying:
            print("Mock: Already landed!")
        else:
            print("Mock: Landing...")
            self.is_flying = False

    def streamon(self):
        self.stream_on = True
        print("Mock: Video stream started")

    def streamoff(self):
        self.stream_on = False
        print("Mock: Video stream stopped")

    def end(self):
        print("Mock: Drone disconnected")

class DroneControlApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Drone Control")
        self.setGeometry(100, 100, 1200, 800)
        self.control_buttons = {}
        
        # Initialize Mock Tello
        self.drone = MockTello()
        self.drone.connect()
        self.is_flying = False
        self.flight_duration = 0
        self.battery_level = 100
        self.height = 0
        self.speed = 0
        self.current_flight_folder = None
        self.flight_timer = QTimer()
        self.flight_timer.timeout.connect(self.update_flight_duration)

        self.init_ui()

        # Timer to update UI stats
        self.ui_timer = QTimer()
        self.ui_timer.timeout.connect(self.update_ui_stats)
        self.ui_timer.start(2000)

        # Initialize Xbox Controller
        pygame.init()
        pygame.joystick.init()
        self.controller = None
        self.update_controller_status()

        # Timer to poll controller input
        self.controller_timer = QTimer()
        self.controller_timer.timeout.connect(self.poll_controller_input)
        self.controller_timer.start(50)  # Check every 50ms
        
        # Key mapping
        self.key_pressed_mapping = {
            Qt.Key.Key_W: self.move_forward,
            Qt.Key.Key_S: self.move_backward,
            Qt.Key.Key_A: self.move_left,
            Qt.Key.Key_D: self.move_right,
            Qt.Key.Key_Q: self.flip_left,
            Qt.Key.Key_E: self.flip_right,
            Qt.Key.Key_Return: self.take_off,
            Qt.Key.Key_Space: self.land,
            Qt.Key.Key_Up: self.move_up,
            Qt.Key.Key_Down: self.move_down,
            Qt.Key.Key_Left: self.rotate_left,
            Qt.Key.Key_Right: self.rotate_right,
        }

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)

        # Connection status
        # Connection status
        self.connection_status = QLabel("CONNECTED")
        self.connection_status.setStyleSheet(
            "background-color: green; color: white; font-size: 18px; font-weight: bold; border: 2px solid #555;"
        )
        self.connection_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.connection_status.setFixedHeight(50)  # Fix the height to keep it static
        main_layout.addWidget(self.connection_status)
        

        # Content layout
        content_layout = QHBoxLayout()
        main_layout.addLayout(content_layout)
        
        # Add Notification Label
        self.notification_label = QLabel("")
        self.notification_label.setStyleSheet("color: red; font-size: 16px; font-weight: bold;")
        self.notification_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.notification_label.setVisible(False)  # Hidden by default
        main_layout.addWidget(self.notification_label)


        # Left Panel
        left_panel = QVBoxLayout()

        # Battery Group Box
        battery_box = QGroupBox("Battery")
        battery_layout = QVBoxLayout()

        self.battery_bar = QProgressBar()
        self.battery_bar.setValue(self.battery_level)
        self.battery_bar.setStyleSheet(
            "QProgressBar::chunk { background-color: green; }"
        )
        self.battery_bar.setFixedHeight(20)  # Reduce the height of the progress bar

        battery_layout.addWidget(self.battery_bar)
        battery_box.setLayout(battery_layout)

        # Set fixed size for the group box to make it compact
        battery_box.setFixedHeight(60)  # Height: 60px
        #battery_box.setMaximumWidth(400)

        left_panel.addWidget(battery_box)

        # Controller Status Box
        controller_status_box = QGroupBox("Controller Status")
        controller_layout = QVBoxLayout()

        self.controller_status_label = QLabel("No Controller Connected")
        self.controller_status_label.setStyleSheet("color: red; font-size: 14px; font-weight: bold;")
        controller_layout.addWidget(self.controller_status_label)

        controller_status_box.setLayout(controller_layout)
        controller_status_box.setFixedSize(200, 60)  # Compact size for the box
        left_panel.addWidget(controller_status_box)


        # Info Group Box
        info_box = QGroupBox("Drone Info")
        info_layout = QVBoxLayout()
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
        left_panel.addWidget(info_box)

        content_layout.addLayout(left_panel)

        # Center Panel (Live Stream) with updated size
        self.stream_label = QLabel("Drone Stream Placeholder")
        self.stream_label.setStyleSheet("background-color: #000; color: white; font-size: 14px; border: 1px solid #555;")
        self.stream_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stream_label.setFixedSize(1280, 720)  # Set size for 720p video
        content_layout.addWidget(self.stream_label)

        # Bottom Controls - Compact Layout
        controls_layout = QVBoxLayout()

        # Row 1: Top Movement Controls
        top_controls_layout = QHBoxLayout()
        top_controls_layout.setSpacing(5)  # Reduce spacing between buttons
        top_controls_layout.addWidget(self.create_control_button("Q", "Flip Left"))
        top_controls_layout.addWidget(self.create_control_button("W", "Forward"))
        top_controls_layout.addWidget(self.create_control_button("E", "Flip Right"))
        top_controls_layout.addWidget(self.create_control_button("R", "Flip Forward"))
        controls_layout.addLayout(top_controls_layout)

        # Row 2: Middle Movement Controls
        middle_controls_layout = QHBoxLayout()
        middle_controls_layout.setSpacing(5)  # Reduce spacing between buttons
        middle_controls_layout.addWidget(self.create_control_button("A", "Left"))
        middle_controls_layout.addWidget(self.create_control_button("S", "Backward"))
        middle_controls_layout.addWidget(self.create_control_button("D", "Right"))
        middle_controls_layout.addWidget(self.create_control_button("F", "Flip Back"))
        controls_layout.addLayout(middle_controls_layout)

        # Row 3: Action Controls
        action_controls_layout = QHBoxLayout()
        action_controls_layout.setSpacing(5)  # Reduce spacing between buttons
        action_controls_layout.addWidget(self.create_control_button("Enter", "Take Off", "green"))
        action_controls_layout.addWidget(self.create_control_button("Space", "Land", "red"))
        controls_layout.addLayout(action_controls_layout)

        # Row 4: Directional Controls
        directional_controls_layout = QHBoxLayout()
        directional_controls_layout.setSpacing(5)  # Reduce spacing between buttons
        directional_controls_layout.addWidget(self.create_control_button("Up Arrow", "Up"))
        directional_controls_layout.addWidget(self.create_control_button("Down Arrow", "Down"))
        directional_controls_layout.addWidget(self.create_control_button("Left Arrow", "Rotate Left"))
        directional_controls_layout.addWidget(self.create_control_button("Right Arrow", "Rotate Right"))
        controls_layout.addLayout(directional_controls_layout)

        main_layout.addLayout(controls_layout)




        # View Flight History Button
        self.history_button = QPushButton("View Flight History")
        
        self.history_button.setStyleSheet("font-size: 14px; padding: 10px;")
        self.history_button.clicked.connect(self.view_flight_history)
        
        main_layout.addWidget(self.history_button)
        self.update_history_button()


    def update_controller_status(self):
        if pygame.joystick.get_count() > 0:
            if not self.controller:
                self.controller = pygame.joystick.Joystick(0)
                self.controller.init()
            self.controller_status_label.setText("Controller Connected")
            self.controller_status_label.setStyleSheet("color: green; font-size: 14px; font-weight: bold;")
            self.set_controls_enabled(False)  # Disable buttons and keyboard control
        else:
            self.controller = None
            self.controller_status_label.setText("No Controller Connected")
            self.controller_status_label.setStyleSheet("color: red; font-size: 14px; font-weight: bold;")
            self.set_controls_enabled(True)  # Enable buttons and keyboard control

    def set_controls_enabled(self, enabled):
        # Disable or enable all control buttons
        for button in self.control_buttons.values():
            button.setEnabled(enabled)

        # Toggle keyboard control
        self.keyboard_control_enabled = enabled


    
    def poll_controller_input(self):
        pygame.event.pump()  # Process controller events
        controller_count = pygame.joystick.get_count()

        # Update status if connection changes
        if (self.controller and controller_count == 0) or (not self.controller and controller_count > 0):
            self.update_controller_status()

        if self.controller:
            for event in pygame.event.get():
                if event.type == pygame.JOYBUTTONDOWN:
                    self.handle_button_press(event.button)
                elif event.type == pygame.JOYAXISMOTION:
                    self.handle_axis_motion(event.axis, event.value)

    
    def handle_button_press(self, button):
        """Map controller buttons to drone actions."""
        if button == 0:  # Example: Button A
            self.take_off()
        elif button == 1:  # Example: Button B
            self.land()
        elif button == 2:  # Example: Button X
            self.flip_left()
        elif button == 3:  # Example: Button Y
            self.flip_right()

    def handle_axis_motion(self, axis, value):
        """Map joystick axes to drone movement."""
        if axis == 0:  # Left joystick horizontal
            if value < -0.5:
                self.move_left()
            elif value > 0.5:
                self.move_right()
        elif axis == 1:  # Left joystick vertical
            if value < -0.5:
                self.move_forward()
            elif value > 0.5:
                self.move_backward()
        elif axis == 2:  # Right joystick horizontal
            if value < -0.5:
                self.rotate_left()
            elif value > 0.5:
                self.rotate_right()
        elif axis == 3:  # Right joystick vertical
            if value < -0.5:
                self.move_up()
            elif value > 0.5:
                self.move_down()


    
    def create_control_button(self, key, action, color=None):
        button = QPushButton(f"{key}\n({action})")
        if color:
            button.setStyleSheet(f"background-color: {color}; color: white; font-weight: bold;")
        button.clicked.connect(self.create_button_handler(action))
        self.control_buttons[action] = button  # Store button in the dictionary
        return button

    
    def create_button_handler(self, action):
        def handler():
            # Adjust method name mapping for consistency
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


    def keyPressEvent(self, event: QKeyEvent):
        if not self.keyboard_control_enabled:
            return  # Ignore keyboard input if disabled
        if event.key() in self.key_pressed_mapping:
            self.key_pressed_mapping[event.key()]()


    def update_flight_duration(self):
        self.flight_duration += 1
        self.info_labels["Flight Duration"].setText(f"{self.flight_duration} sec")

    def update_ui_stats(self):
        self.battery_level = max(0, self.battery_level - random.randint(0, 2))  # Simulate battery drain
        self.height = random.randint(0, 500) if self.is_flying else 0
        self.speed = random.uniform(0, 10) if self.is_flying else 0

        # Update battery progress bar
        self.battery_bar.setValue(self.battery_level)

        # Check for low battery and display notification
        if self.battery_level < 20:
            self.notification_label.setText("Warning: Battery level is critically low!")
            self.notification_label.setVisible(True)
        else:
            self.notification_label.setVisible(False)

        # Update other stats
        self.info_labels["Height"].setText(f"{self.height} cm")
        self.info_labels["Speed"].setText(f"{self.speed:.2f} cm/s")


    def take_off(self):
        self.history_button.setEnabled(False)
        if not self.is_flying:
            self.is_flying = True
            self.flight_timer.start(1000)
            self.flight_start_time = datetime.datetime.now()
            # Create flight folder
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self.current_flight_folder = os.path.join(FLIGHTS_FOLDER, f"flight_{timestamp}")
            os.makedirs(self.current_flight_folder, exist_ok=True)

            # Start video stream
            self.stream_label.setText("Stream On")
            self.drone.streamon()
            print("Take off successful")

    def land(self):
        if self.is_flying:
            self.is_flying = False
            self.flight_timer.stop()
            self.stream_label.setText("Stream Off")
            self.drone.streamoff()
            print("Landing successful")
            
            self.flight_end_time = datetime.datetime.now()
            duration = self.flight_end_time - self.flight_start_time
            QMessageBox.information(self, "Drone Status", f"Η πτήση ολοκληρώθηκε!\nΔιάρκεια: {duration}")
            # Process flight video
            self.process_flight_video(duration)
            self.update_history_button()
            
    def process_flight_video(self, duration):
        """Process the flight video using video_process.py."""
        # Supported video formats
        video_formats = [".mp4", ".mov", ".avi"]
        
        # Search for a video file in the flight folder
        video_path = None
        for fmt in video_formats:
            potential_path = os.path.join(self.current_flight_folder, f"flight_video{fmt}")
            if os.path.exists(potential_path):
                video_path = potential_path
                break

        if video_path:
            # Process the video using video_process.py
            try:
                run(video_path, duration)
                self.update_history_button()
            except Exception as e:
                QMessageBox.critical(self, "Processing Error", f"Σφάλμα κατά την επεξεργασία του βίντεο: {e}")
        else:
            # Show warning if no video is found
            QMessageBox.warning(self, "Video Missing", "Δεν βρέθηκε βίντεο πτήσης για επεξεργασία!")

    def update_history_button(self):
        """Enable the history button if runs folder has content."""
        runs_dir = "runs"
        if os.path.exists(runs_dir) and os.listdir(runs_dir):
            self.history_button.setEnabled(True)
        else:
            self.history_button.setEnabled(False)

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

    def view_flight_history(self):
        # Launch report generation app
        self.report_app = DroneReportApp()
        self.report_app.show()
        


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DroneControlApp()
    window.show()
    sys.exit(app.exec())
