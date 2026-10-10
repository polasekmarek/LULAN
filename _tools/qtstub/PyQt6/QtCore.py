"""Minimalni nahrada PyQt6.QtCore."""


class _Enum:
    def __getattr__(self, name):
        return name


class Qt:
    WindowModality = _Enum()
    Orientation = _Enum()
    ItemDataRole = _Enum()
    SortOrder = _Enum()


def pyqtSignal(*a, **kw):
    class _Sig:
        def connect(self, fn):
            pass

        def emit(self, *args):
            pass

    return _Sig()


class QThread:
    def __init__(self, *a, **kw):
        pass

    def start(self):
        self.run()


class QTimer:  # pragma: no cover
    pass


class QSortFilterProxyModel:  # pragma: no cover
    pass


class QSize:  # pragma: no cover - jen pro import
    def __init__(self, sirka=0, vyska=0):
        self._s, self._v = sirka, vyska

    def width(self):
        return self._s

    def height(self):
        return self._v


class QPoint:  # pragma: no cover - jen pro import
    def __init__(self, x=0, y=0):
        self._x, self._y = x, y

    def x(self):
        return self._x

    def y(self):
        return self._y


class QEvent:  # pragma: no cover - jen pro import
    class Type:
        Resize = 14
        Show = 17
        LayoutRequest = 76
