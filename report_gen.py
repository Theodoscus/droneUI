from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget, QFrame, QGridLayout, QDialog, QSlider, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem
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

class DroneReportApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Drone Flight Report")
        self.setGeometry(100, 100, 1200, 800)

        #Main Widget
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout()
        
        #Load UI components
        self.setup_ui(main_layout)

        #Set layout to the main widget
        main_widget.setLayout(main_layout)

        #Load the newest flight data
        self.load_newest_flight_data()

    def setup_ui(self, main_layout):
        #Header Section
        header_layout = QHBoxLayout()
        self.flight_time_label = QLabel("ΠΤΗΣΗ: ")
        self.flight_time_label.setStyleSheet("font-size: 16px; font-weight: bold; color: white;")
        header_layout.addWidget(self.flight_time_label, alignment=Qt.AlignmentFlag.AlignLeft)

        self.run_selector = QComboBox()
        self.run_selector.setStyleSheet("font-size: 14px; color: black; background-color: lightgray; padding: 5px;")
        self.run_selector.addItems(self.list_previous_runs())
        self.run_selector.currentTextChanged.connect(self.load_selected_run)
        header_layout.addWidget(self.run_selector, alignment=Qt.AlignmentFlag.AlignLeft)
        
        close_button = QPushButton("Κλείσιμο")
        close_button.setStyleSheet("font-size: 14px; color: black; background-color: lightgray; padding: 5px 10px;")
        close_button.clicked.connect(self.close)
        header_layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignRight)

        main_layout.addLayout(header_layout)
        
        #Top Statistics Section
        stats_frame = QFrame()
        stats_frame.setStyleSheet("border: 1px solid gray; padding: 10px; background-color: #f5f5f5;")
        stats_layout = QGridLayout(stats_frame)

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

        #Bar Chart Section
        self.figure, self.ax = plt.subplots()
        self.canvas = FigureCanvas(self.figure)

        chart_frame = QFrame()
        chart_frame.setStyleSheet("border: 1px solid gray; padding: 10px;")
        chart_frame.setMinimumHeight(400)
        chart_layout = QVBoxLayout(chart_frame)
        chart_layout.addWidget(self.canvas)
        main_layout.addWidget(chart_frame)

        #Image Section
        
        image_frame = QFrame()
        image_frame.setStyleSheet("border: 1px solid gray; padding: 10px; background-color: #f9f9f9;")
        image_layout = QVBoxLayout(image_frame)

        self.image_label = QLabel("Φύλλα με ασθένειες που εντοπίστηκαν στην πτήση")
        self.image_label.setStyleSheet("font-size: 16px; font-weight: bold; color: black;")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image_layout.addWidget(self.image_label)

        self.placeholder_image = QLabel()
        self.placeholder_image.setStyleSheet("background-color: lightgray; border: 1px solid black; color: black;")
        self.placeholder_image.setFixedHeight(200)
        self.placeholder_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image_layout.addWidget(self.placeholder_image)

        fullscreen_button = QPushButton("Προβολή Μεγαλύτερης Εικόνας")
        fullscreen_button.setStyleSheet("font-size: 14px; background-color: #d9d9d9; color: black; padding: 5px;")
        fullscreen_button.clicked.connect(self.show_fullscreen_image)
        image_layout.addWidget(fullscreen_button)
        main_layout.addWidget(image_frame)
          
        #Navigation Buttons
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



        

        # Open in External Player Button
        external_player_button = QPushButton("Αναπαραγωγή Καταγραφής Πτήσης")
        external_player_button.setStyleSheet("font-size: 14px; background-color: #d9d9d9; color: black; padding: 5px;")
        external_player_button.clicked.connect(self.open_video_in_external_player)
        main_layout.addWidget(external_player_button)

        
        #Footer Section
        footer_layout = QHBoxLayout()

        export_pdf_button = QPushButton("Εξαγωγή αναφοράς σε PDF")
        export_pdf_button.setStyleSheet("font-size: 14px; background-color: #d9d9d9; color: black; padding: 10px;")
        export_pdf_button.clicked.connect(self.export_to_pdf)
        footer_layout.addWidget(export_pdf_button)

        footer_layout.addStretch()

        countermeasures_button = QPushButton("Τρόποι αντιμετώπισης")
        countermeasures_button.setStyleSheet("font-size: 14px; background-color: #d9d9d9; color: black; padding: 10px;")
        footer_layout.addWidget(countermeasures_button)

        main_layout.addLayout(footer_layout)

        
    def load_newest_flight_data(self):
        """Load the newest flight data from the runs directory."""
        runs_dir = "runs"  
        
        
        if not os.path.exists(runs_dir):
            print("No runs directory found.")
            return

        #Get all flight folders sorted by timestamp
        flight_folders = [
            f for f in os.listdir(runs_dir)
            if os.path.isdir(os.path.join(runs_dir, f)) and f.startswith("run_")
        ]
        if not flight_folders:
            print("No flight data found.")
            return

        #Sort folders by timestamp (newest first)
        flight_folders.sort(reverse=True)
        newest_flight = os.path.join(runs_dir, flight_folders[0])

        #Load the newest flight data to display
        print(f"Loading data from: {newest_flight}")
        self.load_results(newest_flight)

    
    def draw_chart(self, categories=None, values=None):
        #Δημιουργία γραφήματος με δεδομένα που παρέχονται από την πτήση 
        if categories is None:
            categories = ["Κατηγορία 1", "Κατηγορία 2"]
        if values is None:
            values = [0, 0]

        self.ax.clear()
        
           #Υπολογισμός της μέγιστης τιμής για τον κάθετο άξονα
        max_value = max(values)
        y_max = max_value + 100  #Προσθήκη 100 στη μέγιστη τιμή για καλύτερη προβολή

        #Δημιουργία γραφήματος
        bars = self.ax.bar(categories, values, color='gray')

        #Ρυθμίσεις τίτλων και αξόνων
        self.ax.set_title("Κατάσταση Φύλλων", fontsize=16)
        self.ax.set_ylabel("Αριθμός Φύλλων", fontsize=12)
        self.ax.set_xticks(range(len(categories)))
        self.ax.set_xticklabels(categories, rotation=45, ha="right", fontsize=10)

        self.ax.set_ylim(0, y_max)
        
        #Εμφάνιση τιμών πάνω από κάθε στήλη
        for bar, value in zip(bars, values):
            self.ax.annotate(
                f'{value}',  #Το κείμενο που θα εμφανιστεί
                xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),  #Συντεταγμένες
                xytext=(0, 5),  #Απόσταση από τη στήλη
                textcoords="offset points",  #Το κείμενο τοποθετείται σχετικά με το σημείο
                ha='center', va='bottom', fontsize=10  #Κέντρο και μέγεθος γραμματοσειράς
            )

        #Προσαρμογή διαστήματος για τις ετικέτες
        self.figure.subplots_adjust(bottom=0.3, top=0.9)

        #Ενημέρωση του καμβά
        self.canvas.draw()


    def update_flight_data(self, flight_time, diseases, plants_analyzed, affected_plants):
        #Ενημερώνει τα δεδομένα της πτήσης.
        try:
            #Combine date and time into a single string and parse it
            combined_time = f"{flight_time[1]}_{flight_time[2]}"  # e.g., "20250109_101230"
            formatted_time = datetime.strptime(combined_time, "%Y%m%d_%H%M%S").strftime("%d/%m/%Y %H:%M:%S")
        except ValueError:
            formatted_time = "Unknown"  # Fallback in case of parsing issues

        # Update the labels
        self.flight_time_label.setText(f"ΠΤΗΣΗ: {formatted_time}")
        self.disease_count_label.setText(f"Ασθένειες που εντοπίστηκαν: {diseases}")
        self.plants_analyzed_label.setText(f"Φύλλα που αναλύθηκαν: {plants_analyzed}")
        self.affected_plants_label.setText(f"Επηρεασμένα φύλλα: {affected_plants}")


    def export_to_pdf(self): #Εξαγωγή σε PDF (δεν έχει ολοκληρωθεί)
        pdf_file = "flight_report.pdf"
        c = canvas.Canvas(pdf_file)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, 800, "Αναφορά Πτήσης")
        c.setFont("Helvetica", 12)
        c.drawString(50, 780, f"Ημερομηνία: {self.flight_time_label.text()}")
        c.drawString(50, 750, f"{self.disease_count_label.text()}")
        c.drawString(50, 730, f"{self.plants_analyzed_label.text()}")
        c.drawString(50, 710, f"{self.affected_plants_label.text()}")
        c.save()
        print(f"PDF saved to {pdf_file}")
    
    

    def load_results(self, output_folder):
        """Loads and displays the results from the video processing."""
        #Path to the tracked_data.csv file
        self.current_flight_folder = output_folder
        results_file = os.path.join(output_folder, "tracked_data.csv")
        photos_folder = os.path.join(output_folder, "photos")
        #Check if the results file exists
        if not os.path.exists(results_file):
            print(f"Results file not found: {results_file}")
            return

        #Load results from the file
        results = pd.read_csv(results_file)

        #Retain only the row with the highest confidence for each ID
        filtered_results = results.loc[results.groupby("ID")["Confidence"].idxmax()]

        #Count diseases, ensuring "Healthy" is included
        disease_counts = filtered_results["Class"].value_counts()

        #Add "Healthy" to the disease counts if missing
        if "Healthy" not in disease_counts:
            disease_counts["Healthy"] = 0

        #Aggregate statistics
        total_plants = results["ID"].nunique()  #Count of unique plants analyzed
        healthy_plants = filtered_results[filtered_results["Class"] == "Healthy"]["ID"].nunique()  #Unique healthy plants
        affected_plants = total_plants - healthy_plants  #Affected plants are those not healthy

        #Remove "Healthy" from the disease count for unique diseases detected
        unique_diseases = len(disease_counts) - (1 if "Healthy" in disease_counts else 0)

        #Update the report with aggregated data
        self.update_flight_data(
            flight_time=output_folder.split("_"),  # Extract timestamp from folder name
            diseases=unique_diseases,
            plants_analyzed=total_plants,
            affected_plants=affected_plants,
        )

        #Update the bar chart with unique counts
        self.draw_chart(categories=disease_counts.index.tolist(), values=disease_counts.values.tolist())

        #Load photos of detected objects
        self.load_photos(photos_folder, results_file)



    def load_photos(self, photos_folder, results_file):
        """Load photos of non-healthy plants from the photos folder."""
        if not os.path.exists(photos_folder):
            print(f"Photos folder not found: {photos_folder}")
            self.image_label.setText("No photos available")
            return

        if not os.path.exists(results_file):
            print(f"Results file not found: {results_file}")
            self.image_label.setText("No results available")
            return

        # Load results and filter out healthy plants
        results = pd.read_csv(results_file)
        non_healthy_ids = results[results["Class"] != "Healthy"]["ID"].unique()

        # Get the list of photo files for non-healthy plants
        photo_files = [
            f for f in os.listdir(photos_folder)
            if f.endswith(".jpg") and int(f.split("_ID")[-1].replace(".jpg", "")) in non_healthy_ids
        ]

        if not photo_files:
            self.image_label.setText("No photos of non-healthy plants available")
            return

        # Initialize carousel
        self.photo_files = photo_files
        self.photo_index = 0
        self.photos_folder = photos_folder

        # Display the first photo
        self.update_carousel_image()

    def update_carousel_image(self):
        """Update the displayed image in the carousel."""
        if not hasattr(self, 'photo_files') or not self.photo_files:
            return

        # Get the current photo file
        photo_file = os.path.join(self.photos_folder, self.photo_files[self.photo_index])

        # Load and display the image
        pixmap = QPixmap(photo_file)
        if not pixmap.isNull():
            self.placeholder_image.setPixmap(pixmap.scaled(self.placeholder_image.size(), Qt.AspectRatioMode.KeepAspectRatio))
        else:
            self.placeholder_image.setText("Error loading image")

    def navigate_photos(self, direction):
        """Navigate through the photos in the carousel."""
        if not hasattr(self, 'photo_files') or not self.photo_files:
            return

    # Update the photo index
        if direction == "next":
            self.photo_index = (self.photo_index + 1) % len(self.photo_files)
        elif direction == "prev":
            self.photo_index = (self.photo_index - 1) % len(self.photo_files)

        self.update_carousel_image()


    from datetime import datetime

    def list_previous_runs(self, base_folder="runs"):
        """List all previous runs with formatted date and time."""
        if not os.path.exists(base_folder):
            print(f"No runs found in {base_folder}")
            return []

        # Get all run folders
        runs = [
            f for f in os.listdir(base_folder)
            if os.path.isdir(os.path.join(base_folder, f)) and f.startswith("run_")
        ]

        # Sort by timestamp (newest first)
        runs.sort(reverse=True)

        # Format as "Πτήση: ημερομηνία ώρα"
        formatted_runs = []
        for run in runs:
            try:
                # Extract the timestamp from the folder name (e.g., "run_20250109_101230")
                timestamp = run.split("_")[1]
                time_part = run.split("_")[2]
                flight_datetime = datetime.strptime(timestamp + time_part, "%Y%m%d%H%M%S")
                formatted_runs.append(f"Πτήση: {flight_datetime.strftime('%d/%m/%Y %H:%M:%S')}")
            except (IndexError, ValueError):
                print(f"Invalid folder name format: {run}")
                continue

        return formatted_runs



    def load_selected_run(self, selected_run):
        """Load and display the results from the selected run."""
        base_folder = "runs"

        # Extract date and time from the selected run (e.g., "Πτήση: 09/01/2025 10:12:30")
        if not selected_run.startswith("Πτήση:"):
            return

        selected_datetime = selected_run.split(": ")[1]
        try:
            formatted_datetime = datetime.strptime(selected_datetime, "%d/%m/%Y %H:%M:%S").strftime("%Y%m%d_%H%M%S")
        except ValueError:
            print(f"Invalid datetime format: {selected_datetime}")
            return

        # Find the corresponding folder
        matching_folders = [
            f for f in os.listdir(base_folder)
            if f.startswith(f"run_{formatted_datetime}")
        ]
        if not matching_folders:
            print(f"No matching folder found for datetime: {selected_datetime}")
            return

        # Load the results from the first matching folder
        self.load_results(os.path.join(base_folder, matching_folders[0]))


    def create_image_controls(self, image_layout):
        """Create zoom and full-screen controls."""
        # Full-Screen Button
        fullscreen_button = QPushButton("Full Screen")
        fullscreen_button.setStyleSheet("font-size: 14px; background-color: #d9d9d9; color: black; padding: 5px;")
        fullscreen_button.clicked.connect(self.show_fullscreen_image)
        image_layout.addWidget(fullscreen_button)

        # Zoom Slider
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setMinimum(50)  # 50% zoom
        self.zoom_slider.setMaximum(200)  # 200% zoom
        self.zoom_slider.setValue(100)  # Default zoom level (100%)
        self.zoom_slider.valueChanged.connect(self.update_zoom)
        image_layout.addWidget(self.zoom_slider)
    
    def update_zoom(self, value):
        """Update the zoom level of the displayed image."""
        if not hasattr(self, 'photo_files') or not self.photo_files:
            return

        # Get the current photo file
        photo_file = os.path.join(self.photos_folder, self.photo_files[self.photo_index])

        # Load and scale the image based on the zoom level
        pixmap = QPixmap(photo_file)
        if not pixmap.isNull():
            scaled_pixmap = pixmap.scaled(
                self.placeholder_image.size() * (value / 100),
                Qt.AspectRatioMode.KeepAspectRatio
            )
            self.placeholder_image.setPixmap(scaled_pixmap)
        else:
            self.placeholder_image.setText("Error loading image")
    
    def show_fullscreen_image(self):
        """Display the current image in a zoomable window."""
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
        """Open the flight video in an external media player."""
        if self.current_flight_folder is None:
            print("No flight data loaded.")
            return

        video_path = os.path.join(self.current_flight_folder, "processed_video.mp4")
        if not os.path.exists(video_path):
            print("Flight video not found.")
            return

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
        self.zoom_slider.setValue(100)  # Default zoom: 100%
        self.zoom_slider.valueChanged.connect(self.zoom_image)
        layout.addWidget(self.zoom_slider)

        # Add a close button
        close_button = QPushButton("Close", self)
        close_button.setStyleSheet("font-size: 14px; background-color: #d9d9d9; color: black; padding: 5px;")
        close_button.clicked.connect(self.close)
        layout.addWidget(close_button)

        self.setMinimumSize(self.pixmap.width(), self.pixmap.height())

    def zoom_image(self, value):
        """Zoom the image based on the slider value."""
        scale_factor = value / 100.0
        self.graphics_view.resetTransform()  # Reset any existing transformations
        self.graphics_view.scale(scale_factor, scale_factor)  # Apply new scale

        
if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication

    # Create the application
    app = QApplication(sys.argv)

    # Instantiate and show the DroneReportApp
    report_app = DroneReportApp()
    report_app.show()

    # Execute the application
    sys.exit(app.exec())


    