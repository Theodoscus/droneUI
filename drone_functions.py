import os
import datetime
import cv2
from djitellopy import Tello
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar
from PyQt6.QtCore import QObject, pyqtSignal
import time
import logging
import math

# ---------------------------------------------------------------------
# DroneController: Handles all direct drone operations.
# ---------------------------------------------------------------------
class DroneController:
    _instance = None  # Class-level variable for the singleton instance

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(DroneController, cls).__new__(cls)
        return cls._instance

    def __init__(self, tello: Tello, flights_folder: str):
        # Run initialization only once
        if hasattr(self, '_initialized'):
            return
        self._initialized = True

        self.tello = tello
        self.flights_folder = flights_folder

        # Connection and recording states.
        self.is_connected = False
        self.frame_read = None
        self.is_recording = False
        self.video_writer = None

        # Flight timing and folder for the current flight.
        self.flight_start_time = None
        self.current_flight_folder = None

        # Video recording parameters.
        self.frame_width = 960
        self.frame_height = 720

        # Flag to indicate whether the drone is flying.
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

            self.tello.streamon()
            time.sleep(2)
            self.is_connected = True

            # Only initialize frame_read if it hasn't been done yet
            if self.frame_read is None:
                print("Initializing frame read...")
                self.tello.send_command_with_return('setfps high')
                self.tello.send_command_with_return('setresolution high')
                self.frame_read = self.tello.get_frame_read()
            
            print("Drone connected successfully.")

        except Exception as e:
            raise Exception(f"Drone connection failed: {e}")


    def disconnect(self):
        """
        Disconnect from the drone by stopping the video stream.
        Also stops the frame reading thread if it exists.
        """
        if self.is_connected:
            try:
                
                
                self.tello.streamoff()
            except Exception as e:
                print("Error turning off drone stream:", e)
            self.is_connected = False
            
    def get_wifi_signal(self):
        """ 
        Retrieves the Wi-Fi signal strength from the drone.
        Returns a string (or numeric value) representing the signal strength.
        """
        try:
            # This method is provided by djitellopy.
            if self.is_flying:
                signal = self.tello.query_wifi_signal_noise_ratio()
                return signal  # could be a number or a string, depending on the SDK version
            else: 
                return "N/A"
        except Exception as e:
            logging.error("Error getting Wi-Fi signal: %s", e)
            return "N/A"


    # ----- Drone State Getters (wrappers) -----
    def get_battery(self):
        """Return the current battery level of the drone."""
        return self.tello.get_battery()

    def get_temperature(self):
        """Return the current temperature reported by the drone."""
        return self.tello.get_temperature()

    def get_height(self):
        """Return the current height of the drone."""
        return self.tello.get_height()

    def get_speed_x(self):
        try:
            vx = self.tello.get_speed_x()
            vy = self.tello.get_speed_y()  # Make sure this method exists in your drone API
            vz = self.tello.get_speed_z()  # Likewise for this method
            total_speed = math.sqrt(vx**2 + vy**2 + vz**2)
            return int(total_speed)
        except Exception as e:
            logging.error("Error calculating total speed: %s", e)
            return 0

    def get_frame(self):
        """
        Retrieve the latest video frame from the drone's camera.
        Returns None if the frame reader is not initialized.
        """
        
            
        if self.frame_read is not None:
            return self.frame_read.frame
        return None

    # ----- New: Continuous Control Method -----
    def send_continuous_control(self, lr, fb, ud, yaw):
        """
        Send a continuous control command by setting velocities.
        lr: Left/right velocity (-100 to 100; negative for left)
        fb: Forward/backward velocity (-100 to 100; positive for forward)
        ud: Up/down velocity (-100 to 100; positive for up)
        yaw: Yaw (rotation) velocity (-100 to 100; positive for clockwise)
        """
        if not (self.is_connected and self.is_flying):
            return
        self.tello.send_rc_control(lr, fb, ud, yaw)

    # ----- Video Recording Methods -----
    def start_recording(self):
        """
        Begin recording the video stream.
        Requires that the drone is connected and a flight folder is set.
        Initializes an OpenCV VideoWriter with the correct parameters.
        """
        if not self.is_connected or self.current_flight_folder is None:
            return
        self.is_recording = True
        output_path = os.path.join(self.current_flight_folder, "flight_video.mp4")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self.video_writer = cv2.VideoWriter(output_path, fourcc, 30.0, (self.frame_width, self.frame_height))
        print(f"Recording started: {output_path}")

    def stop_recording(self):
        """
        Stop recording the video stream.
        Releases the VideoWriter and resets the recording flag.
        """
        if self.is_recording and self.video_writer is not None:
            self.is_recording = False
            self.video_writer.release()
            self.video_writer = None
            print("Recording stopped and VideoWriter released.")

    def record_frame(self, frame):
        """
        Writes a single frame to the video file if recording is active.
        Converts the frame from RGB to BGR (VideoWriter expects BGR) and ensures a minimum interval 
        between frames to prevent duplicate presentation timestamps.
        """
        if self.is_recording and self.video_writer is not None:
            current_time = time.time()
            # Initialize last_write_time if not already done.
            if not hasattr(self, 'last_write_time'):
                self.last_write_time = current_time
            # Desired interval based on the fps used in VideoWriter (30 fps => ~0.0333 sec).
            desired_interval = 1.0 / 30.0  
            # If not enough time has passed, skip writing this frame.
            if current_time - self.last_write_time < desired_interval:
                return
            self.last_write_time = current_time
            # Convert frame from RGB (drone native) to BGR for VideoWriter.
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            try:
                self.video_writer.write(frame_bgr)
            except cv2.error as e:
                logging.error("Error writing frame: %s", e)


    # ----- Flight Operations -----
    def takeoff(self):
        """
        Command the drone to take off.
        Sets up flight timing, creates a flight folder based on the current timestamp,
        starts video recording, and updates the 'is_flying' flag.
        """
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
        """
        Command the drone to land.
        Tries landing up to two times before raising an exception if unsuccessful.
        Also stops video recording and updates the 'is_flying' flag.
        """
        if not self.is_connected:
            raise Exception("Drone not connected")
        if not self.is_flying:
            raise Exception("Drone is already landed")
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

    # ----- Discrete Movement Commands (for non-held triggers) -----

    def flip_left(self):
        """Command the drone to perform a left flip."""
        if not (self.is_connected and self.is_flying):
            print("Cannot flip left: Drone must be connected and flying.")
            return
        self.tello.flip_left()

    def flip_right(self):
        """Command the drone to perform a right flip."""
        if not (self.is_connected and self.is_flying):
            print("Cannot flip right: Drone must be connected and flying.")
            return
        self.tello.flip_right()

    def streamon(self):
        """Start the drone's video stream."""
        self.tello.streamon()
        print("Real drone stream started")

    def streamoff(self):
        """Stop the drone's video stream."""
        self.tello.streamoff()
        print("Real drone stream stopped")

# =============================================================================
# DroneConnectWorker: For asynchronous connection.
# =============================================================================
class DroneConnectWorker(QObject):
    """
    Worker class for connecting to the drone asynchronously.
    Emits signals for success or error so that the UI thread can update accordingly.
    """
    connect_success = pyqtSignal()
    connect_error = pyqtSignal(str)

    def __init__(self, drone_controller: DroneController):
        super().__init__()
        self.drone_controller = drone_controller

    def run(self):
        """
        Attempt to connect to the drone.
        If successful, emit 'connect_success'; otherwise, emit 'connect_error' with the error message.
        """
        try:
            self.drone_controller.connect()
            
            self.connect_success.emit()
        except Exception as e:
            self.connect_error.emit(str(e))


# =============================================================================
# ConnectingDialog: A simple dialog to show while connecting.
# =============================================================================
class ConnectingDialog(QDialog):
    """
    A modal dialog that displays a busy indicator while attempting to connect to the drone.
    This dialog prevents user interaction until the connection attempt completes.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Connecting to Drone")
        # Optionally remove the close button by keeping the existing window flags.
        self.setWindowFlags(self.windowFlags())
        self.setModal(True)

        # Set up a vertical layout for the dialog contents.
        layout = QVBoxLayout()

        # Title and informative labels.
        title_label = QLabel("<h2>Connecting to Tello Drone</h2>")
        info_label = QLabel("Please wait while we establish a connection...")

        # An indeterminate progress bar (busy indicator).
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate mode.
        self.progress_bar.setTextVisible(False)

        # Add widgets to the layout.
        layout.addWidget(title_label)
        layout.addWidget(info_label)
        layout.addWidget(self.progress_bar)

        self.setLayout(layout)