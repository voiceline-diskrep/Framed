"""GPU VRAM texture cache using PySide6 QtOpenGL with headless software fallback."""

import os
from dataclasses import dataclass
from typing import Dict, List, Optional

from PySide6.QtGui import QImage, QOffscreenSurface, QOpenGLContext, QSurface
from PySide6.QtOpenGL import QOpenGLTexture


@dataclass
class VRAMTextureEntry:
    """Represents a single photo frame allocated in GPU VRAM (or fallback QImage in headless mode)."""
    index: int
    texture: Optional[object]
    width: int
    height: int
    bytes_used: int
    fallback_qimage: Optional[QImage] = None


def _is_headless_platform() -> bool:
    platform_name = os.environ.get("QT_QPA_PLATFORM", "").strip().lower()
    return platform_name in ("offscreen", "minimal", "vnc")


class VRAMTextureCache:
    """Manages QOpenGLTexture entries on a QOpenGLContext + QSurface with accurate byte accounting."""

    def __init__(
        self,
        gl_context: Optional[QOpenGLContext] = None,
        gl_surface: Optional[QSurface] = None,
    ):
        self._entries: Dict[int, VRAMTextureEntry] = {}
        self._gl_context: Optional[QOpenGLContext] = None
        self._gl_surface: Optional[QSurface] = None
        self._owned_surface: Optional[QOffscreenSurface] = None
        self.is_gl_supported: bool = False
        self.set_gl_context(gl_context, gl_surface)

    def set_gl_context(
        self,
        gl_context: Optional[QOpenGLContext],
        gl_surface: Optional[QSurface] = None,
    ) -> None:
        """Attach or update the OpenGL context and surface used for texture uploads."""
        self._gl_context = gl_context
        self._gl_surface = gl_surface
        self.is_gl_supported = self._check_gl_usable(gl_context)

    def _check_gl_usable(self, ctx: Optional[QOpenGLContext]) -> bool:
        if _is_headless_platform():
            return False
        if ctx is None:
            return False
        try:
            return bool(ctx.isValid())
        except Exception:
            return False

    def _resolve_surface(
        self,
        ctx: QOpenGLContext,
        gl_surface: Optional[QSurface] = None,
    ) -> Optional[QSurface]:
        if gl_surface is not None:
            return gl_surface
        if self._gl_surface is not None:
            return self._gl_surface
        if self._owned_surface is None:
            try:
                surf = QOffscreenSurface()
                surf.setFormat(ctx.format())
                surf.create()
                if surf.isValid():
                    self._owned_surface = surf
            except Exception:
                self._owned_surface = None
        return self._owned_surface

    def upload(
        self,
        index: int,
        qimage: QImage,
        gl_context: Optional[QOpenGLContext] = None,
        gl_surface: Optional[QSurface] = None,
    ) -> bool:
        """Upload a QImage into GPU VRAM as an RGBA8 QOpenGLTexture (or fallback QImage when GL is unavailable)."""
        if qimage is None or qimage.isNull():
            return False

        w = qimage.width()
        h = qimage.height()
        if w <= 0 or h <= 0:
            return False

        # Release any existing entry for this index before replacing it
        if index in self._entries:
            self.release(index)

        bytes_used = w * h * 4  # RGBA8888 GPU texture footprint
        ctx = gl_context if gl_context is not None else self._gl_context

        if self._check_gl_usable(ctx):
            assert ctx is not None
            target_surface = self._resolve_surface(ctx, gl_surface)
            if target_surface is not None:
                prev_ctx = QOpenGLContext.currentContext()
                prev_surface = prev_ctx.surface() if prev_ctx is not None else None
                made_current = False
                try:
                    made_current = bool(ctx.makeCurrent(target_surface))
                    if made_current:
                        rgba_img = (
                            qimage
                            if qimage.format() == QImage.Format.Format_RGBA8888
                            else qimage.convertToFormat(QImage.Format.Format_RGBA8888)
                        )
                        tex = QOpenGLTexture(rgba_img)
                        tex.setMinMagFilters(QOpenGLTexture.Filter.Linear, QOpenGLTexture.Filter.Linear)
                        tex.setWrapMode(QOpenGLTexture.WrapMode.ClampToEdge)
                        if tex.isCreated():
                            self.is_gl_supported = True
                            self._entries[index] = VRAMTextureEntry(
                                index=index,
                                texture=tex,
                                width=w,
                                height=h,
                                bytes_used=bytes_used,
                                fallback_qimage=None,
                            )
                            return True
                        try:
                            tex.destroy()
                        except Exception:
                            pass
                except Exception:
                    pass
                finally:
                    if made_current:
                        try:
                            if prev_ctx is not None and prev_surface is not None and prev_ctx is not ctx:
                                prev_ctx.makeCurrent(prev_surface)
                            elif prev_ctx is None:
                                ctx.doneCurrent()
                        except Exception:
                            pass

        # Headless / no valid GL context fallback: keep QImage + accurate byte accounting
        self.is_gl_supported = self._check_gl_usable(self._gl_context)
        self._entries[index] = VRAMTextureEntry(
            index=index,
            texture=None,
            width=w,
            height=h,
            bytes_used=bytes_used,
            fallback_qimage=qimage,
        )
        return True

    def has(self, index: int) -> bool:
        return index in self._entries

    def get_entry(self, index: int) -> Optional[VRAMTextureEntry]:
        return self._entries.get(index)

    def keys(self) -> List[int]:
        return list(self._entries.keys())

    def release(self, index: int) -> int:
        """Destroy the texture / release the cached entry for `index` and return freed bytes."""
        entry = self._entries.pop(index, None)
        if entry is None:
            return 0

        freed = entry.bytes_used
        if entry.texture is not None:
            ctx = self._gl_context
            if ctx is not None and self._check_gl_usable(ctx):
                target_surface = self._resolve_surface(ctx)
                prev_ctx = QOpenGLContext.currentContext()
                prev_surface = prev_ctx.surface() if prev_ctx is not None else None
                made_current = False
                try:
                    if target_surface is not None:
                        made_current = bool(ctx.makeCurrent(target_surface))
                    if made_current or prev_ctx is ctx:
                        entry.texture.destroy()
                except Exception:
                    pass
                finally:
                    if made_current:
                        try:
                            if prev_ctx is not None and prev_surface is not None and prev_ctx is not ctx:
                                prev_ctx.makeCurrent(prev_surface)
                            elif prev_ctx is None:
                                ctx.doneCurrent()
                        except Exception:
                            pass
            else:
                try:
                    entry.texture.destroy()
                except Exception:
                    pass

        entry.texture = None
        entry.fallback_qimage = None
        return freed

    def clear(self) -> None:
        """Release all cached VRAM texture entries."""
        for idx in list(self._entries.keys()):
            self.release(idx)
        self._entries.clear()

    @property
    def used_bytes(self) -> int:
        return sum(entry.bytes_used for entry in self._entries.values())

    @property
    def used_mb(self) -> float:
        return self.used_bytes / (1024.0 * 1024.0)

    @property
    def count(self) -> int:
        return len(self._entries)
