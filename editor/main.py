import sys
import os
from PyQt5.QtWidgets import QApplication

# Ensure root directory is in sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from editor.editor_window import EditorMainWindow


def main():
    app = QApplication(sys.argv)
    window = EditorMainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
