import sys
import pygame
import cv2
import os
import random
import logging
import datetime
from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QPushButton, QGroupBox, QVBoxLayout, QProgressBar,QHBoxLayout, QMessageBox
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor, QPolygon
from PyQt6.QtCore import QPoint
from video_process import run
from shared import open_drone_control



# # Setup logging
# logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Global exception handler to log uncaught exceptions
def log_uncaught_exceptions(exctype, value, traceback):
    logging.critical("Uncaught exception", exc_info=(exctype, value, traceback))

sys.excepthook = log_uncaught_exceptions

# class VideoThread(QThread):
#     frame_updated = pyqtSignal(QImage)

#     def __init__(self):
#         super().__init__()
#         try:
#             self.capture = cv2.VideoCapture(1)  # Open the default webcam
#             if not self.capture.isOpened():
#                 logging.critical("Failed to open webcam.")
#                 raise Exception("Webcam not accessible.")
#             self.running = True
#         except Exception as e:
#             logging.error(f"Error initializing VideoThread: {e}")

#     def run(self):
#         while self.running:
#             try:
#                 ret, frame = self.capture.read()
#                 if ret:
#                     # Convert frame to RGB and then to QImage
#                     frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
#                     height, width, channel = frame.shape
#                     bytes_per_line = channel * width
#                     qt_image = QImage(frame.data, width, height, bytes_per_line, QImage.Format.Format_RGB888)
#                     self.frame_updated.emit(qt_image)
#                 else:
#                     logging.warning("Failed to read frame from webcam.")
#             except Exception as e:
#                 logging.error(f"Error in VideoThread run: {e}")

#     def stop(self):
#         try:
#             self.running = False
#             self.capture.release()
#             self.quit()
#         except Exception as e:
#             logging.error(f"Error stopping VideoThread: {e}")
            
# Mock class to simulate the behavior of a drone
class MockPTello:
    def __init__(self):
        # Tracks whether the drone is currently flying
        self.is_flying = False
        # Tracks whether the video stream is active
        self.stream_on = False

    def connect(self):
        # Simulates connecting to the drone
        print("Mock: Drone connected")

    

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
        print(self.is_flying)
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

class DroneOperatingPage(QWidget):
    def __init__(self,field_path):
        super().__init__()
        
        self.drone = MockPTello()
        self.drone.connect()
        self.is_flying = False  # Tracks if the drone is flying
        self.flight_duration = 0  # Tracks the flight duration
        self.battery_level = 100  # Battery level of the drone
        self.fly_height = 0  # Height of the drone
        self.button_states = {}  # Track button states to handle single presses
        self.speed = 0  # Speed of the drone
        self.current_flight_folder = None  # Folder to save flight data
        self.field_path = field_path  # Save the field path
        self.flights_folder = os.path.join(self.field_path, "flights")  # Path to flights folder
        os.makedirs(self.flights_folder, exist_ok=True)  # Ensure the flights folder exists
        
        self.flight_timer = QTimer()  # Timer to update flight duration
        self.flight_timer.timeout.connect(self.update_flight_duration)
        
        self.init_ui()
        
        # Timer to update UI statistics
        self.ui_timer = QTimer()
        self.ui_timer.timeout.connect(self.update_ui_stats)
        self.ui_timer.start(2000)  # Update every 2 seconds
        
        # Timer to update joystick overlays
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_joystick_inputs)
        self.timer.timeout.connect(self.setup_controller)
        self.timer.start(20)  # Update every 20ms for smoother inputs

        # Initialize pygame for controller input
        pygame.init()
        pygame.joystick.init()
        self.controller = None
        self.setup_controller()
        
    def init_ui(self):
        try:
            

            # Remove window decorations
            self.setWindowFlags(Qt.WindowType.FramelessWindowHint)

            # Determine screen size and enforce 16:9 aspect ratio
            screen = QApplication.primaryScreen().size()
            screen_width, screen_height = screen.width(), screen.height()
            aspect_ratio_width = 16
            aspect_ratio_height = 9

            # Calculate appropriate dimensions
            max_width = screen_width
            max_height = screen_width * aspect_ratio_height // aspect_ratio_width

            if max_height > screen_height:
                max_height = screen_height
                max_width = screen_height * aspect_ratio_width // aspect_ratio_height

            # Set fixed size based on aspect ratio
            self.setFixedSize(max_width, max_height)

            # Video Stream Placeholder (16:9)
            self.stream_label = QLabel(self)
            self.stream_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.stream_label.setGeometry(0, 0, self.width(), self.height())
            self.stream_label.setScaledContents(True)

            # Emergency Button
            self.emergency_button = QPushButton("EMERGENCY", self)
            self.emergency_button.setGeometry(self.width() // 2 - 100, 10, 200, 50)
            self.emergency_button.setStyleSheet("background-color: red; color: white; font-size: 18px; font-weight: bold;")
            self.emergency_button.clicked.connect(self.emergency_landing)

            # Close Button
            self.close_button = QPushButton("Λειτουργία Παραθύρου", self)
            self.close_button.setStyleSheet("background-color: blue; color: white; font-size: 16px; font-weight: bold;")
            self.close_button.clicked.connect(self.launch_windowed)

            # Adjust size to fit the contents dynamically
            self.close_button.adjustSize()

            # Optionally position the button after adjusting its size
            button_width = self.close_button.width()
            self.close_button.setGeometry(self.width() - button_width - 10, 10, 200, 50)

        

            # Status Information (Signal, Connection)
            self.status_label = QLabel("Signal: Strong | Connection: Stable", self)
            self.status_label.setStyleSheet(
                "background-color: rgba(0, 0, 0, 0.5); color: white; font-size: 18px; padding: 10px;"
            )
            self.status_label.setGeometry(10, 10, 400, 50)

            # Controller Status Box
            controller_status_box = QGroupBox("Controller Status", self)
            controller_layout = QVBoxLayout()

            self.controller_status_label = QLabel("No Controller Connected")
            self.controller_status_label.setStyleSheet("color: red; font-size: 14px; font-weight: bold;")
            controller_layout.addWidget(self.controller_status_label)

            controller_status_box.setLayout(controller_layout)
            
            controller_status_box.setGeometry(10, 70, 400, 50)

            

            # Battery Level Indicator
            battery_box = QGroupBox("Battery", self)
            battery_layout = QVBoxLayout()
            battery_box.setGeometry(10, 130, 400, 50)  # Adjust x, y, width, and height

            self.battery_bar = QProgressBar()
            self.battery_bar.setValue(self.battery_level)
            self.battery_bar.setStyleSheet(
                "QProgressBar::chunk { background-color: green; }"
            )

            battery_layout.addWidget(self.battery_bar)
            battery_box.setLayout(battery_layout)
            
            # Drone information group box
            info_box = QGroupBox("Drone Info",self)
            info_layout = QVBoxLayout()
            info_box.setGeometry(10, 190, 400, 250)  # Adjust x, y, width, and height
            
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
            self.joystick_left.setGeometry(50, self.height() - 300, 200, 200)
            self.joystick_right = CircularJoystick(self, "Right Joystick")
            self.joystick_right.setGeometry(self.width() - 250, self.height() - 300, 200, 200)

            # Drone State Label
            self.drone_state_label = QLabel("Landed", self)
            self.drone_state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.drone_state_label.setStyleSheet("background-color: rgba(200, 200, 200, 0.7); color: black; font-size: 18px; font-weight: bold; padding: 5px;")

            # Place the label where it was originally intended
            self.drone_state_label.move(self.width() // 2 - 50, self.height() - 100)  # Example fixed position
            self.drone_state_label.adjustSize()  # Adjust size to fit the contents dynamically

            # Start the video thread
            # self.video_thread = VideoThread()
            # self.video_thread.frame_updated.connect(self.update_video_frame)
            # self.video_thread.start()
        except Exception as e:
            logging.error(f"Error initializing DroneOperatingPage: {e}")

    def launch_windowed(self):
        """Launch the fullscreen drone operation page."""
        # Stop any active timers
        self.flight_timer.stop()
        self.ui_timer.stop()
        self.timer.stop()
        
        # Stop the video thread
        # if hasattr(self, 'video_thread') and self.video_thread.isRunning():
        #     self.video_thread.stop()
        
        # Quit pygame to release resources
        pygame.joystick.quit()
        pygame.quit()
        
        self.fullscreen_window = open_drone_control(self.field_path)
        self.fullscreen_window.show()
        self.close()  # Close the current window
    
    # Update the flight duration
    def update_flight_duration(self):
        self.flight_duration += 1
        self.info_labels["Flight Duration"].setText(f"{self.flight_duration} sec")

    # Update UI stats dynamically
    def update_ui_stats(self):
        self.battery_level = max(0, self.battery_level - random.randint(0, 2))  # Simulate battery drain
        self.fly_height = random.randint(0, 500) if self.drone.is_flying else 0
        self.speed = random.uniform(0, 10) if self.drone.is_flying else 0
        
        # Update battery progress bar
        self.battery_bar.setValue(self.battery_level)

        # Check for low battery and display notification
        # if self.battery_level < 20:
        #     self.notification_label.setText("Warning: Battery level is critically low!")
        #     self.notification_label.setVisible(True)
        # else:
        #     self.notification_label.setVisible(False)

        # Update other stats
        self.info_labels["Height"].setText(f"{self.fly_height} cm")
        self.info_labels["Speed"].setText(f"{self.speed:.2f} cm/s")
        
    
    def take_off(self):
        # Check if the drone is already flying
        if not self.drone.is_flying:
            self.drone_state_label.setText("Taking Off...")
            self.drone_state_label.adjustSize()  # Resize the label dynamically
            self.close_button.setEnabled(False)
            self.close_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: lightgray; color: gray;")
            
            # Delay the following actions by 5 seconds
            QTimer.singleShot(5000, lambda: self._perform_take_off())

    def _perform_take_off(self):
        
        """Perform the actual takeoff actions after the delay."""
        self.drone_state_label.setText("On Air.")
        self.drone_state_label.adjustSize()  # Resize the label dynamically
        self.drone.is_flying = True
        
        self.flight_timer.start(1000)
        self.flight_start_time = datetime.datetime.now()

        # Create flight folder
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.current_flight_folder = os.path.join(self.flights_folder, f"flight_{timestamp}")
        os.makedirs(self.current_flight_folder, exist_ok=True)

        # Start video stream
        self.stream_label.setText("Stream On")
        #self.drone.streamon()
        print("Take off successful")

    def land(self):
        if self.drone.is_flying:
            self.drone_state_label.setText("Landing...")
            self.drone_state_label.adjustSize()  # Resize the label dynamically
            self.close_button.setEnabled(True)
            self.close_button.setStyleSheet("font-size: 16px; padding: 10px; background-color: #007BFF; color: white;")
            # Delay the following actions by 5 seconds
            QTimer.singleShot(5000, lambda: self._perform_landing())

    def _perform_landing(self):
        print("check check")
        """Perform the actual landing actions after the delay."""
        self.drone_state_label.setText("Landed.")
        self.drone_state_label.adjustSize()  # Resize the label dynamically
        self.drone.is_flying = False
        self.flight_timer.stop()
        self.stream_label.setText("Stream Off")
        #self.drone.streamoff()
        print("Landing successful")

        # Calculate flight duration
        self.flight_end_time = datetime.datetime.now()
        duration = self.flight_end_time - self.flight_start_time

        # Display flight completion information
        QMessageBox.information(self, "Drone Status", f"Η πτήση ολοκληρώθηκε!\nΔιάρκεια: {duration}")

        # Process flight video
        self.process_flight_video(duration)

        # Update history button (if implemented)
        # self.update_history_button()

      
    # Flight video processing by passing it through the run() method        
    def process_flight_video(self, duration):
        """Process the flight video using video_process.py and save results in the `runs` folder."""
        if not self.current_flight_folder:
            QMessageBox.warning(self, "Error", "Flight folder not set. Cannot process video.")
            return

        # Ensure the `runs` folder exists within the field path
        runs_folder = os.path.join(self.field_path, "runs")
        os.makedirs(runs_folder, exist_ok=True)

        # Generate a run folder based on the current timestamp
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        run_folder = os.path.join(runs_folder, f"run_{timestamp}")
        os.makedirs(run_folder, exist_ok=True)

        # Supported video formats
        video_formats = [".mp4", ".mov", ".avi"]

        # Search for a video file in the current flight folder
        video_path = None
        for fmt in video_formats:
            potential_path = os.path.join(self.current_flight_folder, f"flight_video{fmt}")
            if os.path.exists(potential_path):
                video_path = potential_path
                break

        if video_path:
            try:
                # Call the `run` function with the correct paths
                run(video_path, duration, self.field_path)

                QMessageBox.information(
                    self,
                    "Video Processing",
                    f"Η επεξεργασία του βίντεο ολοκληρώθηκε επιτυχώς!\nΑποτελέσματα αποθηκεύτηκαν στον φάκελο:\n{run_folder}"
                )
            except Exception as e:
                QMessageBox.critical(self, "Processing Error", f"Σφάλμα κατά την επεξεργασία του βίντεο: {e}")
        else:
            QMessageBox.warning(self, "Video Missing", "Δεν βρέθηκε βίντεο πτήσης για επεξεργασία!")

    
    def update_video_frame(self, frame):
        """Update the QLabel with the new video frame."""
        try:
            pixmap = QPixmap.fromImage(frame)
            self.stream_label.setPixmap(pixmap)
        except Exception as e:
            logging.error(f"Error updating video frame: {e}")

    def setup_controller(self):
        """Initialize the Xbox controller if connected."""
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
        """Poll joystick inputs and update the overlays."""
        try:
            if self.controller:
                pygame.event.pump()

                # Handle joystick axes
                left_x = self.controller.get_axis(0)  # Left stick horizontal
                left_y = self.controller.get_axis(1)  # Left stick vertical
                right_x = self.controller.get_axis(2)  # Right stick horizontal
                right_y = self.controller.get_axis(3)  # Right stick vertical

                # Smooth the inputs
                left_x = self.smooth_input(left_x)
                left_y = self.smooth_input(left_y)
                right_x = self.smooth_input(right_x)
                right_y = self.smooth_input(right_y)

                # Update joysticks
                self.joystick_left.update_position(left_x, -left_y)  # Invert vertical axis
                self.joystick_right.update_position(right_x, -right_y)  # Invert vertical axis

                # Map joystick inputs to drone actions
                self.map_joystick_to_drone(left_x, left_y, right_x, right_y)

                # Handle button presses
                for button_id, action in [(0, self.take_off), (1, self.land)]:  # Button 0: A, Button 1: B
                    button_pressed = self.controller.get_button(button_id)
                    if button_pressed and not self.button_states.get(button_id, False):
                        # Trigger action on initial press
                        action()
                        self.button_states[button_id] = True  # Mark button as pressed
                    elif not button_pressed:
                        self.button_states[button_id] = False  # Reset button state when released
        except Exception as e:
            logging.error(f"Error updating joystick inputs: {e}")

    def map_joystick_to_drone(self, left_x, left_y, right_x, right_y):
        """Map joystick inputs to drone movements."""
        try:
            
            if left_y < -0.5:
                self.drone.move_forward()
        
            elif left_y > 0.5:
                self.drone.move_backward()

            if left_x < -0.5:
                self.drone.move_left()
            elif left_x > 0.5:
                self.drone.move_right()

            if right_y < -0.5:
                self.drone.move_up()
            elif right_y > 0.5:
                self.drone.move_down()

            if right_x < -0.5:
                self.drone.rotate_left()
            elif right_x > 0.5:
                self.drone.rotate_right()
        except Exception as e:
            logging.error(f"Error mapping joystick inputs to drone: {e}")

    def smooth_input(self, value, threshold=0.1):
        """Apply deadzone and smoothing to joystick input."""
        if abs(value) < threshold:
            return 0.0
        return round(value, 2)

    

    

    def emergency_landing(self):
        """Handle emergency landing logic."""
        logging.info("Emergency landing initiated!")
        self.update_drone_state("Emergency Landing")

    def update_drone_state(self, state):
        """Update the drone state label."""
        self.drone_state_label.setText(state)
        self.drone_state_label.adjustSize()
        self.drone_state_label.move(self.width() // 2 - self.drone_state_label.width() // 2, self.height() - 100)

    def close_application(self):
        """Close the application safely."""
        logging.info("Application closing.")
        try:
            self.video_thread.stop()
        except Exception as e:
            logging.error(f"Error stopping video thread during close: {e}")
        self.close()

class DirectionalJoystick(QWidget):
    def __init__(self, parent, label):
        super().__init__(parent)
        self.setFixedSize(200, 200)
        self.label = label
        self.x_pos = 0.0  # Joystick horizontal axis (-1 to 1)
        self.y_pos = 0.0  # Joystick vertical axis (-1 to 1)

    def paintEvent(self, event):
        """Draw joystick position, background, and directional arrows."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw circular joystick area
        painter.setBrush(QColor(50, 50, 50, 150))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, 200, 200)

        # Draw directional arrows
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

        # Draw joystick position
        joystick_x = int(100 + self.x_pos * 75)  # Map -1 to 1 -> position
        joystick_y = int(100 - self.y_pos * 75)  # Map -1 to 1 -> position
        painter.setBrush(QColor(200, 0, 0, 200))
        painter.drawEllipse(joystick_x - 10, joystick_y - 10, 20, 20)

    def update_position(self, x, y):
        """Update joystick position (-1 to 1)."""
        self.x_pos = x
        self.y_pos = y
        self.update()


class CircularJoystick(QWidget):
    def __init__(self, parent, label):
        super().__init__(parent)
        self.setFixedSize(200, 200)
        self.label = label
        self.x_pos = 0.0  # Joystick horizontal axis (-1 to 1)
        self.y_pos = 0.0  # Joystick vertical axis (-1 to 1)

    def paintEvent(self, event):
        """Draw joystick position and concentric circles."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw concentric circles
        for radius in range(30, 121, 30):
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QColor(255, 255, 255, 100))
            painter.drawEllipse(100 - radius, 100 - radius, radius * 2, radius * 2)

        # Draw joystick position
        joystick_x = int(100 + self.x_pos * 75)  # Map -1 to 1 -> position
        joystick_y = int(100 - self.y_pos * 75)  # Map -1 to 1 -> position
        painter.setBrush(QColor(200, 0, 0, 200))
        painter.drawEllipse(joystick_x - 10, joystick_y - 10, 20, 20)

    def update_position(self, x, y):
        """Update joystick position (-1 to 1)."""
        self.x_pos = x
        self.y_pos = y
        self.update()




# if __name__ == "__main__":
#      try:
#          app = QApplication(sys.argv)
#          window = DroneOperatingPage()
#          window.show()
#          sys.exit(app.exec())
#      except Exception as e:
#          logging.critical(f"Unhandled exception in main: {e}")
