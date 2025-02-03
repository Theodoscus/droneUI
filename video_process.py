import os
import sys
import cv2
import sqlite3
import pandas as pd
from datetime import datetime
from time import time, strftime, gmtime
import logging
from typing import Tuple

from PyQt6.QtWidgets import QApplication, QDialog, QVBoxLayout, QLabel, QProgressBar
from PyQt6.QtCore import Qt

# YOLO import
from ultralytics import YOLO

# Local import for the report application
from report_gen import DroneReportApp

# ------------------------------------------------------------
# Global Constants and Configuration
# ------------------------------------------------------------

BATCH_SIZE = 4  # Number of frames processed per batch

# Configure logging for the module
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

# ------------------------------------------------------------
# YOLO Model Initialization Functions
# ------------------------------------------------------------

def initialize_model(model_path: str) -> YOLO:
    """
    Loads a YOLO model from the specified .pt file.

    Args:
        model_path (str): Path to the YOLO model file.

    Returns:
        YOLO: The loaded YOLO model instance.
    """
    logging.info("Loading YOLO model from: %s", model_path)
    try:
        model = YOLO(model_path)
        logging.info("Model loaded successfully.")
        return model
    except Exception as e:
        raise RuntimeError(f"Error initializing YOLO model: {e}")

def track_and_detect_batch(model: YOLO, frames: list) -> list:
    """
    Performs YOLO tracking on a batch of video frames.

    Args:
        model (YOLO): The YOLO model instance.
        frames (list): A list of video frames (NumPy arrays).

    Returns:
        list: A list of detection/tracking results for each frame.
    """
    try:
        return model.track(
            source=frames,
            persist=True,
            imgsz=1280,
            conf=0.25,
            augment=True,
            agnostic_nms=True,
            batch=-1
        )
    except Exception as e:
        raise RuntimeError(f"Error during YOLO track/detect batch: {e}")

# ------------------------------------------------------------
# Folder and Database Setup Functions
# ------------------------------------------------------------

def create_output_folder(base_folder: str) -> str:
    """
    Creates a unique run folder (named with a timestamp) within the base folder.

    Args:
        base_folder (str): The parent directory for run folders.

    Returns:
        str: The full path of the newly created run folder.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_folder = os.path.join(base_folder, f"run_{timestamp}")
    os.makedirs(run_folder, exist_ok=True)
    return run_folder

def initialize_database(db_path: str):
    """
    Initializes an SQLite database by creating (or opening) the specified file and ensuring
    that the 'flight_results' table exists.

    Args:
        db_path (str): The path to the SQLite database file.

    Returns:
        tuple: A tuple (conn, cursor) with the database connection and cursor.
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS flight_results (
                Frame INTEGER,
                ID INTEGER,
                Class TEXT,
                BBox TEXT,
                Confidence REAL,
                FlightDuration TEXT
            )
        """)
        conn.commit()
        return conn, cursor
    except sqlite3.Error as e:
        raise RuntimeError(f"Database initialization error at {db_path}: {e}")

# ------------------------------------------------------------
# Data Saving and Frame Processing Functions
# ------------------------------------------------------------

def save_tracking_data_to_db(cursor, tracking_data: list, duration: str) -> None:
    """
    Saves a batch of tracking data into the 'flight_results' table in the database.

    Args:
        cursor: SQLite cursor used for executing queries.
        tracking_data (list): A list of tuples, each containing (frame, track_id, class_name, bbox_str, conf).
        duration (str): The flight duration string (e.g., '00:05:12').
    """
    if not tracking_data:
        return

    try:
        for frame, track_id, class_name, bbox_str, conf in tracking_data:
            cursor.execute("""
                INSERT INTO flight_results (Frame, ID, Class, BBox, Confidence, FlightDuration)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (frame, track_id, class_name, bbox_str, round(float(conf), 4), str(duration)))
    except sqlite3.Error as e:
        raise RuntimeError(f"Error inserting tracking data: {e}")

def process_frame(
    results, 
    frames, 
    frame_start_index: int,
    tracking_data: list, 
    saved_ids: set, 
    photo_folder: str
) -> Tuple[list, list]:
    """
    Processes a batch of frames by annotating them with YOLO detection results, appending
    tracking data for database storage, and saving a cropped image for each unique object ID.
    Also counts the number of affected (non-Healthy) detections per frame.

    Args:
        results (list): YOLO detection/tracking results for the batch.
        frames (list): The list of video frames corresponding to the results.
        frame_start_index (int): The index of the first frame in the current batch.
        tracking_data (list): List where tracking data tuples are appended.
        saved_ids (set): Set of object IDs for which a photo has already been saved.
        photo_folder (str): Folder path where cropped object photos are saved.

    Returns:
        tuple: (annotated_frames, detection_info) where detection_info is a list of tuples
               (frame_index, affected_count, frame_copy).
    """
    # Define a local color mapping for drawing bounding boxes
    class_colors = {
        "Healthy": (0, 255, 0),
        "Early blight": (0, 165, 255),
        "Late blight": (0, 0, 255),
        "Bacterial Spot": (255, 0, 255),
        "Leaf Mold": (255, 255, 0),
        "Leaf Miner": (0, 255, 255),
        "Mosaic Virus": (0, 255, 0),
        "Septoria": (255, 165, 0),
        "Spider Mites": (75, 0, 130),
        "Yellow Leaf Curl Virus": (238, 130, 238),
    }

    annotated_frames = []
    detection_info = []  # List to store (frame_index, affected_count, frame copy)

    for i, (result, frame) in enumerate(zip(results, frames)):
        current_frame_index = frame_start_index + i
        affected_count = 0  # Count non-Healthy detections

        for box_result in result.boxes:
            # Skip objects that are not tracked (no ID)
            if box_result.id is None:
                continue

            # Extract basic YOLO data from the result
            box = box_result.xyxy[0].tolist()
            conf = box_result.conf[0].tolist()
            class_id = int(box_result.cls[0])
            track_id = int(box_result.id[0])
            class_name = result.names.get(class_id, "Unknown")

            # Count affected (non-Healthy) detections
            if class_name.lower() != "healthy":
                affected_count += 1

            # Determine bounding box color based on class name
            box_color = class_colors.get(class_name, (255, 255, 255))
            bbox_str = f"{box[0]:.2f},{box[1]:.2f},{box[2]:.2f},{box[3]:.2f}"

            # Append the tracking data for later database insertion
            tracking_data.append((current_frame_index, track_id, class_name, bbox_str, conf))

            # Save the object's cropped photo if it hasn't been saved yet
            if track_id not in saved_ids:
                saved_ids.add(track_id)
                save_object_photo(frame, box, track_id, class_name, photo_folder)

            # Annotate the frame with a rectangle and label
            x_min, y_min, x_max, y_max = map(int, box)
            padding = 10
            x_min = max(0, x_min - padding)
            y_min = max(0, y_min - padding)
            x_max = min(frame.shape[1], x_max + padding)
            y_max = min(frame.shape[0], y_max + padding)

            label = f"ID {track_id}: {class_name} ({conf * 100:.2f}%)"
            font_scale = 1.5
            font_thickness = 3

            cv2.rectangle(frame, (x_min, y_min), (x_max, y_max), box_color, 4)
            cv2.putText(
                frame,
                label,
                (x_min, y_min - 15),
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale,
                box_color,
                font_thickness
            )

        annotated_frames.append(frame)
        # Save detection info (a copy of the frame is stored to avoid later modifications)
        detection_info.append((current_frame_index, affected_count, frame.copy()))

    return annotated_frames, detection_info

def save_object_photo(frame, bbox: list, track_id: int, class_name: str, photo_folder: str) -> None:
    """
    Crops and saves a photo of the detected object from the frame. Ensures that only one photo per
    unique track_id is saved.

    Args:
        frame (np.ndarray): The video frame.
        bbox (list): A list [x_min, y_min, x_max, y_max] defining the bounding box.
        track_id (int): Unique tracking ID for the detected object.
        class_name (str): The detected class name.
        photo_folder (str): The folder in which to save the cropped image.
    """
    x_min, y_min, x_max, y_max = map(int, bbox)
    cropped_object = frame[y_min:y_max, x_min:x_max]
    photo_filename = f"{class_name}_ID{track_id}.jpg"
    photo_path = os.path.join(photo_folder, photo_filename)

    try:
        cv2.imwrite(photo_path, cropped_object)
    except Exception as e:
        logging.error("Error saving object photo: %s", e)

def save_infected_frames(detection_info: list, output_folder: str, top_n: int = 5) -> None:
    """
    Saves the top N frames (with the highest number of affected detections)
    to a subfolder called 'infected_frames' inside output_folder.
    
    Args:
        detection_info (list): List of tuples (frame_index, affected_count, frame).
        output_folder (str): The output folder where the run data is saved.
        top_n (int): Number of top frames to save.
    """
    infected_folder = os.path.join(output_folder, "infected_frames")
    os.makedirs(infected_folder, exist_ok=True)
    
    # Sort the detection info by affected_count in descending order
    sorted_info = sorted(detection_info, key=lambda x: x[1], reverse=True)
    
    for idx, (frame_index, affected_count, frame) in enumerate(sorted_info[:top_n]):
        filename = f"infected_frame_{frame_index}_count_{affected_count}.jpg"
        filepath = os.path.join(infected_folder, filename)
        try:
            cv2.imwrite(filepath, frame)
        except Exception as e:
            logging.error("Error saving infected frame %s: %s", filepath, e)

# ------------------------------------------------------------
# Video Processing Function
# ------------------------------------------------------------

def process_video(
    video_path: str,
    model: YOLO,
    output_folder: str,
    duration: str,
    field_path: str
) -> None:
    """
    Processes the input video to perform plant/disease detection using YOLO. It saves an annotated
    video, logs tracking data to a database, and updates a progress dialog during processing.

    Args:
        video_path (str): Path to the input video file.
        model (YOLO): The YOLO model instance.
        output_folder (str): Folder where the processing results (video, DB, photos) are stored.
        duration (str): Flight duration string to be stored in the database.
        field_path (str): Base field folder path (used for additional summary DB updates).
    """
    # Ensure output folder is placed under field_path/runs
    base_folder = os.path.join(field_path, "runs")
    if not output_folder.startswith(base_folder):
        output_folder = os.path.join(base_folder, output_folder)
    os.makedirs(output_folder, exist_ok=True)

    start_time = time()
    cap = cv2.VideoCapture(video_path)

    # Retrieve video properties
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = int(cap.get(cv2.CAP_PROP_FPS))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # Define output paths for processed video, database, and photos
    processed_video_path = os.path.join(output_folder, "processed_video.mp4")
    db_path = os.path.join(output_folder, "flight_data.db")
    photo_folder = os.path.join(output_folder, "photos")
    os.makedirs(photo_folder, exist_ok=True)

    # Initialize video writer for the annotated video
    video_writer = cv2.VideoWriter(
        processed_video_path,
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (frame_width, frame_height)
    )

    # Initialize the database and get a cursor for executing queries
    conn, cursor = initialize_database(db_path)

    saved_ids = set()       # To track which object IDs have been saved as photos
    tracking_data = []      # List to hold tracking data for DB insertion
    all_detection_info = [] # List to collect detection info from all frames

    # Initialize the loading/progress dialog using PyQt6
    app = QApplication.instance() or QApplication(sys.argv)
    loading_dialog = LoadingDialog(total_frames)
    loading_dialog.show()
    app.processEvents()

    logging.info("Processing video...")

    frame_index = 0
    while frame_index < total_frames:
        batch_start_time = time()

        # Read a batch of frames from the video
        batch_frames = []
        for _ in range(BATCH_SIZE):
            ret, frame = cap.read()
            if not ret:
                break
            batch_frames.append(frame)

        if not batch_frames:
            break

        # Perform YOLO tracking on the current batch of frames
        results = track_and_detect_batch(model, batch_frames)

        # Process frames: annotate and collect tracking & detection info
        annotated_frames, detection_info = process_frame(
            results, batch_frames,
            frame_index, tracking_data, saved_ids,
            photo_folder
        )
        all_detection_info.extend(detection_info)

        # Write each annotated frame to the output video file
        for ann_frame in annotated_frames:
            video_writer.write(ann_frame)

        # Save collected tracking data to the database periodically
        if tracking_data:
            save_tracking_data_to_db(cursor, tracking_data, duration)
            tracking_data.clear()

        # Estimate the remaining processing time for progress feedback
        batch_end_time = time()
        batch_duration = batch_end_time - batch_start_time
        frames_processed = len(batch_frames)
        remaining_frames = total_frames - (frame_index + frames_processed)
        time_per_frame = batch_duration / frames_processed if frames_processed > 0 else 0
        estimated_remaining_time = time_per_frame * remaining_frames
        formatted_remaining_time = strftime("%H:%M:%S", gmtime(estimated_remaining_time))

        # Update progress dialog with current progress and estimated time remaining
        loading_dialog.update_progress(frame_index + frames_processed)
        loading_dialog.label.setText(
            "Processing video, please wait...\n"
            f"Estimated time remaining: {formatted_remaining_time}"
        )
        app.processEvents()

        frame_index += frames_processed

    # After processing all frames, save the top infected frames
    save_infected_frames(all_detection_info, output_folder, top_n=5)

    # Cleanup: close the progress dialog, commit and close DB, and release video resources
    loading_dialog.close()
    conn.commit()
    conn.close()
    video_writer.release()
    cap.release()

    end_time = time()
    total_processing_time = end_time - start_time
    formatted_processing_time = strftime("%H:%M:%S", gmtime(total_processing_time))
    logging.info("Processing completed in %s. Results: %s", formatted_processing_time, output_folder)

    # Update the field summary database with run statistics
    update_field_database(field_path)

    # Display the DroneReportApp to show the processing results
    report_app = DroneReportApp(field_path)
    report_app.show()

def run(video_path: str, duration: str, field_path: str) -> None:
    """
    Entry point for processing a single video file. This function sets up the output folders,
    loads the YOLO model, and triggers the video processing.

    Args:
        video_path (str): Path to the input video file.
        duration (str): Flight duration string (e.g., '00:05:12') for DB storage.
        field_path (str): The base field folder path.
    """
    base_output_folder = os.path.join(field_path, "runs")
    os.makedirs(base_output_folder, exist_ok=True)

    # Load the YOLO model from the given model file
    model_path = "yolol100.pt"
    model = initialize_model(model_path)

    # Create a new unique run folder and process the video
    output_folder = create_output_folder(base_output_folder)
    process_video(video_path, model, output_folder, duration, field_path)

# ------------------------------------------------------------
# Field Database Summary Functions
# ------------------------------------------------------------

def update_field_database(field_path: str) -> None:
    """
    Iterates over run folders and builds/updates a summary table (field_summary) in a
    central 'field_data.db' that aggregates information from each run's flight_data.db.

    Args:
        field_path (str): The base field directory (which contains the 'runs' folder).
    """
    field_db_path = os.path.join(field_path, "field_data.db")
    try:
        field_conn = sqlite3.connect(field_db_path)
        field_cursor = field_conn.cursor()
    except sqlite3.Error as e:
        logging.error("Error opening field database %s: %s", field_db_path, e)
        return

    # Define disease columns for the summary table
    diseases = [
        "early_blight",
        "late_blight",
        "bacterial_spot",
        "leaf_mold",
        "leaf_miner",
        "mosaic_virus",
        "septoria",
        "spider_mites",
        "yellow_leaf_curl_virus"
    ]

    # Create the field_summary table if it does not already exist
    try:
        field_cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS field_summary (
                run_id TEXT PRIMARY KEY,
                flight_datetime TEXT,
                flight_duration TEXT,
                total_plants INTEGER,
                healthy_plants INTEGER,
                {", ".join([f"{d} INTEGER" for d in diseases])}
            )
        """)
        field_conn.commit()
    except sqlite3.Error as e:
        logging.error("Error creating field_summary table: %s", e)
        field_conn.close()
        return

    runs_folder = os.path.join(field_path, "runs")
    if not os.path.exists(runs_folder):
        field_conn.close()
        return

    # Process each run folder to extract and summarize flight data
    for run_folder in os.listdir(runs_folder):
        run_path = os.path.join(runs_folder, run_folder)
        if not os.path.isdir(run_path):
            continue

        run_db_path = os.path.join(run_path, "flight_data.db")
        if not os.path.exists(run_db_path):
            continue

        try:
            run_conn = sqlite3.connect(run_db_path)
            run_cursor = run_conn.cursor()

            # Retrieve flight duration from the first row (if available)
            run_cursor.execute("SELECT FlightDuration FROM flight_results LIMIT 1")
            row = run_cursor.fetchone()
            flight_duration = row[0] if row else "Unknown"

            # Retrieve all detection/tracking records
            run_cursor.execute("SELECT ID, Class, Confidence FROM flight_results")
            run_rows = run_cursor.fetchall()
            if not run_rows:
                run_conn.close()
                continue

            # Select the highest confidence label for each unique plant ID
            plant_data = {}
            for pid, cls, conf in run_rows:
                if pid not in plant_data or conf > plant_data[pid][1]:
                    plant_data[pid] = (cls, conf)

            total_plants = len(plant_data)
            healthy_plants = sum(1 for (cls, _) in plant_data.values() if cls == "Healthy")

            # Tally counts for each disease type
            disease_counts = {d: 0 for d in diseases}
            for (cls_name, _) in plant_data.values():
                key = cls_name.lower().replace(" ", "_")
                if key in disease_counts:
                    disease_counts[key] += 1

            run_id = run_folder
            # Extract flight_datetime from run folder name (expected format: run_YYYYMMDD_HHMMSS)
            flight_datetime = run_folder.split("_", 1)[-1]

            # Insert or update the summary record in the field_summary table
            field_cursor.execute(f"""
                INSERT OR REPLACE INTO field_summary (
                    run_id, flight_datetime, flight_duration,
                    total_plants, healthy_plants,
                    {", ".join(diseases)}
                ) VALUES (
                    ?, ?, ?, ?, ?,
                    {", ".join("?" * len(diseases))}
                )
            """, (
                run_id, flight_datetime, flight_duration,
                total_plants, healthy_plants,
                *[disease_counts[d] for d in diseases]
            ))

            run_conn.close()

        except sqlite3.Error as e:
            logging.error("Error processing run DB %s: %s", run_db_path, e)

    field_conn.commit()
    field_conn.close()

# ------------------------------------------------------------
# Loading Dialog (PyQt6 GUI)
# ------------------------------------------------------------

class LoadingDialog(QDialog):
    """
    A modal dialog that displays a progress bar and status message during video processing.
    """
    def __init__(self, total_frames: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Επεξεργασία Βίντεο")
        self.setGeometry(400, 200, 400, 150)

        # Disable window buttons (close, minimize, maximize)
        self.setWindowFlags(
            Qt.WindowType.WindowTitleHint |
            Qt.WindowType.CustomizeWindowHint
        )
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        layout = QVBoxLayout(self)
        self.label = QLabel("Επεξεργασία βίντεο, παρακαλώ περιμένετε...")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, total_frames)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # Show the dialog immediately
        self.show()
        QApplication.processEvents()

    def update_progress(self, frame_index: int):
        """
        Updates the progress bar with the latest processed frame index.

        Args:
            frame_index (int): The current processed frame count.
        """
        self.progress_bar.setValue(frame_index)
        QApplication.processEvents()
