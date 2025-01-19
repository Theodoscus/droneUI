from PyQt6.QtWidgets import (
    QMessageBox, QMainWindow, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget, QFrame, QGridLayout, QDialog, QSlider, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem
)
from PyQt6.QtCore import Qt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt
from reportlab.pdfgen import canvas
from datetime import datetime
import pandas as pd
import os
from datetime import datetime
from PyQt6.QtWidgets import QComboBox
from PyQt6.QtGui import QPixmap, QPainter
import subprocess
import platform
import sqlite3
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet
from countermeasures import CounterMeasuresWindow
from PyQt6.QtGui import QPainter, QFont
from PyQt6.QtPrintSupport import QPrinter
from field_progress import FieldProgressPage



class DroneReportApp(QMainWindow):
    def __init__(self, field_path):
        # Initialize the main application window
        super().__init__()
        self.setWindowTitle("Drone Flight Report")
        self.setGeometry(100, 50, 1200, 800)
        
        # Store the field path
        self.field_path = field_path
        
        # Set the runs folder inside the field path
        self.runs_folder = os.path.join(self.field_path, "runs")
        os.makedirs(self.runs_folder, exist_ok=True)  # Ensure the runs folder exists

        # Set up the main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout()
        
        # Load UI components
        self.setup_ui(main_layout)

        # Set layout to the main widget
        main_widget.setLayout(main_layout)

        # Load the newest flight data
        self.load_newest_flight_data()

    def setup_ui(self, main_layout): # Create the UI layout for the application
        
        # Header section: displays flight information and controls
        header_layout = QHBoxLayout()
        self.flight_time_label = QLabel("ΠΤΗΣΗ: ")
        self.flight_time_label.setStyleSheet("font-size: 16px; font-weight: bold; color: white;")
        header_layout.addWidget(self.flight_time_label, alignment=Qt.AlignmentFlag.AlignLeft)

    
        # Dropdown to select previous flight runs
        self.run_selector = QComboBox()
        self.run_selector.setStyleSheet("font-size: 14px; color: black; background-color: lightgray; padding: 5px;")
        self.run_selector.addItems(self.list_previous_runs())
        self.run_selector.currentTextChanged.connect(self.load_selected_run)
    

        header_layout.addWidget(self.run_selector, alignment=Qt.AlignmentFlag.AlignLeft)
        
        # Close button to exit the application
        close_button = QPushButton("Κλείσιμο")
        close_button.setStyleSheet("font-size: 14px; color: black; background-color: lightgray; padding: 5px 10px;")
        close_button.clicked.connect(self.close)
        header_layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignRight)

        main_layout.addLayout(header_layout)
        
        # Statistics section: displays key metrics for the flight
        stats_frame = QFrame()
        stats_frame.setStyleSheet("border: 1px solid gray; padding: 10px; background-color: #f5f5f5;")
        stats_layout = QGridLayout(stats_frame)

        # Labels for various statistics
        self.disease_count_label = QLabel("Ασθένειες που εντοπίστηκαν: ")
        self.plants_analyzed_label = QLabel("Φυτά που αναλύθηκαν: ")
        self.affected_plants_label = QLabel("Επηρεασμένα φυτά: ")

        for label in [self.disease_count_label, self.plants_analyzed_label, self.affected_plants_label]:
            label.setStyleSheet("font-size: 16px; padding: 5px; color: black;")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        stats_layout.addWidget(self.disease_count_label, 0, 0)
        stats_layout.addWidget(self.plants_analyzed_label, 0, 1)
        stats_layout.addWidget(self.affected_plants_label, 0, 2)

        main_layout.addWidget(stats_frame)

        # Chart section: displays a bar chart of disease data
        self.figure, self.ax = plt.subplots()
        self.canvas = FigureCanvas(self.figure)

        chart_frame = QFrame()
        chart_frame.setStyleSheet("border: 1px solid gray; padding: 10px;")
        chart_frame.setMinimumHeight(500)
        chart_layout = QVBoxLayout(chart_frame)
        chart_layout.addWidget(self.canvas)
        main_layout.addWidget(chart_frame)
        
        


        # Image section: shows images of affected plants
        image_frame = QFrame()
        image_frame.setStyleSheet("border: 1px solid gray; padding: 10px; background-color: #f9f9f9;")
        image_layout = QVBoxLayout(image_frame)
        
        
        
        # Label for the image section
        self.image_label = QLabel("Φύλλα με ασθένειες που εντοπίστηκαν στην πτήση")
        self.image_label.setStyleSheet("font-size: 16px; font-weight: bold; color: black;")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image_layout.addWidget(self.image_label)
        
        # Disease Information Box
        info_frame = QFrame()
        info_frame.setStyleSheet("border: 1px solid gray; padding: 10px; background-color: #f1f1f1;")
        info_layout = QVBoxLayout(info_frame)

        self.disease_label = QLabel("Disease: --")
        self.disease_label.setStyleSheet("font-size: 14px; font-weight: bold; color: black;")
        info_layout.addWidget(self.disease_label)

        self.plant_id_label = QLabel("Plant ID: --")
        self.plant_id_label.setStyleSheet("font-size: 14px; font-weight: bold; color: black;")
        info_layout.addWidget(self.plant_id_label)

        self.confidence_label = QLabel("Confidence: --%")
        self.confidence_label.setStyleSheet("font-size: 14px; font-weight: bold; color: black;")
        info_layout.addWidget(self.confidence_label)

        image_layout.addWidget(info_frame)  # Add the info frame above the image

        # Placeholder image
        self.placeholder_image = QLabel()
        self.placeholder_image.setStyleSheet("background-color: lightgray; border: 1px solid black; color: black;")
        self.placeholder_image.setFixedHeight(200)
        self.placeholder_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image_layout.addWidget(self.placeholder_image)

        # Button to view a larger version of the image with zoom
        fullscreen_button = QPushButton("Προβολή Μεγαλύτερης Εικόνας")
        fullscreen_button.setStyleSheet("font-size: 14px; background-color: #d9d9d9; color: black; padding: 5px;")
        fullscreen_button.clicked.connect(self.show_fullscreen_image)
        image_layout.addWidget(fullscreen_button)
        main_layout.addWidget(image_frame)
          
        # Navigation Buttons
        nav_buttons_layout = QHBoxLayout()

        prev_button = QPushButton("Προηγούμενο")
        prev_button.setStyleSheet("font-size: 14px; background-color: #d9d9d9; color: black; padding: 5px;")
        prev_button.clicked.connect(lambda: self.navigate_photos("prev"))
        nav_buttons_layout.addWidget(prev_button)

        next_button = QPushButton("Επόμενο")
        next_button.setStyleSheet("font-size: 14px; background-color: #d9d9d9; color: black; padding: 5px;")
        next_button.clicked.connect(lambda: self.navigate_photos("next"))
        nav_buttons_layout.addWidget(next_button)

        image_layout.addLayout(nav_buttons_layout)



        

        # Button to play the flight video in an external player
        external_player_button = QPushButton("Αναπαραγωγή Καταγραφής Πτήσης")
        external_player_button.setStyleSheet("font-size: 14px; background-color: #d9d9d9; color: black; padding: 10px;")
        external_player_button.clicked.connect(self.open_video_in_external_player)
        main_layout.addWidget(external_player_button)

        
        # Footer section: contains additional actions and flight duration
        footer_layout = QHBoxLayout()

        # Button to export the flight data to a PDF report
        export_pdf_button = QPushButton("Εξαγωγή αναφοράς σε PDF")
        export_pdf_button.setStyleSheet("font-size: 14px; background-color: #d9d9d9; color: black; padding: 10px;")
        export_pdf_button.clicked.connect(self.export_to_pdf)
        footer_layout.addWidget(export_pdf_button)

        # Label to display flight duration
        self.flight_duration_label = QLabel("Διάρκεια Πτήσης: --:--:--")
        self.flight_duration_label.setStyleSheet("font-size: 14px; color: white; padding: 10px;")
        self.flight_duration_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer_layout.addWidget(self.flight_duration_label)
        
        # Button for countermeasures or additional actions
        countermeasures_button = QPushButton("Τρόποι αντιμετώπισης")
        countermeasures_button.setStyleSheet("font-size: 14px; background-color: #d9d9d9; color: black; padding: 10px;")
        countermeasures_button.clicked.connect(self.show_countermeasures)
        footer_layout.addWidget(countermeasures_button)
        
        

        main_layout.addLayout(footer_layout)
        progress_button = QPushButton("View Field Health Progress")
        progress_button.setStyleSheet("font-size: 14px; background-color: #d9d9d9; color: black; padding: 10px;")
        progress_button.clicked.connect(self.open_field_progress_page)
        main_layout.addWidget(progress_button)

        
    def load_newest_flight_data(self):
        # Load the newest flight data from the runs directory
        if not os.path.exists(self.runs_folder):
            print(f"No runs directory found in {self.runs_folder}.")
            return

        # List all run folders sorted by timestamp (newest first)
        flight_folders = [
            f for f in os.listdir(self.runs_folder)
            if os.path.isdir(os.path.join(self.runs_folder, f)) and f.startswith("run_")
        ]
        if not flight_folders:
            print("No flight data found.")
            return

        # Select the newest flight folder
        flight_folders.sort(reverse=True)
        newest_flight = os.path.join(self.runs_folder, flight_folders[0])
        print(f"Loading data from: {newest_flight}")
        self.load_results(newest_flight)


    def open_field_progress_page(self):
        self.progress_page = FieldProgressPage(self.field_path)
        self.progress_page.show()
    
    def draw_chart(self, categories=None, values=None):
        # Greek disease name mapping from the file
        disease_translation = {
            "Healthy": "Υγιή",
            "Early Βlight": "Αλτερναρίωση",
            "Late Βlight": "Περονόσπορος",
            "Bacterial Spot": "Βακτηριακή Κηλίδωση",
            "Leaf Mold": "Κλαδοσπορίωση",
            "Leaf_Miner": "Φυλλοκνίστης",
            "Mosaic Virus": "Ιός του Μωσαικού",
            "Septoria": "Αδηλομήκυτας",
            "Spider Mites": "Τετράνυχος",
            "Yellow Leaf Curl Virus": "Ιός του Κίτρινου Καρουλιάσματος"
        }

        if categories is None or values is None:
            categories = []
            values = []

        self.ax.clear()  # Clear any existing chart

        # Ensure "Healthy" is included in the chart
        if "Healthy" not in categories:
            categories.append("Υγιή")
            values.append(0)

        # Translate category names to Greek if available
        translated_categories = [
            disease_translation.get(category, category) for category in categories
        ]

        # Determine maximum value for scaling the chart
        max_value = max(values) if values else 0
        y_max = max_value + 100  # Add some padding for better visibility

        # Draw the bars and add value annotations
        bars = self.ax.bar(translated_categories, values, color="gray")

        # Add labels above bars
        for bar, value in zip(bars, values):
            self.ax.annotate(
                f"{value}",
                xy=(bar.get_x() + bar.get_width() / 2, value),
                xytext=(0, 5),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=10,
            )

        # Set chart title and labels
        self.ax.set_title("Κατάσταση Φύλλων", fontsize=16)
        self.ax.set_ylabel("Αριθμός Φύλλων", fontsize=12)
        self.ax.set_xticks(range(len(translated_categories)))
        self.ax.set_xticklabels(translated_categories, rotation=30, ha="right", fontsize=10, wrap=True)
        self.ax.set_ylim(0, y_max)

        # Adjust chart layout and update the canvas
        self.figure.subplots_adjust(bottom=0.4, top=0.9)
        self.canvas.draw()





    def update_flight_data(self, flight_time, diseases, plants_analyzed, affected_plants):
        # Update flight statistics displayed in the UI
        try:
            # Parse and format the flight time from the provided data
            combined_time = f"{flight_time[1]}_{flight_time[2]}"  
            formatted_time = datetime.strptime(combined_time, "%Y%m%d_%H%M%S").strftime("%d/%m/%Y %H:%M:%S")
        except ValueError:
            formatted_time = "Unknown"  # Fallback in case of parsing issues

        # Update the UI labels with the new data
        self.flight_time_label.setText(f"ΠΤΗΣΗ: {formatted_time}")
        self.disease_count_label.setText(f"Ασθένειες που εντοπίστηκαν: {diseases}")
        self.plants_analyzed_label.setText(f"Φύλλα που αναλύθηκαν: {plants_analyzed}")
        self.affected_plants_label.setText(f"Επηρεασμένα φύλλα: {affected_plants}")


    

    

    def export_to_pdf(self, filename="report.pdf"):
       print("empty")








    def save_chart_as_image(self, filename="chart.png"):
        """
        Save the chart to a file as an image.
        """
        self.figure.savefig(filename, bbox_inches="tight", dpi=300)




    def show_countermeasures(self):
        
        disease_translation = {
            "Early blight": "Αλτερναρίωση",
            "Late blight": "Περονόσπορος",
            "Bacterial Spot": "Βακτηριακή Κηλίδωση",
            "Leaf Mold": "Κλαδοσπορίωση",
            "Leaf_Miner": "Φυλλοκνίστης",
            "Mosaic Virus": "Ιός του Μωσαϊκού",
            "Septoria": "Αδηλομήκυτας",
            "Spider Mites": "Τετράνυχος",
            "Yellow Leaf Curl Virus": "Ιός του Κίτρινου Καρουλιάσματος"
        }
        # Path to the SQLite database
        db_path = os.path.join(self.current_flight_folder, "flight_data.db")
        if not os.path.exists(db_path):
            QMessageBox.warning(self, "Σφάλμα", "Η βάση δεδομένων πτήσης δεν βρέθηκε.")
            return

        # Query to get non-healthy diseases with higher confidence
        query = """
            SELECT ID,
                MAX(CASE WHEN Class = 'Healthy' THEN Confidence ELSE 0 END) AS HealthyConfidence,
                MAX(CASE WHEN Class != 'Healthy' THEN Confidence ELSE 0 END) AS NonHealthyConfidence,
                MAX(CASE WHEN Class != 'Healthy' THEN Class ELSE NULL END) AS NonHealthyClass
            FROM flight_results
            GROUP BY ID
            HAVING NonHealthyConfidence > HealthyConfidence
        """

        conn = sqlite3.connect(db_path)
        results = pd.read_sql_query(query, conn)
        conn.close()

        # Extract unique non-healthy diseases and translate them to Greek
        diseases = results["NonHealthyClass"].dropna().unique().tolist()
        translated_diseases = [disease_translation.get(disease, disease) for disease in diseases]

        if not translated_diseases:
            QMessageBox.information(self, "Δεν Βρέθηκαν Ασθένειες", "Δεν ανιχνεύθηκαν μη υγιή φυτά σε αυτή την πτήση.")
            return

        # Open the CounterMeasuresWindow with Greek disease names
        countermeasures_window = CounterMeasuresWindow(translated_diseases, self)
        countermeasures_window.exec()



        
    def load_results(self, flight_folder):
        # Load flight data from the specified folder and display it in the UI
        db_path = os.path.join(flight_folder, "flight_data.db") # Path to the SQLite database
        photos_folder = os.path.join(flight_folder, "photos") # Path to the photos directory
        self.current_flight_folder = flight_folder  # Store the current flight folder

        if not os.path.exists(db_path):
            print(f"Database not found: {db_path}") # Log an error if the database is missing
            return

        conn = sqlite3.connect(db_path) # Connect to the SQLite database

        # Query all flight results
        query = "SELECT * FROM flight_results"
        results = pd.read_sql_query(query, conn)

        # Keep only the entry with the highest confidence for each ID
        results = results.loc[results.groupby("ID")["Confidence"].idxmax()]

        # Count diseases, ensuring "Healthy" is included
        disease_counts = results["Class"].value_counts()
        if "Healthy" not in disease_counts:
            disease_counts["Healthy"] = 0

        # Calculate total and affected plants
        total_plants = results["ID"].nunique()
        affected_plants = total_plants - disease_counts["Healthy"]

        # Get unique disease classes excluding Healthy
        unique_diseases = len(disease_counts) - 1 if "Healthy" in disease_counts else len(disease_counts)

        # Update the statistics in the GUI
        self.update_flight_data(
            flight_time=flight_folder.split("_"),  # Extract the timestamp from the folder name
            diseases=unique_diseases,
            plants_analyzed=total_plants,
            affected_plants=affected_plants,
        )

        # Draw the chart
        self.draw_chart(categories=disease_counts.index.tolist(), values=disease_counts.values.tolist())

        # Load and display photos of affected plants
        self.load_photos(photos_folder, db_path)

        # Update the flight duration in the UI
        if "FlightDuration" in results.columns:
            duration = results["FlightDuration"].iloc[0]
            self.flight_duration_label.setText(f"Διάρκεια Πτήσης: {duration}")

        conn.close() # Close the database connection

    def load_photos(self, photos_folder, db_path):
        # Load photos of plants where the highest confidence class is affected (non-healthy)
        if not os.path.exists(photos_folder):
            print(f"Photos folder not found: {photos_folder}")
            self.placeholder_image.setText("No photos available")
            return

        if not os.path.exists(db_path):
            print(f"Database not found: {db_path}")
            self.placeholder_image.setText("No results available")
            return

        conn = sqlite3.connect(db_path) # Connect to the SQLite database

        # Query to get the highest confidence class for each ID
        query = """
            SELECT ID, 
                MAX(CASE WHEN Class = 'Healthy' THEN Confidence ELSE 0 END) AS HealthyConfidence,
                MAX(CASE WHEN Class != 'Healthy' THEN Confidence ELSE 0 END) AS NonHealthyConfidence
            FROM flight_results
            GROUP BY ID
        """
        results = pd.read_sql_query(query, conn)
        conn.close()

        # Filter IDs where the highest confidence is for a non-healthy class
        affected_ids = results[results["NonHealthyConfidence"] > results["HealthyConfidence"]]["ID"].tolist()

        # Get photos corresponding to affected IDs
        photo_files = [
            f for f in os.listdir(photos_folder)
            if f.endswith(".jpg") and int(f.split("_ID")[-1].replace(".jpg", "")) in affected_ids
        ]
        

        if not photo_files:
            self.placeholder_image.setText("No photos of affected plants available")
            return

        self.photo_files = photo_files  # Store photo file names
        self.photo_index = 0  # Initialize photo index
        self.photos_folder = photos_folder  # Store photos folder path
        self.update_carousel_image()  # Display the first image





    def update_carousel_image(self):
        # Update the displayed image in the carousel
        if not hasattr(self, 'photo_files') or not self.photo_files:
            return

        # Get the current photo file
        photo_file = os.path.join(self.photos_folder, self.photo_files[self.photo_index])

        # Extract details from the database
        conn = sqlite3.connect(os.path.join(self.current_flight_folder, "flight_data.db"))
        cursor = conn.cursor()

        # Retrieve the plant ID from the photo filename
        plant_id = int(photo_file.split("_ID")[-1].replace(".jpg", ""))

        # Query the database for details of the selected plant
        query = "SELECT Class, Confidence FROM flight_results WHERE ID = ? ORDER BY Confidence DESC LIMIT 1"
        cursor.execute(query, (plant_id,))
        result = cursor.fetchone()

        # Greek disease name mapping
        disease_translation = {
            "Early blight": "Αλτερναρίωση",
            "Late blight": "Περονόσπορος",
            "Bacterial Spot": "Βακτηριακή Κηλίδωση",
            "Leaf Mold": "Κλαδοσπορίωση",
            "Leaf_Miner": "Φυλλοκνίστης",
            "Mosaic Virus": "Ιός του Μωσαικού",
            "Septoria": "Αδηλομήκυτας",
            "Spider Mites": "Τετράνυχος",
            "Yellow Leaf Curl Virus": "Ιός του Κίτρινου Καρουλιάσματος",
        }

        if result:
            disease, confidence = result
            translated_disease = disease_translation.get(disease, disease)  # Translate disease if possible
            self.disease_label.setText(f"Ασθένεια: {translated_disease}")
            self.plant_id_label.setText(f"ID Φυτού: {plant_id}")
            self.confidence_label.setText(f"Βεβαιότητα: {confidence * 100:.2f}%")
        else:
            self.disease_label.setText("Ασθένεια: --")
            self.plant_id_label.setText("ID Φυτού: --")
            self.confidence_label.setText("Βεβαιότητα: --%")

        conn.close()

        # Load and display the image
        pixmap = QPixmap(photo_file)
        if not pixmap.isNull():
            self.placeholder_image.setPixmap(pixmap.scaled(self.placeholder_image.size(), Qt.AspectRatioMode.KeepAspectRatio))
        else:
            self.placeholder_image.setText("Σφάλμα φόρτωσης εικόνας")



    def navigate_photos(self, direction):
        # Navigate through the photos in the carousel
        if not hasattr(self, 'photo_files') or not self.photo_files:
            return

        # Update the photo index based on the direction
        if direction == "next":
            self.photo_index = (self.photo_index + 1) % len(self.photo_files)
        elif direction == "prev":
            self.photo_index = (self.photo_index - 1) % len(self.photo_files)

        self.update_carousel_image() # Update the displayed image


    def list_previous_runs(self):
        # List all previous runs in the runs folder
        if not os.path.exists(self.runs_folder):
            print(f"No runs found in {self.runs_folder}")
            return []

        # Get all run folders
        runs = [
            f for f in os.listdir(self.runs_folder)
            if os.path.isdir(os.path.join(self.runs_folder, f)) and f.startswith("run_")
        ]

        # Sort by timestamp (newest first)
        runs.sort(reverse=True)

        # Create a mapping of raw run names to formatted names
        self.run_name_mapping = {}
        for run in runs:
            try:
                # Extract the timestamp from the folder name
                timestamp = run.split("_")[1]
                time_part = run.split("_")[2]
                flight_datetime = datetime.strptime(timestamp + time_part, "%Y%m%d%H%M%S")
                formatted_name = f"Πτήση: {flight_datetime.strftime('%d/%m/%Y %H:%M:%S')}"
                self.run_name_mapping[formatted_name] = run
            except (IndexError, ValueError):
                print(f"Invalid folder name format: {run}")
                continue

        # Return only formatted names for display
        return list(self.run_name_mapping.keys())





    def load_selected_run(self):
        # Get the selected run from the dropdown menu
        selected_run = self.run_selector.currentText()
        if not selected_run:
            QMessageBox.warning(self, "No Run Selected", "Please select a run to load.")
            return

        # Map the selected run to its corresponding folder
        raw_run_name = self.run_name_mapping.get(selected_run, None)
        if not raw_run_name:
            QMessageBox.critical(
                self, "Invalid Run", f"The selected run could not be mapped to a valid folder."
            )
            return

        selected_run_folder = os.path.join(self.runs_folder, raw_run_name)
        if not os.path.exists(selected_run_folder):
            QMessageBox.critical(
                self, "Invalid Run", f"The selected run folder does not exist: {selected_run_folder}"
            )
            return

        # Load the results from the selected run
        try:
            self.load_results(selected_run_folder)
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred while loading the run: {e}")



        
    def show_fullscreen_image(self):
        # Display the current image in a zoomable window
        if not hasattr(self, 'photo_files') or not self.photo_files:
                return

        # Get the current photo file
        photo_file = os.path.join(self.photos_folder, self.photo_files[self.photo_index])

        try:
            # Create and show the zoomable image dialog
            dialog = ZoomableImageDialog(photo_file, self)
            dialog.exec()
        except ValueError as e:
            print(e)
        
 

    def open_video_in_external_player(self):
        # Open the flight video in an external media player
        if not self.current_flight_folder:
            print("No flight data loaded.")
            return

        # Check for supported video formats in the flight folder
        video_formats = [".mp4", ".mov", ".avi"]
        for ext in video_formats:
            potential_path = os.path.join(self.current_flight_folder, f"processed_video{ext}")
            if os.path.exists(potential_path):
                video_path = potential_path
                break

        if not video_path:
            print("Flight video not found.")
            return

        # Open the video using the appropriate command for the OS
        try:
            # Windows
            if platform.system() == "Windows":
                os.startfile(video_path)
            # macOS
            elif platform.system() == "Darwin":
                subprocess.run(["open", video_path])
            # Linux
            elif platform.system() == "Linux":
                subprocess.run(["xdg-open", video_path])
            else:
                print("Unsupported operating system.")
        except Exception as e:
            print(f"Error opening video: {e}")





class ZoomableImageDialog(QDialog):
    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Image Viewer")
        self.image_path = image_path

        # Load the image
        self.pixmap = QPixmap(image_path)
        if self.pixmap.isNull():
            raise ValueError("Error loading image")

        # Set up the layout
        layout = QVBoxLayout(self)

        # Create a QGraphicsView for displaying the image
        self.graphics_view = QGraphicsView(self)
        self.graphics_scene = QGraphicsScene(self)
        self.pixmap_item = QGraphicsPixmapItem(self.pixmap)
        self.graphics_scene.addItem(self.pixmap_item)
        self.graphics_view.setScene(self.graphics_scene)

        # Enable mouse dragging for panning
        self.graphics_view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.graphics_view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        layout.addWidget(self.graphics_view)

        # Add a slider for zoom control
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.zoom_slider.setMinimum(50)  # Minimum zoom: 50%
        self.zoom_slider.setMaximum(200)  # Maximum zoom: 200%
        self.zoom_slider.setValue(150)  # Default zoom: 150%
        self.zoom_slider.valueChanged.connect(self.zoom_image)
        layout.addWidget(self.zoom_slider)

        # Add a close button
        close_button = QPushButton("Close", self)
        close_button.setStyleSheet("font-size: 14px; background-color: #d9d9d9; color: black; padding: 5px;")
        close_button.clicked.connect(self.close)
        layout.addWidget(close_button)

        self.setMinimumSize(self.pixmap.width(), self.pixmap.height())

    def zoom_image(self, value):
        # Zoom the image based on the slider value
        scale_factor = value / 100.0
        self.graphics_view.resetTransform()  # Reset any existing transformations
        self.graphics_view.scale(scale_factor, scale_factor)  # Apply new scale

        



    