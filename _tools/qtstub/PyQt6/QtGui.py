class _Any:
    def __init__(self, *a, **kw):
        pass

    def __getattr__(self, name):
        return _Any()


def __getattr__(name):
    return _Any
