import sqlite3
from cloudra.session_class import Session
import time

class SQLTable:
    def __init__(self, db_path, table_name, **kwargs):
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        self.table_name = table_name
        if self.cursor.execute('''
                               SELECT name FROM sqlite_master WHERE type='table' AND name=?                              
                               ''',(table_name)).fetchone() is None:
            self.cursor.execute(
                f'''
                CREATE TABLE {table_name} ({kwargs})
                ''')


    def insert(self, **kwargs_value):
        cursor = self.cursor
        cursor.execute(f'''
        INSERT INTO ? VALUES (
        {kwargs_value}
        )
        ''', self.table_name)
        self.conn.commit()

    def insert_by_dict(self, data_dict: dict):
        cursor = self.cursor
        columns = []
        values = []
        for column in data_dict.keys():
            columns.append(column)
            values.append(data_dict[column])
        cursor.execute(f'''
        INSERT INTO {self.table_name} ({','.join(columns)}) VALUES (
        {','.join(values)}
        )

        ''')
        self.conn.commit()

    def delete(self, condition: str):
        cursor = self.cursor
        cursor.execute(f'''
        DELETE FROM {self.table_name} WHERE {condition}
        ''')
        self.conn.commit()




    def upload(self):
        pass

    def select(self, condition: str):
        cursor = self.cursor
        cursor.execute(f'''
        SELECT * FROM {self.table_name} WHERE {condition}
        ''')
        result = cursor.fetchall()
        return result
