import os
import sys
import cv2
import sqlite3
import pandas as pd
from datetime import datetime
from time import time, strftime, gmtime

from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QLabel, QProgressBar
)
from PyQt6.QtCore import Qt

# YOLO imports
from ultralytics import YOLO

# Local imports
from report_gen import DroneReportApp


# ----------------------------------------------
# Constants / Configuration
# ----------------------------------------------

BATCH_SIZE = 4  # Number of frames processed per batch


# ----------------------------------------------
# YOLO Model Initialization
# ----------------------------------------------

def initialize_model(model_path: str) -> YOLO:
    """
    Loads a YOLO model from the given .pt file.

    Args:
        model_path (str): Path to the YOLO model.

    Returns:
        YOLO: The YOLO model instance.
    """
    print("Loading YOLO model from:", model_path)
    try:
        model = YOLO(model_path)
        print("Model loaded successfully.")
        return model
    except Exception as e:
        raise RuntimeError(f"Error initializing YOLO model: {e}")


def track_and_detect_batch(model: YOLO, frames: list) -> list:
    """
    Runs YOLO tracking on a batch of frames.

    Args:
        model  (YOLO): The loaded YOLO model.
        frames (list): List of frames (NumPy arrays).

    Returns:
        list: A list of results for each frame in the batch.
    """
    # You can tweak these arguments (imgsz, conf, augment, etc.) for performance/accuracy
    try:
        return model.track(
            source=frames,
            persist=True,
            imgsz=1280,
            conf=0.5,
            augment=True,
            agnostic_nms=True,
            batch=-1
        )
    except Exception as e:
        raise RuntimeError(f"Error during YOLO track/detect batch: {e}")


# ----------------------------------------------
# Folder / Database Setup
# ----------------------------------------------

def create_output_folder(base_folder: str) -> str:
    """
    Creates a unique run folder named with a timestamp under base_folder.
    E.g., base_folder/run_YYYYMMDD_HHMMSS

    Args:
        base_folder (str): The parent folder where runs are stored.

    Returns:
        str: The path to the newly created run folder.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_folder = os.path.join(base_folder, f"run_{timestamp}")
    os.makedirs(run_folder, exist_ok=True)
    return run_folder


def initialize_database(db_path: str):
    """
    Creates or opens an SQLite database, then ensures a flight_results table exists.

    Args:
        db_path (str): The path to the SQLite database file.

    Returns:
        (conn, cursor): The opened database connection and cursor.
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


# ----------------------------------------------
# Data Saving / Frame Processing
# ----------------------------------------------

def save_tracking_data_to_db(cursor, tracking_data: list, duration: str) -> None:
    """
    Saves batched tracking data into the 'flight_results' table.

    Args:
        cursor: A SQLite cursor for executing queries.
        tracking_data (list): A list of tuples (frame, track_id, class_name, bbox_str, conf).
        duration (str): The flight duration string (e.g. '00:05:12').
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
    results, frames, frame_start_index: int,
    tracking_data: list, saved_ids: set, photo_folder: str
) -> list:
    """
    Annotates frames with YOLO results, saves tracking data, and crops the first photo of each ID.

    Args:
        results          (list): YOLO detection/tracking results.
        frames           (list): Batch of frames (NumPy arrays).
        frame_start_index(int) : Index of the first frame in this batch.
        tracking_data    (list): Where new tracking data is appended.
        saved_ids        (set) : Tracks IDs already saved (so each ID's photo is saved once).
        photo_folder     (str) : Path to save object photos.

    Returns:
        list: A list of annotated frames.
    """
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

    for i, (result, frame) in enumerate(zip(results, frames)):
        current_frame_index = frame_start_index + i

        for box_result in result.boxes:
            if box_result.id is None:
                # Skip untracked objects
                continue

            # Basic YOLO data extraction
            box = box_result.xyxy[0].tolist()
            conf = box_result.conf[0].tolist()
            class_id = int(box_result.cls[0])
            track_id = int(box_result.id[0])
            class_name = result.names.get(class_id, "Unknown")

            # Choose bounding box color
            box_color = class_colors.get(class_name, (255, 255, 255))
            bbox_str = f"{box[0]:.2f},{box[1]:.2f},{box[2]:.2f},{box[3]:.2f}"

            # Append to tracking_data
            tracking_data.append((current_frame_index, track_id, class_name, bbox_str, conf))

            # Save first photo if ID not in saved_ids
            if track_id not in saved_ids:
                saved_ids.add(track_id)
                save_object_photo(frame, box, track_id, class_name, photo_folder)

            # Annotate the frame
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

    return annotated_frames


def save_object_photo(frame, bbox: list, track_id: int, class_name: str, photo_folder: str) -> None:
    """
    Saves a cropped object photo once per track_id.

    Args:
        frame (np.ndarray): The video frame.
        bbox  (list)      : [x_min, y_min, x_max, y_max].
        track_id (int)    : Unique track ID from YOLO.
        class_name (str)  : Detected class name.
        photo_folder (str): Folder to save the cropped photo.
    """
    x_min, y_min, x_max, y_max = map(int, bbox)
    cropped_object = frame[y_min:y_max, x_min:x_max]
    photo_filename = f"{class_name}_ID{track_id}.jpg"
    photo_path = os.path.join(photo_folder, photo_filename)

    try:
        cv2.imwrite(photo_path, cropped_object)
    except Exception as e:
        print(f"Error saving object photo: {e}")


# ----------------------------------------------
# Video Processing
# ----------------------------------------------

def process_video(
    video_path: str,
    model: YOLO,
    output_folder: str,
    duration: str,
    field_path: str
) -> None:
    """
    Processes a video for plant/disease detection with YOLO, saves annotated video + DB,
    and updates a progress dialog during processing.

    Args:
        video_path    (str): Path to the input video.
        model         (YOLO): YOLO model instance.
        output_folder (str): Folder where results are stored.
        duration      (str): Flight duration (for DB).
        field_path    (str): Field folder path.
    """
    # Ensure output_folder is under "runs" in field_path
    base_folder = os.path.join(field_path, "runs")
    if not output_folder.startswith(base_folder):
        output_folder = os.path.join(base_folder, output_folder)
    os.makedirs(output_folder, exist_ok=True)

    start_time = time()
    cap = cv2.VideoCapture(video_path)

    # Basic video properties
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = int(cap.get(cv2.CAP_PROP_FPS))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # Output paths
    processed_video_path = os.path.join(output_folder, "processed_video.mp4")
    db_path = os.path.join(output_folder, "flight_data.db")
    photo_folder = os.path.join(output_folder, "photos")
    os.makedirs(photo_folder, exist_ok=True)

    # Video writer
    video_writer = cv2.VideoWriter(
        processed_video_path,
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (frame_width, frame_height)
    )

    # DB init
    conn, cursor = initialize_database(db_path)

    saved_ids = set()
    tracking_data = []

    # Loading dialog
    app = QApplication.instance() or QApplication(sys.argv)
    loading_dialog = LoadingDialog(total_frames)
    loading_dialog.show()
    app.processEvents()

    print("Processing video...")

    frame_index = 0
    while frame_index < total_frames:
        batch_start_time = time()

        # Read frames in small batches
        batch_frames = []
        for _ in range(BATCH_SIZE):
            ret, frame = cap.read()
            if not ret:
                break
            batch_frames.append(frame)

        if not batch_frames:
            break

        # YOLO tracking
        results = track_and_detect_batch(model, batch_frames)

        # Annotate frames, gather data
        annotated_frames = process_frame(
            results, batch_frames,
            frame_index, tracking_data, saved_ids,
            photo_folder
        )

        # Write annotated frames
        for ann_frame in annotated_frames:
            video_writer.write(ann_frame)

        # Save tracking data to DB periodically
        if tracking_data:
            save_tracking_data_to_db(cursor, tracking_data, duration)
            tracking_data.clear()

        # Estimate time left
        batch_end_time = time()
        batch_duration = batch_end_time - batch_start_time
        frames_processed = len(batch_frames)
        remaining_frames = total_frames - (frame_index + frames_processed)

        # Calculate time per frame
        if frames_processed > 0:
            time_per_frame = batch_duration / frames_processed
        else:
            time_per_frame = 0
        estimated_remaining_time = time_per_frame * remaining_frames
        formatted_remaining_time = strftime("%H:%M:%S", gmtime(estimated_remaining_time))

        # Update dialog
        loading_dialog.update_progress(frame_index + frames_processed)
        loading_dialog.label.setText(
            "Processing video, please wait...\n"
            f"Estimated time remaining: {formatted_remaining_time}"
        )
        app.processEvents()

        frame_index += frames_processed

    # Cleanup
    loading_dialog.close()
    conn.commit()
    conn.close()
    video_writer.release()
    cap.release()

    end_time = time()
    total_processing_time = end_time - start_time
    formatted_processing_time = strftime("%H:%M:%S", gmtime(total_processing_time))

    # Update the field database summary
    update_field_database(field_path)

    print(f"Processing completed in {formatted_processing_time}. Results: {output_folder}")

    # Display results in the DroneReportApp
    report_app = DroneReportApp(field_path)
    report_app.show()


def run(video_path: str, duration: str, field_path: str) -> None:
    """
    Entry point for a single video processing run.

    Args:
        video_path (str): Path to input video.
        duration   (str): Flight duration for DB.
        field_path (str): The field folder path.
    """
    base_output_folder = os.path.join(field_path, "runs")
    os.makedirs(base_output_folder, exist_ok=True)

    # Load YOLO model
    model_path = "yolol100.pt"
    model = initialize_model(model_path)

    # Create run folder
    output_folder = create_output_folder(base_output_folder)

    # Process video
    process_video(video_path, model, output_folder, duration, field_path)


# ----------------------------------------------
# Field Database Summaries
# ----------------------------------------------

def update_field_database(field_path: str) -> None:
    """
    Iterates over run folders, builds or updates a 'field_data.db' summary table
    (field_summary) that collects info from each run's flight_data.db.

    Args:
        field_path (str): The base field path (contains 'runs').
    """
    field_db_path = os.path.join(field_path, "field_data.db")
    try:
        field_conn = sqlite3.connect(field_db_path)
        field_cursor = field_conn.cursor()
    except sqlite3.Error as e:
        print(f"Error opening field database {field_db_path}: {e}")
        return

    # Column names for various diseases
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

    # Ensure summary table
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
        print(f"Error creating field_summary table: {e}")
        field_conn.close()
        return

    runs_folder = os.path.join(field_path, "runs")
    if not os.path.exists(runs_folder):
        field_conn.close()
        return

    # Iterate over all run folders
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

            # Try reading flight duration from the first row
            run_cursor.execute("SELECT FlightDuration FROM flight_results LIMIT 1")
            row = run_cursor.fetchone()
            flight_duration = row[0] if row else "Unknown"

            # Query all results
            run_cursor.execute("SELECT ID, Class, Confidence FROM flight_results")
            run_rows = run_cursor.fetchall()
            if not run_rows:
                run_conn.close()
                continue

            # Keep highest confidence label per plant
            plant_data = {}
            for pid, cls, conf in run_rows:
                if pid not in plant_data or conf > plant_data[pid][1]:
                    plant_data[pid] = (cls, conf)

            total_plants = len(plant_data)
            healthy_plants = sum(1 for (cls, _) in plant_data.values() if cls == "Healthy")

            # Tally each disease
            disease_counts = {d: 0 for d in diseases}
            for (cls_name, _) in plant_data.values():
                key = cls_name.lower().replace(" ", "_")
                if key in disease_counts:
                    disease_counts[key] += 1

            run_id = run_folder
            # run_YYYYMMDD_HHMMSS -> flight_datetime: "YYYYMMDD_HHMMSS"
            flight_datetime = run_folder.split("_", 1)[-1]

            # Insert or update in field_summary
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
            print(f"Error processing run DB {run_db_path}: {e}")

    field_conn.commit()
    field_conn.close()


# ----------------------------------------------
# Loading Dialog
# ----------------------------------------------

class LoadingDialog(QDialog):
    """
    A simple dialog with a progress bar to indicate how many frames of the video have been processed.
    """
    def __init__(self, total_frames: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Επεξεργασία Βίντεο")
        self.setGeometry(400, 200, 400, 150)

        # Disallow close/minimize/maximize
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

        # Show immediately
        self.show()
        QApplication.processEvents()

    def update_progress(self, frame_index: int):
        """
        Updates the progress bar with how many frames have been processed.

        Args:
            frame_index (int): The last processed frame index.
        """
        self.progress_bar.setValue(frame_index)
        QApplication.processEvents()
