from sqlalchemy import (Column, DateTime, ForeignKey, Integer, MetaData, String, Table, create_engine, event)
from sqlalchemy.engine import Engine
from sqlite3 import Connection as SQLite3Connection


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, SQLite3Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()


class DataBase:

    def __init__(self, dbname=''):
        self.db_engine = create_engine(f'sqlite:///{dbname}')

    def create_db_tables(self):
        metadata = MetaData()

        users = Table('users', metadata,
                      Column('username', String, primary_key=True),
                      Column('password', String, nullable=False)
                      )

        try:
            metadata.create_all(self.db_engine)
        except Exception as e:
            print(e)
            return False

    def execute(self, query, params=()):
        with self.db_engine.connect() as conn:
            try:
                conn.execute(query, params)
            except Exception as e:
                print(e)
                return False
        return True

    def fetchall(self, query, params=()):
        with self.db_engine.connect() as connection:
            try:
                res = connection.execute(query, params).fetchall()
            except Exception as e:
                print(e)
                return False
        return list(map(list, res)) if res else False

    def fetchone(self, query, params=()):
        with self.db_engine.connect() as connection:
            try:
                res = connection.execute(query, params).fetchone()
            except Exception as e:
                print(e)
                return False
        return list(res) if res else False


db = DataBase('users.db')
execute = db.execute
fetchall = db.fetchall
fetchone = db.fetchone

if __name__ == "__main__":
    db.create_db_tables()
    pass
