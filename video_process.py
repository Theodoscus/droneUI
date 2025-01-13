import sqlite3
from ultralytics import YOLO
import cv2
import os
from datetime import datetime
from report_gen import DroneReportApp
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar, QApplication
from PyQt6.QtCore import Qt


BASE_OUTPUT_FOLDER = "runs"

def initialize_model(model_path):
    # Load the YOLO model
    print("Loading YOLO model...")
    model = YOLO(model_path)
    print("Model loaded successfully.")
    return model


def track_and_detect(model, frame):
    # Run YOLO tracking on a single frame each time
    # We can also adjust the parameters for more accurate and faster results
    results = model.track(source=frame, persist=True, imgsz=1280, conf=0.25, augment=True, agnostic_nms=True)
    return results


def create_output_folder(base_folder):
    # Create a unique output folder for each run.
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_folder = os.path.join(base_folder, f"run_{timestamp}")
    os.makedirs(run_folder, exist_ok=True)
    return run_folder


def initialize_database(db_path):
    # Create an SQLite database and flight results table.
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create table for flight results
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


def save_tracking_data_to_db(cursor, tracking_data, duration):
    # Save tracking data directly to the SQLite database.
    for data in tracking_data:
        frame, track_id, class_name, bbox, conf = data

        # Convert bbox to a string
        bbox_str = ",".join(map(str, bbox))

        # Round Confidence to 4 decimal places
        conf = round(float(conf), 4)

        # Ensure duration is a string
        duration = str(duration)

        cursor.execute("""
            INSERT INTO flight_results (Frame, ID, Class, BBox, Confidence, FlightDuration)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (frame, track_id, class_name, bbox_str, conf, duration))




def process_frame(results, frame, frame_count, tracking_data, saved_ids, photo_folder):
    # Process detections in the frame
    for result in results[0].boxes:
        # Skip untracked objects
        if result.id is None:
            continue

        box = result.xyxy[0].tolist()  # Bounding box: [x_min, y_min, x_max, y_max]
        conf = result.conf[0].tolist()  # Confidence score
        class_id = int(result.cls[0])  # Class ID
        track_id = int(result.id[0])  # Track ID
        class_name = results[0].names[class_id]  # Get class name

        # Prepare tracking data for saving
        bbox_str = f"{box[0]:.2f},{box[1]:.2f},{box[2]:.2f},{box[3]:.2f}"
        tracking_data.append((frame_count, track_id, class_name, bbox_str, conf))

        # Save the first photo for each object by ID
        if track_id not in saved_ids:
            saved_ids.add(track_id)  # Mark the ID as saved
            save_object_photo(frame, box, track_id, class_name, photo_folder)

        # Annotate frame with bounding box and labels
        label = f"ID {track_id}: {class_name} ({conf:.2f})"
        x_min, y_min, x_max, y_max = map(int, box)
        cv2.rectangle(frame, (x_min, y_min), (x_max, y_max), (255, 255, 255), 3)  # White bounding box, thicker
        cv2.putText(
            frame,
            label,
            (x_min, y_min - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,  # Increased font size
            (255, 255, 255),
            2,  # Thicker text
        )

    return frame




def process_video(video_path, model, output_folder, duration):
    # Process the entire video for plant tracking and disease detection.
    cap = cv2.VideoCapture(video_path)
    frame_count = 0

    # Get video properties
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = int(cap.get(cv2.CAP_PROP_FPS))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # Create processed video path and SQLite database
    processed_video_path = os.path.join(output_folder, "processed_video.mp4")
    db_path = os.path.join(output_folder, "flight_data.db")
    photo_folder = os.path.join(output_folder, "photos")
    os.makedirs(photo_folder, exist_ok=True)

    # Initialize video writer and SQLite database
    video_writer = cv2.VideoWriter(
        processed_video_path,
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (frame_width, frame_height),
    )
    conn, cursor = initialize_database(db_path)

    saved_ids = set()
    tracking_data = []

    # Create the loading dialog
    app = QApplication.instance() or QApplication([])  # Ensure QApplication exists
    loading_dialog = LoadingDialog(total_frames)
    loading_dialog.show()

    print("Processing video...")
    for frame_index in range(total_frames):
        ret, frame = cap.read()
        if not ret:
            break

        # Run YOLO detection and tracking
        results = track_and_detect(model, frame)

        # Process the frame and annotate it
        annotated_frame = process_frame(results, frame, frame_index, tracking_data, saved_ids, photo_folder)

        # Write the annotated frame to the processed video
        video_writer.write(annotated_frame)

        # Save tracking data to the database periodically
        if len(tracking_data) > 0:
            save_tracking_data_to_db(cursor, tracking_data, duration)
            tracking_data.clear()

        # Update the loading dialog
        loading_dialog.update_progress(frame_index)
        app.processEvents()  # Allow the GUI to refresh

        frame_count += 1

    # Close the loading dialog
    loading_dialog.close()

    # Commit remaining tracking data and close database connection
    conn.commit()
    conn.close()
    video_writer.release()
    cap.release()

    print(f"Processing completed. Results saved in {output_folder}")

    # Display results in the report generation app
    report_app = DroneReportApp()
    report_app.load_results(output_folder)  # Load and display the results
    report_app.show()



def save_object_photo(frame, bbox, track_id, class_name, photo_folder):
    # Save only the first photo of an object by unique ID
    x_min, y_min, x_max, y_max = map(int, bbox)
    cropped_object = frame[y_min:y_max, x_min:x_max]
    photo_path = os.path.join(photo_folder, f"{class_name}_ID{track_id}.jpg")
    cv2.imwrite(photo_path, cropped_object)


def run(video_path, duration):
    # Run the video processing pipeline
    model_path = "yolol100.pt"
    model = initialize_model(model_path)
    output_folder = create_output_folder(BASE_OUTPUT_FOLDER)
    process_video(video_path, model, output_folder, duration)
    

class LoadingDialog(QDialog):
    # A simple dialog with a progress bar for video processing
    def __init__(self, total_frames, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Processing Video")
        self.setGeometry(400, 200, 400, 150)

        # Layout and widgets
        layout = QVBoxLayout(self)
        self.label = QLabel("Processing video, please wait...")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, total_frames)
        layout.addWidget(self.progress_bar)

    def update_progress(self, frame_index):
        # Update the progress bar.
        self.progress_bar.setValue(frame_index)