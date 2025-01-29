import os
import sqlite3

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton, QScrollArea, QWidget, QFrame,
    QHBoxLayout, QFileDialog, QTextEdit, QMessageBox
)
from PyQt6.QtCore import Qt


class CounterMeasuresWindow(QDialog):
    """
    A QDialog that displays recommended countermeasures for detected diseases.
    Also manages a personal note (saved to flight_data.db).
    """

    def __init__(self, diseases, flight_db_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Τρόποι Αντιμετώπισης για Ανιχνευμένες Ασθένειες")

        self.diseases = diseases
        self.flight_db_path = flight_db_path  # We'll store/read notes from this DB

        # Main layout
        main_layout = QVBoxLayout(self)
        self.setStyleSheet("background-color: #f9f9f9;")  # Light background

        # Title label
        title_label = QLabel("Τρόποι Αντιμετώπισης για Ανιχνευμένες Ασθένειες")
        title_label.setStyleSheet(
            "font-size: 24px; font-weight: bold; margin-bottom: 20px; color: black;"
        )
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title_label)

        # Scroll area for diseases
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        main_layout.addWidget(scroll_area)

        # Content widget in the scroll area
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.populate_diseases(self.diseases)  # Populate frames for each disease
        scroll_area.setWidget(self.content_widget)

        # Buttons at bottom
        button_layout = QHBoxLayout()
        
        export_button = QPushButton("Εξαγωγή Μέτρων")
        export_button.setStyleSheet(
            "font-size: 16px; color: black; padding: 10px; background-color: #ffffff; border: 1px solid #ccc;"
        )
        export_button.clicked.connect(self.export_measures)
        button_layout.addWidget(export_button)

        self.note_button = QPushButton("Προσωπική Σημείωση")
        self.note_button.setStyleSheet(
            "font-size: 16px; color: black; padding: 10px; background-color: #ffffff; border: 1px solid #ccc;"
        )
        self.note_button.clicked.connect(self.open_personal_note)
        button_layout.addWidget(self.note_button)

        close_button = QPushButton("Κλείσιμο")
        close_button.setStyleSheet(
            "font-size: 16px; color: black; padding: 10px; background-color: #ffffff; border: 1px solid #ccc;"
        )
        close_button.clicked.connect(self.close)
        button_layout.addWidget(close_button)

        main_layout.addLayout(button_layout)

    # ---------------------------------------------------------------------
    # Disease Data
    # ---------------------------------------------------------------------
    def populate_diseases(self, diseases_list):
        """
        Populates the scrollable area with frames for each disease + recommended measures.
        """
        self.countermeasures_dict = {
            "Αλτερναρίωση": (
                "Χρησιμοποιήστε μυκητοκτόνα που περιέχουν χλωροθαλονίλη ή μανκοζέμπ. "
                "Διατηρήστε τον χώρο καθαρό από υπολείμματα φυτών και εφαρμόστε αμειψισπορά "
                "για να μειώσετε τον κίνδυνο μόλυνσης. Αποφύγετε το υπερβολικό πότισμα και "
                "προτιμήστε ποικιλίες ανθεκτικές στην ασθένεια."
            ),
            "Περονόσπορος": (
                "Εφαρμόστε μυκητοκτόνα που βασίζονται σε χαλκό. Αφαιρέστε άμεσα τα μολυσμένα "
                "φυτά και καταστρέψτε τα. Διατηρήστε επαρκή αερισμό μεταξύ των φυτών και αποφύγετε "
                "το υπερβολικό πότισμα. Χρησιμοποιήστε ανθεκτικές ποικιλίες όπου είναι δυνατόν."
            ),
            "Βακτηριακή Κηλίδωση": (
                "Εξασφαλίστε επαρκή απόσταση μεταξύ των φυτών για καλή κυκλοφορία αέρα. "
                "Χρησιμοποιήστε βακτηριοκτόνα με βάση το χαλκό. Καταστρέψτε τα υπολείμματα "
                "μολυσμένων φυτών και αποφύγετε την καλλιέργεια σε υγρά εδάφη."
            ),
            "Κλαδοσπορίωση": (
                "Βελτιώστε τον αερισμό στα θερμοκήπια και μειώστε την υγρασία. "
                "Αποφύγετε το υπερβολικό πότισμα και προτιμήστε την άρδευση στο έδαφος "
                "αντί για το φύλλωμα. Χρησιμοποιήστε μυκητοκτόνα που συστήνονται για την ασθένεια."
            ),
            "Φυλλοκνίστης": (
                "Χρησιμοποιήστε παγίδες κόλλας για να μειώσετε τον πληθυσμό των εντόμων. "
                "Εισάγετε φυσικούς εχθρούς, όπως παρασιτικές σφήκες. Εφαρμόστε βιολογικά "
                "εντομοκτόνα όπου είναι απαραίτητο."
            ),
            "Ιός του Μωσαϊκού": (
                "Αφαιρέστε και καταστρέψτε τα μολυσμένα φυτά. Ελέγξτε τις αφίδες που διαδίδουν "
                "τον ιό με εντομοκτόνα ή φυσικούς εχθρούς. Χρησιμοποιήστε ανθεκτικές ποικιλίες "
                "και διατηρήστε τον χώρο καθαρό από ζιζάνια που μπορεί να φιλοξενούν τον ιό."
            ),
            "Αδηλομήκυτας": (
                "Εφαρμόστε μυκητοκτόνα με βάση τον χαλκό ή τη σουλφοναμίδη. Αφαιρέστε και "
                "καταστρέψτε τα μολυσμένα φύλλα. Μειώστε την υγρασία του φυλλώματος με καλό αερισμό "
                "και αποφύγετε την υπερβολική άρδευση."
            ),
            "Τετράνυχος": (
                "Ψεκάστε τα φυτά με ακαρεοκτόνα που συνιστώνται για την αντιμετώπιση του τετράνυχου. "
                "Εισάγετε αρπακτικά ακάρεα όπως το Phytoseiulus persimilis για βιολογικό έλεγχο. "
                "Διατηρήστε τις καλλιέργειες καθαρές από υπολείμματα που φιλοξενούν τον τετράνυχο."
            ),
            "Ιός του Κίτρινου Καρουλιάσματος": (
                "Χρησιμοποιήστε ανθεκτικές ποικιλίες φυτών. Ελέγξτε τους αλευρώδεις με "
                "εντομοκτόνα ή φυσικούς εχθρούς. Εφαρμόστε δίχτυα προστασίας στα θερμοκήπια "
                "για να αποτρέψετε την είσοδο των εντόμων."
            ),
        }

        for disease in diseases_list:
            if disease in self.countermeasures_dict:
                disease_frame = QFrame()
                disease_frame.setStyleSheet("border: 1px solid black; margin-bottom: 10px; padding: 10px;")
                disease_layout = QVBoxLayout(disease_frame)

                disease_label = QLabel(f"<b>{disease}</b>")
                disease_label.setStyleSheet("font-size: 16px; color: black; margin-bottom: 5px; border: none;")
                disease_layout.addWidget(disease_label)

                measures_text = self.countermeasures_dict[disease]
                measures_label = QLabel(measures_text)
                measures_label.setStyleSheet("font-size: 14px; color: black; border: none;")
                measures_label.setWordWrap(True)
                disease_layout.addWidget(measures_label)

                self.content_layout.addWidget(disease_frame)

    # ---------------------------------------------------------------------
    # Export & Personal Note
    # ---------------------------------------------------------------------
    def export_measures(self):
        """
        Exports the displayed countermeasures to a text file.
        """
        from PyQt6.QtWidgets import QFileDialog

        lines = ["## Ανιχνευμένες Ασθένειες & Τρόποι Αντιμετώπισης ##\n"]
        for disease in self.diseases:
            if disease in self.countermeasures_dict:
                lines.append(f"- {disease}:")
                lines.append(f"  {self.countermeasures_dict[disease]}\n")

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Εξαγωγή Μέτρων",
            os.getcwd(),
            "Text Files (*.txt);;All Files (*)"
        )
        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines))
                QMessageBox.information(self, "Επιτυχία", "Τα μέτρα εξήχθησαν με επιτυχία!")
            except Exception as e:
                QMessageBox.critical(self, "Σφάλμα", f"Αποτυχία εξαγωγής μέτρων: {e}")

    def open_personal_note(self):
        """
        Opens a PersonalNoteDialog that loads/saves a user note from flight_data.db.
        """
        note_dialog = PersonalNoteDialog(self.flight_db_path, self)
        note_dialog.exec()


class PersonalNoteDialog(QDialog):
    """
    A dialog for the farmer to view/edit a personal note. Stores the note in flight_data.db.
    """

    def __init__(self, db_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Προσωπική Σημείωση")
        self.setGeometry(500, 300, 400, 300)

        self.db_path = db_path
        self.init_ui()

        # Create user_notes table if not exists
        self.create_notes_table()

        # Load existing note (if any)
        existing_note = self.get_existing_note()
        if existing_note:
            self.note_edit.setPlainText(existing_note)

    def init_ui(self):
        """Constructs the UI elements (QTextEdit and Save/Cancel buttons)."""
        main_layout = QVBoxLayout(self)

        # -- ADD A STYLESHEET FOR THE DIALOG OR TEXTEDIT --
        # The simplest approach: Make the entire QDialog background white
        # and text color black
        self.setStyleSheet("""
            QDialog {
                background-color: white;
                color: black;
            }
            QPushButton {
                background-color: white;
                color: black;
            }
            QTextEdit {
                background-color: white;
                color: black;
                font-size: 14px;
            }
            QMessageBox {
                background-color: white;
                color: black;
            }
        """)

        self.note_edit = QTextEdit(self)
        self.note_edit.setPlaceholderText("Πληκτρολογήστε τις σημειώσεις σας εδώ...")
        main_layout.addWidget(self.note_edit)

        button_layout = QHBoxLayout()
        self.save_button = QPushButton("Αποθήκευση")
        self.save_button.clicked.connect(self.save_note)
        button_layout.addWidget(self.save_button)

        self.cancel_button = QPushButton("Ακύρωση")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        main_layout.addLayout(button_layout)

    # ---------------------------------------------------------------------
    # Database Operations
    # ---------------------------------------------------------------------
    def create_notes_table(self):
        """
        Ensures there's a 'user_notes' table in flight_data.db
        that holds exactly one note for now (id=1).
        You can adapt to store multiple notes if desired.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS user_notes (
                    id INTEGER PRIMARY KEY,
                    note_text TEXT
                )
            """)
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            QMessageBox.critical(
                self, "Database Error", f"Unable to create user_notes table:\n{e}"
            )

    def get_existing_note(self) -> str:
        """
        Retrieves the existing note from user_notes (row with id=1).
        Returns the note text or an empty string if none found.
        """
        note_text = ""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("SELECT note_text FROM user_notes WHERE id=1 LIMIT 1")
            row = c.fetchone()
            if row:
                note_text = row[0] or ""
            conn.close()
        except sqlite3.Error as e:
            QMessageBox.critical(self, "Database Error", f"Unable to read user_notes:\n{e}")
        return note_text

    def save_note_to_db(self, note: str):
        """
        Inserts or updates the single note in user_notes at id=1.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            # Upsert logic: if row with id=1 doesn't exist, insert it; else update
            c.execute("""
                INSERT INTO user_notes (id, note_text)
                VALUES (1, ?)
                ON CONFLICT(id)
                DO UPDATE SET note_text=excluded.note_text
            """, (note,))
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            QMessageBox.critical(self, "Database Error", f"Error saving note:\n{e}")

    # ---------------------------------------------------------------------
    # Button Handlers
    # ---------------------------------------------------------------------
    def save_note(self):
        # Existing logic: save the note to DB
        note_content = self.note_edit.toPlainText().strip()
        self.save_note_to_db(note_content)

        # Now, create a custom QMessageBox with a dark-on-light style
        msg = QMessageBox(self)
        msg.setWindowTitle("Αποθήκευση")
        msg.setText("Η σημείωση αποθηκεύτηκε με επιτυχία.")
        msg.setIcon(QMessageBox.Icon.Information)

        # Apply a stylesheet so the text + background are visible
        msg.setStyleSheet("""
            QMessageBox {
                background-color: white;
            }
            QMessageBox QLabel {
                color: black;  /* Message text color */
                font-size: 14px;
            }
            QMessageBox QPushButton {
                background-color: white; 
                color: black; 
                font-size: 14px;
            }
        """)

        msg.exec()  # Show the message box

        self.accept()  # Finally close the dialog after user presses OK
