import sys
import os
import datetime
import random

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget,
    QLabel, QComboBox, QPushButton, QLineEdit, QMessageBox, QSpacerItem, QSizePolicy
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QPixmap, QPalette, QColor, QIcon

from shared import open_drone_control, open_report_gen, open_real_drone_control


FIELDS_FOLDER = "fields"


class HomePage(QMainWindow):
    """
    The main landing/home page for AgroDrone, allowing users to:
      - Select an existing field or create a new one.
      - Proceed to drone control for a selected field.
      - View flight history if available.
    """

    def __init__(self):
        """
        Initializes the HomePage window with fixed size, sets up the UI,
        and centers the window on the screen.
        """
        super().__init__()
        self.setWindowTitle("AgroDrone - Home")
        # self.setGeometry(200, 200, 600, 500)

        # Set up the UI
        self.init_ui()
        # Center the window
        self.center_window()
        # Fix the window size
        self.setFixedSize(600, 500)

    # ---------------------------------------------------------------------
    # UI Initialization
    # ---------------------------------------------------------------------

    def init_ui(self):
        """
        Builds and lays out the main interface components:
          - Title + Logo
          - Field selector
          - Drone/History navigation buttons
          - Controls for creating a new field
        """
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        # Set a neutral background color
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#ECECEA"))
        self.setPalette(palette)

        # ---------------
        # Title Section
        # ---------------
        title_layout = QVBoxLayout()

        title_label = QLabel("AgroDrone")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setFont(QFont("Arial", 32, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #2e7d32;")
        title_layout.addWidget(title_label)

        # Display a logo if available, otherwise fallback text
        logo_label = QLabel()
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_pixmap = QPixmap("logos\logo.webp")  # Replace with your logo path
        if not logo_pixmap.isNull():
            logo_label.setPixmap(logo_pixmap.scaled(150, 150, Qt.AspectRatioMode.KeepAspectRatio))
        else:
            logo_label.setText("LOGO")
            logo_label.setFont(QFont("Arial", 20))
            logo_label.setStyleSheet("color: #9e9e9e;")
        title_layout.addWidget(logo_label)

        main_layout.addLayout(title_layout)

        # ---------------
        # Field Selector
        # ---------------
        dropdown_layout = QVBoxLayout()

        dropdown_label = QLabel("Επιλογή Χωραφιού:")
        dropdown_label.setFont(QFont("Arial", 14))
        dropdown_label.setStyleSheet("color: #37474f;")
        dropdown_layout.addWidget(dropdown_label)

        self.field_selector = QComboBox()
        self.field_selector.setFont(QFont("Arial", 12))
        self.field_selector.setStyleSheet(
            """
            QComboBox {
                padding: 5px;
                border: 1px solid #bdbdbd;
                background-color: #ffffff;
                color: #37474f;
            }
            QComboBox QAbstractItemView {
                background-color: #ffffff;
                color: #37474f;
                border: 1px solid #bdbdbd;
            }
            """
        )
        # Populate the combo with existing fields
        self.field_selector.addItems(self.get_existing_fields())
        self.field_selector.currentTextChanged.connect(self.update_view_history_button)
        dropdown_layout.addWidget(self.field_selector)

        main_layout.addLayout(dropdown_layout)

        # ---------------
        # Buttons Section
        # ---------------
        buttons_layout = QVBoxLayout()

        # Drone Control / Proceed Button
        proceed_button = QPushButton("Έλεγχος Drone")
        proceed_button.setFont(QFont("Arial", 16))
        proceed_button.setStyleSheet(
            "padding: 10px; background-color: #4caf50; color: white; border-radius: 5px;"
        )
        proceed_button.setFixedHeight(50)
        proceed_button.clicked.connect(self.proceed_to_drone_control)
        buttons_layout.addWidget(proceed_button)

        # View History Button
        self.history_button = QPushButton("Ιστορικό Πτήσεων")
        self.history_button.setFont(QFont("Arial", 16))
        self.history_button.setStyleSheet(
            """
            QPushButton {
                padding: 10px;
                background-color: #2196f3;
                color: white;
                border-radius: 5px;
            }
            QPushButton:disabled {
                background-color: #b0bec5;  /* Faded color for disabled state */
                color: #eceff1;            /* Light text for disabled button */
            }
            """
        )
        self.history_button.setFixedHeight(50)
        self.history_button.clicked.connect(self.view_flight_history)
        buttons_layout.addWidget(self.history_button)

        # New Field Input + Create Button
        new_field_layout = QHBoxLayout()

        self.new_field_input = QLineEdit()
        self.new_field_input.setPlaceholderText("Εισάγετε το όνομα του νέου χωραφιού")
        self.new_field_input.setFont(QFont("Arial", 14))
        self.new_field_input.setStyleSheet(
            """
            QLineEdit {
                padding: 5px;
                border: 1px solid #bdbdbd;
                background-color: #ffffff;
                color: #37474f;
            }
            """
        )
        new_field_layout.addWidget(self.new_field_input)

        create_button = QPushButton("Δημιουργία Χωραφιού")
        create_button.setFont(QFont("Arial", 14))
        create_button.setStyleSheet(
            "padding: 10px; background-color: #ff9800; color: white; border-radius: 5px;"
        )
        create_button.clicked.connect(self.create_new_field)
        new_field_layout.addWidget(create_button)

        buttons_layout.addLayout(new_field_layout)
        main_layout.addLayout(buttons_layout)

        # ---------------
        # Vertical Spacer
        # ---------------
        main_layout.addSpacerItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        # Initial update to set the state of the "View History" button
        self.update_view_history_button()

    # ---------------------------------------------------------------------
    # Window Positioning
    # ---------------------------------------------------------------------

    def center_window(self):
        """
        Centers the window on the primary screen.
        Called after init_ui to ensure correct geometry.
        """
        screen = self.screen().availableGeometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

    # ---------------------------------------------------------------------
    # Field Management
    # ---------------------------------------------------------------------

    def get_existing_fields(self):
        """
        Returns a sorted list of existing field folders in FIELDS_FOLDER.
        Creates FIELDS_FOLDER if it doesn't exist.
        """
        if not os.path.exists(FIELDS_FOLDER):
            os.makedirs(FIELDS_FOLDER)
        return sorted(os.listdir(FIELDS_FOLDER))

    def update_view_history_button(self):
        """
        Enables or disables the 'View Flight History' button based on whether
        the selected field has the necessary folders/files:
          - runs folder with content
          - flights folder with content
          - field_data.db
        """
        selected_field = self.field_selector.currentText()
        if not selected_field:
            self.history_button.setEnabled(False)
            return

        field_path = os.path.join(FIELDS_FOLDER, selected_field)
        if not os.path.exists(field_path):
            self.history_button.setEnabled(False)
            return

        runs_path = os.path.join(field_path, "runs")
        flights_path = os.path.join(field_path, "flights")
        flight_data_db = os.path.join(field_path, "field_data.db")

        runs_has_content = os.path.exists(runs_path) and any(os.listdir(runs_path))
        flights_has_content = os.path.exists(flights_path) and any(os.listdir(flights_path))
        db_exists = os.path.exists(flight_data_db)

        self.history_button.setEnabled(runs_has_content and flights_has_content and db_exists)

    # ---------------------------------------------------------------------
    # Navigation Methods
    # ---------------------------------------------------------------------

    def proceed_to_drone_control(self):
        """
        Opens the DroneControlApp for the currently selected field,
        if valid. Closes this window afterward.
        """
        selected_field = self.field_selector.currentText()
        if not selected_field:
            QMessageBox.warning(self, "Warning", "Please select a field.")
            return

        field_path = os.path.join(FIELDS_FOLDER, selected_field)
        if not os.path.exists(field_path):
            QMessageBox.warning(self, "Error", f"Field path does not exist: {field_path}")
            return

        # Launch drone control
        self.drone_control_app = open_real_drone_control(field_path)
        self.drone_control_app.show()
        self.close()

    def view_flight_history(self):
        """
        Opens the DroneReportApp with the currently selected field if valid.
        """
        selected_field = self.field_selector.currentText()
        if not selected_field:
            QMessageBox.warning(self, "Warning", "Please select a field.")
            return

        field_path = os.path.join(FIELDS_FOLDER, selected_field)
        if not os.path.exists(field_path):
            QMessageBox.warning(self, "Error", f"Field path does not exist: {field_path}")
            return

        # Launch flight history/report
        self.report_app = open_report_gen(field_path)
        self.report_app.show()
        self.close()
        

    def create_new_field(self):
        """
        Creates a new field folder if it doesn't already exist.
        Then adds the new field to the combo box and sets it as current.
        """
        new_field = self.new_field_input.text().strip()
        if not new_field:
            QMessageBox.warning(self, "Warning", "Field name cannot be empty.")
            return

        field_path = os.path.join(FIELDS_FOLDER, new_field)
        if os.path.exists(field_path):
            QMessageBox.warning(self, "Warning", "Field already exists.")
            return

        os.makedirs(field_path)
        self.field_selector.addItem(new_field)
        self.field_selector.setCurrentText(new_field)
        QMessageBox.information(self, "Success", f"Field '{new_field}' created successfully!")
        self.new_field_input.clear()
        self.update_view_history_button()


# ---------------------------------------------------------------------
# Main Guard
# ---------------------------------------------------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon("logos\\uop.gif"))
    window = HomePage()
    window.show()
    sys.exit(app.exec())
