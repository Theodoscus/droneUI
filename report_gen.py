import os
import sqlite3
import subprocess
import platform
import pandas as pd
from datetime import datetime
import logging

# PyQt6 imports
from PyQt6.QtWidgets import (
    QMessageBox, QMainWindow, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget,
    QFrame, QGridLayout, QDialog, QSlider, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QScrollArea, QComboBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QPainter

# Matplotlib imports for chart display in PyQt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt

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
from shared import open_homepage

# ------------------------------------------------------------
# Register Fonts and Constants
# ------------------------------------------------------------

# Register Greek-capable font for ReportLab PDF generation
arial_font_path = "arial_greek.ttf"
pdfmetrics.registerFont(TTFont("ArialGreek", arial_font_path))

# Dictionary for translating disease classes from English to Greek
DISEASE_TRANSLATION = {
    "Healthy": "Υγιές",
    "Early Blight": "Αλτερναρίωση",
    "Late Blight": "Περονόσπορος",
    "Bacterial Spot": "Βακτηριακή Κηλίδωση",
    "Leaf Mold": "Κλαδοσπορίωση",
    "Leaf_Miner": "Φυλλοκνίστης",
    "Mosaic Virus": "Ιός του Μωσαϊκού",
    "Septoria": "Αδηλομήκυτας",
    "Spider Mites": "Τετράνυχος",
    "Yellow Leaf Curl Virus": "Ιός του Κίτρινου Καρουλιάσματος"
}

# Configure logging for the module
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

# ------------------------------------------------------------
# Drone Report Application Class
# ------------------------------------------------------------

class DroneReportApp(QMainWindow):
    """
    Main window class for displaying and managing drone flight reports.
    Responsibilities:
      - Load flight data from flight_data.db (SQLite)
      - Display disease counts via a bar chart
      - Show a photo carousel of affected plants with additional details
      - Export flight summaries to a Greek-enabled PDF report
    """

    def __init__(self, field_path: str):
        """
        Initializes the DroneReportApp window.

        Args:
            field_path (str): The path to the field folder (containing runs/ etc.)
        """
        super().__init__()
        self.setWindowTitle("Drone Flight Report")
        self.setGeometry(100, 100, 1200, 800)

        # Set up field paths and ensure the runs/ folder exists
        self.field_path = field_path
        self.runs_folder = os.path.join(self.field_path, "runs")
        os.makedirs(self.runs_folder, exist_ok=True)

        # Create a scrollable area for the content
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        self.main_layout = QVBoxLayout(scroll_content)
        scroll_area.setWidget(scroll_content)
        self.setCentralWidget(scroll_area)

        # Build the UI components
        self.setup_ui(self.main_layout)
        # Load the newest flight data if available
        self.load_newest_flight_data()

    # ---------------------------------------------------------------------
    # Database Utility Method
    # ---------------------------------------------------------------------
    @staticmethod
    def open_database(db_path: str):
        """
        Safely opens a SQLite database and returns the connection and cursor.

        Args:
            db_path (str): Path to the SQLite database file.

        Returns:
            tuple: (connection, cursor)
        """
        try:
            conn = sqlite3.connect(db_path)
            return conn, conn.cursor()
        except sqlite3.Error as e:
            raise RuntimeError(f"Database error: {e}")

    # ---------------------------------------------------------------------
    # UI Setup Methods
    # ---------------------------------------------------------------------
    def setup_ui(self, main_layout: QVBoxLayout):
        """
        Sets up the overall UI elements including header, stats, chart,
        photo carousel, and footer.

        Args:
            main_layout (QVBoxLayout): The main layout to populate with UI elements.
        """
        self.setup_header(main_layout)
        self.setup_stats_section(main_layout)
        self.setup_chart_section(main_layout)
        self.setup_image_section(main_layout)
        self.setup_footer(main_layout)

    def setup_header(self, main_layout: QVBoxLayout):
        """
        Builds the header layout containing:
          - Flight time label
          - Run selector combo box
          - Close button

        Args:
            main_layout (QVBoxLayout): Layout to add the header.
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
        close_button.clicked.connect(self.go_to_homepage)
        header_layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignRight)

        main_layout.addLayout(header_layout)

    def setup_stats_section(self, main_layout: QVBoxLayout):
        """
        Builds a frame to display flight statistics:
          - Disease count
          - Plants analyzed
          - Affected plants

        Args:
            main_layout (QVBoxLayout): Layout to add the stats section.
        """
        stats_frame = QFrame()
        stats_frame.setStyleSheet("border: 1px solid gray; padding: 10px; background-color: #f5f5f5;")
        stats_layout = QGridLayout(stats_frame)

        self.disease_count_label = QLabel("Ασθένειες που εντοπίστηκαν: ")
        self.plants_analyzed_label = QLabel("Φύλλα που αναλύθηκαν: ")
        self.affected_plants_label = QLabel("Επηρεασμένα φύλλα: ")

        for lbl in [self.disease_count_label, self.plants_analyzed_label, self.affected_plants_label]:
            lbl.setStyleSheet("font-size: 16px; padding: 5px; color: black;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        stats_layout.addWidget(self.disease_count_label, 0, 0)
        stats_layout.addWidget(self.plants_analyzed_label, 0, 1)
        stats_layout.addWidget(self.affected_plants_label, 0, 2)
        
        # New: Field Status Label
        self.field_status_label = QLabel("Κατάσταση Χωραφιού: --")
        self.field_status_label.setStyleSheet("font-size: 14px; color: red;")
        self.field_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Span the label across three columns
        stats_layout.addWidget(self.field_status_label, 1, 0, 1, 3)

        main_layout.addWidget(stats_frame)

    def setup_chart_section(self, main_layout: QVBoxLayout):
        """
        Builds a section containing a matplotlib bar chart.

        Args:
            main_layout (QVBoxLayout): Layout to add the chart section.
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
        Builds a section to display plant photos (photo carousel) and related disease info.

        Args:
            main_layout (QVBoxLayout): Layout to add the image section.
        """
        image_frame = QFrame()
        image_frame.setStyleSheet("border: 1px solid gray; padding: 10px; background-color: #f9f9f9;")
        image_layout = QVBoxLayout(image_frame)

        self.image_label = QLabel("Φύλλα με ασθένειες που εντοπίστηκαν στην πτήση")
        self.image_label.setStyleSheet("font-size: 16px; font-weight: bold; color: black;")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image_layout.addWidget(self.image_label)

        # Information frame for disease details
        info_frame = QFrame()
        info_frame.setStyleSheet("border: 1px solid gray; padding: 10px; background-color: #f1f1f1;")
        info_layout = QVBoxLayout(info_frame)

        self.disease_label = QLabel("Ασθένεια: --")
        self.disease_label.setStyleSheet("font-size: 14px; font-weight: bold; color: black;")
        info_layout.addWidget(self.disease_label)

        self.plant_id_label = QLabel("ID Φυτού: --")
        self.plant_id_label.setStyleSheet("font-size: 14px; font-weight: bold; color: black;")
        info_layout.addWidget(self.plant_id_label)

        self.confidence_label = QLabel("Βεβαιότητα: --%")
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

        # Navigation buttons for the photo carousel
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

        # Button to open the flight video in an external player
        external_player_button = QPushButton("Αναπαραγωγή Καταγραφής Πτήσης")
        external_player_button.setStyleSheet("font-size: 14px; background-color: #d9d9d9; color: black; padding: 10px;")
        external_player_button.clicked.connect(self.open_video_in_external_player)
        main_layout.addWidget(external_player_button)

        # Button to open the photos folder
        photos_button = QPushButton("Φωτογραφίες Επηρεασμένων Φύλλων", self)
        photos_button.setStyleSheet("font-size: 14px; background-color: #007BFF; color: white; padding: 10px;")
        photos_button.clicked.connect(self.open_photos_folder)
        main_layout.addWidget(photos_button)
        
        # Button to open the areas folder
        areas_button = QPushButton("Φωτογραφίες Επηρεασμένων Περιοχών", self)
        areas_button.setStyleSheet("font-size: 14px; background-color: #007BFF; color: white; padding: 10px;")
        areas_button.clicked.connect(self.open_areas_folder)
        main_layout.addWidget(areas_button)

    def setup_footer(self, main_layout: QVBoxLayout):
        """
        Builds the footer containing:
          - PDF export button
          - Flight duration label
          - Countermeasures button
          - Field progress view button

        Args:
            main_layout (QVBoxLayout): Layout to add the footer.
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

        progress_button = QPushButton("Πρόοδος Υγείας Χωραφιού")
        progress_button.setStyleSheet("font-size: 14px; background-color: #d9d9d9; color: black; padding: 10px;")
        progress_button.clicked.connect(self.open_field_progress_page)
        main_layout.addWidget(progress_button)

    # ---------------------------------------------------------------------
    # Flight Data Loading Methods
    # ---------------------------------------------------------------------
    def load_newest_flight_data(self):
        """
        Loads the newest flight data folder (by timestamp) from the runs/ directory.
        If the newest run’s flight_data.db is empty, then search older runs.
        If no run with data is found, show a message and return to the homepage.
        """
        if not os.path.exists(self.runs_folder):
            logging.info("No runs directory found in %s.", self.runs_folder)
            return

        flight_folders = [
            d for d in os.listdir(self.runs_folder)
            if os.path.isdir(os.path.join(self.runs_folder, d)) and d.startswith("run_")
        ]
        if not flight_folders:
            logging.info("Δεν βρέθηκαν δεδομένα πτήσης.")
            return

        flight_folders.sort(reverse=True)
        newest_run = os.path.join(self.runs_folder, flight_folders[0])
        db_path = os.path.join(newest_run, "flight_data.db")
        data_available = False

        if os.path.exists(db_path):
            try:
                conn = sqlite3.connect(db_path)
                df_all = pd.read_sql_query("SELECT * FROM flight_results", conn)
            except Exception as e:
                logging.error("Error reading DB in %s: %s", newest_run, e)
            finally:
                if 'conn' in locals():
                    conn.close()
            if not df_all.empty:
                data_available = True

        if data_available:
            logging.info("Loading newest run with data: %s", newest_run)
            self.load_results(newest_run)
            return
        else:
            # Newest run has no data; search for an older run that has data.
            for folder in flight_folders[1:]:
                run_folder = os.path.join(self.runs_folder, folder)
                db_path = os.path.join(run_folder, "flight_data.db")
                if os.path.exists(db_path):
                    try:
                        conn = sqlite3.connect(db_path)
                        df_all = pd.read_sql_query("SELECT * FROM flight_results", conn)
                    except Exception as e:
                        logging.error("Error reading DB in %s: %s", run_folder, e)
                        continue
                    finally:
                        if 'conn' in locals():
                            conn.close()
                    if not df_all.empty:
                        QMessageBox.information(self, "Δεν υπάρχουν δεδομένα",
                            "Η πιο πρόσφατη πτήση δεν έχει δεδομένα. Θα προβληθεί η πιο πρόσφατη αναφορά πτήσης που περιέχει δεδομένα.")
                        logging.info("Loading older run with data: %s", run_folder)
                        self.load_results(run_folder)
                        return
            # If no run with data is found:
            QMessageBox.information(self, "Δεν υπάρχουν δεδομένα", "Καμία αναφορά δεν έχει δεδομένα πτήσης. Επιστροφή στην αρχική σελίδα.")
            self.go_to_homepage()

    def list_previous_runs(self):
        """
        Lists previous flight run folders (sorted descending by timestamp) and maps
        a user-friendly display name to the folder name.

        Returns:
            list: A list of run display names.
        """
        if not os.path.exists(self.runs_folder):
            logging.info("No runs found in %s.", self.runs_folder)
            return []

        runs = [
            f for f in os.listdir(self.runs_folder)
            if os.path.isdir(os.path.join(self.runs_folder, f)) and f.startswith("run_")
        ]
        runs.sort(reverse=True)
        self.run_name_mapping = {}

        for run in runs:
            try:
                parts = run.split("_")  # Expected format: ["run", "YYYYMMDD", "HHMMSS"]
                timestamp = parts[1] + parts[2]
                flight_datetime = datetime.strptime(timestamp, "%Y%m%d%H%M%S")
                display_name = f"Πτήση: {flight_datetime.strftime('%d/%m/%Y %H:%M:%S')}"
                self.run_name_mapping[display_name] = run
            except (IndexError, ValueError):
                logging.warning("Invalid folder name format: %s", run)
                continue
        return list(self.run_name_mapping.keys())

    def load_selected_run(self):
        """
        Loads the run selected from the run_selector combo box.
        Displays warnings if no valid run is selected.
        """
        selected_run = self.run_selector.currentText()
        if not selected_run:
            QMessageBox.warning(self, "Δεν έχει επιλεγεί πτήση", "Παρακαλώ επιλέξτε πτήση.")
            return

        raw_run_name = self.run_name_mapping.get(selected_run)
        if not raw_run_name:
            QMessageBox.critical(self, "Μη έγκυρη πτήση", "Η επιλεγμένη πτήση δεν αντιστοιχεί σε έγκυρο φάκελο.")
            return

        run_folder = os.path.join(self.runs_folder, raw_run_name)
        if not os.path.exists(run_folder):
            QMessageBox.critical(self, "Μη έγκυρη πτήση", f"Ο φάκελος της πτήσης δεν υπάρχει: {run_folder}")
            return

        try:
            self.load_results(run_folder)
        except Exception as e:
            QMessageBox.critical(self, "Σφάλμα", f"Παρουσιάστηκε σφάλμα κατά τη φόρτωση της πτήσης: {e}")

    def load_results(self, flight_folder):
        """
        Loads flight results from flight_data.db within the provided flight folder.
        Updates charts, stats, and photo carousel accordingly.

        Args:
            flight_folder (str): The folder path containing flight_data.db and photos/.
        """
        self.current_flight_folder = flight_folder
        db_path = os.path.join(flight_folder, "flight_data.db")
        photos_folder = os.path.join(flight_folder, "photos")

        if not os.path.exists(db_path):
            logging.info("Database not found at: %s", db_path)
            return

        try:
            conn = sqlite3.connect(db_path)
            df_all = pd.read_sql_query("SELECT * FROM flight_results", conn)
        except sqlite3.Error as e:
            QMessageBox.critical(self, "Σφάλμα Βάσης Δεδομένων", f"Αδύνατη η ανάγνωση των αποτελεσμάτων πτήσης: {e}")
            return
        finally:
            if 'conn' in locals():
                conn.close()

        if df_all.empty:
            QMessageBox.information(self, "Δεν υπάρχουν δεδομένα", "Δεν βρέθηκαν αποτελέσματα πτήσης στη βάση δεδομένων.")
            return

        # Keep highest-confidence row per plant (ID)
        df_all = df_all.loc[df_all.groupby("ID")["Confidence"].idxmax()]

        disease_counts = df_all["Class"].value_counts()
        if "Healthy" not in disease_counts:
            disease_counts["Healthy"] = 0

        total_plants = df_all["ID"].nunique()
        affected_plants = total_plants - disease_counts["Healthy"]

        # Calculate the number of distinct diseases (excluding healthy)
        unique_diseases = len(disease_counts) - (1 if "Healthy" in disease_counts else 0)

        self.update_flight_data(
            flight_time=flight_folder.split("_"),
            diseases=unique_diseases,
            plants_analyzed=total_plants,
            affected_plants=affected_plants,
        )

        # Draw the bar chart using the disease counts
        self.draw_chart(disease_counts.index.tolist(), disease_counts.values.tolist())

        # Load the photo carousel
        self.load_photos(photos_folder, db_path)

        # Update flight duration if available
        if "FlightDuration" in df_all.columns:
            duration = df_all["FlightDuration"].iloc[0]
            self.flight_duration_label.setText(f"Διάρκεια Πτήσης: {duration}")

    # ---------------------------------------------------------------------
    # Photo Carousel Methods
    # ---------------------------------------------------------------------
    def load_photos(self, photos_folder: str, db_path: str):
        """
        Loads photos of plants whose highest-confidence classification is not "Healthy".
        Sets up the photo carousel if affected photos exist.

        Args:
            photos_folder (str): The folder containing plant photos.
            db_path (str): Path to the flight_data.db file.
        """
        if not os.path.exists(photos_folder):
            logging.info("Photos folder not found: %s", photos_folder)
            self.placeholder_image.setText("Δεν υπάρχουν διαθέσιμες φωτογραφίες.")
            return

        if not os.path.exists(db_path):
            logging.info("Database not found: %s", db_path)
            self.placeholder_image.setText("Δεν υπάρχουν διαθέσιμα αποτελέσματα.")
            return

        try:
            conn = sqlite3.connect(db_path)
            query = """
                SELECT ID,
                       MAX(CASE WHEN Class = 'Healthy' THEN Confidence ELSE 0 END) AS HealthyConfidence,
                       MAX(CASE WHEN Class != 'Healthy' THEN Confidence ELSE 0 END) AS NonHealthyConfidence
                FROM flight_results
                GROUP BY ID
            """
            df = pd.read_sql_query(query, conn)
        except sqlite3.Error as e:
            QMessageBox.critical(self, "Σφάλμα Βάσης Δεδομένων", f"Σφάλμα κατά την ανάγνωση της βάσης δεδομένων για τις φωτογραφίες ασθενών: {e}")
            return
        finally:
            if 'conn' in locals():
                conn.close()

        if df.empty:
            self.placeholder_image.setText("Δεν βρέθηκαν αποτελέσματα πτήσης.")
            return

        # Keep only IDs where non-healthy confidence exceeds healthy confidence
        affected_ids = df[df["NonHealthyConfidence"] > df["HealthyConfidence"]]["ID"].tolist()

        photo_files = [
            f for f in os.listdir(photos_folder)
            if f.endswith(".jpg") and int(f.split("_ID")[-1].replace(".jpg", "")) in affected_ids
        ]
        if not photo_files:
            self.placeholder_image.setText("Δεν υπάρχουν φωτογραφίες ασθενών φυτών.")
            return

        self.photo_files = photo_files
        self.photo_index = 0
        self.photos_folder = photos_folder
        self.update_carousel_image()

    def update_carousel_image(self):
        """
        Updates the displayed image in the photo carousel along with
        the associated disease details from the database.
        """
        if not hasattr(self, "photo_files") or not self.photo_files:
            return

        photo_file = os.path.join(self.photos_folder, self.photo_files[self.photo_index])
        if not os.path.exists(photo_file):
            self.placeholder_image.setText("Το αρχείο της φωτογραφίας δεν βρέθηκε.")
            return

        # Extract plant ID from photo filename
        try:
            plant_id = int(photo_file.split("_ID")[-1].replace(".jpg", ""))
        except ValueError:
            self.placeholder_image.setText("Μη έγκυρη μορφή ονόματος αρχείου φωτογραφίας.")
            return

        db_path = os.path.join(self.current_flight_folder, "flight_data.db")
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT Class, Confidence FROM flight_results WHERE ID=? ORDER BY Confidence DESC LIMIT 1", (plant_id,))
            row = cursor.fetchone()
        except sqlite3.Error as e:
            QMessageBox.critical(self, "Σφάλμα Βάσης Δεδομένων", f"Σφάλμα κατά την ανάγνωση των δεδομένων ταξινόμησης: {e}")
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
        """
        Moves to the next or previous photo in the carousel.

        Args:
            direction (str): "next" or "prev" to navigate through photos.
        """
        if not hasattr(self, "photo_files") or not self.photo_files:
            return

        if direction == "next":
            self.photo_index = (self.photo_index + 1) % len(self.photo_files)
        else:
            self.photo_index = (self.photo_index - 1) % len(self.photo_files)
        self.update_carousel_image()

    # ---------------------------------------------------------------------
    # Chart Visualization Methods
    # ---------------------------------------------------------------------
    def draw_chart(self, categories=None, values=None):
        """
        Draws a bar chart of disease categories versus counts.
        Ensures 'Healthy' is included, translates labels to Greek, and annotates bars.

        Args:
            categories (list): List of disease category names.
            values (list): List of counts corresponding to each category.
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
    # Flight Data Stats Update Method
    # ---------------------------------------------------------------------
    def update_flight_data(self, flight_time, diseases, plants_analyzed, affected_plants):
        """
        Updates the flight information labels and toggles the countermeasures button
        based on the number of diseases detected. Also updates the field status label
        based on the ratio of affected plants to total plants with intermediate statuses:
        - Normal (<20% affected)
        - Small Danger (20%-40%)
        - Moderate (40%-50%)
        - Critical (≥50%)

        Args:
            flight_time (list): Split parts of the flight folder name.
            diseases (int): Number of distinct disease types detected.
            plants_analyzed (int): Total number of plants analyzed.
            affected_plants (int): Number of plants affected (non-healthy).
        """
        try:
            combined_time = f"{flight_time[1]}_{flight_time[2]}"
            dt = datetime.strptime(combined_time, "%Y%m%d_%H%M%S").strftime("%d/%m/%Y %H:%M:%S")
        except (IndexError, ValueError):
            dt = "Άγνωστη"

        self.flight_time_label.setText(f"ΠΤΗΣΗ: {dt}")
        self.disease_count_label.setText(f"Ασθένειες που εντοπίστηκαν: {diseases}")
        self.plants_analyzed_label.setText(f"Φύλλα που αναλύθηκαν: {plants_analyzed}")
        self.affected_plants_label.setText(f"Επηρεασμένα φύλλα: {affected_plants}")

        # Compute the affected ratio and decide the status and style
        if plants_analyzed > 0:
            affected_ratio = affected_plants / plants_analyzed
        else:
            affected_ratio = 0

        if affected_ratio < 0.2:
            status_text = "Κανονική"
            bg_color = "green"
        elif affected_ratio < 0.5:
            status_text = "Μέτρια"
            bg_color = "orange"
        else:
            status_text = "Σοβαρή"
            bg_color = "red"

        self.field_status_label.setText(f"Κατάσταση Χωραφιού: {status_text}")
        self.field_status_label.setStyleSheet(f"font-size: 14px; background-color: {bg_color}; color: white;")

        # Enable or disable the countermeasures button
        if diseases == 0:
            self.countermeasures_button.setEnabled(False)
            self.countermeasures_button.setStyleSheet("font-size: 14px; background-color: #e0e0e0; color: gray; padding: 10px;")
        else:
            self.countermeasures_button.setEnabled(True)
            self.countermeasures_button.setStyleSheet("font-size: 14px; background-color: #d9d9d9; color: black; padding: 10px;")

    # ---------------------------------------------------------------------
    # PDF Export Methods
    # ---------------------------------------------------------------------
    def export_to_pdf(self):
        """
        Exports a PDF report including:
          - Flight info (date/time, duration)
          - A bar chart of disease classes
          - A table listing only diseased plants with photos
        """
        if not hasattr(self, "current_flight_folder") or not self.current_flight_folder:
            QMessageBox.warning(self, "Σφάλμα", "Δεν έχετε επιλέξει πτήση. Φορτώστε δεδομένα πριν την εξαγωγή.")
            return

        db_path = os.path.join(self.current_flight_folder, "flight_data.db")
        photos_folder = os.path.join(self.current_flight_folder, "photos")
        if not os.path.exists(db_path):
            QMessageBox.warning(self, "Σφάλμα", "Το αρχείο flight_data.db δεν υπάρχει. Αδυναμία εξαγωγής PDF.")
            return
        if not os.path.exists(photos_folder):
            QMessageBox.warning(self, "Σφάλμα", "Ο φάκελος φωτογραφιών δεν υπάρχει. Αδυναμία εξαγωγής PDF.")
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
            QMessageBox.critical(self, "Σφάλμα Βάσης Δεδομένων", f"Αδύνατη η ανάγνωση των αποτελεσμάτων πτήσης για το PDF: {e}")
            return
        finally:
            if 'conn' in locals():
                conn.close()

        if df_all.empty:
            QMessageBox.warning(self, "Δεν υπάρχουν δεδομένα", "Δεν βρέθηκαν αποτελέσματα πτήσης για εξαγωγή PDF.")
            return

        # Keep only the highest-confidence record per plant (ID)
        df_all = df_all.loc[df_all.groupby("ID")["Confidence"].idxmax()]

        total_plants = df_all["ID"].nunique()
        class_counts = df_all["Class"].value_counts()
        diseased_df = df_all[df_all["Class"] != "Healthy"]

        # Save the chart image temporarily for PDF insertion
        chart_filepath = os.path.join(self.current_flight_folder, "temp_chart.png")
        self.save_flight_chart_all_classes(class_counts, chart_filepath)

        doc = SimpleDocTemplate(pdf_path, pagesize=A4)
        elements = []
        styles = getSampleStyleSheet()
        greek_normal_style = styles["Normal"]
        greek_normal_style.fontName = "ArialGreek"

        greek_title_style = styles["Title"]
        greek_title_style.fontName = "ArialGreek"

        # Add title
        elements.append(Paragraph("Αναφορά Πτήσης (Flight Report)", greek_title_style))
        elements.append(Spacer(1, 12))

        # Flight summary information
        flight_info = f"""
        <b>Χωράφι:</b> {field_name}<br/>
        <b>Ημερομηνία Πτήσης:</b> {flight_date_text}<br/>
        <b>Διάρκεια Πτήσης:</b> {flight_duration_text}<br/>
        <b>Συνολικά Φυτά:</b> {total_plants}
        """
        elements.append(Paragraph(flight_info, greek_normal_style))
        elements.append(Spacer(1, 12))

        # Insert the chart image
        if os.path.exists(chart_filepath):
            chart_img = Image(chart_filepath, width=6 * inch, height=4 * inch)
            elements.append(chart_img)
            elements.append(Spacer(1, 12))
        else:
            elements.append(Paragraph("Το γράφημα δεν είναι διαθέσιμο.", greek_normal_style))
            elements.append(Spacer(1, 12))

        # Build the table of diseased plants
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
            QMessageBox.information(self, "Επιτυχία", f"Το PDF αποθηκεύτηκε στο: {pdf_path}")
        except Exception as e:
            QMessageBox.critical(self, "Σφάλμα", f"Αποτυχία δημιουργίας PDF: {e}")
        finally:
            if os.path.exists(chart_filepath):
                os.remove(chart_filepath)

    def get_field_name_from_folder(self, run_folder_path: str) -> str:
        """
        Extracts the field folder name from a run folder path. For example, given:
          /.../fields/<field_name>/runs/run_YYYYMMDD_HHMMSS
        it retrieves <field_name>.

        Args:
            run_folder_path (str): The full run folder path.

        Returns:
            str: The field name.
        """
        runs_dir = os.path.dirname(run_folder_path)
        field_dir = os.path.dirname(runs_dir)
        return os.path.basename(field_dir)

    def save_flight_chart_all_classes(self, class_counts: pd.Series, filepath: str):
        """
        Creates and saves a bar chart (including 'Healthy') representing the flight's class counts.
        The Y-axis maximum is set to max + 50.

        Args:
            class_counts (pd.Series): Series with class counts.
            filepath (str): The file path to save the chart image.
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
    # External Buttons & Windows Methods
    # ---------------------------------------------------------------------
    def show_countermeasures(self):
        """
        Opens a dialog displaying countermeasures for non-healthy diseases
        detected in the current flight.
        """
        if not getattr(self, "current_flight_folder", None):
            QMessageBox.warning(self, "Σφάλμα", "Δεν φορτώθηκε φάκελος πτήσης.")
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
            QMessageBox.critical(self, "Σφάλμα Βάσης Δεδομένων", f"Σφάλμα κατά την ανάγνωση της βάσης δεδομένων: {e}")
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
        # Open the countermeasures window (from countermeasures.py)
        db_path = os.path.join(self.current_flight_folder, "flight_data.db")
        cm_window = CounterMeasuresWindow(diseases_gr, db_path, parent=self)
        cm_window.exec()

    def open_video_in_external_player(self):
        """
        Opens the processed flight video in the OS default media player.
        """
        if not getattr(self, "current_flight_folder", None):
            logging.info("Δεν φορτώθηκαν δεδομένα πτήσης.")
            return

        exts = [".mp4", ".mov", ".avi"]
        video_path = None
        for ex in exts:
            candidate = os.path.join(self.current_flight_folder, f"processed_video{ex}")
            if os.path.exists(candidate):
                video_path = candidate
                break

        if not video_path:
            logging.info("Το βίντεο πτήσης δεν βρέθηκε.")
            return

        try:
            if platform.system() == "Windows":
                os.startfile(video_path)
            elif platform.system() == "Darwin":
                subprocess.run(["open", video_path])
            elif platform.system() == "Linux":
                subprocess.run(["xdg-open", video_path])
            else:
                logging.warning("Μη υποστηριζόμενο λειτουργικό σύστημα.")
        except Exception as e:
            logging.error("Σφάλμα κατά το άνοιγμα του βίντεο: %s", e)

    def open_photos_folder(self):
        """
        Opens the photos folder for the selected flight run in the OS file explorer.
        """
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
            QMessageBox.warning(self, "Σφάλμα", "Ο φάκελος φωτογραφιών δεν βρέθηκε.")
            return

        try:
            if platform.system() == "Windows":
                os.startfile(photos_dir)
            elif platform.system() == "Darwin":
                subprocess.run(["open", photos_dir])
            elif platform.system() == "Linux":
                subprocess.run(["xdg-open", photos_dir])
            else:
                QMessageBox.warning(self, "Σφάλμα", "Μη υποστηριζόμενο λειτουργικό σύστημα.")
        except Exception as e:
            QMessageBox.critical(self, "Σφάλμα", f"Αποτυχία ανοίγματος φακέλου: {e}")
            
    def open_areas_folder(self):
        """
        Opens the photos folder for the selected flight run in the OS file explorer.
        """
        selected_run = self.run_selector.currentText()
        if not selected_run:
            QMessageBox.warning(self, "Σφάλμα", "Παρακαλώ επιλέξτε πτήση.")
            return

        raw_run_name = getattr(self, "run_name_mapping", {}).get(selected_run, None)
        if not raw_run_name:
            QMessageBox.warning(self, "Σφάλμα", "Η επιλεγμένη πτήση δεν εντοπίστηκε.")
            return

        photos_dir = os.path.join(self.field_path, "runs", raw_run_name, "infected_frames")
        if not os.path.exists(photos_dir):
            QMessageBox.warning(self, "Σφάλμα", "Ο φάκελος επηρεασμένων περιοχών δεν βρέθηκε.")
            return

        try:
            if platform.system() == "Windows":
                os.startfile(photos_dir)
            elif platform.system() == "Darwin":
                subprocess.run(["open", photos_dir])
            elif platform.system() == "Linux":
                subprocess.run(["xdg-open", photos_dir])
            else:
                QMessageBox.warning(self, "Σφάλμα", "Μη υποστηριζόμενο λειτουργικό σύστημα.")
        except Exception as e:
            QMessageBox.critical(self, "Σφάλμα", f"Αποτυχία ανοίγματος φακέλου: {e}")

    def open_field_progress_page(self):
        """
        Opens the FieldProgressPage window to display a health/time chart for the field.
        """
        self.progress_page = FieldProgressPage(self.field_path)
        self.progress_page.show()

    # ---------------------------------------------------------------------
    # Fullscreen Zoomable Image Methods
    # ---------------------------------------------------------------------
    def show_fullscreen_image(self):
        """
        Displays the current photo from the carousel in a separate zoomable dialog.
        """
        if not hasattr(self, "photo_files") or not self.photo_files:
            return

        photo_file = os.path.join(self.photos_folder, self.photo_files[self.photo_index])
        if not os.path.exists(photo_file):
            logging.info("Το αρχείο της φωτογραφίας δεν βρέθηκε ή είναι μη έγκυρο.")
            return

        try:
            dlg = ZoomableImageDialog(photo_file, self)
            dlg.exec()
        except ValueError as e:
            logging.error("Σφάλμα κατά την προβολή της εικόνας σε πλήρη οθόνη: %s", e)

    # ---------------------------------------------------------------------
    # Navigation / Cleanup Methods
    # ---------------------------------------------------------------------
    def go_to_homepage(self):
        """
        Navigates back to the homepage.
        """
        # Here you would typically instantiate and show your homepage window.
        # For example:
        # from homepage import HomePage
        self.home_page = open_homepage()
        self.home_page.show()
        
        
        self.close()

# ------------------------------------------------------------
# Zoomable Image Dialog Class
# ------------------------------------------------------------
class ZoomableImageDialog(QDialog):
    """
    A dialog that displays an image with zoom and pan capabilities.
    A QSlider adjusts the zoom level from 50% to 200%.
    """

    def __init__(self, image_path: str, parent=None):
        """
        Initializes the ZoomableImageDialog with the specified image.

        Args:
            image_path (str): Path to the image file.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle("Προβολή Εικόνων")
        self.image_path = image_path

        self.pixmap = QPixmap(image_path)
        if self.pixmap.isNull():
            raise ValueError("Σφάλμα φόρτωσης εικόνας")

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
        self.zoom_slider.setRange(50, 200)  # Zoom range: 50% to 200%
        self.zoom_slider.setValue(150)
        self.zoom_slider.valueChanged.connect(self.zoom_image)
        layout.addWidget(self.zoom_slider)

        close_btn = QPushButton("Κλείσιμο", self)
        close_btn.setStyleSheet("font-size: 14px; background-color: #d9d9d9; color: black; padding: 5px;")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

        self.setMinimumSize(self.pixmap.width(), self.pixmap.height())

    def zoom_image(self, value: int):
        """
        Adjusts the zoom level of the image in the QGraphicsView based on the slider value.

        Args:
            value (int): Zoom percentage (50–200).
        """
        scale_factor = value / 100.0
        self.graphics_view.resetTransform()
        self.graphics_view.scale(scale_factor, scale_factor)
