# 🚁 DroneUI – Smart Drone System for Tomato Disease Detection

This repository contains the implementation of my master thesis at the **Computer Engineering & Informatics Department**, University of Patras.

🎓 **Thesis Title**:  
**Development and evaluation of a drone system user interface with artificial intelligence for the detection of phytopathological diseases in tomato crops**

👨‍💻 Author: Theodosios Chronopoulos  
📅 Year: 2025  
🎓 Supervisor: Prof. Michalis Xenos
🎓 Co-supervisor: PhD Candidate Dimosthenis Minas

---

## 📌 Overview

This project presents a low-cost, user-friendly system for **tomato crop surveillance using a DJI Tello EDU drone and AI-based analysis**. A custom-built **Python GUI (PyQt6)** allows manual drone control, video capture, real-time disease detection using **YOLOv11**, and the generation of detailed flight reports.

🔍 The system was tested with **real farmers**, comparing its effectiveness against traditional visual inspection, and showed promising results in both speed and detection accuracy.

---

## 🚀 Features

- 🧭 **Manual Drone Flight** via keyboard/GUI/Controller
- 🎥 **Video Capture & Frame Extraction**
- 🧠 **Disease Detection** on tomato leaves using YOLOv11 (`yolol100.pt`)
- 📈 **Progress Monitoring** of each field over time
- 📄 **PDF Flight Report Generation** with results and stats
- 🗃️ **Field-specific Folder & Data Management**
- 💊 **Suggested Countermeasures** for each disease

---

| Category                 | Technology / Tool                                          | Description                                                             |
| ------------------------ | ---------------------------------------------------------- | ------------------------------------------------------------------------|
| **Programming Language** | Python 3.10+                                               | Core language used for development                                      |
| **Drone SDK**            | [`djitellopy`](https://github.com/damiafuentes/DJITelloPy) | Python library to control the DJI Tello EDU                             |
| **GUI Framework**        | PyQt6                                                      | For building the interactive user interface                             |
| **Video Processing**     | OpenCV, NumPy                                              | For real-time video frame extraction and manipulation                   |
| **AI / Detection**       | YOLOv11 (via Ultralytics) – `yolol100.pt`, PyTorch         | Custom-trained object detection model for tomato leaf disease detection |
| **PDF Report Gen.**      | FPDF, Matplotlib, custom logic                             | For generating user-friendly flight reports                             |
| **Data Storage**         | Folder-based storage & SQLite (embedded)                   | Field progress, detection logs, and session data                        |
| **Graphics & Fonts**     | PNG logos, `arial_greek.ttf`                               | For UI elements and Greek text compatibility in reports                 |

---

## 🧪 How to Run

### 1. Clone the repository
git clone https://github.com/Theodoscus/droneUI.git
cd droneUI

### 2. Install dependencies
Copy
Edit
pip install -r requirements.txt
Make sure you also have PyTorch installed with GPU support if available.

### 3. Connect to the drone
Power on your DJI Tello EDU

Connect your computer to its Wi-Fi network

### 4. Launch the system
run python homepage.py

---

## 🧠 YOLOv11 Model
The model yolol100.pt is a YOLOv11-based object detector trained on a custom tomato dataset. It recognizes leaf diseases with high accuracy, even under varied lighting and conditions.

<img width="1856" height="1391" alt="2025-05-31_132832" src="https://github.com/user-attachments/assets/2e2fc0f0-16cb-46a1-8091-b92c134a790b" />

Frame analysis is triggered after the flight session ends and uses video_process.py to extract, detect, and store infected frames.

---

## 📊 Reports & Field Monitoring
After each flight, a PDF report is generated with:

List of detected diseases

Annotated images

Disease stats and frequency

Suggested treatments

The system keeps track of each field’s health history across time.

<img width="1200" height="1501" alt="2025-05-31_133257" src="https://github.com/user-attachments/assets/c886adc8-89a0-4ca5-9832-7c253d6e4524" />

## 📄 Thesis Summary
The system was evaluated in both controlled and real-world settings, with farmers comparing it to traditional inspection methods.
Key findings:

Inspection time was reduced by over 50%

Detection accuracy was much higher than the traditional inspection method

Farmers rated the system highly in terms of usability and usefulness

## ✉️ Contact
Theodosios Chronopoulos
📧 theodoschr@gmail.com
📍 University of Patras – Computer Engineering & Informatics Department

