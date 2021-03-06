from sqlite3 import Connection as SQLite3Connection

from sqlalchemy import (Column, ForeignKey, Integer, MetaData, String, Table, create_engine, event)
from sqlalchemy.engine import Engine


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

        rides = Table('rides', metadata,
                      Column('rideId', Integer, autoincrement=True, primary_key=True),
                      Column('created_by', String, ForeignKey('users.username', ondelete='CASCADE'), nullable=False),
                      Column('timestamp', String, nullable=False),
                      Column('source', Integer, nullable=False),
                      Column('destination', Integer, nullable=False)
                      )

        users = Table('users', metadata,
                      Column('username', String, primary_key=True),
                      Column('password', String, nullable=False))

        riders = Table('riders', metadata,
                       Column('rideId', None, ForeignKey('rides.rideId', ondelete='CASCADE'), primary_key=True),
                       Column('user', String, ForeignKey('users.username', ondelete='CASCADE'), primary_key=True)
                       )

        apicount = Table('apicount', metadata,
                         Column('service_name', String, primary_key=True),
                         Column('count', Integer, default=0))

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


db = DataBase('data.db')
execute = db.execute
fetchall = db.fetchall
fetchone = db.fetchone

if __name__ == "__main__":
    db.create_db_tables()
    execute('''INSERT INTO APICOUNT VALUES ('rides',0)''')
    execute('''INSERT INTO APICOUNT VALUES ('users',0)''')
