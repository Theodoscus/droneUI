import os
import datetime
import cv2
from djitellopy import Tello
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar
from PyQt6.QtCore import QObject, pyqtSignal
import time

# ---------------------------------------------------------------------
# DroneController: Handles all direct drone operations.
# ---------------------------------------------------------------------
class DroneController:
    """
    Encapsulates all drone-control functionality independent of the UI.
    This class wraps connection, movement, flight operations, and video recording.
    It maintains an internal 'is_flying' flag so that takeoff and landing occur only once.
    """
    def __init__(self, tello: Tello, flights_folder: str):
        # Store the Tello instance and the folder where flight data will be saved.
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

        # Video recording parameters (frame dimensions).
        self.frame_width = 960
        self.frame_height = 720

        # Flag to indicate whether the drone is currently flying.
        self.is_flying = False
        self.count = 1
        

    def connect(self):
        
        
        """
        Connect to the drone and initialize the video stream.
        It validates the response from the Tello, starts video streaming,
        and sets the 'is_connected' flag.
        """
        try:
            
            raw_response = self.tello.connect()
            # In some cases the response might be a tuple or list.
            if isinstance(raw_response, (tuple, list)):
                raw_response = raw_response[0]
            if raw_response is not None:
                # Decode bytes if necessary.
                if isinstance(raw_response, bytes):
                    raw_response = raw_response.decode("utf-8")
                response_str = str(raw_response).strip().strip('"').strip("'")
                # If the response is not recognized as success, raise an exception.
                if response_str not in ["ok", "192.168.10.1"]:
                    raise Exception(response_str)
            # Start the video stream from the drone.
            self.tello.streamon()
            time.sleep(2)
            self.is_connected = True
            if self.count == 1:
                if self.is_connected:
                        self.frame_read = self.tello.get_frame_read()
                else:
                        self.frame_read = None
                
            self.count+=1
            
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
        """Return the current horizontal speed (x-axis) of the drone."""
        return self.tello.get_speed_x()

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
        self.video_writer = cv2.VideoWriter(output_path, fourcc, 20.0, (self.frame_width, self.frame_height))
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
        Write a single frame to the video file if recording is active.
        This method should be called each time a new frame is available.
        """
        if self.is_recording and self.video_writer is not None:
            self.video_writer.write(frame)

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