"""Vector icon renderer for consistent, sharp, and purpose-driven iconography."""

from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QPainterPath, QBrush
from PySide6.QtCore import Qt, QRectF, QPointF

def render_icon(name: str, size: int = 16, color_hex: str = "#EDEFEA") -> QIcon:
    """Renders a sharp geometric icon using QPainter."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)

    color = QColor(color_hex)
    pen = QPen(color, 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)

    s = float(size)
    pad = s * 0.15

    if name == "plus":
        painter.drawLine(QPointF(s / 2, pad), QPointF(s / 2, s - pad))
        painter.drawLine(QPointF(pad, s / 2), QPointF(s - pad, s / 2))

    elif name == "check":
        path = QPainterPath()
        path.moveTo(pad, s * 0.52)
        path.lineTo(s * 0.42, s - pad)
        path.lineTo(s - pad, pad * 1.2)
        painter.drawPath(path)

    elif name == "cross":
        painter.drawLine(QPointF(pad, pad), QPointF(s - pad, s - pad))
        painter.drawLine(QPointF(s - pad, pad), QPointF(pad, s - pad))

    elif name == "arrow_left":
        path = QPainterPath()
        path.moveTo(s * 0.65, pad)
        path.lineTo(s * 0.35, s / 2)
        path.lineTo(s * 0.65, s - pad)
        painter.drawPath(path)

    elif name == "arrow_right":
        path = QPainterPath()
        path.moveTo(s * 0.35, pad)
        path.lineTo(s * 0.65, s / 2)
        path.lineTo(s * 0.35, s - pad)
        painter.drawPath(path)

    elif name == "folder":
        path = QPainterPath()
        path.moveTo(pad, pad * 1.5)
        path.lineTo(s * 0.45, pad * 1.5)
        path.lineTo(s * 0.55, pad * 2.2)
        path.lineTo(s - pad, pad * 2.2)
        path.lineTo(s - pad, s - pad)
        path.lineTo(pad, s - pad)
        path.closeSubpath()
        painter.drawPath(path)

    elif name == "edit":
        # Sharp minimalist pencil
        path = QPainterPath()
        path.moveTo(s - pad, pad + 2)
        path.lineTo(s - pad - 2, pad)
        path.lineTo(pad + 2, s - pad - 2)
        path.lineTo(pad, s - pad)
        path.lineTo(pad + 2, s - pad)
        path.closeSubpath()
        painter.drawPath(path)

    elif name == "loupe":
        r = (s - pad * 2) * 0.38
        cx, cy = pad + r, pad + r
        painter.drawEllipse(QPointF(cx, cy), r, r)
        painter.drawLine(QPointF(cx + r * 0.7, cy + r * 0.7), QPointF(s - pad, s - pad))

    elif name == "fit":
        # Fit to window: 4 corner brackets
        corner_len = s * 0.22
        # Top-left
        painter.drawLine(QPointF(pad, pad + corner_len), QPointF(pad, pad))
        painter.drawLine(QPointF(pad, pad), QPointF(pad + corner_len, pad))
        # Top-right
        painter.drawLine(QPointF(s - pad - corner_len, pad), QPointF(s - pad, pad))
        painter.drawLine(QPointF(s - pad, pad), QPointF(s - pad, pad + corner_len))
        # Bottom-left
        painter.drawLine(QPointF(pad, s - pad - corner_len), QPointF(pad, s - pad))
        painter.drawLine(QPointF(pad, s - pad), QPointF(pad + corner_len, s - pad))
        # Bottom-right
        painter.drawLine(QPointF(s - pad - corner_len, s - pad), QPointF(s - pad, s - pad))
        painter.drawLine(QPointF(s - pad, s - pad), QPointF(s - pad, s - pad - corner_len))

    elif name == "actual_size":
        # 1:1 icon
        rect = QRectF(pad, pad + 1, s - pad * 2, s - pad * 2 - 2)
        painter.drawRect(rect)
        # Inner '1'
        painter.drawLine(QPointF(s / 2, pad + 3), QPointF(s / 2, s - pad - 2))

    elif name == "info":
        painter.drawEllipse(QRectF(pad, pad, s - pad * 2, s - pad * 2))
        painter.drawPoint(QPointF(s / 2, pad + 3.5))
        painter.drawLine(QPointF(s / 2, pad + 6), QPointF(s / 2, s - pad - 3))

    elif name == "settings":
        # Sliders / mechanical adjust
        painter.drawLine(QPointF(pad, s * 0.3), QPointF(s - pad, s * 0.3))
        painter.drawLine(QPointF(pad, s * 0.7), QPointF(s - pad, s * 0.7))
        painter.setBrush(QBrush(color))
        painter.drawRect(QRectF(s * 0.35, s * 0.22, 3, s * 0.16))
        painter.drawRect(QRectF(s * 0.65, s * 0.62, 3, s * 0.16))

    elif name == "export":
        # Box with upward arrow
        painter.drawLine(QPointF(pad, s * 0.45), QPointF(pad, s - pad))
        painter.drawLine(QPointF(pad, s - pad), QPointF(s - pad, s - pad))
        painter.drawLine(QPointF(s - pad, s - pad), QPointF(s - pad, s * 0.45))
        # Arrow up
        painter.drawLine(QPointF(s / 2, s * 0.7), QPointF(s / 2, pad))
        painter.drawLine(QPointF(s * 0.35, pad + s * 0.15), QPointF(s / 2, pad))
        painter.drawLine(QPointF(s * 0.65, pad + s * 0.15), QPointF(s / 2, pad))

    elif name == "restore":
        # Circular recovery arrow
        rect = QRectF(pad, pad, s - pad * 2, s - pad * 2)
        painter.drawArc(rect, 45 * 16, 270 * 16)
        painter.drawLine(QPointF(s / 2, pad), QPointF(s * 0.65, pad * 1.5))
        painter.drawLine(QPointF(s * 0.65, pad * 1.5), QPointF(s * 0.65, pad * 0.5))

    elif name in ("maybe", "question"):
        # Distinct question mark
        path = QPainterPath()
        path.moveTo(pad, pad + s * 0.15)
        path.arcTo(QRectF(pad, pad, s - pad * 2, (s - pad * 2) * 0.55), 180, -180)
        path.lineTo(s / 2, s * 0.6)
        painter.drawPath(path)
        painter.drawEllipse(QPointF(s / 2, s - pad * 0.9), 1.2, 1.2)

    elif name == "flag":
        painter.drawLine(QPointF(pad, pad), QPointF(pad, s - pad))
        path = QPainterPath()
        path.moveTo(pad, pad)
        path.lineTo(s - pad, pad + s * 0.2)
        path.lineTo(pad, pad + s * 0.4)
        painter.drawPath(path)

    elif name in ("theme", "palette"):
        rect = QRectF(pad, pad, s - pad * 2, s - pad * 2)
        painter.drawEllipse(rect)
        # Thumb hole
        painter.drawEllipse(QPointF(s * 0.65, s * 0.65), s * 0.1, s * 0.1)
        # Color spots
        painter.setBrush(QBrush(color))
        painter.drawEllipse(QPointF(s * 0.35, s * 0.35), 1.5, 1.5)
        painter.drawEllipse(QPointF(s * 0.55, s * 0.28), 1.5, 1.5)
        painter.drawEllipse(QPointF(s * 0.72, s * 0.40), 1.5, 1.5)

    else:
        # Default dot
        painter.drawEllipse(QPointF(s / 2, s / 2), 2, 2)

    painter.end()
    return QIcon(pixmap)
