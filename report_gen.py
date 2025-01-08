from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget, QFrame, QGridLayout
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


class DroneReportApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Drone Flight Report")
        self.setGeometry(100, 100, 1200, 800)

        # Main Widget
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout()

        # Header Section
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

        # Top Statistics Section
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

        # Bar Chart Section
        self.figure, self.ax = plt.subplots()
        self.canvas = FigureCanvas(self.figure)

        chart_frame = QFrame()
        chart_frame.setStyleSheet("border: 1px solid gray; padding: 10px;")
        chart_frame.setMinimumHeight(400)
        chart_layout = QVBoxLayout(chart_frame)
        chart_layout.addWidget(self.canvas)
        main_layout.addWidget(chart_frame)

        # Image Section
        image_frame = QFrame()
        image_frame.setStyleSheet("border: 1px solid gray; padding: 10px; background-color: #f9f9f9;")
        image_layout = QVBoxLayout(image_frame)

        self.image_label = QLabel("Φυτά με ασθένειες που εντοπίστηκαν στην πτήση")
        self.image_label.setStyleSheet("font-size: 16px; font-weight: bold; color: black;")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image_layout.addWidget(self.image_label)

        # Placeholder for Image Carousel
        placeholder_image = QLabel()
        placeholder_image.setStyleSheet("background-color: lightgray; border: 1px solid black; color: black;")
        placeholder_image.setFixedHeight(200)
        placeholder_image.setText("Image Placeholder")
        placeholder_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image_layout.addWidget(placeholder_image)

        main_layout.addWidget(image_frame)

        # Footer Section
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

        main_widget.setLayout(main_layout)

    def draw_chart(self, categories=None, values=None):
        #Δημιουργεί το γράφημα με δεδομένα που παρέχονται.
        if categories is None:
            categories = ["Κατηγορία 1", "Κατηγορία 2"]
        if values is None:
            values = [0, 0]

        self.ax.clear()
        
           # Υπολογισμός της μέγιστης τιμής για τον κάθετο άξονα
        max_value = max(values)
        y_max = max_value + 100  # Προσθήκη 100 στη μέγιστη τιμή

        # Δημιουργία γραφήματος
        bars = self.ax.bar(categories, values, color='gray')

        # Ρυθμίσεις τίτλων και αξόνων
        self.ax.set_title("Κατάσταση Φυτών", fontsize=16)
        self.ax.set_ylabel("Αριθμός Φυτών", fontsize=12)
        self.ax.set_xticks(range(len(categories)))
        self.ax.set_xticklabels(categories, rotation=45, ha="right", fontsize=10)

        self.ax.set_ylim(0, y_max)
        
        # Εμφάνιση τιμών πάνω από κάθε στήλη
        for bar, value in zip(bars, values):
            self.ax.annotate(
                f'{value}',  # Το κείμενο που θα εμφανιστεί
                xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),  # Συντεταγμένες
                xytext=(0, 5),  # Απόσταση από τη στήλη
                textcoords="offset points",  # Το κείμενο τοποθετείται σχετικά με το σημείο
                ha='center', va='bottom', fontsize=10  # Κέντρο και μέγεθος γραμματοσειράς
            )

        # Προσαρμογή διαστήματος για τις ετικέτες
        self.figure.subplots_adjust(bottom=0.3, top=0.9)

        # Ενημέρωση του καμβά
        self.canvas.draw()


    def update_flight_data(self, flight_time, diseases, plants_analyzed, affected_plants):
        """Ενημερώνει τα δεδομένα της πτήσης."""
        try:
            # Combine date and time into a single string and parse it
            combined_time = f"{flight_time[1]}_{flight_time[2]}"  # e.g., "20250109_101230"
            formatted_time = datetime.strptime(combined_time, "%Y%m%d_%H%M%S").strftime("%d/%m/%Y %H:%M:%S")
        except ValueError:
            formatted_time = "Unknown"  # Fallback in case of parsing issues

        # Update the labels
        self.flight_time_label.setText(f"ΠΤΗΣΗ: {formatted_time}")
        self.disease_count_label.setText(f"Ασθένειες που εντοπίστηκαν: {diseases}")
        self.plants_analyzed_label.setText(f"Φυτά που αναλύθηκαν: {plants_analyzed}")
        self.affected_plants_label.setText(f"Επηρεασμένα φυτά: {affected_plants}")


    def export_to_pdf(self):
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
        # Path to the tracked_data.csv file
        results_file = os.path.join(output_folder, "tracked_data.csv")

        # Check if the results file exists
        if not os.path.exists(results_file):
            print(f"Results file not found: {results_file}")
            return

        # Load results from the file
        results = pd.read_csv(results_file)

        # Retain only the row with the highest confidence for each ID
        filtered_results = results.loc[results.groupby("ID")["Confidence"].idxmax()]

        # Count diseases, ensuring "Healthy" is included
        disease_counts = filtered_results["Class"].value_counts()

        # Add "Healthy" to the disease counts if missing
        if "Healthy" not in disease_counts:
            disease_counts["Healthy"] = 0

        # Aggregate statistics
        total_plants = results["ID"].nunique()  # Count of unique plants analyzed
        healthy_plants = filtered_results[filtered_results["Class"] == "Healthy"]["ID"].nunique()  # Unique healthy plants
        affected_plants = total_plants - healthy_plants  # Affected plants are those not healthy

        # Remove "Healthy" from the disease count for unique diseases detected
        unique_diseases = len(disease_counts) - (1 if "Healthy" in disease_counts else 0)

        # Update the report with aggregated data
        self.update_flight_data(
            flight_time=output_folder.split("_")[-1],  # Extract timestamp from folder name
            diseases=unique_diseases,
            plants_analyzed=total_plants,
            affected_plants=affected_plants,
        )

        # Update the bar chart with unique counts
        self.draw_chart(categories=disease_counts.index.tolist(), values=disease_counts.values.tolist())

        # Load photos of detected objects
        photos_folder = os.path.join(output_folder, "photos")
        self.load_photos(photos_folder)





    def load_photos(self, photos_folder):
        """Load photos from the photos folder."""
        if not os.path.exists(photos_folder):
            print(f"Photos folder not found: {photos_folder}")
            return

        # Get the list of photo files
        photo_files = [f for f in os.listdir(photos_folder) if f.endswith(".jpg")]

        # Placeholder: Update with actual image carousel logic
        if photo_files:
            self.image_label.setText(f"Loaded {len(photo_files)} photos")
        else:
            self.image_label.setText("No photos available")

    def list_previous_runs(self, base_folder="runs"):
        """List all previous runs from the base folder."""
        if not os.path.exists(base_folder):
            print(f"No runs found in {base_folder}")
            return []

        # Get all run folders sorted by timestamp
        runs = [f for f in os.listdir(base_folder) if os.path.isdir(os.path.join(base_folder, f))]
        runs.sort(reverse=True)  # Show the most recent runs first
        return runs


    def load_selected_run(self, selected_run):
        """Load and display the results from the selected run."""
        base_folder = "runs"
        output_folder = os.path.join(base_folder, selected_run)

        # Load results from the selected run
        if os.path.exists(output_folder):
            self.load_results(output_folder)
        else:
            print(f"Run folder not found: {output_folder}")

    
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


    