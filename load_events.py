import pandas as pd
import sqlalchemy
from sqlalchemy import create_engine, text
import os
import time

def create_database(engine_url):
    base_url = engine_url.rsplit('/', 1)[0]
    engine = create_engine(base_url)
    
    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE DATABASE IF NOT EXISTS workshop_db"))
            conn.commit()
    finally:
        engine.dispose()

def create_table(engine):
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS events (
        id VARCHAR(255) PRIMARY KEY,
        cohort_id VARCHAR(255),
        player_id VARCHAR(255),
        player_type VARCHAR(50),
        session_id VARCHAR(255),
        event_type VARCHAR(50),
        timestamp VARCHAR(50),
        stage_id VARCHAR(255),
        stage_score INT
    )
    """
    with engine.connect() as conn:
        conn.execute(text(create_table_sql))
        conn.commit()

def insert_row(engine, row):
    """Insert a single row into the database"""
    # Convert the row to a DataFrame
    df_row = pd.DataFrame([row])
    
    # Convert empty strings to None for stage_score
    df_row['stage_score'] = pd.to_numeric(df_row['stage_score'], errors='coerce')
    
    # Insert the row
    df_row.to_sql('events', engine, if_exists='append', index=False)

def main():
    # Get Aurora connection details from environment variables
    db_username = os.environ.get('DB_USERNAME')
    db_password = os.environ.get('DB_PASSWORD')
    db_host = os.environ.get('DB_HOST')
    db_name = os.environ.get('DB_NAME', 'workshop_db')
    
    # Create connection string
    connection_string = f"mysql+pymysql://{db_username}:{db_password}@{db_host}/{db_name}"
    
    try:
        # First create the database
        print("Creating database if it doesn't exist...")
        create_database(connection_string)
        
        # Now connect to the database and create engine
        print("Connecting to database...")
        engine = create_engine(connection_string)
        
        # Create table
        print("Creating table if it doesn't exist...")
        create_table(engine)
        
        # Read CSV file
        print("Reading CSV file...")
        df = pd.read_csv('events.csv')
        
        # Insert rows one by one with 1 second delay
        print("Starting to insert data row by row...")
        for index, row in df.iterrows():
            try:
                insert_row(engine, row)
                print(f"Inserted row {index + 1} of {len(df)}")
                time.sleep(1)  # Wait for 1 second before next insertion
            except Exception as e:
                print(f"Error inserting row {index + 1}: {str(e)}")
                continue
        
        print("Successfully completed data insertion")
        
    except Exception as e:
        print(f"Error: {str(e)}")
    finally:
        if 'engine' in locals():
            engine.dispose()

if __name__ == "__main__":
    main()
