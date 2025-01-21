from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QScrollArea, QWidget, QFrame
from PyQt6.QtCore import Qt

class CounterMeasuresWindow(QDialog):
    def __init__(self, diseases, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Τρόποι Αντιμετώπισης για Ανιχνευμένες Ασθένειες")
        

        # Set up the main layout
        layout = QVBoxLayout(self)
        self.setStyleSheet("background-color: #f9f9f9;")  # Bright background

        # Add a label for the title
        title_label = QLabel("Τρόποι Αντιμετώπισης για Ανιχνευμένες Ασθένειες")
        title_label.setStyleSheet("font-size: 24px; font-weight: bold; margin-bottom: 20px; color: black;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        # Create a scrollable area to display the countermeasures
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        layout.addWidget(scroll_area)

        # Content widget for the scroll area
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)

        # Define countermeasures for diseases in Greek with more details
        countermeasures = {
            "Αλτερναρίωση": "Χρησιμοποιήστε μυκητοκτόνα που περιέχουν χλωροθαλονίλη ή μανκοζέμπ. Διατηρήστε τον χώρο καθαρό από υπολείμματα φυτών και εφαρμόστε αμειψισπορά για να μειώσετε τον κίνδυνο μόλυνσης. Αποφύγετε το υπερβολικό πότισμα και προτιμήστε ποικιλίες ανθεκτικές στην ασθένεια.",
            "Περονόσπορος": "Εφαρμόστε μυκητοκτόνα που βασίζονται σε χαλκό. Αφαιρέστε άμεσα τα μολυσμένα φυτά και καταστρέψτε τα. Διατηρήστε επαρκή αερισμό μεταξύ των φυτών και αποφύγετε το υπερβολικό πότισμα. Χρησιμοποιήστε ανθεκτικές ποικιλίες όπου είναι δυνατόν.",
            "Βακτηριακή Κηλίδωση": "Εξασφαλίστε επαρκή απόσταση μεταξύ των φυτών για καλή κυκλοφορία αέρα. Χρησιμοποιήστε βακτηριοκτόνα με βάση το χαλκό. Καταστρέψτε τα υπολείμματα μολυσμένων φυτών και αποφύγετε την καλλιέργεια σε υγρά εδάφη.",
            "Κλαδοσπορίωση": "Βελτιώστε τον αερισμό στα θερμοκήπια και μειώστε την υγρασία. Αποφύγετε το υπερβολικό πότισμα και προτιμήστε την άρδευση στο έδαφος αντί για το φύλλωμα. Χρησιμοποιήστε μυκητοκτόνα που συστήνονται για την ασθένεια.",
            "Φυλλοκνίστης": "Χρησιμοποιήστε παγίδες κόλλας για να μειώσετε τον πληθυσμό των εντόμων. Εισάγετε φυσικούς εχθρούς, όπως παρασιτικές σφήκες. Εφαρμόστε βιολογικά εντομοκτόνα όπου είναι απαραίτητο.",
            "Ιός του Μωσαϊκού": "Αφαιρέστε και καταστρέψτε τα μολυσμένα φυτά. Ελέγξτε τις αφίδες που διαδίδουν τον ιό με εντομοκτόνα ή φυσικούς εχθρούς. Χρησιμοποιήστε ανθεκτικές ποικιλίες και διατηρήστε τον χώρο καθαρό από ζιζάνια που μπορεί να φιλοξενούν τον ιό.",
            "Αδηλομήκυτας": "Εφαρμόστε μυκητοκτόνα με βάση τον χαλκό ή τη σουλφοναμίδη. Αφαιρέστε και καταστρέψτε τα μολυσμένα φύλλα. Μειώστε την υγρασία του φυλλώματος με καλό αερισμό και αποφύγετε την υπερβολική άρδευση.",
            "Τετράνυχος": "Ψεκάστε τα φυτά με ακαρεοκτόνα που συνιστώνται για την αντιμετώπιση του τετράνυχου. Εισάγετε αρπακτικά ακάρεα όπως το Phytoseiulus persimilis για βιολογικό έλεγχο. Διατηρήστε τις καλλιέργειες καθαρές από υπολείμματα που φιλοξενούν τον τετράνυχο.",
            "Ιός του Κίτρινου Καρουλιάσματος": "Χρησιμοποιήστε ανθεκτικές ποικιλίες φυτών. Ελέγξτε τους αλευρώδεις με εντομοκτόνα ή φυσικούς εχθρούς. Εφαρμόστε δίχτυα προστασίας στα θερμοκήπια για να αποτρέψετε την είσοδο των εντόμων.",
        }

        # Populate the scroll area with countermeasures for detected diseases
        for disease in diseases:
            if disease in countermeasures:
                # Create a frame for each disease
                disease_frame = QFrame()
                disease_frame.setStyleSheet("border: 1px solid black; margin-bottom: 10px; padding: 10px;")
                disease_layout = QVBoxLayout(disease_frame)

                # Disease label
                disease_label = QLabel(f"<b>{disease}</b>")
                disease_label.setStyleSheet("font-size: 16px; color: black; margin-bottom: 5px; border: none;")
                disease_layout.addWidget(disease_label)

                # Countermeasure label
                countermeasure_label = QLabel(countermeasures[disease])
                countermeasure_label.setStyleSheet("font-size: 14px; color: black; border: none;")
                countermeasure_label.setWordWrap(True)
                disease_layout.addWidget(countermeasure_label)

                content_layout.addWidget(disease_frame)

        scroll_area.setWidget(content_widget)

        # Add a close button
        close_button = QPushButton("Κλείσιμο")
        close_button.setStyleSheet("font-size: 16px; color: black; padding: 10px; background-color: #ffffff; border: 1px solid #ccc;")
        close_button.clicked.connect(self.close)
        layout.addWidget(close_button)
