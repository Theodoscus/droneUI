from PyQt6.QtWidgets import (
    QApplication, QMessageBox, QMainWindow, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget, QFrame, QGridLayout, QDialog, QSlider, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem
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

        self.flight_duration_label = QLabel("Διάρκεια Πτήσης: --:--:--")
        self.flight_duration_label.setStyleSheet("font-size: 14px; color: white; padding: 10px;")
        self.flight_duration_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer_layout.addWidget(self.flight_duration_label)
        
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
        print(newest_flight)

        #Load the newest flight data to display
        print(f"Loading data from: {newest_flight}")
        self.load_results(newest_flight)

    
    def draw_chart(self, categories=None, values=None):
        """Create a bar chart with the provided data."""
        if categories is None or values is None:
            categories = []
            values = []

        self.ax.clear()

        # Ensure "Healthy" appears in the chart
        if "Healthy" not in categories:
            categories.append("Healthy")
            values.append(0)

        max_value = max(values) if values else 0
        y_max = max_value + 100  # Add padding for better visibility

        bars = self.ax.bar(categories, values, color='gray')

        # Add labels above bars
        for bar, value in zip(bars, values):
            self.ax.annotate(f"{value}", xy=(bar.get_x() + bar.get_width() / 2, value),
                            xytext=(0, 5), textcoords="offset points", ha='center', va='bottom', fontsize=10)

        self.ax.set_title("Κατάσταση Φύλλων", fontsize=16)
        self.ax.set_ylabel("Αριθμός Φύλλων", fontsize=12)
        self.ax.set_xticks(range(len(categories)))
        self.ax.set_xticklabels(categories, rotation=45, ha="right", fontsize=10)
        self.ax.set_ylim(0, y_max)

        self.figure.subplots_adjust(bottom=0.3, top=0.9)
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


    def export_to_pdf(self):
        """Export flight report to a visually appealing PDF."""
        if not self.current_flight_folder:
            QMessageBox.warning(self, "Error", "No flight data loaded.")
            return

        db_path = os.path.join(self.current_flight_folder, "flight_data.db")
        photos_folder = os.path.join(self.current_flight_folder, "photos")
        pdf_path = os.path.join(self.current_flight_folder, "flight_report.pdf")

        # Load data from the database
        conn = sqlite3.connect(db_path)
        query = "SELECT ID, Class, Confidence FROM flight_results WHERE Class != 'Healthy'"
        results = pd.read_sql_query(query, conn)
        conn.close()

        # Prepare the document
        doc = SimpleDocTemplate(pdf_path, pagesize=A4)
        styles = getSampleStyleSheet()
        elements = []

        # Title and Metadata
        elements.append(Paragraph("Flight Report", styles['Title']))
        elements.append(Spacer(1, 0.2 * inch))
        elements.append(Paragraph(f"Date and Time: {self.flight_time_label.text()}", styles['Normal']))
        elements.append(Paragraph(f"Flight Duration: {self.flight_duration_label.text()}", styles['Normal']))
        elements.append(Paragraph(f"Total Plants Analyzed: {self.plants_analyzed_label.text()}", styles['Normal']))
        elements.append(Paragraph(f"Affected Plants: {self.affected_plants_label.text()}", styles['Normal']))
        elements.append(Spacer(1, 0.3 * inch))

        # Add a bar chart
        chart_path = os.path.join(self.current_flight_folder, "chart.png")
        self.generate_chart(chart_path, results)  # Generate the chart
        elements.append(Image(chart_path, width=5 * inch, height=3 * inch))
        elements.append(Spacer(1, 0.3 * inch))

        # # Add a table of affected plants
        # elements.append(Paragraph("Details of Affected Plants:", styles['Heading2']))
        # table_data = [["ID", "Class", "Confidence"]]
        # table_data += results.values.tolist()
        # table = Table(table_data, colWidths=[1.5 * inch, 2 * inch, 1.5 * inch])
        # table.setStyle(TableStyle([
        #     ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        #     ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        #     ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        #     ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        #     ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        #     ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        #     ('GRID', (0, 0), (-1, -1), 1, colors.black),
        # ]))
        # elements.append(table)
        # elements.append(Spacer(1, 0.3 * inch))

        # Add photos of affected plants
        elements.append(Paragraph("Photos of Affected Plants:", styles['Heading2']))
        photo_files = [os.path.join(photos_folder, f) for f in os.listdir(photos_folder) if f.endswith(".jpg")]
        for photo_file in photo_files[:5]:  # Limit to 5 photos for the report
            elements.append(Image(photo_file, width=3 * inch, height=2 * inch))
            elements.append(Spacer(1, 0.2 * inch))

        # Build the document
        doc.build(elements)
        QMessageBox.information(self, "PDF Exported", f"PDF saved to {pdf_path}")

    def generate_chart(self, chart_path, results):
        """Generate a bar chart for the PDF."""
        class_counts = results["Class"].value_counts()
        plt.figure(figsize=(8, 4))
        class_counts.plot(kind="bar", color="gray")
        plt.title("Affected Plants by Class")
        plt.xlabel("Class")
        plt.ylabel("Count")
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.savefig(chart_path)
        plt.close()


    
    

    
    def load_results(self, flight_folder):
        """Load results from SQLite database and display them."""
        db_path = os.path.join(flight_folder, "flight_data.db")
        photos_folder = os.path.join(flight_folder, "photos")
        self.current_flight_folder = flight_folder  # Store the current flight folder for other functions

        if not os.path.exists(db_path):
            print(f"Database not found: {db_path}")
            return

        conn = sqlite3.connect(db_path)

        # Query all flight results
        query = "SELECT * FROM flight_results"
        results = pd.read_sql_query(query, conn)

        # Keep only the entry with the highest confidence for each ID
        results = results.loc[results.groupby("ID")["Confidence"].idxmax()]

        # Count unique diseases, including Healthy as its own category
        disease_counts = results["Class"].value_counts()

        # Ensure "Healthy" is always present in the counts
        if "Healthy" not in disease_counts:
            disease_counts["Healthy"] = 0

        # Calculate total plants and affected plants
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

        # Load photos of non-healthy plants
        self.load_photos(photos_folder, db_path)

        # Get and display flight duration
        if "FlightDuration" in results.columns:
            duration = results["FlightDuration"].iloc[0]
            self.flight_duration_label.setText(f"Διάρκεια Πτήσης: {duration}")

        conn.close()







    def load_photos(self, photos_folder, db_path):
        """Load photos of plants where the highest confidence class is affected (non-healthy)."""
        if not os.path.exists(photos_folder):
            print(f"Photos folder not found: {photos_folder}")
            self.placeholder_image.setText("No photos available")
            return

        if not os.path.exists(db_path):
            print(f"Database not found: {db_path}")
            self.placeholder_image.setText("No results available")
            return

        conn = sqlite3.connect(db_path)

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

        # Filter photos by affected IDs
        photo_files = [
            f for f in os.listdir(photos_folder)
            if f.endswith(".jpg") and int(f.split("_ID")[-1].replace(".jpg", "")) in affected_ids
        ]
        

        if not photo_files:
            self.placeholder_image.setText("No photos of affected plants available")
            return

        self.photo_files = photo_files
        self.photo_index = 0
        self.photos_folder = photos_folder
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
        if not self.current_flight_folder:
            print("No flight data loaded.")
            return

        video_formats = [".mp4", ".mov", ".avi"]
        for ext in video_formats:
            potential_path = os.path.join(self.current_flight_folder, f"processed_video{ext}")
            if os.path.exists(potential_path):
                video_path = potential_path
                break

        if not video_path:
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
        """Zoom the image based on the slider value."""
        scale_factor = value / 100.0
        self.graphics_view.resetTransform()  # Reset any existing transformations
        self.graphics_view.scale(scale_factor, scale_factor)  # Apply new scale

        
# if __name__ == "__main__":
#     import sys
#     from PyQt6.QtWidgets import QApplication

#     # Create the application
#     app = QApplication(sys.argv)

#     # Instantiate and show the DroneReportApp
#     report_app = DroneReportApp()
#     report_app.show()

#     # Execute the application
#     sys.exit(app.exec())


    