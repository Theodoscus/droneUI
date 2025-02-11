# dronefunctions.py
import os
import datetime
import cv2
from djitellopy import Tello
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar
from PyQt6.QtCore import QObject, pyqtSignal

# ---------------------------------------------------------------------
# DroneController: Handles all direct drone operations.
# ---------------------------------------------------------------------
class DroneController:
    """
    Encapsulates all drone-control functionality independent of the UI.
    This class wraps connection, movement, flight operations, and video recording.
    It maintains an internal 'is_flying' flag (and retries landing once) so that
    takeoff and landing occur only once.
    """
    def __init__(self, tello: Tello, flights_folder: str):
        self.tello = tello
        self.flights_folder = flights_folder
        self.is_connected = False
        self.frame_read = None
        self.is_recording = False
        self.video_writer = None
        self.flight_start_time = None
        self.current_flight_folder = None
        # Video recording parameters.
        self.frame_width = 960
        self.frame_height = 720
        # Flag to indicate if the drone is currently flying.
        self.is_flying = False

    def connect(self):
        try:
            raw_response = self.tello.connect()
            if isinstance(raw_response, (tuple, list)):
                raw_response = raw_response[0]
            if raw_response is not None:
                if isinstance(raw_response, bytes):
                    raw_response = raw_response.decode("utf-8")
                response_str = str(raw_response).strip().strip('"').strip("'")
                if response_str not in ["ok", "192.168.10.1"]:
                    raise Exception(response_str)
            # Start video streaming.
            self.tello.streamon()
            self.frame_read = self.tello.get_frame_read()
            self.is_connected = True
        except Exception as e:
            raise Exception(f"Drone connection failed: {e}")

    def disconnect(self):
        if self.is_connected:
            try:
                self.tello.streamoff()
                if self.frame_read:
                    self.frame_read.stop()
            except Exception as e:
                print("Error turning off drone stream:", e)
            self.is_connected = False

    # ----- Drone State Getters (wrappers) -----
    def get_battery(self):
        return self.tello.get_battery()

    def get_temperature(self):
        return self.tello.get_temperature()

    def get_height(self):
        return self.tello.get_height()

    def get_speed_x(self):
        return self.tello.get_speed_x()

    def get_frame(self):
        if self.frame_read is not None:
            return self.frame_read.frame
        return None

    # ----- Video Recording Methods -----
    def start_recording(self):
        if not self.is_connected or self.current_flight_folder is None:
            return
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
            print("Recording stopped and VideoWriter released.")

    def record_frame(self, frame):
        if self.is_recording and self.video_writer is not None:
            self.video_writer.write(frame)

    # ----- Flight Operations -----
    def takeoff(self):
        if not self.is_connected:
            raise Exception("Drone not connected")
        if self.is_flying:
            raise Exception("Drone is already in flight")
        self.tello.takeoff()
        self.flight_start_time = datetime.datetime.now()
        timestamp = self.flight_start_time.strftime("%Y%m%d_%H%M%S")
        self.current_flight_folder = os.path.join(self.flights_folder, f"flight_{timestamp}")
        os.makedirs(self.current_flight_folder, exist_ok=True)
        self.start_recording()
        self.is_flying = True

    def land(self):
        if not self.is_connected:
            raise Exception("Drone not connected")
        if not self.is_flying:
            raise Exception("Drone is already landed")
        # Try landing up to two times.
        for attempt in range(2):
            try:
                self.tello.land()
                self.stop_recording()
                self.is_flying = False
                return 
            except Exception as e:
                print(f"Landing attempt {attempt + 1} failed: {e}")
                if attempt == 0:
                    import time
                    time.sleep(1)
                else:
                    raise Exception("Landing failed on both attempts.")

    # ----- Movement Commands -----
    def move_forward(self, distance=30):
        if self.is_connected:
            self.tello.move_forward(distance)

    def move_backward(self, distance=30):
        if self.is_connected:
            self.tello.move_back(distance)

    def move_left(self, distance=30):
        if self.is_connected:
            self.tello.move_left(distance)

    def move_right(self, distance=30):
        if self.is_connected:
            self.tello.move_right(distance)

    def move_up(self, distance=30):
        if self.is_connected:
            self.tello.move_up(distance)

    def move_down(self, distance=30):
        if self.is_connected:
            self.tello.move_down(distance)

    def rotate_left(self, angle=30):
        if self.is_connected:
            self.tello.rotate_counter_clockwise(angle)

    def rotate_right(self, angle=30):
        if self.is_connected:
            self.tello.rotate_clockwise(angle)

    def flip_left(self):
        if self.is_connected:
            self.tello.flip_left()

    def flip_right(self):
        if self.is_connected:
            self.tello.flip_right()

    def streamon(self):
        self.tello.streamon()
        print("Real drone stream started")

    def streamoff(self):
        self.tello.streamoff()
        print("Real drone stream stopped")
# =============================================================================
# DroneConnectWorker: For asynchronous connection.
# =============================================================================
class DroneConnectWorker(QObject):
    connect_success = pyqtSignal()
    connect_error = pyqtSignal(str)

    def __init__(self, drone_controller: DroneController):
        super().__init__()
        self.drone_controller = drone_controller

    def run(self):
        try:
            self.drone_controller.connect()
            self.connect_success.emit()
        except Exception as e:
            self.connect_error.emit(str(e))


# =============================================================================
# ConnectingDialog: A simple dialog to show while connecting.
# =============================================================================
class ConnectingDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Connecting to Drone")
        self.setWindowFlags(self.windowFlags())  # Remove close button.
        self.setModal(True)
        layout = QVBoxLayout()
        title_label = QLabel("<h2>Connecting to Tello Drone</h2>")
        info_label = QLabel("Please wait while we establish a connection...")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate (busy) mode.
        self.progress_bar.setTextVisible(False)
        layout.addWidget(title_label)
        layout.addWidget(info_label)
        layout.addWidget(self.progress_bar)
        self.setLayout(layout)
