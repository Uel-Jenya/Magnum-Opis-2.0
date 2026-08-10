import math
import sys
import threading
import ctypes
import ctypes.wintypes

from PyQt5.QtCore import QPoint, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPen, QPolygon
from PyQt5.QtWidgets import QApplication, QWidget


class OverlayScreen(QWidget):
    """A click-through overlay for engine arrows and evaluation information."""

    update_overlay_signal = pyqtSignal(object)

    def __init__(self, stockfish_queue, colors):
        super().__init__()
        self.stockfish_queue = stockfish_queue
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)

        self.arrows = []
        self.board_rect = None
        self.player_is_white = True
        self.evaluation = None
        self.predictions = []
        self.move_colors = [QColor(*[int(v) for v in colors[str(rank)]]) for rank in (1, 2, 3)]
        self.update_overlay_signal.connect(self.update_overlay)

        threading.Thread(target=self.listen_to_queue, daemon=True).start()

    def listen_to_queue(self):
        while True:
            self.update_overlay_signal.emit(self.stockfish_queue.get())

    def update_overlay(self, message):
        # Lists are retained for compatibility with older Stockfish processes.
        if isinstance(message, list):
            message = {"type": "arrows", "arrows": message}

        kind = message.get("type")
        if kind == "arrows":
            self.arrows = []
            for arrow in message["arrows"]:
                start = QPoint(*arrow["position"][0])
                end = QPoint(*arrow["position"][1])
                polygon = self.get_arrow_polygon(start, end)
                if polygon is not None:
                    self.arrows.append({"polygon": polygon, "start": start, "end": end,
                                        "label": arrow.get("label", "")})
        elif kind == "board":
            self.board_rect = tuple(message["rect"])
            self.player_is_white = message.get("player_is_white", True)
        elif kind == "evaluation":
            self.evaluation = message
        elif kind == "predictions":
            self.predictions = message["values"]
        elif kind == "clear":
            self.arrows = []
            self.predictions = []
            self.evaluation = None
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(QPen(Qt.PenStyle.NoPen))

        # Draw the evaluation bar FIRST so it is underneath the arrows.
        # This prevents arrow colours (especially the red third-choice arrow)
        # from bleeding into the evaluation bar visually.
        if self.board_rect and self.evaluation:
            self.draw_evaluation(painter)

        # Draw arrows on top of the evaluation bar.
        for index, arrow in enumerate(self.arrows):
            color = self.move_colors[min(index, len(self.move_colors) - 1)]
            painter.setBrush(color)
            painter.drawPolygon(arrow["polygon"])
            if arrow["label"]:
                self.draw_arrow_label(painter, arrow["start"], arrow["end"], arrow["label"], color)

        painter.end()

    @staticmethod
    def draw_arrow_label(painter, start, end, label, color):
        """Draw the resulting evaluation at the midpoint of an arrow shaft."""
        label_x = int(start.x() * 0.58 + end.x() * 0.42)
        label_y = int(start.y() * 0.58 + end.y() * 0.42)
        label_rect = painter.fontMetrics().boundingRect(label).adjusted(-7, -3, 7, 3)
        label_rect.moveCenter(QPoint(label_x, label_y))
        painter.setPen(Qt.PenStyle.NoPen)
        badge_color = QColor(color)
        badge_color.setAlpha(225)
        painter.setBrush(badge_color)
        painter.drawRoundedRect(label_rect, 4, 4)
        brightness = color.red() * 0.299 + color.green() * 0.587 + color.blue() * 0.114
        painter.setPen(QColor(20, 20, 20) if brightness > 190 else QColor(255, 255, 255))
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, label)
        painter.setPen(Qt.PenStyle.NoPen)

    def draw_evaluation(self, painter):
        board_x, board_y, board_width, board_height = self.board_rect
        bar_width = max(18, min(30, int(board_width * 0.055)))
        bar_x = int(board_x - bar_width - 6)
        bar_y = int(board_y)
        bar_height = int(board_height)

        # Evaluation is in centipawns from White's point of view.  Clamp it at
        # +/- 10 pawns so a large engine advantage remains readable.
        score = self.evaluation.get("score_cp", 0)
        white_fraction = max(0.0, min(1.0, 0.5 + score / 2000.0))
        # Replace this rectangle's pixels instead of alpha-blending them with
        # previously painted arrows.  This is important while it is the
        # player's turn, when the red third-choice arrow is visible.
        painter.save()
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(bar_x, bar_y, bar_width, bar_height, QColor(30, 30, 30))
        white_height = int(bar_height * white_fraction)
        # The bottom of the bar represents the side the player is using.  The
        # engine score is still White-perspective, so when playing Black the
        # White portion is drawn from the top instead.
        white_y = bar_y + bar_height - white_height if self.player_is_white else bar_y
        painter.fillRect(bar_x, white_y, bar_width, white_height, QColor(238, 238, 238))
        painter.restore()
        painter.setPen(QPen(QColor(110, 110, 110), 1))
        painter.drawRect(bar_x, bar_y, bar_width, bar_height)

        painter.setPen(QColor(255, 255, 255))
        painter.drawText(bar_x - 42, bar_y + 18, 40, 18, Qt.AlignmentFlag.AlignRight, self.evaluation["label"])
        for index, value in enumerate(self.predictions[:3]):
            painter.setPen(self.move_colors[index])
            painter.drawText(bar_x - 72, bar_y + 43 + index * 19, 68, 18,
                             Qt.AlignmentFlag.AlignRight, f"{index + 1}: {value}")

    @staticmethod
    def get_arrow_polygon(start_point, end_point):
        dx, dy = start_point.x() - end_point.x(), start_point.y() - end_point.y()
        length = math.hypot(dx, dy)
        if length == 0:
            return None
        norm_x, norm_y = dx / length, dy / length
        perp_x, perp_y = -norm_y, norm_x
        arrow_size = 25
        left = QPoint(int(end_point.x() + arrow_size * norm_x * 1.5 + arrow_size * perp_x),
                      int(end_point.y() + arrow_size * norm_y * 1.5 + arrow_size * perp_y))
        right = QPoint(int(end_point.x() + arrow_size * norm_x * 1.5 - arrow_size * perp_x),
                       int(end_point.y() + arrow_size * norm_y * 1.5 - arrow_size * perp_y))
        middle_left = QPoint(int((2 * left.x() + 3 * right.x()) / 5), int((2 * left.y() + 3 * right.y()) / 5))
        middle_right = QPoint(int((3 * left.x() + 2 * right.x()) / 5), int((3 * left.y() + 2 * right.y()) / 5))
        tail_left = QPoint(int(start_point.x() + arrow_size * perp_x / 5), int(start_point.y() + arrow_size * perp_y / 5))
        tail_right = QPoint(int(start_point.x() - arrow_size * perp_x / 5), int(start_point.y() - arrow_size * perp_y / 5))
        return QPolygon([end_point, left, middle_left, tail_right, tail_left, middle_right, right])


def run(stockfish_queue, colors):
    app = QApplication(sys.argv)
    overlay = OverlayScreen(stockfish_queue, colors)
    overlay.show()
    # Exclude overlay from Discord/OBS screen capture using its native HWND
    try:
        hwnd = int(overlay.winId())
        if hwnd:
            # Layer 1: SetWindowDisplayAffinity
            # WDA_EXCLUDEFROMCAPTURE | WDA_MONITOR = 0x13
            ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x13)
            # Layer 2: DWM exclusion attribute (Windows 10 2004+)
            try:
                excluded = ctypes.c_int(1)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    ctypes.wintypes.HWND(hwnd), 33,
                    ctypes.byref(excluded), ctypes.sizeof(excluded)
                )
            except Exception:
                pass
    except Exception:
        pass
    app.exec()
