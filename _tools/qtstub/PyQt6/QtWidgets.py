"""Minimalni nahrada PyQt6.QtWidgets."""


class _Any:
    def __init__(self, *a, **kw):
        pass

    def __getattr__(self, name):
        return _Any()

    def __call__(self, *a, **kw):
        return _Any()


class QMessageBox(_Any):
    class StandardButton:
        Yes = 1
        No = 0

    @staticmethod
    def information(*a, **kw):
        pass

    @staticmethod
    def critical(*a, **kw):
        pass

    @staticmethod
    def question(*a, **kw):
        return 1


class QProgressDialog(_Any):
    pass


def __getattr__(name):
    return _Any
