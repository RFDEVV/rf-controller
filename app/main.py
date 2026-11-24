"""RF Controller: aplikasi setting untuk remot RC GA-4H + ESP32-S3."""
import sys

from PySide6.QtCore import QSettings, Qt, QVariantAnimation
from PySide6.QtGui import QFont, QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication

from rfc import APP_NAME
from rfc.params import resource_path
from rfc.splash import Splash
from rfc.theme import Theme
from rfc.window import MainWindow


def main():
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("RFBuilder")
    app.setWindowIcon(QIcon(resource_path("assets/icon.png")))
    s = QSettings("RFBuilder", "RFController")
    theme = Theme(dark=str(s.value("dark", "true")).lower() == "true")
    theme.animations = str(s.value("animations", "true")).lower() == "true"
    app.setStyleSheet(theme.qss())

    win = MainWindow(theme)
    splash = Splash(theme)

    def reveal():
        win.setWindowOpacity(0.0)
        win.show()
        a = QVariantAnimation(win)
        a.setDuration(300 if theme.animations else 0)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.valueChanged.connect(lambda v: win.setWindowOpacity(float(v)))
        a.start()
        win._reveal = a

    splash.finished.connect(reveal)
    splash.start()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
