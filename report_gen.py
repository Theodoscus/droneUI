from PyQt6.QtWidgets import (
    QMessageBox, QMainWindow, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget,
    QFrame, QGridLayout, QDialog, QSlider, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QScrollArea, QComboBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QPainter
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt

import os
import sqlite3
import subprocess
import platform
import pandas as pd
from datetime import datetime

# ReportLab imports for PDF generation
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Local imports
from countermeasures import CounterMeasuresWindow
from field_progress import FieldProgressPage

# Register Greek-capable font for ReportLab
arial_font_path = "arial_greek.ttf"
pdfmetrics.registerFont(TTFont("ArialGreek", arial_font_path))

# Dictionary for translating disease classes from English to Greek
DISEASE_TRANSLATION = {
    "Healthy": "Υγιές",
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


class DroneReportApp(QMainWindow):
    """
    A main window class for displaying and managing drone flight reports:
      - Loads flight data from flight_data.db (SQLite).
      - Shows disease counts in a bar chart.
      - Displays a photo carousel of affected plants.
      - Exports summaries to a Greek-enabled PDF.
    """

    def __init__(self, field_path: str):
        """
        :param field_path: The path to the field folder (containing runs/, etc.).
        """
        super().__init__()
        self.setWindowTitle("Drone Flight Report")
        self.setGeometry(100, 100, 1200, 800)

        # Set up field paths and ensure runs/ folder exists
        self.field_path = field_path
        self.runs_folder = os.path.join(self.field_path, "runs")
        os.makedirs(self.runs_folder, exist_ok=True)

        # Scrollable content
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)

        # Main container for the UI
        scroll_content = QWidget()
        self.main_layout = QVBoxLayout(scroll_content)
        scroll_area.setWidget(scroll_content)
        self.setCentralWidget(scroll_area)

        # Build UI elements
        self.setup_ui(self.main_layout)
        # Load newest flight data if available
        self.load_newest_flight_data()

    # ---------------------------------------------------------------------
    # Database Utility
    # ---------------------------------------------------------------------
    @staticmethod
    def open_database(db_path: str):
        """
        Safely opens a SQLite database and returns (conn, cursor).
        Raises an exception if the DB cannot be opened.
        """
        try:
            conn = sqlite3.connect(db_path)
            return conn, conn.cursor()
        except sqlite3.Error as e:
            raise RuntimeError(f"Database error: {e}")

    # ---------------------------------------------------------------------
    # UI Setup
    # ---------------------------------------------------------------------
    def setup_ui(self, main_layout: QVBoxLayout):
        """
        Sets up the UI elements:
          - Header with flight time, run selector, close
          - Stats frame for disease count
          - Bar chart area
          - Photo carousel with disease info
          - Footer with PDF export, flight duration, etc.
        """
        self.setup_header(main_layout)
        self.setup_stats_section(main_layout)
        self.setup_chart_section(main_layout)
        self.setup_image_section(main_layout)
        self.setup_footer(main_layout)

    def setup_header(self, main_layout: QVBoxLayout):
        """
        Builds the header layout containing flight time label,
        run selector, and a close button.
        """
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

    def setup_stats_section(self, main_layout: QVBoxLayout):
        """
        Builds a frame to display stats about the flight:
        (Disease count, plants analyzed, affected plants).
        """
        stats_frame = QFrame()
        stats_frame.setStyleSheet("border: 1px solid gray; padding: 10px; background-color: #f5f5f5;")
        stats_layout = QGridLayout(stats_frame)

        self.disease_count_label = QLabel("Ασθένειες που εντοπίστηκαν: ")
        self.plants_analyzed_label = QLabel("Φυτά που αναλύθηκαν: ")
        self.affected_plants_label = QLabel("Επηρεασμένα φυτά: ")

        for lbl in [self.disease_count_label, self.plants_analyzed_label, self.affected_plants_label]:
            lbl.setStyleSheet("font-size: 16px; padding: 5px; color: black;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        stats_layout.addWidget(self.disease_count_label, 0, 0)
        stats_layout.addWidget(self.plants_analyzed_label, 0, 1)
        stats_layout.addWidget(self.affected_plants_label, 0, 2)

        main_layout.addWidget(stats_frame)

    def setup_chart_section(self, main_layout: QVBoxLayout):
        """
        Builds a frame containing a matplotlib bar chart.
        """
        self.figure, self.ax = plt.subplots()
        self.canvas = FigureCanvas(self.figure)

        chart_frame = QFrame()
        chart_frame.setStyleSheet("border: 1px solid gray; padding: 10px;")
        chart_frame.setMinimumHeight(500)

        chart_layout = QVBoxLayout(chart_frame)
        chart_layout.addWidget(self.canvas)
        main_layout.addWidget(chart_frame)

    def setup_image_section(self, main_layout: QVBoxLayout):
        """
        Builds a section to display affected plant photos, along with
        disease info labels and navigation buttons.
        """
        image_frame = QFrame()
        image_frame.setStyleSheet("border: 1px solid gray; padding: 10px; background-color: #f9f9f9;")
        image_layout = QVBoxLayout(image_frame)

        self.image_label = QLabel("Φύλλα με ασθένειες που εντοπίστηκαν στην πτήση")
        self.image_label.setStyleSheet("font-size: 16px; font-weight: bold; color: black;")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image_layout.addWidget(self.image_label)

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

        image_layout.addWidget(info_frame)

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

        # Navigation (Prev/Next) buttons under the image
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

        # Button: open flight video
        external_player_button = QPushButton("Αναπαραγωγή Καταγραφής Πτήσης")
        external_player_button.setStyleSheet("font-size: 14px; background-color: #d9d9d9; color: black; padding: 10px;")
        external_player_button.clicked.connect(self.open_video_in_external_player)
        main_layout.addWidget(external_player_button)

        # Button: open photos folder
        photos_button = QPushButton("Άνοιγμα Φακέλου Φωτογραφιών", self)
        photos_button.setStyleSheet("font-size: 14px; background-color: #007BFF; color: white; padding: 10px;")
        photos_button.clicked.connect(self.open_photos_folder)
        main_layout.addWidget(photos_button)

    def setup_footer(self, main_layout: QVBoxLayout):
        """
        Builds the footer with PDF export, flight duration, and a countermeasures button.
        Adds a final button for viewing field progress.
        """
        footer_layout = QHBoxLayout()

        export_pdf_button = QPushButton("Εξαγωγή αναφοράς σε PDF")
        export_pdf_button.setStyleSheet("font-size: 14px; background-color: #d9d9d9; color: black; padding: 10px;")
        export_pdf_button.clicked.connect(self.export_to_pdf)
        footer_layout.addWidget(export_pdf_button)

        self.flight_duration_label = QLabel("Διάρκεια Πτήσης: --:--:--")
        self.flight_duration_label.setStyleSheet("font-size: 14px; color: white; padding: 10px;")
        self.flight_duration_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer_layout.addWidget(self.flight_duration_label)

        self.countermeasures_button = QPushButton("Τρόποι αντιμετώπισης")
        self.countermeasures_button.setStyleSheet("font-size: 14px; background-color: #d9d9d9; color: black; padding: 10px;")
        self.countermeasures_button.clicked.connect(self.show_countermeasures)
        footer_layout.addWidget(self.countermeasures_button)

        main_layout.addLayout(footer_layout)

        progress_button = QPushButton("View Field Health Progress")
        progress_button.setStyleSheet("font-size: 14px; background-color: #d9d9d9; color: black; padding: 10px;")
        progress_button.clicked.connect(self.open_field_progress_page)
        main_layout.addWidget(progress_button)

    # ---------------------------------------------------------------------
    # Flight Data Loading
    # ---------------------------------------------------------------------

    def load_newest_flight_data(self):
        """
        Loads the newest run in 'runs/' by timestamp. 
        Does nothing if no runs exist.
        """
        if not os.path.exists(self.runs_folder):
            print(f"No runs directory found in {self.runs_folder}.")
            return

        flight_folders = [
            d for d in os.listdir(self.runs_folder)
            if os.path.isdir(os.path.join(self.runs_folder, d)) and d.startswith("run_")
        ]
        if not flight_folders:
            print("No flight data found.")
            return

        flight_folders.sort(reverse=True)
        newest_run = os.path.join(self.runs_folder, flight_folders[0])
        print(f"Loading data from: {newest_run}")
        self.load_results(newest_run)

    def list_previous_runs(self):
        """
        Returns a list of run folders in descending order, each formatted as 'Πτήση: dd/mm/yyyy hh:mm:ss'.
        Populates self.run_name_mapping to map displayed name -> folder name.
        """
        if not os.path.exists(self.runs_folder):
            print(f"No runs found in {self.runs_folder}")
            return []

        runs = [
            f for f in os.listdir(self.runs_folder)
            if os.path.isdir(os.path.join(self.runs_folder, f)) and f.startswith("run_")
        ]
        runs.sort(reverse=True)
        self.run_name_mapping = {}

        for run in runs:
            try:
                parts = run.split("_")  # ["run", "YYYYMMDD", "HHMMSS"]
                timestamp = parts[1] + parts[2]
                flight_datetime = datetime.strptime(timestamp, "%Y%m%d%H%M%S")
                display_name = f"Πτήση: {flight_datetime.strftime('%d/%m/%Y %H:%M:%S')}"
                self.run_name_mapping[display_name] = run
            except (IndexError, ValueError):
                print(f"Invalid folder name format: {run}")
                continue
        return list(self.run_name_mapping.keys())

    def load_selected_run(self):
        """
        Loads the run selected from the run_selector combo.
        Shows a warning if invalid.
        """
        selected_run = self.run_selector.currentText()
        if not selected_run:
            QMessageBox.warning(self, "No Run Selected", "Please select a run.")
            return

        raw_run_name = self.run_name_mapping.get(selected_run)
        if not raw_run_name:
            QMessageBox.critical(self, "Invalid Run", "The selected run could not be mapped to a valid folder.")
            return

        run_folder = os.path.join(self.runs_folder, raw_run_name)
        if not os.path.exists(run_folder):
            QMessageBox.critical(self, "Invalid Run", f"Run folder does not exist: {run_folder}")
            return

        try:
            self.load_results(run_folder)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred while loading the run: {e}")

    def load_results(self, flight_folder):
        """
        Loads flight data from flight_data.db in flight_folder, populates chart & stats,
        sets up the photo carousel if diseased photos exist.
        """
        self.current_flight_folder = flight_folder
        db_path = os.path.join(flight_folder, "flight_data.db")
        photos_folder = os.path.join(flight_folder, "photos")

        if not os.path.exists(db_path):
            print(f"Database not found at: {db_path}")
            return

        # Safely open the DB, query, and close
        try:
            conn = sqlite3.connect(db_path)
            df_all = pd.read_sql_query("SELECT * FROM flight_results", conn)
        except sqlite3.Error as e:
            QMessageBox.critical(self, "Database Error", f"Unable to read flight_results: {e}")
            return
        finally:
            if 'conn' in locals():
                conn.close()

        # For each plant, keep the highest-confidence classification
        if df_all.empty:
            QMessageBox.information(self, "No Data", "No flight results found in the database.")
            return

        df_all = df_all.loc[df_all.groupby("ID")["Confidence"].idxmax()]

        disease_counts = df_all["Class"].value_counts()
        if "Healthy" not in disease_counts:
            disease_counts["Healthy"] = 0

        total_plants = df_all["ID"].nunique()
        affected_plants = total_plants - disease_counts["Healthy"]

        # Number of distinct diseases (excluding healthy)
        if "Healthy" in disease_counts:
            unique_diseases = len(disease_counts) - 1
        else:
            unique_diseases = len(disease_counts)

        self.update_flight_data(
            flight_time=flight_folder.split("_"),
            diseases=unique_diseases,
            plants_analyzed=total_plants,
            affected_plants=affected_plants,
        )

        # Draw the bar chart
        self.draw_chart(disease_counts.index.tolist(), disease_counts.values.tolist())

        # Load photo carousel
        self.load_photos(photos_folder, db_path)

        # If flight duration is present
        if "FlightDuration" in df_all.columns:
            duration = df_all["FlightDuration"].iloc[0]
            self.flight_duration_label.setText(f"Διάρκεια Πτήσης: {duration}")

    # ---------------------------------------------------------------------
    # Photo Carousel
    # ---------------------------------------------------------------------

    def load_photos(self, photos_folder: str, db_path: str):
        """
        Loads photos of plants with highest-confidence classification != Healthy.
        Sets up the photo carousel if any diseased photos exist.
        """
        if not os.path.exists(photos_folder):
            print(f"Photos folder not found: {photos_folder}")
            self.placeholder_image.setText("No photos available.")
            return

        if not os.path.exists(db_path):
            print(f"Database not found: {db_path}")
            self.placeholder_image.setText("No results available.")
            return

        try:
            conn = sqlite3.connect(db_path)
            q = """
                SELECT ID,
                       MAX(CASE WHEN Class = 'Healthy' THEN Confidence ELSE 0 END) AS HealthyConfidence,
                       MAX(CASE WHEN Class != 'Healthy' THEN Confidence ELSE 0 END) AS NonHealthyConfidence
                FROM flight_results
                GROUP BY ID
            """
            df = pd.read_sql_query(q, conn)
        except sqlite3.Error as e:
            QMessageBox.critical(self, "Database Error", f"Error reading DB for diseased photos: {e}")
            return
        finally:
            if 'conn' in locals():
                conn.close()

        if df.empty:
            self.placeholder_image.setText("No flight results found.")
            return

        # Keep only IDs where NonHealthyConfidence > HealthyConfidence
        affected_ids = df[df["NonHealthyConfidence"] > df["HealthyConfidence"]]["ID"].tolist()

        photo_files = [
            f for f in os.listdir(photos_folder)
            if f.endswith(".jpg") and int(f.split("_ID")[-1].replace(".jpg", "")) in affected_ids
        ]
        if not photo_files:
            self.placeholder_image.setText("No photos of affected plants available.")
            return

        self.photo_files = photo_files
        self.photo_index = 0
        self.photos_folder = photos_folder
        self.update_carousel_image()

    def update_carousel_image(self):
        """
        Updates the displayed photo in the carousel, along with disease details from DB.
        """
        if not hasattr(self, "photo_files") or not self.photo_files:
            return

        photo_file = os.path.join(self.photos_folder, self.photo_files[self.photo_index])
        if not os.path.exists(photo_file):
            self.placeholder_image.setText("Photo file not found.")
            return

        # Get plant ID from the photo filename
        try:
            plant_id = int(photo_file.split("_ID")[-1].replace(".jpg", ""))
        except ValueError:
            self.placeholder_image.setText("Invalid photo filename format.")
            return

        # Query DB for that plant ID
        db_path = os.path.join(self.current_flight_folder, "flight_data.db")
        try:
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            c.execute("SELECT Class, Confidence FROM flight_results WHERE ID=? ORDER BY Confidence DESC LIMIT 1", (plant_id,))
            row = c.fetchone()
        except sqlite3.Error as e:
            QMessageBox.critical(self, "Database Error", f"Error reading classification data: {e}")
            return
        finally:
            if 'conn' in locals():
                conn.close()

        if row:
            disease, confidence = row
            disease_name = DISEASE_TRANSLATION.get(disease, disease)
            self.disease_label.setText(f"Ασθένεια: {disease_name}")
            self.plant_id_label.setText(f"ID Φυτού: {plant_id}")
            self.confidence_label.setText(f"Βεβαιότητα: {confidence * 100:.2f}%")
        else:
            self.disease_label.setText("Ασθένεια: --")
            self.plant_id_label.setText("ID Φυτού: --")
            self.confidence_label.setText("Βεβαιότητα: --%")

        pixmap = QPixmap(photo_file)
        if pixmap.isNull():
            self.placeholder_image.setText("Σφάλμα φόρτωσης εικόνας.")
        else:
            self.placeholder_image.setPixmap(pixmap.scaled(self.placeholder_image.size(), Qt.AspectRatioMode.KeepAspectRatio))

    def navigate_photos(self, direction: str):
        """Moves to the next or previous photo in the carousel."""
        if not hasattr(self, "photo_files") or not self.photo_files:
            return

        if direction == "next":
            self.photo_index = (self.photo_index + 1) % len(self.photo_files)
        else:
            self.photo_index = (self.photo_index - 1) % len(self.photo_files)
        self.update_carousel_image()

    # ---------------------------------------------------------------------
    # Chart Visualization
    # ---------------------------------------------------------------------
    def draw_chart(self, categories=None, values=None):
        """
        Draws a bar chart of disease classes vs. counts.
        Ensures 'Healthy' is included, translates to Greek, annotates bars.
        """
        if categories is None or values is None:
            categories, values = [], []

        self.ax.clear()

        if "Healthy" not in categories:
            categories.append("Υγιή")
            values.append(0)

        translated = [DISEASE_TRANSLATION.get(cat, cat) for cat in categories]
        max_val = max(values) if values else 0
        y_lim = max_val + 100
        bars = self.ax.bar(translated, values, color="gray")

        for bar, val in zip(bars, values):
            self.ax.annotate(
                str(val),
                xy=(bar.get_x() + bar.get_width() / 2, val),
                xytext=(0, 5),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=10,
            )

        self.ax.set_title("Κατάσταση Φύλλων", fontsize=16)
        self.ax.set_ylabel("Αριθμός Φύλλων", fontsize=12)
        self.ax.set_xticks(range(len(translated)))
        self.ax.set_xticklabels(translated, rotation=30, ha="right", fontsize=10, wrap=True)
        self.ax.set_ylim(0, y_lim)

        self.figure.subplots_adjust(bottom=0.4, top=0.9)
        self.canvas.draw()

    # ---------------------------------------------------------------------
    # Updating Flight Data Stats
    # ---------------------------------------------------------------------
    def update_flight_data(self, flight_time, diseases, plants_analyzed, affected_plants):
        """Updates labels for flight info (time, disease count, etc.) and toggles the countermeasures button."""
        try:
            combined_time = f"{flight_time[1]}_{flight_time[2]}"
            dt = datetime.strptime(combined_time, "%Y%m%d_%H%M%S").strftime("%d/%m/%Y %H:%M:%S")
        except (IndexError, ValueError):
            dt = "Unknown"

        self.flight_time_label.setText(f"ΠΤΗΣΗ: {dt}")
        self.disease_count_label.setText(f"Ασθένειες που εντοπίστηκαν: {diseases}")
        self.plants_analyzed_label.setText(f"Φύλλα που αναλύθηκαν: {plants_analyzed}")
        self.affected_plants_label.setText(f"Επηρεασμένα φύλλα: {affected_plants}")

        if diseases == 0:
            self.countermeasures_button.setEnabled(False)
            self.countermeasures_button.setStyleSheet("font-size: 14px; background-color: #e0e0e0; color: gray; padding: 10px;")
        else:
            self.countermeasures_button.setEnabled(True)
            self.countermeasures_button.setStyleSheet("font-size: 14px; background-color: #d9d9d9; color: black; padding: 10px;")

    # ---------------------------------------------------------------------
    # PDF Export
    # ---------------------------------------------------------------------
    def export_to_pdf(self):
        """
        Exports a PDF report containing:
          - Flight info (date/time, duration)
          - Bar chart of disease classes
          - Table of only diseased plants
        """
        if not hasattr(self, "current_flight_folder") or not self.current_flight_folder:
            QMessageBox.warning(self, "Error", "Δεν έχετε επιλέξει πτήση. Φορτώστε δεδομένα πριν την εξαγωγή.")
            return

        db_path = os.path.join(self.current_flight_folder, "flight_data.db")
        photos_folder = os.path.join(self.current_flight_folder, "photos")
        if not os.path.exists(db_path):
            QMessageBox.warning(self, "Error", "Το αρχείο flight_data.db δεν υπάρχει. Αδυναμία εξαγωγής PDF.")
            return
        if not os.path.exists(photos_folder):
            QMessageBox.warning(self, "Error", "Ο φάκελος φωτογραφιών δεν υπάρχει. Αδυναμία εξαγωγής PDF.")
            return

        folder_name = os.path.basename(self.current_flight_folder)
        try:
            _, date_str, time_str = folder_name.split("_", 2)
            pdf_filename = f"flight_report_{date_str}_{time_str}.pdf"
        except ValueError:
            pdf_filename = "flight_report.pdf"
        pdf_path = os.path.join(self.current_flight_folder, pdf_filename)

        flight_date_text = self.flight_time_label.text().replace("ΠΤΗΣΗ:", "").strip()
        flight_duration_text = self.flight_duration_label.text().replace("Διάρκεια Πτήσης:", "").strip()

        field_name = self.get_field_name_from_folder(self.current_flight_folder)

        try:
            conn = sqlite3.connect(db_path)
            df_all = pd.read_sql_query("SELECT * FROM flight_results", conn)
        except sqlite3.Error as e:
            QMessageBox.critical(self, "Database Error", f"Unable to read flight_results for PDF: {e}")
            return
        finally:
            if 'conn' in locals():
                conn.close()

        if df_all.empty:
            QMessageBox.warning(self, "No Data", "No flight results found for PDF export.")
            return

        # Keep highest confidence row per ID
        df_all = df_all.loc[df_all.groupby("ID")["Confidence"].idxmax()]

        total_plants = df_all["ID"].nunique()
        class_counts = df_all["Class"].value_counts()
        diseased_df = df_all[df_all["Class"] != "Healthy"]

        # Save chart for PDF
        chart_filepath = os.path.join(self.current_flight_folder, "temp_chart.png")
        self.save_flight_chart_all_classes(class_counts, chart_filepath)

        doc = SimpleDocTemplate(pdf_path, pagesize=A4)
        elements = []
        styles = getSampleStyleSheet()
        greek_normal_style = styles["Normal"]
        greek_normal_style.fontName = "ArialGreek"

        greek_title_style = styles["Title"]
        greek_title_style.fontName = "ArialGreek"

        # Title
        elements.append(Paragraph("Αναφορά Πτήσης (Flight Report)", greek_title_style))
        elements.append(Spacer(1, 12))

        # Flight summary
        flight_info = f"""
        <b>Χωράφι:</b> {field_name}<br/>
        <b>Ημερομηνία Πτήσης:</b> {flight_date_text}<br/>
        <b>Διάρκεια Πτήσης:</b> {flight_duration_text}<br/>
        <b>Συνολικά Φυτά:</b> {total_plants}
        """
        elements.append(Paragraph(flight_info, greek_normal_style))
        elements.append(Spacer(1, 12))

        # Insert chart
        if os.path.exists(chart_filepath):
            chart_img = Image(chart_filepath, width=6 * inch, height=4 * inch)
            elements.append(chart_img)
            elements.append(Spacer(1, 12))
        else:
            elements.append(Paragraph("Το γράφημα δεν είναι διαθέσιμο.", greek_normal_style))
            elements.append(Spacer(1, 12))

        # Table of only diseased plants
        table_data = [[
            Paragraph("ID Φυτού", greek_normal_style),
            Paragraph("Ασθένεια / Κατάσταση", greek_normal_style),
            Paragraph("Βεβαιότητα (%)", greek_normal_style),
            Paragraph("Φωτογραφία", greek_normal_style)
        ]]

        diseased_df.sort_values(by="ID", inplace=True)

        for _, row in diseased_df.iterrows():
            pid = row["ID"]
            disease_class = row["Class"]
            conf_val = row["Confidence"] * 100.0
            disease_greek = DISEASE_TRANSLATION.get(disease_class, disease_class)

            photo_file = next((f for f in os.listdir(photos_folder) if f.endswith(f"_ID{pid}.jpg")), None)
            if photo_file:
                photo_path = os.path.join(photos_folder, photo_file)
                img = Image(photo_path, width=1.5 * inch, height=1.5 * inch)
            else:
                img = Paragraph("Χωρίς Φωτογραφία", greek_normal_style)

            table_data.append([
                str(pid),
                disease_greek,
                f"{conf_val:.2f}",
                img
            ])

        col_widths = [1 * inch, 2 * inch, 1.2 * inch, 2 * inch]
        report_table = Table(table_data, colWidths=col_widths)
        report_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 1), (-1, -1), 'ArialGreek'),
        ]))
        elements.append(report_table)

        try:
            doc.build(elements)
            QMessageBox.information(self, "Επιτυχία", f"PDF αποθηκεύτηκε στο: {pdf_path}")
        except Exception as e:
            QMessageBox.critical(self, "Σφάλμα", f"Αποτυχία δημιουργίας PDF: {e}")
        finally:
            if os.path.exists(chart_filepath):
                os.remove(chart_filepath)

    def get_field_name_from_folder(self, run_folder_path: str) -> str:
        """
        Extracts the field folder name from a run path like:
          /.../fields/<field_name>/runs/run_YYYYMMDD_HHMMSS
        Goes up two directories to get <field_name>.
        """
        runs_dir = os.path.dirname(run_folder_path)
        field_dir = os.path.dirname(runs_dir)
        return os.path.basename(field_dir)

    def save_flight_chart_all_classes(self, class_counts: pd.Series, filepath: str):
        """
        Creates a bar chart (including 'Healthy'), saves as an image.
        Y-axis max is set to (max + 50).
        """
        if "Healthy" not in class_counts.index:
            class_counts["Healthy"] = 0

        class_counts = class_counts.sort_values(ascending=False)
        labels = [DISEASE_TRANSLATION.get(c, c) for c in class_counts.index]
        counts = class_counts.values
        mx = max(counts) if counts.size else 0
        y_lim = mx + 50

        fig, ax = plt.subplots(figsize=(7, 4))
        bars = ax.bar(labels, counts, color="gray")
        ax.set_title("Ασθένειες / Καταστάσεις Φυτών", fontsize=14)
        ax.set_ylabel("Αριθμός Φυτών", fontsize=12)
        ax.set_ylim([0, y_lim])
        ax.set_xticklabels(labels, rotation=30, ha="right")

        for bar, val in zip(bars, counts):
            ax.annotate(
                f"{val}",
                xy=(bar.get_x() + bar.get_width() / 2, val),
                xytext=(0, 5),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=9
            )

        plt.tight_layout()
        fig.savefig(filepath, dpi=120)
        plt.close(fig)

    # ---------------------------------------------------------------------
    # External Buttons & Windows
    # ---------------------------------------------------------------------
    def show_countermeasures(self):
        """
        Opens a dialog with possible countermeasures for all non-healthy diseases
        found in the current flight.
        """
        if not getattr(self, "current_flight_folder", None):
            QMessageBox.warning(self, "Σφάλμα", "No flight folder loaded.")
            return

        db_path = os.path.join(self.current_flight_folder, "flight_data.db")
        if not os.path.exists(db_path):
            QMessageBox.warning(self, "Σφάλμα", "Η βάση δεδομένων δεν βρέθηκε.")
            return

        query = """
            SELECT ID,
                MAX(CASE WHEN Class='Healthy' THEN Confidence ELSE 0 END) AS HealthyConfidence,
                MAX(CASE WHEN Class!='Healthy' THEN Confidence ELSE 0 END) AS NonHealthyConfidence,
                MAX(CASE WHEN Class!='Healthy' THEN Class ELSE NULL END) AS NonHealthyClass
            FROM flight_results
            GROUP BY ID
            HAVING NonHealthyConfidence > HealthyConfidence
        """

        try:
            conn = sqlite3.connect(db_path)
            df = pd.read_sql_query(query, conn)
        except sqlite3.Error as e:
            QMessageBox.critical(self, "Database Error", f"Error reading DB: {e}")
            return
        finally:
            if 'conn' in locals():
                conn.close()

        if df.empty or "NonHealthyClass" not in df.columns:
            QMessageBox.information(self, "Δεν Βρέθηκαν Ασθένειες", "Καμία μη-υγιής κατάσταση δεν ανιχνεύθηκε.")
            return

        diseases_eng = df["NonHealthyClass"].dropna().unique().tolist()
        diseases_gr = [DISEASE_TRANSLATION.get(d, d) for d in diseases_eng]

        if not diseases_gr:
            QMessageBox.information(self, "Δεν Βρέθηκαν Ασθένειες", "Δεν ανιχνεύθηκαν μη-υγιή φυτά.")
            return

        cm_window = CounterMeasuresWindow(diseases_gr, self)
        cm_window.exec()

    def open_video_in_external_player(self):
        """Opens processed video in default OS media player."""
        if not getattr(self, "current_flight_folder", None):
            print("No flight data loaded.")
            return

        exts = [".mp4", ".mov", ".avi"]
        video_path = None
        for ex in exts:
            candidate = os.path.join(self.current_flight_folder, f"processed_video{ex}")
            if os.path.exists(candidate):
                video_path = candidate
                break

        if not video_path:
            print("Flight video not found.")
            return

        try:
            if platform.system() == "Windows":
                os.startfile(video_path)
            elif platform.system() == "Darwin":
                subprocess.run(["open", video_path])
            elif platform.system() == "Linux":
                subprocess.run(["xdg-open", video_path])
            else:
                print("Unsupported OS.")
        except Exception as e:
            print(f"Error opening video: {e}")

    def open_photos_folder(self):
        """Opens the photos folder for the selected run in the OS file explorer."""
        selected_run = self.run_selector.currentText()
        if not selected_run:
            QMessageBox.warning(self, "Σφάλμα", "Παρακαλώ επιλέξτε πτήση.")
            return

        raw_run_name = getattr(self, "run_name_mapping", {}).get(selected_run, None)
        if not raw_run_name:
            QMessageBox.warning(self, "Σφάλμα", "Η επιλεγμένη πτήση δεν εντοπίστηκε.")
            return

        photos_dir = os.path.join(self.field_path, "runs", raw_run_name, "photos")
        if not os.path.exists(photos_dir):
            QMessageBox.warning(self, "Σφάλμα", "Φάκελος φωτογραφιών δεν βρέθηκε.")
            return

        try:
            if platform.system() == "Windows":
                os.startfile(photos_dir)
            elif platform.system() == "Darwin":
                subprocess.run(["open", photos_dir])
            elif platform.system() == "Linux":
                subprocess.run(["xdg-open", photos_dir])
            else:
                QMessageBox.warning(self, "Σφάλμα", "OS δεν υποστηρίζεται.")
        except Exception as e:
            QMessageBox.critical(self, "Σφάλμα", f"Αποτυχία ανοίγματος φακέλου: {e}")

    def open_field_progress_page(self):
        """Opens the 'FieldProgressPage' to show a health/time chart for the field."""
        self.progress_page = FieldProgressPage(self.field_path)
        self.progress_page.show()

    # ---------------------------------------------------------------------
    # Fullscreen Zoomable Image
    # ---------------------------------------------------------------------
    def show_fullscreen_image(self):
        """Shows the current photo in a separate zoomable dialog."""
        if not hasattr(self, "photo_files") or not self.photo_files:
            return

        photo_file = os.path.join(self.photos_folder, self.photo_files[self.photo_index])
        if not os.path.exists(photo_file):
            print("Photo file not found or invalid.")
            return

        try:
            dlg = ZoomableImageDialog(photo_file, self)
            dlg.exec()
        except ValueError as e:
            print(e)


class ZoomableImageDialog(QDialog):
    """
    Displays an image with zoom & pan. A QSlider adjusts the zoom level (50–200%).
    """

    def __init__(self, image_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Image Viewer")
        self.image_path = image_path

        self.pixmap = QPixmap(image_path)
        if self.pixmap.isNull():
            raise ValueError("Error loading image")

        layout = QVBoxLayout(self)
        self.graphics_view = QGraphicsView(self)
        self.graphics_scene = QGraphicsScene(self)
        self.pixmap_item = QGraphicsPixmapItem(self.pixmap)
        self.graphics_scene.addItem(self.pixmap_item)
        self.graphics_view.setScene(self.graphics_scene)
        self.graphics_view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.graphics_view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        layout.addWidget(self.graphics_view)

        self.zoom_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.zoom_slider.setRange(50, 200)  # 50% to 200%
        self.zoom_slider.setValue(150)
        self.zoom_slider.valueChanged.connect(self.zoom_image)
        layout.addWidget(self.zoom_slider)

        close_btn = QPushButton("Close", self)
        close_btn.setStyleSheet("font-size: 14px; background-color: #d9d9d9; color: black; padding: 5px;")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

        self.setMinimumSize(self.pixmap.width(), self.pixmap.height())

    def zoom_image(self, value: int):
        """Adjust the QGraphicsView scale based on the slider's value."""
        scale_factor = value / 100.0
        self.graphics_view.resetTransform()
        self.graphics_view.scale(scale_factor, scale_factor)
