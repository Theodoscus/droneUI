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


# Mock class to simulate the behavior of a drone
class MockTello:
    def __init__(self):
        # Tracks whether the drone is currently flying
        self.is_flying = False
        # Tracks whether the video stream is active
        self.stream_on = False

    def connect(self):
        # Simulates connecting to the drone
        print("Mock: Drone connected")

    def takeoff(self):
        # Simulates the takeoff process of the drone
        if self.is_flying:
            print("Mock: Already flying!")
        else:
            print("Mock: Taking off...")
            self.is_flying = True  # Updates the state to flying

    def land(self):
        # Simulates the landing process of the drone
        if not self.is_flying:
            print("Mock: Already landed!")
        else:
            print("Mock: Landing...")
            self.is_flying = False  # Updates the state to landed

    def streamon(self):
        # Simulates starting the video stream from the drone
        self.stream_on = True
        print("Mock: Video stream started")

    def streamoff(self):
        # Simulates stopping the video stream from the drone
        self.stream_on = False
        print("Mock: Video stream stopped")

    def end(self):
        # Simulates disconnecting from the drone
        print("Mock: Drone disconnected")
        
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

# Main class for the Drone Control Application
class DroneControlApp(QMainWindow):
    def __init__(self, field_path):
        super().__init__()
        self.setWindowTitle("Drone Control")  # Set the window title
        #self.setWindowState(Qt.WindowState.WindowFullScreen)

        self.setGeometry(100,100,1200,800)
        self.control_buttons = {}  # Dictionary to store control buttons
        # self.setWindowFlags(Qt.WindowType.FramelessWindowHint)

        # Store the field path
        self.field_path = field_path
        
        # Ensure the `flights` folder exists within the field path
        self.flights_folder = os.path.join(self.field_path, "flights")
        os.makedirs(self.flights_folder, exist_ok=True)
        
        # Initialize the Mock Drone
        self.drone = MockTello()
        self.drone.connect()
        
        self.drone.is_flying = False  # Tracks if the drone is flying
        self.flight_duration = 0  # Tracks the flight duration
        self.battery_level = 100  # Battery level of the drone
        self.fly_height = 0  # Height of the drone
        self.speed = 0  # Speed of the drone
        self.current_flight_folder = None  # Folder to save flight data
        self.flight_timer = QTimer()  # Timer to update flight duration
        self.flight_timer.timeout.connect(self.update_flight_duration) 
        
        

        # Initialize the User Interface
        self.init_ui()
        
        # Center the window on the screen
        # self.center_window()

        # Timer to update UI statistics
        self.ui_timer = QTimer()
        self.ui_timer.timeout.connect(self.update_ui_stats)
        self.ui_timer.start(2000)  # Update every 2 seconds

        # Initialize Xbox Controller
        pygame.init()
        pygame.joystick.init()
        self.controller = None
        self.update_controller_status()

        # Timer to poll Xbox controller input
        self.controller_timer = QTimer()
        self.controller_timer.timeout.connect(self.poll_controller_input)
        self.controller_timer.start(20)  # Poll every 50ms

        # Key mapping for keyboard controls
        self.key_pressed_mapping = {
            Qt.Key.Key_W: self.drone.move_forward,
            Qt.Key.Key_S: self.drone.move_backward,
            Qt.Key.Key_A: self.drone.move_left,
            Qt.Key.Key_D: self.drone.move_right,
            Qt.Key.Key_Q: self.drone.flip_left,
            Qt.Key.Key_E: self.drone.flip_right,
            Qt.Key.Key_Return: self.take_off,  # Takeoff and trigger related action
            Qt.Key.Key_P: self.land,         # Land and trigger related action
            Qt.Key.Key_Up: self.drone.move_up,
            Qt.Key.Key_Down: self.drone.move_down,
            Qt.Key.Key_Left: self.drone.rotate_left,
            Qt.Key.Key_Right: self.drone.rotate_right,
        }

    


    def init_ui(self):
        # Main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)

        # Connection status label
        self.connection_status = QLabel("CONNECTED")
        self.connection_status.setStyleSheet(
            "background-color: green; color: white; font-size: 18px; font-weight: bold; border: 2px solid #555;"
        )
        self.connection_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.connection_status.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        main_layout.addWidget(self.connection_status)

        # Notification label
        self.notification_label = QLabel("")
        self.notification_label.setStyleSheet("color: red; font-size: 16px; font-weight: bold;")
        self.notification_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.notification_label.setVisible(False)  # Initially hidden
        main_layout.addWidget(self.notification_label)

        # Content layout with left panel and stream label
        content_layout = QHBoxLayout()
        main_layout.addLayout(content_layout)

        # Left panel layout for drone stats and controls
        left_panel = QVBoxLayout()

        # Battery Group Box
        battery_box = QGroupBox("Battery")
        battery_layout = QVBoxLayout()
        self.battery_bar = QProgressBar()
        self.battery_bar.setValue(self.battery_level)
        self.battery_bar.setStyleSheet("QProgressBar::chunk { background-color: green; }")
        self.battery_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        battery_layout.addWidget(self.battery_bar)
        battery_box.setLayout(battery_layout)
        battery_box.setFixedHeight(60)  # Fix the height of the battery box
        left_panel.addWidget(battery_box)

        # Controller Status Box
        controller_status_box = QGroupBox("Controller Status")
        controller_layout = QVBoxLayout()
        self.controller_status_label = QLabel("No Controller Connected")
        self.controller_status_label.setStyleSheet("color: red; font-size: 14px; font-weight: bold;")
        controller_layout.addWidget(self.controller_status_label)
        controller_status_box.setLayout(controller_layout)
        controller_status_box.setFixedHeight(60)  # Fix the height of the controller status box
        left_panel.addWidget(controller_status_box)

        # Drone information group box
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
        info_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)  # Info box height adjusts dynamically
        left_panel.addWidget(info_box, stretch=1)  # Stretch ensures the info box grows to fill remaining space

        # Add the left panel to the content layout
        left_panel_widget = QWidget()
        left_panel_widget.setLayout(left_panel)
        left_panel_widget.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        left_panel_widget.setMaximumWidth(300)  # Limit the maximum width of the left panel
        content_layout.addWidget(left_panel_widget, stretch=1)  # 1/4 width

        # Center panel for live stream
        self.stream_label = QLabel("Drone Stream Placeholder")
        self.stream_label.setStyleSheet("background-color: #000; color: white; font-size: 14px; border: 1px solid #555;")
        self.stream_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stream_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        content_layout.addWidget(self.stream_label, stretch=3)  # 3/4 width

        # Footer with controls and buttons
        controls_layout = QVBoxLayout()

        # Add control buttons
        control_buttons = [
            [("Q", "Flip Left"), ("W", "Forward"), ("E", "Flip Right"), ("R", "Flip Forward")],
            [("A", "Left"), ("S", "Backward"), ("D", "Right"), ("F", "Flip Back")],
            [("Enter", "Take Off", "green"), ("Space", "Land", "red")],
            [("Up Arrow", "Up"), ("Down Arrow", "Down"), ("Left Arrow", "Rotate Left"), ("Right Arrow", "Rotate Right")],
        ]
        for row in control_buttons:
            row_layout = QHBoxLayout()
            for button in row:
                if len(button) == 3:
                    btn = self.create_control_button(button[0], button[1], button[2])
                else:
                    btn = self.create_control_button(button[0], button[1])
                row_layout.addWidget(btn)
            controls_layout.addLayout(row_layout)

        main_layout.addLayout(controls_layout)

        # Footer buttons
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




            
    def debug_active_threads(self):
            print("Active threads:")
            for thread in threading.enumerate():
                print(thread.name)

    def launch_fullscreen(self):
            """Launch the fullscreen drone operation page."""
            # Stop any active timers
            self.flight_timer.stop()
            self.ui_timer.stop()
            self.controller_timer.stop()
            
            # Quit pygame to release resources
            pygame.joystick.quit()
            pygame.quit()
            
            self.fullscreen_window = open_full_screen(self.field_path)
            self.fullscreen_window.show()
            self.close()  # Close the current window     
            
            
    def center_window(self):
            """Centers the window on the screen."""
            # Ensure the window is fully initialized and has its size calculated
            self.show()  # Make sure the window is rendered before positioning
            self.updateGeometry()  # Update the window's geometry

            # Get the available geometry of the primary screen
            screen_geometry = QApplication.primaryScreen().availableGeometry()

            # Calculate the center position
            center_x = screen_geometry.x() + (screen_geometry.width() - self.width()) // 2
            center_y = screen_geometry.y() + (screen_geometry.height() - self.height()) // 2

            # Move the window to the calculated position
            self.move(center_x, center_y)





    

    



    # Update the controller status and enable/disable controls accordingly
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
            
    # Enable or disable all control buttons
    def set_controls_enabled(self, enabled):
        # Disable or enable all control buttons
        for button in self.control_buttons.values():
            button.setEnabled(enabled)

        # Toggle keyboard control
        self.keyboard_control_enabled = enabled


        
    # Poll input from the Xbox controller
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

    # Handle button press events from the Xbox controller
    def handle_button_press(self, button):
        """Map controller buttons to drone actions."""
        if button == 0:  # Example: Button A
            print("here")
            self.take_off()
        elif button == 1:  # Example: Button B
            self.land()
        elif button == 2:  # Example: Button X
            self.drone.flip_left()
        elif button == 3:  # Example: Button Y
            self.drone.flip_right()

    # Handle joystick axis motion from the Xbox controller
    def handle_axis_motion(self, axis, value):
        """Map joystick axes to drone movement."""
        if axis == 0:  # Left joystick horizontal
            if value < -0.5:
                self.drone.move_left()
            elif value > 0.5:
                self.drone.move_right()
        elif axis == 1:  # Left joystick vertical
            if value < -0.5:
                self.drone.move_forward()
            elif value > 0.5:
                self.drone.move_backward()
        elif axis == 2:  # Right joystick horizontal
            if value < -0.5:
                self.drone.rotate_left()
            elif value > 0.5:
                self.drone.rotate_right()
        elif axis == 3:  # Right joystick vertical
            if value < -0.5:
                self.drone.move_up()
            elif value > 0.5:
                self.drone.move_down()


    # Dynamically create a button for control and map it to an action
    def create_control_button(self, key, action, color=None):
        button = QPushButton(f"{key}\n({action})")
        if color:
            button.setStyleSheet(f"background-color: {color}; color: white; font-weight: bold;")
        button.clicked.connect(self.create_button_handler(action))
        self.control_buttons[action] = button  # Store button in the dictionary
        return button

    # Map button actions to their corresponding methods
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

    # Handle keyboard input events
    def keyPressEvent(self, event: QKeyEvent):
        if not self.keyboard_control_enabled:
            return  # Ignore keyboard input if disabled
        if event.key() in self.key_pressed_mapping:
            self.key_pressed_mapping[event.key()]()

    # Update the flight duration
    def update_flight_duration(self):
        self.flight_duration += 1
        self.info_labels["Flight Duration"].setText(f"{self.flight_duration} sec")

    # Update UI stats dynamically
    def update_ui_stats(self):
        self.battery_level = max(0, self.battery_level - random.randint(0, 2))  # Simulate battery drain
        self.fly_height = random.randint(0, 500) if self.drone.is_flying else 0
        self.speed = random.uniform(0, 10) if self.drone.is_flying else 0
        # self.debug_active_threads()
        # Update battery progress bar
        self.battery_bar.setValue(self.battery_level)

        # Check for low battery and display notification
        if self.battery_level < 20:
            self.notification_label.setText("Warning: Battery level is critically low!")
            self.notification_label.setVisible(True)
        else:
            self.notification_label.setVisible(False)

        # Update other stats
        self.info_labels["Height"].setText(f"{self.fly_height} cm")
        self.info_labels["Speed"].setText(f"{self.speed:.2f} cm/s")

    # Take off action for the drone
    def take_off(self):
        self.history_button.setEnabled(False)
        self.home_button.setEnabled(False)
        self.fullscreen_button.setEnabled(False)
        self.home_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: lightgray; color: gray;")
        self.fullscreen_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: lightgray; color: gray;")
        
        if not self.drone.is_flying:
            self.drone.is_flying = True
            
            self.flight_timer.start(1000)
            self.flight_start_time = datetime.datetime.now()
            # Create flight folder
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self.current_flight_folder = os.path.join(self.flights_folder, f"flight_{timestamp}")
            os.makedirs(self.current_flight_folder, exist_ok=True)

            print(f"Flight folder created: {self.current_flight_folder}")

            # Start video stream
            self.stream_label.setText("Stream On")
            self.drone.streamon()
            print("Take off successful")

    # Land action for the drone
    def land(self):
        if self.drone.is_flying:
            self.drone.is_flying = False
            self.flight_timer.stop()
            self.stream_label.setText("Stream Off")
            self.drone.streamoff()
            self.home_button.setEnabled(True)  # Re-enable the home button
            self.fullscreen_button.setEnabled(True)
            self.home_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: #007BFF; color: white;")
            self.fullscreen_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: #007BFF; color: white;")
            print("Landing successful")
            
            self.flight_end_time = datetime.datetime.now()
            duration = self.flight_end_time - self.flight_start_time
            QMessageBox.information(self, "Flight Completed", f"Flight duration: {duration}")

            print(f"Flight data saved in: {self.current_flight_folder}")
            # Process flight video
            self.process_flight_video(duration)
            self.update_history_button()
            
      
    def process_flight_video(self, duration):
        """Process the flight video using video_process.py."""
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
                from video_process import run
                run(video_path, duration, self.field_path)  # Pass the field path to the run function
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

    def go_to_homepage(self):
        # Stop any active timers
        self.flight_timer.stop()
        self.ui_timer.stop()
        self.controller_timer.stop()
        
        self.home_page = open_homepage()
        self.home_page.show()
        self.close()
   
    def view_flight_history(self):
        # Launch the DroneReportApp with the current field path
        self.report_app = DroneReportApp(self.field_path)
        self.report_app.show()

        


# if __name__ == "__main__":
#     app = QApplication(sys.argv)
#     window = DroneControlApp()
#     window.show()
#     sys.exit(app.exec())
