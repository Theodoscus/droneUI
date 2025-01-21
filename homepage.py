import os
import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget,
    QLabel, QComboBox, QPushButton, QLineEdit, QMessageBox, QSpacerItem, QSizePolicy
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QPixmap, QPalette, QColor

from shared import open_drone_control,open_report_gen


FIELDS_FOLDER = "fields"


class HomePage(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AgroDrone - Home")
        # self.setGeometry(200, 200, 600, 500)
        self.init_ui()
        self.center_window()
        self.setFixedSize(600, 500)  # Set fixed width and height
        
    def init_ui(self):
        # Main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)

        # Set background color
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#ECECEA"))
        self.setPalette(palette)

        # Title Section
        title_layout = QVBoxLayout()
        title_label = QLabel("AgroDrone")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setFont(QFont("Arial", 32, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #2e7d32;")
        title_layout.addWidget(title_label)

        # Space for logo
        logo_label = QLabel()
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_pixmap = QPixmap("logo.webp")  # Replace with your logo path
        if not logo_pixmap.isNull():
            logo_label.setPixmap(logo_pixmap.scaled(150, 150, Qt.AspectRatioMode.KeepAspectRatio))
        else:
            logo_label.setText("LOGO")
            logo_label.setFont(QFont("Arial", 20))
            logo_label.setStyleSheet("color: #9e9e9e;")
        title_layout.addWidget(logo_label)

        main_layout.addLayout(title_layout)

        # Dropdown for selecting a field
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
                color: #37474f;  /* Darker color for text */
            }
            QComboBox QAbstractItemView {
                background-color: #ffffff;
                color: #37474f;  /* Darker color for dropdown items */
                border: 1px solid #bdbdbd;
            }
            """
        )
        self.field_selector.addItems(self.get_existing_fields())
        self.field_selector.currentTextChanged.connect(self.update_view_history_button)
        dropdown_layout.addWidget(self.field_selector)
        main_layout.addLayout(dropdown_layout)

        # Buttons Section
        buttons_layout = QVBoxLayout()

        # Proceed Button
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
                color: #eceff1;  /* Light text for disabled button */
            }
            """
        )
        self.history_button.setFixedHeight(50)
        self.history_button.clicked.connect(self.view_flight_history)
        buttons_layout.addWidget(self.history_button)

        # New Field Input and Button
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
                color: #37474f;  /* Darker text color for readability */
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

        # Spacer to center elements vertically
        main_layout.addSpacerItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        # Initialize button states
        self.update_view_history_button()
        
        
    def center_window(self):
        """Centers the window on the screen."""
        screen = self.screen().availableGeometry()  # Get available screen geometry
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)


    def get_existing_fields(self):
        # Get a list of existing field folders
        if not os.path.exists(FIELDS_FOLDER):
            os.makedirs(FIELDS_FOLDER)
        return sorted(os.listdir(FIELDS_FOLDER))

    def update_view_history_button(self):
        """Enable or disable the 'View Flight History' button based on folder contents."""
        selected_field = self.field_selector.currentText()
        if not selected_field:
            self.history_button.setEnabled(False)
            return

        # Path to the selected field
        field_path = os.path.join(FIELDS_FOLDER, selected_field)
        
        # Check if the field folder exists
        if not os.path.exists(field_path):
            self.history_button.setEnabled(False)
            return

        # Paths for required subfolders and database file
        runs_path = os.path.join(field_path, "runs")
        flights_path = os.path.join(field_path, "flights")
        flight_data_db = os.path.join(field_path, "field_data.db")

        # Check conditions: runs and flights folders exist and have content, and flight_data.db exists
        runs_has_content = os.path.exists(runs_path) and any(os.listdir(runs_path))
        flights_has_content = os.path.exists(flights_path) and any(os.listdir(flights_path))
        db_exists = os.path.exists(flight_data_db)

        # Enable the button only if all conditions are met
        self.history_button.setEnabled(runs_has_content and flights_has_content and db_exists)



    def proceed_to_drone_control(self):
        selected_field = self.field_selector.currentText()
        if not selected_field:
            QMessageBox.warning(self, "Warning", "Please select a field.")
            return

        field_path = os.path.join(FIELDS_FOLDER, selected_field)
        if not os.path.exists(field_path):
            QMessageBox.warning(self, "Error", f"Field path does not exist: {field_path}")
            return

        # Launch DroneControlApp with the selected field path
        self.drone_control_app = open_drone_control(field_path)
        self.drone_control_app.show()
        self.close()


    def view_flight_history(self):
        selected_field = self.field_selector.currentText()
        if not selected_field:
            QMessageBox.warning(self, "Warning", "Please select a field.")
            return

        # Determine the field path
        field_path = os.path.join(FIELDS_FOLDER, selected_field)
        if not os.path.exists(field_path):
            QMessageBox.warning(self, "Error", f"Field path does not exist: {field_path}")
            return

        # Launch the DroneReportApp with the selected field path
        self.report_app = open_report_gen(field_path)
        self.report_app.show()


    def create_new_field(self):
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
        
    


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = HomePage()
    window.show()
    sys.exit(app.exec())
