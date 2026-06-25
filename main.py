# main.py

import sys
from PySide6.QtWidgets import QApplication
from interface import KpiAppGui

if __name__ == "__main__":
    """
    Main entry point for the application.
    Initializes and shows the GUI.
    """
    app = QApplication(sys.argv)
    window = KpiAppGui()
    window.show()
    sys.exit(app.exec())