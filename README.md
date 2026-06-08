# AgroDrone Tomato Disease Detection

A Python desktop application for controlling a DJI Tello EDU drone, recording crop-surveillance flights, detecting tomato leaf diseases with a YOLO model, and generating field-specific flight reports.

The system is designed around a simple workflow: create or select a field, fly the drone over the crop area, record the flight video, process the video with an object-detection model, and review the results through visual reports, charts, detected-plant photos, and suggested countermeasures.

---

## Overview

This project was developed as part of a thesis project at the Department of Computer Engineering and Informatics, University of Patras.

The application combines drone control, graphical user interface design, computer vision, and report generation. It provides a PyQt6 interface that allows the user to manage crop fields, connect to a DJI Tello EDU drone, manually control the drone, record video during flight, process the recorded video using a YOLO model, and store the analysis results for later review.

The main use case is tomato crop monitoring and early identification of possible leaf diseases.

---

## Main Features

### Field Management

The application starts from a home page where the user can:

* Create a new field
* Select an existing field
* Open the drone control screen for the selected field
* View flight history when previous runs exist

Each field is stored as a separate folder under the `fields/` directory. Flight videos, processed runs, images, databases, and summaries are organized inside the selected field folder.

---

### DJI Tello EDU Drone Control

The drone control module connects to a DJI Tello EDU drone using the `djitellopy` library.

The interface supports:

* Drone connection handling
* Live video stream display
* Takeoff and landing
* Emergency landing
* Keyboard control
* Joystick/controller support
* Continuous movement commands
* Battery, height, temperature, speed, and signal monitoring
* Full-screen and windowed control modes

The application sends movement commands asynchronously so that the interface remains responsive while the drone is being controlled.

---

### Flight Video Recording

When a flight starts, the system creates a timestamped flight folder and records the drone video stream as an `.mp4` file.

A typical flight folder contains the raw flight video and is later connected with the processed detection results.

---

### YOLO-Based Disease Detection

After a flight ends, the recorded video is processed using a YOLO model stored as:

```text
yolol100.pt
```

The video processing module:

* Loads the YOLO model
* Reads the recorded flight video
* Processes frames in batches
* Tracks detected plants across frames
* Assigns object IDs
* Draws bounding boxes and class labels
* Saves detection data to SQLite
* Exports cropped plant images
* Saves the most important infected frames
* Generates an annotated processed video

The detected classes include healthy plants and multiple tomato disease categories.

<img width="1856" height="1391" alt="2025-05-31_132832" src="https://github.com/user-attachments/assets/2e2fc0f0-16cb-46a1-8091-b92c134a790b" />

---

### SQLite Flight Results

Each processed run stores its detection results in a local SQLite database.

The `flight_results` table stores information such as:

* Frame number
* Tracked object ID
* Detected class
* Bounding box
* Confidence score
* Flight duration

The project also creates a field-level database that summarizes the results across multiple flights of the same field.

---

### Flight Reports

<img width="1200" height="1501" alt="2025-05-31_133257" src="https://github.com/user-attachments/assets/c886adc8-89a0-4ca5-9832-7c253d6e4524" />

The report module allows the user to review previous flight results.

It displays:

* Flight date and time
* Flight duration
* Disease/class counts
* Bar charts
* Photos of detected plants
* Detection confidence values
* Field progress information

The system can also export a Greek-enabled PDF flight report using ReportLab.

The generated PDF includes:

* Field name
* Flight date
* Flight duration
* Total detected plants
* Disease distribution chart
* Table of diseased plants
* Detection confidence
* Related plant photos

---

### Field Progress Monitoring

The field progress page reads the field-level SQLite database and visualizes the health status of a field over time.

It uses previous flight summaries to compare healthy plants and total detected plants across different runs.

This helps the user observe whether the field condition improves or worsens over time.

---

### Suggested Countermeasures

The application includes a countermeasures window that displays suggested actions for detected tomato diseases.

It also allows the user to save personal notes related to a flight. These notes are stored in the flight database and can be reviewed later.

---

## Tech Stack

| Technology                 | Purpose                                             |
| -------------------------- | --------------------------------------------------- |
| Python                     | Main programming language                           |
| PyQt6                      | Desktop graphical user interface                    |
| DJI Tello SDK / djitellopy | Drone connection and control                        |
| OpenCV                     | Video recording, frame processing, image annotation |
| Ultralytics YOLO           | Plant and disease detection                         |
| PyTorch                    | Deep learning backend used by YOLO                  |
| SQLite                     | Local storage of flight and field results           |
| Pandas                     | Reading and processing result data                  |
| Matplotlib                 | Charts and visual summaries                         |
| ReportLab                  | PDF flight report generation                        |
| Pygame                     | Joystick/controller input support                   |

---

## Project Structure

```text
agrodrone-tomato-disease-detection/
├── homepage.py              # Main field selection and navigation screen
├── real_drone_control.py    # Main windowed drone-control interface
├── drone_control_full.py    # Full-screen drone-control interface
├── drone_functions.py       # DJI Tello connection, control, recording, and telemetry logic
├── video_process.py         # YOLO video processing and SQLite result storage
├── report_gen.py            # Flight history, charts, photos, countermeasures, and PDF reports
├── field_progress.py        # Field-level health progress visualization
├── countermeasures.py       # Suggested countermeasures and personal notes
├── shared.py                # Shared navigation helpers between windows
├── requirements.txt         # Python dependencies
├── yolol100.pt              # YOLO model weights
├── arial_greek.ttf          # Font used for Greek PDF generation
├── logos/                   # UI logos and images
└── Chronopoulos-Thesis.pdf  # Thesis document
```

---

## How the Application Works

1. The user opens the application from `homepage.py`.
2. The user creates or selects a field.
3. The application opens the drone-control interface for the selected field.
4. The user connects to the DJI Tello EDU drone.
5. The user controls the drone manually through keyboard, GUI buttons, or a controller.
6. During flight, the system records video from the drone stream.
7. After landing, the recorded video is processed using the YOLO model.
8. Detection results are stored in a run-specific SQLite database.
9. Annotated videos, cropped plant images, and infected frames are saved.
10. The user reviews the flight results through the report screen.
11. The user can export a PDF report and view field progress over time.

---

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/Theodoscus/droneUI.git
cd droneUI
```

### 2. Create a Virtual Environment

```bash
python -m venv .venv
```

Activate it:

```bash
# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

If you want GPU acceleration for YOLO, install the appropriate PyTorch version for your CUDA setup separately.

---

## Running the Application

Power on the DJI Tello EDU drone and connect your computer to the drone's Wi-Fi network.

Then run:

```bash
python homepage.py
```

The application will open the field-selection screen.

---

## Requirements

The project dependencies include:

* `djitellopy`
* `PyQt6`
* `opencv_python`
* `ultralytics`
* `pygame`
* `pandas`
* `matplotlib`
* `reportlab`
* `tqdm`

The repository also includes the model file `yolol100.pt`, which is required by the video-processing module.

---

## License

This project was developed for academic and research purposes.

Theodosios Chronopoulos || 📧 theodoschr@gmail.com || 📍 University of Patras – Computer Engineering & Informatics Department

