from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget, QFrame, QGridLayout
)
from PyQt6.QtCore import Qt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt
from reportlab.pdfgen import canvas
from datetime import datetime


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
        self.flight_time_label.setText(f"ΠΤΗΣΗ: {flight_time}")
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


    