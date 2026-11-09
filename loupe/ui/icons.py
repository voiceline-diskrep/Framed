"""Vector icon renderer for consistent, sharp, and purpose-driven iconography."""

from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QPainterPath, QBrush
from PySide6.QtCore import Qt, QRectF, QPointF
import math

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

    if name == "brand_frame":
        # Signature FRAMED orange logo: corner brackets forming a camera frame
        cl = s * 0.35
        # Top-left bracket
        painter.drawLine(QPointF(pad, pad + cl), QPointF(pad, pad))
        painter.drawLine(QPointF(pad, pad), QPointF(pad + cl, pad))
        # Bottom-right bracket
        painter.drawLine(QPointF(s - pad - cl, s - pad), QPointF(s - pad, s - pad))
        painter.drawLine(QPointF(s - pad, s - pad), QPointF(s - pad, s - pad - cl))

    elif name in ("photo", "image"):
        rect = QRectF(pad, pad, s - pad * 2, s - pad * 2)
        painter.drawRect(rect)
        painter.drawEllipse(QPointF(pad + s * 0.22, pad + s * 0.22), 1.5, 1.5)
        path = QPainterPath()
        path.moveTo(pad, s - pad)
        path.lineTo(pad + s * 0.25, s * 0.52)
        path.lineTo(pad + s * 0.45, s * 0.65)
        path.lineTo(pad + s * 0.65, s * 0.45)
        path.lineTo(s - pad, s - pad)
        painter.drawPath(path)

    elif name in ("video", "film"):
        rect = QRectF(pad, pad + 1, s - pad * 2, s - pad * 2 - 2)
        painter.drawRect(rect)
        path = QPainterPath()
        path.moveTo(s * 0.42, s * 0.36)
        path.lineTo(s * 0.64, s * 0.50)
        path.lineTo(s * 0.42, s * 0.64)
        path.closeSubpath()
        painter.drawPath(path)

    elif name in ("check_circle", "completed"):
        painter.drawEllipse(QRectF(pad, pad, s - pad * 2, s - pad * 2))
        path = QPainterPath()
        path.moveTo(s * 0.32, s * 0.52)
        path.lineTo(s * 0.46, s * 0.66)
        path.lineTo(s * 0.70, s * 0.38)
        painter.drawPath(path)

    elif name == "calendar":
        rect = QRectF(pad, pad + 2, s - pad * 2, s - pad * 2 - 2)
        painter.drawRect(rect)
        painter.drawLine(QPointF(pad, pad + 6), QPointF(s - pad, pad + 6))
        painter.drawLine(QPointF(pad + 4, pad), QPointF(pad + 4, pad + 2))
        painter.drawLine(QPointF(s - pad - 4, pad), QPointF(s - pad - 4, pad + 2))

    elif name in ("trash", "delete"):
        # Razor-sharp, clean modern trash can
        t_pen = QPen(color, 1.25, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(t_pen)
        # Lid
        painter.drawLine(QPointF(pad, pad + 2.5), QPointF(s - pad, pad + 2.5))
        # Top handle
        painter.drawLine(QPointF(s * 0.36, pad + 1.0), QPointF(s * 0.64, pad + 1.0))
        painter.drawLine(QPointF(s * 0.36, pad + 1.0), QPointF(s * 0.36, pad + 2.5))
        painter.drawLine(QPointF(s * 0.64, pad + 1.0), QPointF(s * 0.64, pad + 2.5))
        # Can body
        body = QPainterPath()
        body.moveTo(pad + 1.5, pad + 3.5)
        body.lineTo(pad + 2.5, s - pad)
        body.lineTo(s - pad - 2.5, s - pad)
        body.lineTo(s - pad - 1.5, pad + 3.5)
        painter.drawPath(body)
        # 2 vertical ribs
        painter.drawLine(QPointF(s * 0.42, pad + 5.0), QPointF(s * 0.42, s - pad - 2.0))
        painter.drawLine(QPointF(s * 0.58, pad + 5.0), QPointF(s * 0.58, s - pad - 2.0))

    elif name == "home":
        path = QPainterPath()
        path.moveTo(pad, s * 0.52)
        path.lineTo(s / 2, pad)
        path.lineTo(s - pad, s * 0.52)
        painter.drawPath(path)
        rect = QRectF(pad + 2, s * 0.52, s - (pad + 2) * 2, s * 0.48 - pad)
        painter.drawRect(rect)

    elif name == "aperture":
        r = (s - pad * 2) / 2.0
        cx, cy = s / 2.0, s / 2.0
        painter.drawEllipse(QPointF(cx, cy), r, r)
        for i in range(6):
            angle = i * (2 * math.pi / 6)
            x1 = cx + r * math.cos(angle)
            y1 = cy + r * math.sin(angle)
            angle2 = (i + 1.8) * (2 * math.pi / 6)
            x2 = cx + (r * 0.45) * math.cos(angle2)
            y2 = cy + (r * 0.45) * math.sin(angle2)
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    elif name == "grid":
        hs = (s - pad * 2 - 2) / 2
        painter.drawRect(QRectF(pad, pad, hs, hs))
        painter.drawRect(QRectF(pad + hs + 2, pad, hs, hs))
        painter.drawRect(QRectF(pad, pad + hs + 2, hs, hs))
        painter.drawRect(QRectF(pad + hs + 2, pad + hs + 2, hs, hs))

    elif name == "list":
        painter.drawLine(QPointF(pad, pad + 2), QPointF(s - pad, pad + 2))
        painter.drawLine(QPointF(pad, s / 2), QPointF(s - pad, s / 2))
        painter.drawLine(QPointF(pad, s - pad - 2), QPointF(s - pad, s - pad - 2))

    elif name == "compact":
        for i in range(4):
            y = pad + i * ((s - pad * 2) / 3)
            painter.drawLine(QPointF(pad, y), QPointF(s - pad, y))

    elif name == "plus":
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

    elif name in ("cloud", "drive"):
        # Cloud / Drive vector icon
        path = QPainterPath()
        y_base = s - pad * 1.4
        path.moveTo(pad * 1.8, y_base)
        path.lineTo(s - pad * 1.6, y_base)
        path.arcTo(QRectF(s * 0.58, s * 0.38, s * 0.30, s * 0.36), -90, 180)
        path.arcTo(QRectF(s * 0.26, pad * 1.2, s * 0.44, s * 0.44), 10, 165)
        path.arcTo(QRectF(pad, s * 0.42, s * 0.32, s * 0.32), 100, 170)
        path.closeSubpath()
        painter.drawPath(path)

    elif name == "gallery":
        # Stacked photo frames with mountain landscape
        r1 = QRectF(pad + 2, pad, s - pad * 2 - 2, s - pad * 2 - 2)
        painter.drawRoundedRect(r1, 2.0, 2.0)
        painter.drawEllipse(QPointF(r1.left() + r1.width() * 0.28, r1.top() + r1.height() * 0.28), 1.3, 1.3)
        path = QPainterPath()
        path.moveTo(r1.left() + 1, r1.bottom() - 1)
        path.lineTo(r1.left() + r1.width() * 0.35, r1.top() + r1.height() * 0.55)
        path.lineTo(r1.left() + r1.width() * 0.58, r1.top() + r1.height() * 0.72)
        path.lineTo(r1.left() + r1.width() * 0.78, r1.top() + r1.height() * 0.48)
        path.lineTo(r1.right() - 1, r1.bottom() - 1)
        painter.drawPath(path)
        # Back frame corner
        painter.drawLine(QPointF(pad, pad + 3), QPointF(pad, s - pad))
        painter.drawLine(QPointF(pad, s - pad), QPointF(s - pad - 3, s - pad))

    elif name in ("heart", "heart_filled"):
        path = QPainterPath()
        cx = s / 2.0
        top_y = pad + s * 0.14
        bottom_y = s - pad * 1.05
        path.moveTo(cx, bottom_y)
        path.cubicTo(QPointF(pad * 0.4, s * 0.58), QPointF(pad * 0.5, pad * 0.8), QPointF(cx, top_y + s * 0.12))
        path.cubicTo(QPointF(s - pad * 0.5, pad * 0.8), QPointF(s - pad * 0.4, s * 0.58), QPointF(cx, bottom_y))
        if name == "heart_filled":
            painter.setBrush(QBrush(color))
        painter.drawPath(path)

    elif name in ("star", "star_filled"):
        path = QPainterPath()
        cx, cy = s / 2.0, s / 2.0
        r_out = (s - pad * 2) * 0.52
        r_in = r_out * 0.42
        for i in range(10):
            angle = -math.pi / 2 + i * (math.pi / 5)
            r = r_out if i % 2 == 0 else r_in
            pt = QPointF(cx + r * math.cos(angle), cy + r * math.sin(angle))
            if i == 0:
                path.moveTo(pt)
            else:
                path.lineTo(pt)
        path.closeSubpath()
        if name == "star_filled":
            painter.setBrush(QBrush(color))
        painter.drawPath(path)

    elif name in ("map_pin", "location"):
        cx = s / 2.0
        r = (s - pad * 2) * 0.34
        cy = pad + r + 1
        path = QPainterPath()
        path.moveTo(cx, s - pad)
        path.cubicTo(QPointF(cx - r * 1.15, cy + r * 0.5), QPointF(cx - r, cy - r * 0.9), QPointF(cx, cy - r))
        path.cubicTo(QPointF(cx + r, cy - r * 0.9), QPointF(cx + r * 1.15, cy + r * 0.5), QPointF(cx, s - pad))
        painter.drawPath(path)
        painter.drawEllipse(QPointF(cx, cy), r * 0.38, r * 0.38)

    elif name in ("warning", "alert"):
        path = QPainterPath()
        path.moveTo(s / 2.0, pad)
        path.lineTo(s - pad, s - pad)
        path.lineTo(pad, s - pad)
        path.closeSubpath()
        painter.drawPath(path)
        painter.drawLine(QPointF(s / 2.0, pad + s * 0.28), QPointF(s / 2.0, s - pad - s * 0.24))
        painter.drawEllipse(QPointF(s / 2.0, s - pad - s * 0.11), 0.9, 0.9)

    elif name in ("database", "storage"):
        rx = (s - pad * 2) / 2.0
        ry = rx * 0.38
        cx = s / 2.0
        top_cy = pad + ry
        bot_cy = s - pad - ry
        painter.drawEllipse(QPointF(cx, top_cy), rx, ry)
        painter.drawLine(QPointF(pad, top_cy), QPointF(pad, bot_cy))
        painter.drawLine(QPointF(s - pad, top_cy), QPointF(s - pad, bot_cy))
        painter.drawArc(QRectF(pad, (top_cy + bot_cy) / 2 - ry, rx * 2, ry * 2), 180 * 16, 180 * 16)
        painter.drawArc(QRectF(pad, bot_cy - ry, rx * 2, ry * 2), 180 * 16, 180 * 16)

    elif name in ("sparkles", "smart"):
        cx, cy = s / 2.0, s / 2.0
        r = (s - pad * 2) * 0.45
        path = QPainterPath()
        path.moveTo(cx, cy - r)
        path.quadTo(QPointF(cx, cy), QPointF(cx + r, cy))
        path.quadTo(QPointF(cx, cy), QPointF(cx, cy + r))
        path.quadTo(QPointF(cx, cy), QPointF(cx - r, cy))
        path.quadTo(QPointF(cx, cy), QPointF(cx, cy - r))
        painter.drawPath(path)

    elif name == "compare":
        rect = QRectF(pad, pad + 1, s - pad * 2, s - pad * 2 - 2)
        painter.drawRoundedRect(rect, 2.0, 2.0)
        painter.drawLine(QPointF(s / 2.0, pad), QPointF(s / 2.0, s - pad))

    elif name == "play":
        path = QPainterPath()
        path.moveTo(s * 0.32, pad * 1.2)
        path.lineTo(s - pad * 1.1, s / 2.0)
        path.lineTo(s * 0.32, s - pad * 1.2)
        path.closeSubpath()
        painter.setBrush(QBrush(color))
        painter.drawPath(path)

    elif name == "pause":
        painter.drawLine(QPointF(s * 0.36, pad * 1.2), QPointF(s * 0.36, s - pad * 1.2))
        painter.drawLine(QPointF(s * 0.64, pad * 1.2), QPointF(s * 0.64, s - pad * 1.2))

    elif name == "duplicate":
        w = (s - pad * 2) * 0.68
        painter.drawRoundedRect(QRectF(pad, pad, w, w), 1.5, 1.5)
        painter.drawRoundedRect(QRectF(s - pad - w, s - pad - w, w, w), 1.5, 1.5)

    elif name == "bulb":
        cx = s / 2.0
        r = (s - pad * 2) * 0.34
        cy = pad + r
        painter.drawEllipse(QPointF(cx, cy), r, r)
        painter.drawLine(QPointF(cx - r * 0.5, s - pad - 2.5), QPointF(cx + r * 0.5, s - pad - 2.5))
        painter.drawLine(QPointF(cx - r * 0.35, s - pad), QPointF(cx + r * 0.35, s - pad))

    else:
        # Default dot
        painter.drawEllipse(QPointF(s / 2, s / 2), 2, 2)

    painter.end()
    return QIcon(pixmap)
