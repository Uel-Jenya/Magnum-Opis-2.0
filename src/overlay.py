'''
import math
import sys
import threading
from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtGui import QBrush, QColor, QPainter, QPen, QGuiApplication, QPolygon, QColorConstants 
from PyQt5.QtWidgets import QApplication, QWidget


class OverlayScreen(QWidget):
    def __init__(self, stockfish_queue, colors):
        super().__init__()
        self.stockfish_queue = stockfish_queue

        # Set the window to be the size of the screen
        self.screen = QGuiApplication.screens()[0]
        self.setFixedWidth(self.screen.size().width())
        self.setFixedHeight(self.screen.size().height())

        # Set the window to be transparent
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)

        # A list of QPolygon objects containing the points of the arrows
        self.arrows = []

        # Start the message queue thread
        self.message_queue_thread = threading.Thread(target=self.message_queue_thread)
        self.message_queue_thread.start()
        
        self.move_colors = {
            'best_move': QBrush(QColor(colors["1"][0], colors["1"][1], colors["1"][2], colors["1"][3]), Qt.BrushStyle.SolidPattern),
            '2nd_best_move': QBrush(QColor(colors["2"][0], colors["2"][1], colors["2"][2], colors["2"][3]), Qt.BrushStyle.SolidPattern),
            '3rd_best_move': QBrush(QColor(colors["3"][0], colors["3"][1], colors["3"][2], colors["3"][3]), Qt.BrushStyle.SolidPattern)
        }

    def message_queue_thread(self):
        """
        This thread is used to receive messages from the stockfish message queue
        and update the arrows
        Args:
            None
        Returns:
            None
        """

        while True:
            message = self.stockfish_queue.get()
            self.set_arrows(message)

    def set_arrows(self, arrows):
        """
        This function is used to set the arrows to be drawn on the screen
        Args:
            arrows: A list of tuples containing the start and end position of the arrows
            in the form of ((start_point, end_point), (start_point, end_point))
        Returns:
            None
        """

        self.arrows = []
        for arrow in arrows:
            poly = self.get_arrow_polygon(
                QPoint(arrow['position'][0][0], arrow['position'][0][1]),
                QPoint(arrow['position'][1][0], arrow['position'][1][1])
            )
            self.arrows.append(poly)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setPen(QPen(Qt.GlobalColor.red, 1, Qt.PenStyle.NoPen))
        for i in range(len(self.arrows)):
            if i == 0:
                painter.setBrush(self.move_colors["best_move"])
            elif i == 1:
                painter.setBrush(self.move_colors["2nd_best_move"])
            elif i == 2:
                painter.setBrush(self.move_colors["3rd_best_move"])

            painter.drawPolygon(self.arrows[i])
        painter.end()

    def get_arrow_polygon(self, start_point, end_point):
        """
        This function is used to get the polygon for the arrow
        Args:
            start_point: The start point of the arrow
            end_point: The end point of the arrow
        Returns:
            A QPolygon object containing the points of the arrow
        """

        try:
            dx, dy = start_point.x() - end_point.x(), start_point.y() - end_point.y()

            # Normalize the vector
            leng = math.sqrt(dx ** 2 + dy ** 2)
            norm_x, norm_y = dx / leng, dy / leng

            # Get the perpendicular vector
            perp_x = -norm_y
            perp_y = norm_x

            arrow_height = 25
            left_x = end_point.x() + arrow_height * norm_x * 1.5 + arrow_height * perp_x
            left_y = end_point.y() + arrow_height * norm_y * 1.5 + arrow_height * perp_y

            right_x = end_point.x() + arrow_height * norm_x * 1.5 - arrow_height * perp_x
            right_y = end_point.y() + arrow_height * norm_y * 1.5 - arrow_height * perp_y

            point2 = QPoint(int(left_x), int(left_y))
            point3 = QPoint(int(right_x), int(right_y))

            mid_point1 = QPoint(int((2 / 5) * point2.x() + (3 / 5) * point3.x()), int((2 / 5) * point2.y() + (3 / 5) * point3.y()))
            mid_point2 = QPoint(int((3 / 5) * point2.x() + (2 / 5) * point3.x()), int((3 / 5) * point2.y() + (2 / 5) * point3.y()))

            start_left = QPoint(int(start_point.x() + (arrow_height / 5) * perp_x), int(start_point.y() + (arrow_height / 5) * perp_y))
            start_right = QPoint(int(start_point.x() - (arrow_height / 5) * perp_x), int(start_point.y() - (arrow_height / 5) * perp_y))

            return QPolygon([end_point, point2, mid_point1, start_right, start_left, mid_point2, point3])
        except Exception as e:
            print(e)


def run(stockfish_queue, colors):
    """
    This function is used to run the overlay
    Args:
        stockfish_queue: The message queue used to communicate with the stockfish thread
    Returns:
        None
    """

    app = QApplication(sys.argv)
    overlay = OverlayScreen(stockfish_queue, colors)
    overlay.show()
    app.exec()
'''

import math
import sys
import threading
import time  # Optional: used for debug timing

from PyQt5.QtCore import Qt, QPoint, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QPainter, QPen, QGuiApplication, QPolygon
from PyQt5.QtWidgets import QApplication, QWidget


class OverlayScreen(QWidget):
    # Signal used to safely update arrows from a background thread
    update_arrows_signal = pyqtSignal(list)

    def __init__(self, stockfish_queue, colors):
        super().__init__()
        self.stockfish_queue = stockfish_queue

        # Get the primary screen and set overlay size to match
        self.screen = QGuiApplication.screens()[0]
        self.setFixedWidth(self.screen.size().width())
        self.setFixedHeight(self.screen.size().height())

        # Configure window to be transparent, always-on-top, and non-interactive
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)

        # Stores arrow shapes (as QPolygon objects) to be drawn
        self.arrows = []

        # Connect signal to GUI-safe arrow updating function
        self.update_arrows_signal.connect(self.set_arrows)

        # Start a background thread to listen for incoming arrows
        self.message_queue_thread = threading.Thread(target=self.listen_to_queue, daemon=True)
        self.message_queue_thread.start()

        # Define colors for the 1st, 2nd, and 3rd best moves
        self.move_colors = {
            'best_move': QBrush(QColor(*colors["1"]), Qt.BrushStyle.SolidPattern),
            '2nd_best_move': QBrush(QColor(*colors["2"]), Qt.BrushStyle.SolidPattern),
            '3rd_best_move': QBrush(QColor(*colors["3"]), Qt.BrushStyle.SolidPattern)
        }

    def listen_to_queue(self):
        """
        Background thread function that listens for new arrow messages
        from the stockfish_queue and emits them via a Qt signal.
        """
        while True:
            message = self.stockfish_queue.get()
            print("[Overlay] Received arrows at", time.time())  # Debug: timestamp
            self.update_arrows_signal.emit(message)

    def set_arrows(self, arrows):
        """
        Receives arrow data, generates polygons, and triggers repaint.
        Args:
            arrows (list): Each item has 'position': [(x1, y1), (x2, y2)]
        """
        self.arrows = []
        for arrow in arrows:
            poly = self.get_arrow_polygon(
                QPoint(arrow['position'][0][0], arrow['position'][0][1]),
                QPoint(arrow['position'][1][0], arrow['position'][1][1])
            )
            if poly:
                self.arrows.append(poly)
        self.update()  # Triggers paintEvent()

    def paintEvent(self, event):
        """
        Called by Qt when the window needs to be repainted.
        Draws each arrow with the appropriate color.
        """
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setPen(QPen(Qt.GlobalColor.red, 1, Qt.PenStyle.NoPen))  # No border around shapes

        for i in range(len(self.arrows)):
            # Set brush color based on arrow order (best → third-best)
            if i == 0:
                painter.setBrush(self.move_colors["best_move"])
            elif i == 1:
                painter.setBrush(self.move_colors["2nd_best_move"])
            elif i == 2:
                painter.setBrush(self.move_colors["3rd_best_move"])

            painter.drawPolygon(self.arrows[i])

        painter.end()

    def get_arrow_polygon(self, start_point, end_point):
        """
        Creates a custom arrow-shaped polygon between two points.
        Args:
            start_point (QPoint): Where the arrow starts
            end_point (QPoint): Where the arrowhead points to
        Returns:
            QPolygon: A 7-point arrow shape
        """
        try:
            dx, dy = start_point.x() - end_point.x(), start_point.y() - end_point.y()
            leng = math.hypot(dx, dy)
            if leng == 0:
                return None  # Avoid division by zero

            # Unit vector pointing from end to start
            norm_x, norm_y = dx / leng, dy / leng

            # Perpendicular vector for arrow width
            perp_x, perp_y = -norm_y, norm_x

            arrow_height = 25  # Total arrow size (length + width)

            # Arrowhead side points
            left_x = end_point.x() + arrow_height * norm_x * 1.5 + arrow_height * perp_x
            left_y = end_point.y() + arrow_height * norm_y * 1.5 + arrow_height * perp_y
            right_x = end_point.x() + arrow_height * norm_x * 1.5 - arrow_height * perp_x
            right_y = end_point.y() + arrow_height * norm_y * 1.5 - arrow_height * perp_y

            point2 = QPoint(int(left_x), int(left_y))
            point3 = QPoint(int(right_x), int(right_y))

            # Smooth middle curve between arrowhead and tail
            mid_point1 = QPoint(int((2 / 5) * point2.x() + (3 / 5) * point3.x()),
                                int((2 / 5) * point2.y() + (3 / 5) * point3.y()))
            mid_point2 = QPoint(int((3 / 5) * point2.x() + (2 / 5) * point3.x()),
                                int((3 / 5) * point2.y() + (2 / 5) * point3.y()))

            # Tail corners
            start_left = QPoint(int(start_point.x() + (arrow_height / 5) * perp_x),
                                int(start_point.y() + (arrow_height / 5) * perp_y))
            start_right = QPoint(int(start_point.x() - (arrow_height / 5) * perp_x),
                                 int(start_point.y() - (arrow_height / 5) * perp_y))

            # Return full arrow shape as a polygon
            return QPolygon([end_point, point2, mid_point1, start_right, start_left, mid_point2, point3])
        except Exception as e:
            print("Arrow polygon error:", e)
            return None


def run(stockfish_queue, colors):
    """
    Launch the overlay as a Qt application window.
    Args:
        stockfish_queue: A Queue object from which arrow data is read
        colors: Dictionary mapping move ranks ("1", "2", "3") to RGBA tuples
    """
    app = QApplication(sys.argv)
    overlay = OverlayScreen(stockfish_queue, colors)
    overlay.show()
    app.exec()
