"""Minimalni nahrada PyQt6.QtSql nad sqlite3 - jen pro testovani mimo Qt."""
import sqlite3


class QSqlError:
    def __init__(self, msg=""):
        self._msg = msg

    def text(self):
        return self._msg


class QSqlDatabase:
    _instances = {}

    def __init__(self, path=None):
        self._path = path
        self.conn = sqlite3.connect(path) if path else None

    @staticmethod
    def addDatabase(driver, name="qt_sql_default_connection"):
        db = QSqlDatabase()
        QSqlDatabase._instances[name] = db
        return db

    def setDatabaseName(self, path):
        self._path = path

    def databaseName(self):
        return self._path

    def open(self):
        self.conn = sqlite3.connect(self._path)
        return True

    def isOpen(self):
        return self.conn is not None

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def transaction(self):
        return True

    def commit(self):
        self.conn.commit()
        return True

    def lastError(self):
        return QSqlError()


class QSqlQuery:
    def __init__(self, db=None):
        self.db = db
        self.cur = db.conn.cursor() if db is not None and db.conn else None
        self._sql = None
        self._binds = []
        self._rows = []
        self._i = -1
        self._err = ""

    def prepare(self, sql):
        self._sql = sql
        self._binds = []
        return True

    def addBindValue(self, v):
        self._binds.append(v)

    def exec(self, sql=None):
        if sql is not None:
            self._sql = sql
            self._binds = []
        self._rows, self._i, self._err = [], -1, ""
        try:
            self.cur.execute(self._sql, tuple(self._binds))
            if self.cur.description:
                self._rows = self.cur.fetchall()
            else:
                self.db.conn.commit()
            self._binds = []
            return True
        except Exception as e:  # noqa: BLE001
            self._err = str(e)
            self._binds = []
            return False

    exec_ = exec

    def next(self):
        if self._i + 1 < len(self._rows):
            self._i += 1
            return True
        return False

    def value(self, i):
        return self._rows[self._i][i]

    def record(self):
        """Nazvy sloupcu posledniho dotazu - protejsek QSqlRecord."""
        popis = self.cur.description if self.cur is not None else None
        return QSqlRecord([s[0] for s in popis] if popis else [])

    def lastError(self):
        return QSqlError(self._err)


class QSqlRecord:
    """Minimalni nahrada QSqlRecord - jen to, co pouziva export_csv."""

    def __init__(self, nazvy):
        self._nazvy = list(nazvy)

    def count(self):
        return len(self._nazvy)

    def fieldName(self, i):
        return self._nazvy[i]


class QSqlTableModel:  # pragma: no cover - jen pro import
    def __init__(self, *a, **kw):
        pass


class QSqlQueryModel:  # pragma: no cover
    def __init__(self, *a, **kw):
        pass
