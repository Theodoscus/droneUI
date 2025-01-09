import sqlite3
from tqdm import tqdm
from ultralytics import YOLO
import cv2
import os
from datetime import datetime


BASE_OUTPUT_FOLDER = "runs"

def initialize_model(model_path):
    """Load the YOLO model."""
    print("Loading YOLO model...")
    model = YOLO(model_path)
    print("Model loaded successfully.")
    return model


def track_and_detect(model, frame):
    """Run YOLO tracking on a single frame."""
    results = model.track(source=frame, persist=True, imgsz=1280, conf=0.25, augment=True, agnostic_nms=True)
    return results


def create_output_folder(base_folder):
    """Create a unique output folder for each run."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_folder = os.path.join(base_folder, f"run_{timestamp}")
    os.makedirs(run_folder, exist_ok=True)
    return run_folder


def initialize_database(db_path):
    """Create an SQLite database and flight results table."""
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
    """Save tracking data directly to the SQLite database."""
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








def process_video(video_path, model, output_folder, duration):
    """Process the video for plant tracking and save results to SQLite."""
    cap = cv2.VideoCapture(video_path)
    frame_count = 0

    # Get video properties
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # Create processed video path and database
    processed_video_path = os.path.join(output_folder, "processed_video.mov")
    db_path = os.path.join(output_folder, "flight_data.db")
    photo_folder = os.path.join(output_folder, "photos")
    os.makedirs(photo_folder, exist_ok=True)

    # Initialize video writer and database
    video_writer = cv2.VideoWriter(
        processed_video_path,
        cv2.VideoWriter_fourcc(*"mp4v"),
        int(cap.get(cv2.CAP_PROP_FPS)),
        (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))),
    )
    conn, cursor = initialize_database(db_path)

    tracking_data = []
    saved_ids = set()

    print("Processing video...")
    for frame_idx in tqdm(range(total_frames), desc="Processing Frames"):
        ret, frame = cap.read()
        if not ret:
            break

        results = track_and_detect(model, frame)

        # Process each frame
        for result in results[0].boxes:
            if result.id is None:
                continue

            bbox = result.xyxy[0].tolist()  # Ensure bbox is a list
            conf = float(result.conf.item())  # Convert NumPy type to native Python float
            class_name = results[0].names[int(result.cls[0])]
            track_id = int(result.id.item())  # Convert NumPy type to native Python int

            tracking_data.append((frame_count, track_id, class_name, bbox, conf))




            if track_id not in saved_ids:
                save_object_photo(frame, bbox, track_id, class_name, photo_folder)
                saved_ids.add(track_id)

        save_tracking_data_to_db(cursor, tracking_data, duration)
        tracking_data.clear()

        # Write annotated frame
        video_writer.write(frame)

    conn.commit()
    conn.close()
    video_writer.release()
    cap.release()
    print(f"Processing completed. Results saved in {output_folder}")


def save_object_photo(frame, bbox, track_id, class_name, photo_folder):
    """Save the first photo of an object by ID."""
    x_min, y_min, x_max, y_max = map(int, bbox)
    cropped_object = frame[y_min:y_max, x_min:x_max]
    photo_path = os.path.join(photo_folder, f"{class_name}_ID{track_id}.jpg")
    cv2.imwrite(photo_path, cropped_object)


def run(video_path, duration):
    """Run the video processing pipeline."""
    model_path = "yolol100.pt"
    model = initialize_model(model_path)
    output_folder = create_output_folder(BASE_OUTPUT_FOLDER)
    process_video(video_path, model, output_folder, duration)
