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
        flight_time_label = QLabel("ΠΤΗΣΗ: 16/12/2024 14:31")
        flight_time_label.setStyleSheet("font-size: 16px; font-weight: bold; color:  white;")
        header_layout.addWidget(flight_time_label, alignment=Qt.AlignmentFlag.AlignLeft)

        close_button = QPushButton("Κλείσιμο")
        close_button.setStyleSheet("font-size: 14px; color: black; background-color: lightgray; padding: 5px 10px;")
        header_layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignRight)

        main_layout.addLayout(header_layout)

        # Top Statistics Section
        stats_frame = QFrame()
        stats_frame.setStyleSheet("border: 1px solid gray; padding: 10px; background-color: #f5f5f5;")
        stats_layout = QGridLayout(stats_frame)

        self.disease_count_label = QLabel("Ασθένειες που εντοπίστηκαν: <b>2 ασθένειες</b>")
        self.plants_analyzed_label = QLabel("Φυτά που αναλύθηκαν: <b>342 φυτά</b>")
        self.affected_plants_label = QLabel("Επηρεασμένα φυτά: <b>50</b>")

        for label in [self.disease_count_label, self.plants_analyzed_label, self.affected_plants_label]:
            label.setStyleSheet("font-size: 16px; padding: 5px; color: black;")

        stats_layout.addWidget(self.disease_count_label, 0, 0)
        stats_layout.addWidget(self.plants_analyzed_label, 0, 1)
        stats_layout.addWidget(self.affected_plants_label, 0, 2)

        main_layout.addWidget(stats_frame)

        # Bar Chart Section
        self.figure, self.ax = plt.subplots()
        self.canvas = FigureCanvas(self.figure)
        self.draw_chart()

        chart_frame = QFrame()
        chart_frame.setStyleSheet("border: 1px solid gray; padding: 10px;")
        chart_layout = QVBoxLayout(chart_frame)
        chart_layout.addWidget(self.canvas)
        main_layout.addWidget(chart_frame)

        # Image Section
        image_frame = QFrame()
        image_frame.setStyleSheet("border: 1px solid gray; padding: 10px; background-color: #f9f9f9;")
        image_layout = QVBoxLayout(image_frame)

        image_label = QLabel("Φυτά με ασθένειες που εντοπίστηκαν στην πτήση")
        image_label.setStyleSheet("font-size: 16px; font-weight: bold; color: black;")
        image_layout.addWidget(image_label)

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

    def draw_chart(self):
        categories = ["Υγιή Φυτά", "Περίση Μάστιγα", "Όψιμη Μάστιγα"]
        values = [292, 35, 15]
        self.ax.clear()
        self.ax.bar(categories, values, color='gray')
        self.ax.set_title("Κατάσταση Φυτών", fontsize=16)
        self.ax.set_ylabel("Αριθμός Φυτών", fontsize=12)
        self.ax.set_xlabel("Κατηγορίες", fontsize=12)
        self.canvas.draw()

    def export_to_pdf(self):
        pdf_file = "flight_report.pdf"
        c = canvas.Canvas(pdf_file)
        
        # Header
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, 800, "Αναφορά Πτήσης")
        c.setFont("Helvetica", 12)
        c.drawString(50, 780, f"Ημερομηνία: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        
        # Statistics
        c.drawString(50, 750, "Στατιστικά:")
        c.drawString(70, 730, f"Ασθένειες που εντοπίστηκαν: 2")
        c.drawString(70, 710, f"Φυτά που αναλύθηκαν: 342")
        c.drawString(70, 690, f"Επηρεασμένα φυτά: 50")
        
        # Placeholder for chart and images
        c.drawString(50, 650, "Γράφημα κατάστασης φυτών:")
        c.rect(50, 500, 500, 100, stroke=1, fill=0)
        c.drawString(60, 580, "(Το γράφημα θα προστεθεί στο τελικό PDF)")
        c.save()
        print(f"PDF saved to {pdf_file}")

# Run the Application
if __name__ == "__main__":
    app = QApplication([])
    window = DroneReportApp()
    window.show()
    app.exec()
