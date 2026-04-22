import time
import psycopg2
import os

DB_URL = os.environ.get('DATABASE_URL')

while True:
    try:
        conn = psycopg2.connect(DB_URL)
        conn.close()
        print("Database is ready!")
        break
    except Exception as e:
        print("Waiting for database...", e)
        time.sleep(2)
