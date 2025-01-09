import cv2
from ultralytics import YOLO
from tqdm import tqdm
import os
from datetime import datetime
from PyQt6.QtWidgets import QApplication
from report_gen import DroneReportApp
import pandas as pd
import os
from datetime import datetime

# Global Output Folder
BASE_OUTPUT_FOLDER = "runs"

def initialize_model(model_path):
    """Load the YOLOv11 model."""
    print("Loading YOLO model...")
    model = YOLO(model_path)
    print("Model loaded successfully.")
    return model


def track_and_detect(model, frame):
    """Run YOLO tracking on a single frame."""
    results = model.track(source=frame, persist=True, imgsz=1280, conf=0.15, augment=True, agnostic_nms=True)
    return results


def process_frame(results, frame, frame_count, tracking_data, saved_ids, photo_folder):
    """Process YOLO results for a single frame."""
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



def save_object_photo(frame, box, track_id, class_name, photo_folder):
    """Save the first photo of an object by its ID."""
    x_min, y_min, x_max, y_max = map(int, box)
    cropped_object = frame[y_min:y_max, x_min:x_max]  # Crop the detected object

    # Ensure the photo folder exists
    os.makedirs(photo_folder, exist_ok=True)

    # Save the cropped object image
    photo_path = os.path.join(photo_folder, f"{class_name}_ID{track_id}.jpg")
    cv2.imwrite(photo_path, cropped_object)
    print(f"Saved photo for ID {track_id}: {photo_path}")



def save_tracking_data(tracking_data, output_file):
    """Save tracking data to a CSV file."""
    # Convert tracking data to a DataFrame
    df = pd.DataFrame(tracking_data, columns=["Frame", "ID", "Class", "BBox", "Confidence"])
    
    # Save to CSV file
    if not os.path.exists(output_file):
        df.to_csv(output_file, index=False, mode="w")  # Create and write the CSV file with a header
    else:
        df.to_csv(output_file, index=False, mode="a", header=False)  # Append without duplicating the header
    print(f"Tracking data saved to {output_file}")



def create_output_folder(base_folder):
    """Create a unique output folder for each run."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_folder = os.path.join(base_folder, f"run_{timestamp}")
    os.makedirs(run_folder, exist_ok=True)
    return run_folder


def process_video(video_path, model, output_folder):
    """Process the entire video for plant tracking and disease detection."""
    cap = cv2.VideoCapture(video_path)
    frame_count = 0

    # Get video properties
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = int(cap.get(cv2.CAP_PROP_FPS))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # Create processed video path, CSV file, and photo folder
    processed_video_path = os.path.join(output_folder, "processed_video.mp4")
    output_file = os.path.join(output_folder, "tracked_data.csv")  # CSV file
    photo_folder = os.path.join(output_folder, "photos")

    # Initialize video writer
    video_writer = cv2.VideoWriter(
        processed_video_path,
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (frame_width, frame_height),
    )

    # Set to track saved IDs
    saved_ids = set()
    tracking_data = []  # Collect tracking data for saving

    # Process frames with a loading bar
    print("Processing video...")
    for _ in tqdm(range(total_frames), desc="Processing Frames"):
        ret, frame = cap.read()
        if not ret:
            break

        # Run YOLO detection and tracking
        results = track_and_detect(model, frame)

        # Process the frame and annotate it
        annotated_frame = process_frame(results, frame, frame_count, tracking_data, saved_ids, photo_folder)

        # Write the annotated frame to the processed video
        video_writer.write(annotated_frame)

        frame_count += 1

    # Save tracking data to CSV after processing all frames
    save_tracking_data(tracking_data, output_file)

    cap.release()
    video_writer.release()
    print(f"Processing completed. Results saved in {output_folder}")
    
    app = QApplication([])
    report_app = DroneReportApp()
    report_app.load_results(output_folder)  # Load and display the results
    report_app.show()
    app.exec()





def main():
    """Main function to run plant tracking and disease detection."""
    # Paths
    video_path = "video3.mov"  # Replace with your video path
    model_path = "yolol100.pt"  # Replace with your YOLO model path

    # Initialize YOLO model
    model = initialize_model(model_path)

    # Create output folder for the current run
    output_folder = create_output_folder(BASE_OUTPUT_FOLDER)

    # Process video and track plants
    process_video(video_path, model, output_folder)


if __name__ == "__main__":
    main()
