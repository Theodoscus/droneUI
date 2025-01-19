import sqlite3
from ultralytics import YOLO
import cv2
import os
from datetime import datetime
from report_gen import DroneReportApp
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar, QApplication
from PyQt6.QtCore import Qt
from time import time, strftime, gmtime


BATCH_SIZE = 4  # Number of frames to process in a batch

def initialize_model(model_path):
    # Load the YOLO model
    print("Loading YOLO model...")
    model = YOLO(model_path)
    print("Model loaded successfully.")
    return model

def track_and_detect_batch(model, frames):
    # Run YOLO tracking on a batch of frames
    results = model.track(source=frames, persist=True, imgsz=1280, conf=0.25, augment=True, agnostic_nms=True, batch=-1)
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

def process_frame(results, frames, frame_start_index, tracking_data, saved_ids, photo_folder):
    # Color mapping for different classes
    class_colors = {
        "Healthy": (0, 255, 0),  # Green for healthy
        "Early blight": (0, 165, 255),  # Orange
        "Late blight": (0, 0, 255),  # Red
        "Bacterial Spot": (255, 0, 255),  # Purple
        "Leaf Mold": (255, 255, 0),  # Yellow
        "Leaf Miner": (0, 255, 255),  # Cyan
        "Mosaic Virus": (0, 255, 0),  # Bright Green
        "Septoria": (255, 165, 0),  # Light Orange
        "Spider Mites": (75, 0, 130),  # Indigo
        "Yellow Leaf Curl Virus": (238, 130, 238),  # Violet
    }

    annotated_frames = []

    for i, (result, frame) in enumerate(zip(results, frames)):
        frame_index = frame_start_index + i
        for box_result in result.boxes:
            # Skip untracked objects
            if box_result.id is None:
                continue

            box = box_result.xyxy[0].tolist()  # Bounding box: [x_min, y_min, x_max, y_max]
            conf = box_result.conf[0].tolist()  # Confidence score
            class_id = int(box_result.cls[0])  # Class ID
            track_id = int(box_result.id[0])  # Track ID
            class_name = result.names[class_id]  # Get class name

            box_color = class_colors.get(class_name, (255, 255, 255))  # Default to white if not found

            # Prepare tracking data for saving
            bbox_str = f"{box[0]:.2f},{box[1]:.2f},{box[2]:.2f},{box[3]:.2f}"
            tracking_data.append((frame_index, track_id, class_name, bbox_str, conf))

            # Save the first photo for each object by ID
            if track_id not in saved_ids:
                saved_ids.add(track_id)  # Mark the ID as saved
                save_object_photo(frame, box, track_id, class_name, photo_folder)

            # Add padding to the bounding box
            padding = 10
            x_min = max(0, int(box[0]) - padding)
            y_min = max(0, int(box[1]) - padding)
            x_max = min(frame.shape[1], int(box[2]) + padding)
            y_max = min(frame.shape[0], int(box[3]) + padding)

            # Annotate frame with bounding box and labels
            label = f"ID {track_id}: {class_name} ({conf * 100:.2f}%)"
            font_scale = 1.5  # Bigger font size
            font_thickness = 3  # Thicker text

            cv2.rectangle(frame, (x_min, y_min), (x_max, y_max), box_color, 4)  # Thicker bounding box
            cv2.putText(
                frame,
                label,
                (x_min, y_min - 15),
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale,
                box_color,
                font_thickness,
            )

        annotated_frames.append(frame)

    return annotated_frames

def process_video(video_path, model, output_folder, duration, field_path):
    # Ensure output folder is within the correct field path
    base_folder = os.path.join(field_path, "runs")
    if not output_folder.startswith(base_folder):
        output_folder = os.path.join(base_folder, output_folder)
    os.makedirs(output_folder, exist_ok=True)
    
    # Process the entire video for plant tracking and disease detection.
    start_time = time()
    cap = cv2.VideoCapture(video_path)

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
    app.processEvents()  # Ensure the dialog and progress bar appear immediately

    print("Processing video...")

    frames = []
    frame_index = 0

    while frame_index < total_frames:
        batch_start_time = time()
        # Read frames in batches
        batch_frames = []
        for _ in range(BATCH_SIZE):
            ret, frame = cap.read()
            if not ret:
                break
            batch_frames.append(frame)

        if not batch_frames:
            break

        # Run YOLO detection on the batch
        results = track_and_detect_batch(model, batch_frames)

        # Process the batch of frames
        annotated_frames = process_frame(
            results, batch_frames, frame_index, tracking_data, saved_ids, photo_folder
        )

        # Write the annotated frames to the processed video
        for annotated_frame in annotated_frames:
            video_writer.write(annotated_frame)

        # Save tracking data to the database periodically
        if len(tracking_data) > 0:
            save_tracking_data_to_db(cursor, tracking_data, duration)
            tracking_data.clear()

        # Calculate time taken for the batch and estimate remaining time
        batch_end_time = time()
        batch_duration = batch_end_time - batch_start_time
        frames_processed = len(batch_frames)
        remaining_frames = total_frames - (frame_index + frames_processed)
        estimated_remaining_time = (batch_duration / frames_processed) * remaining_frames

        # Format remaining time as HH:MM:SS
        formatted_remaining_time = strftime("%H:%M:%S", gmtime(estimated_remaining_time))

        # Update the loading dialog with time estimate
        loading_dialog.update_progress(frame_index + frames_processed)
        loading_dialog.label.setText(
            f"Processing video, please wait...\nEstimated time remaining: {formatted_remaining_time}"
        )
        app.processEvents()  # Allow the GUI to refresh

        # Update frame index
        frame_index += len(batch_frames)

    # Close the loading dialog
    loading_dialog.close()

    # Commit remaining tracking data and close database connection
    conn.commit()
    conn.close()
    video_writer.release()
    cap.release()
    end_time = time()
    total_processing_time = end_time - start_time
    formatted_processing_time = strftime("%H:%M:%S", gmtime(total_processing_time))

    # After processing completes, update the field database
    update_field_database(field_path)
    
    print(f"Processing completed. Total video processing time: {formatted_processing_time}. Results saved in {output_folder}")

    # Display results in the report generation app
    report_app = DroneReportApp(field_path)
    #report_app.load_results(output_folder)  # Load and display the results
    report_app.show()

def save_object_photo(frame, bbox, track_id, class_name, photo_folder):
    # Save only the first photo of an object by unique ID
    x_min, y_min, x_max, y_max = map(int, bbox)
    cropped_object = frame[y_min:y_max, x_min:x_max]
    photo_path = os.path.join(photo_folder, f"{class_name}_ID{track_id}.jpg")
    cv2.imwrite(photo_path, cropped_object)

def run(video_path, duration, field_path):
    # Dynamically create the runs folder inside the selected field folder
    base_output_folder = os.path.join(field_path, "runs")
    os.makedirs(base_output_folder, exist_ok=True)

    # Load the YOLO model
    model_path = "yolol100.pt"
    model = initialize_model(model_path)

    # Create a unique run folder inside the base output folder
    output_folder = create_output_folder(base_output_folder)

    # Process the video
    process_video(video_path, model, output_folder, duration, field_path)

def update_field_database(field_path):
    # Path to the consolidated field database
    field_db_path = os.path.join(field_path, "field_data.db")

    # Ensure the field database exists
    conn = sqlite3.connect(field_db_path)
    cursor = conn.cursor()

    # Disease column names
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

    # Create the summary table
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS field_summary (
            run_id TEXT PRIMARY KEY,
            flight_datetime TEXT,
            flight_duration TEXT,
            total_plants INTEGER,
            healthy_plants INTEGER,
            {", ".join([f"{disease} INTEGER" for disease in diseases])}
        )
    """)
    conn.commit()

    # Iterate through all run databases in the `runs` folder
    runs_folder = os.path.join(field_path, "runs")
    for run_folder in os.listdir(runs_folder):
        run_path = os.path.join(runs_folder, run_folder)
        if not os.path.isdir(run_path):
            continue

        run_db_path = os.path.join(run_path, "flight_data.db")
        if not os.path.exists(run_db_path):
            continue

        # Extract data from the individual run database
        run_conn = sqlite3.connect(run_db_path)
        run_cursor = run_conn.cursor()

        try:
            # Retrieve flight duration from the first row
            run_cursor.execute("SELECT FlightDuration FROM flight_results LIMIT 1")
            flight_duration_row = run_cursor.fetchone()
            flight_duration = flight_duration_row[0] if flight_duration_row else "Unknown"

            # Query data from the run database
            run_cursor.execute("""
                SELECT 
                    ID,
                    Class,
                    Confidence
                FROM flight_results
            """)
            results = run_cursor.fetchall()

            # Keep only the highest confidence label per plant ID
            plant_data = {}
            for plant_id, plant_class, confidence in results:
                if plant_id not in plant_data or confidence > plant_data[plant_id][1]:
                    plant_data[plant_id] = (plant_class, confidence)

            # Summarize data for the run
            total_plants = len(plant_data)
            healthy_plants = sum(1 for plant_class, _ in plant_data.values() if plant_class == "Healthy")

            # Count affected plants per disease
            disease_counts = {disease: 0 for disease in diseases}
            for plant_class, _ in plant_data.values():
                key = plant_class.lower().replace(" ", "_")
                if key in disease_counts:
                    disease_counts[key] += 1

            # Get flight datetime from the run folder name
            run_id = run_folder
            flight_datetime = run_folder.split("_", 1)[-1]

            # Insert data into the field database
            cursor.execute(f"""
                INSERT OR REPLACE INTO field_summary (
                    run_id, flight_datetime, flight_duration, 
                    total_plants, healthy_plants, {", ".join(diseases)}
                ) VALUES (?, ?, ?, ?, ?, {", ".join("?" * len(diseases))})
            """, (run_id, flight_datetime, flight_duration, total_plants, healthy_plants, *[disease_counts[disease] for disease in diseases]))
        except sqlite3.Error as e:
            print(f"Error processing run database {run_db_path}: {e}")
        finally:
            run_conn.close()

    # Commit and close the field database connection
    conn.commit()
    conn.close()


    

class LoadingDialog(QDialog):
    """A simple dialog with a progress bar for video processing."""
    def __init__(self, total_frames, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Επεξεργασία Βίντεο")
        self.setGeometry(400, 200, 400, 150)

        # Set window flags to disable close, minimize, and maximize buttons
        self.setWindowFlags(Qt.WindowType.WindowTitleHint | Qt.WindowType.CustomizeWindowHint)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)  # Block interaction with other windows

        # Layout and widgets
        layout = QVBoxLayout(self)
        self.label = QLabel("Επεξεργασία βίντεο, παρακαλώ περιμένετε...")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, total_frames)
        self.progress_bar.setValue(0)  # Initialize progress at 0%
        layout.addWidget(self.progress_bar)

        # Force the window to display immediately
        self.show()
        QApplication.processEvents()  # Ensure the GUI updates before processing begins

    def update_progress(self, frame_index):
        """Update the progress bar."""
        self.progress_bar.setValue(frame_index)
        QApplication.processEvents()
