from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QDateEdit, QMessageBox
)
from PyQt6.QtCore import Qt, QDate
import sqlite3
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import os


class FieldProgressPage(QMainWindow):
    def __init__(self, field_path):
        super().__init__()
        self.setWindowTitle("Field Health Progress")
        self.setGeometry(100, 100, 800, 600)

        self.field_path = field_path
        self.init_ui()

    def init_ui(self):
        # Main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)

        # Calendar section
        calendar_layout = QHBoxLayout()

        from_label = QLabel("Από:")
        from_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.from_date = QDateEdit()
        self.from_date.setDisplayFormat("yyyy-MM-dd")
        self.from_date.setCalendarPopup(True)
        self.from_date.setDate(QDate.currentDate().addMonths(-1))

        to_label = QLabel("Έως:")
        to_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.to_date = QDateEdit()
        self.to_date.setDisplayFormat("yyyy-MM-dd")
        self.to_date.setCalendarPopup(True)
        self.to_date.setDate(QDate.currentDate())

        generate_button = QPushButton("Δημιουργία Γραφήματος")
        generate_button.clicked.connect(self.generate_chart)

        calendar_layout.addWidget(from_label)
        calendar_layout.addWidget(self.from_date)
        calendar_layout.addWidget(to_label)
        calendar_layout.addWidget(self.to_date)
        calendar_layout.addWidget(generate_button)
        main_layout.addLayout(calendar_layout)

        # Chart area
        self.chart_canvas = FigureCanvas(Figure())
        self.init_empty_chart()
        main_layout.addWidget(self.chart_canvas)

    def init_empty_chart(self):
        """Initialize an empty chart with default labels."""
        ax = self.chart_canvas.figure.add_subplot(111)
        ax.set_title("Πρόοδος Υγείας Καλλιέργειας")
        ax.set_xlabel("Ημερομηνία")
        ax.set_ylabel("Ποσοστό Υγείας (%)")
        ax.grid(True)
        self.chart_canvas.draw()


    def generate_chart(self):
        # Get selected dates
        from_date = self.from_date.date().toString("yyyy-MM-dd")
        to_date = self.to_date.date().toString("yyyy-MM-dd")

        # Load data from field_data.db
        field_db_path = os.path.join(self.field_path, "field_data.db")
        if not os.path.exists(field_db_path):
            QMessageBox.warning(self, "Error", "Field summary database not found.")
            return

        conn = sqlite3.connect(field_db_path)
        query = f"""
            SELECT run_id, flight_datetime, healthy_plants, total_plants
            FROM field_summary
        """
        data = pd.read_sql_query(query, conn)
        conn.close()

        if data.empty:
            QMessageBox.warning(self, "No Data", "No runs found in the database.")
            return

        # Parse the flight_datetime into a proper date
        data['date'] = pd.to_datetime(data['flight_datetime'].str[:8], format='%Y%m%d')

        # Filter data by the selected date range
        from_date_obj = pd.to_datetime(from_date, format='%Y-%m-%d')
        to_date_obj = pd.to_datetime(to_date, format='%Y-%m-%d')
        data = data[(data['date'] >= from_date_obj) & (data['date'] <= to_date_obj)]

        if data.empty:
            QMessageBox.warning(self, "No Data", "No runs found in the selected date range.")
            return

        # Calculate health percentage for each record
        data['health_percentage'] = (data['healthy_plants'] / data['total_plants']) * 100

        # Keep only the record with the maximum total_plants for each day
        data = data.loc[data.groupby('date')['total_plants'].idxmax()].reset_index(drop=True)

        # Sort by date for plotting
        data = data.sort_values(by='date')

        # Plot the data
        self.plot_chart(data['date'], data['health_percentage'])



    def plot_chart(self, dates, health_percentages):
        # Clear the existing chart
        self.chart_canvas.figure.clear()

        # Create a new plot
        ax = self.chart_canvas.figure.add_subplot(111)
        ax.plot(dates, health_percentages, marker='o', linestyle='-', color='b')

        # Customize the chart
        ax.set_title("Field Health Progress Over Time")
        ax.set_xlabel("Date")
        ax.set_ylabel("Health Percentage (%)")
        ax.grid(True)

        # Format x-axis for dates
        self.chart_canvas.figure.autofmt_xdate()

        # Redraw the chart
        self.chart_canvas.draw()
