import os
import sqlite3
import pandas as pd

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDateEdit, QMessageBox
)
from PyQt6.QtCore import Qt, QDate
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas


class FieldProgressPage(QMainWindow):
    """
    A window that displays the health progress of a field over time.
    Reads summarized data from 'field_data.db' and plots a chart of healthy vs total plants.
    """

    def __init__(self, field_path: str):
        """
        Constructor:
          field_path: The path to the field folder containing 'field_data.db'.
        """
        super().__init__()
        self.setWindowTitle("Field Health Progress")
        self.setGeometry(100, 100, 800, 600)

        # Store reference to the field path
        self.field_path = field_path

        # Build the UI
        self.init_ui()

    # ---------------------------------------------------------------------
    # UI Initialization
    # ---------------------------------------------------------------------

    def init_ui(self):
        """
        Sets up the main layout:
         - A row with two QDateEdit widgets (from_date, to_date) and a 'Generate Chart' button
         - A matplotlib chart area
        """
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        # ------------------
        # Date Range & Generate Button
        # ------------------
        calendar_layout = QHBoxLayout()

        # "From" label and QDateEdit
        from_label = QLabel("Από:")
        from_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.from_date = QDateEdit()
        self.from_date.setDisplayFormat("yyyy-MM-dd")
        self.from_date.setCalendarPopup(True)
        # Default to one month ago
        self.from_date.setDate(QDate.currentDate().addMonths(-1))

        # "To" label and QDateEdit
        to_label = QLabel("Έως:")
        to_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.to_date = QDateEdit()
        self.to_date.setDisplayFormat("yyyy-MM-dd")
        self.to_date.setCalendarPopup(True)
        # Default to today's date
        self.to_date.setDate(QDate.currentDate())

        # Generate button
        generate_button = QPushButton("Δημιουργία Γραφήματος")
        generate_button.clicked.connect(self.generate_chart)

        # Assemble the calendar row
        calendar_layout.addWidget(from_label)
        calendar_layout.addWidget(self.from_date)
        calendar_layout.addWidget(to_label)
        calendar_layout.addWidget(self.to_date)
        calendar_layout.addWidget(generate_button)
        main_layout.addLayout(calendar_layout)

        # ------------------
        # Chart Area
        # ------------------
        self.chart_canvas = FigureCanvas(Figure())
        self.init_empty_chart()
        main_layout.addWidget(self.chart_canvas)

    # ---------------------------------------------------------------------
    # Chart Initialization
    # ---------------------------------------------------------------------

    def init_empty_chart(self):
        """
        Initializes an empty chart with default labels/title.
        Called once during UI setup.
        """
        ax = self.chart_canvas.figure.add_subplot(111)
        ax.set_title("Πρόοδος Υγείας Καλλιέργειας")
        ax.set_xlabel("Ημερομηνία")
        ax.set_ylabel("Ποσοστό Υγείας (%)")
        ax.grid(True)
        self.chart_canvas.draw()

    # ---------------------------------------------------------------------
    # Generate Chart Logic
    # ---------------------------------------------------------------------

    def generate_chart(self):
        """
        Retrieves data for the selected date range from 'field_data.db',
        filters it, calculates health percentage, and plots a line chart.
        """
        # Get the date range from the UI
        from_date = self.from_date.date().toString("yyyy-MM-dd")
        to_date = self.to_date.date().toString("yyyy-MM-dd")

        # Check if the database exists
        field_db_path = os.path.join(self.field_path, "field_data.db")
        if not os.path.exists(field_db_path):
            QMessageBox.warning(self, "Error", "Field summary database not found.")
            return

        # Load data from the 'field_summary' table
        conn = sqlite3.connect(field_db_path)
        query = """
            SELECT run_id, flight_datetime, healthy_plants, total_plants
            FROM field_summary
        """
        data = pd.read_sql_query(query, conn)
        conn.close()

        if data.empty:
            QMessageBox.warning(self, "No Data", "No runs found in the database.")
            return

        # Convert flight_datetime (e.g., '20250129_103000') into a date (YYYYMMDD)
        # We'll parse just the first 8 characters, which represent YYYYMMDD
        data['date'] = pd.to_datetime(data['flight_datetime'].str[:8], format='%Y%m%d')

        # Filter rows to the user-selected date range
        from_date_obj = pd.to_datetime(from_date, format='%Y-%m-%d')
        to_date_obj = pd.to_datetime(to_date, format='%Y-%m-%d')
        data = data[(data['date'] >= from_date_obj) & (data['date'] <= to_date_obj)]

        if data.empty:
            QMessageBox.warning(self, "No Data", "No runs found in the selected date range.")
            return

        # Calculate the percentage of healthy plants for each record
        data['health_percentage'] = (data['healthy_plants'] / data['total_plants']) * 100

        # For each date, keep only the record with the max total_plants
        data = data.loc[data.groupby('date')['total_plants'].idxmax()].reset_index(drop=True)

        # Sort by date for plotting
        data = data.sort_values(by='date')

        # Plot on the chart
        self.plot_chart(data['date'], data['health_percentage'])

    def plot_chart(self, dates, health_percentages):
        """
        Draws the line chart of health percentage vs. date on the existing canvas.
        """
        # Clear any existing plots
        self.chart_canvas.figure.clear()

        # Create a new subplot
        ax = self.chart_canvas.figure.add_subplot(111)
        ax.plot(dates, health_percentages, marker='o', linestyle='-', color='b')

        # Customize plot
        ax.set_title("Field Health Progress Over Time")
        ax.set_xlabel("Date")
        ax.set_ylabel("Health Percentage (%)")
        ax.grid(True)

        # Auto-format x-axis for date labels
        self.chart_canvas.figure.autofmt_xdate()

        # Redraw canvas
        self.chart_canvas.draw()
