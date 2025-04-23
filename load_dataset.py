import pandas as pd
import sqlalchemy
from sqlalchemy import create_engine, text
import os

def create_database(engine_url):
    # Create a connection without specifying the database
    base_url = engine_url.rsplit('/', 1)[0]
    engine = create_engine(base_url)
    
    try:
        with engine.connect() as conn:
            # Create database if it doesn't exist
            conn.execute(text("CREATE DATABASE IF NOT EXISTS workshop_db"))
            conn.commit()
    finally:
        engine.dispose()

def create_tables(engine):
    # Create game_events table
    create_game_events_sql = """
    CREATE TABLE IF NOT EXISTS game_events (
        event_id INT PRIMARY KEY,
        user_id INT,
        event_time DATETIME,
        event_type VARCHAR(50),
        event_detail TEXT,
        level_id INT,
        result VARCHAR(10),
        duration INT
    )
    """
    
    # Create game_progress table
    create_game_progress_sql = """
    CREATE TABLE IF NOT EXISTS game_progress (
        progress_id INT PRIMARY KEY,
        user_id INT,
        level INT,
        experience INT,
        game_coins INT,
        diamonds INT,
        update_time DATETIME,
        total_play_time INT
    )
    """
    
    # Create payment_transactions table
    create_payment_transactions_sql = """
    CREATE TABLE IF NOT EXISTS payment_transactions (
        transaction_id INT PRIMARY KEY,
        user_id INT,
        transaction_time DATETIME,
        amount DECIMAL(10,2),
        payment_method VARCHAR(50),
        currency VARCHAR(10),
        item_id INT,
        item_name VARCHAR(100),
        item_type VARCHAR(50)
    )
    """
    
    # Create user_login table
    create_user_login_sql = """
    CREATE TABLE IF NOT EXISTS user_login (
        login_id INT PRIMARY KEY,
        user_id INT,
        login_time DATETIME,
        logout_time DATETIME,
        session_length INT,
        ip_address VARCHAR(50),
        device_id VARCHAR(50)
    )
    """
    
    # Create user_profile table
    create_user_profile_sql = """
    CREATE TABLE IF NOT EXISTS user_profile (
        user_id INT PRIMARY KEY,
        register_time DATETIME,
        channel VARCHAR(50),
        device_type VARCHAR(50),
        os_version VARCHAR(50),
        region VARCHAR(50),
        gender VARCHAR(10),
        age INT,
        vip_level INT
    )
    """
    
    with engine.connect() as conn:
        conn.execute(text(create_game_events_sql))
        conn.execute(text(create_game_progress_sql))
        conn.execute(text(create_payment_transactions_sql))
        conn.execute(text(create_user_login_sql))
        conn.execute(text(create_user_profile_sql))
        conn.commit()

def load_table_data(engine, table_name, csv_path):
    print(f"Reading {csv_path}...")
    df = pd.read_csv(csv_path)
    
    # Convert datetime columns based on table
    if table_name == 'game_events':
        df['event_time'] = pd.to_datetime(df['event_time'])
    elif table_name == 'game_progress':
        df['update_time'] = pd.to_datetime(df['update_time'])
    elif table_name == 'payment_transactions':
        df['transaction_time'] = pd.to_datetime(df['transaction_time'])
    elif table_name == 'user_login':
        df['login_time'] = pd.to_datetime(df['login_time'])
        df['logout_time'] = pd.to_datetime(df['logout_time'])
    elif table_name == 'user_profile':
        df['register_time'] = pd.to_datetime(df['register_time'])
    
    print(f"Loading data into {table_name} table...")
    df.to_sql(table_name, engine, if_exists='append', index=False, 
              method='multi', chunksize=1000)
    print(f"Successfully loaded data into {table_name}")

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
        
        # Create tables
        print("Creating tables if they don't exist...")
        create_tables(engine)
        
        # Load data for each table
        tables_and_files = [
            ('game_events', 'dataset/game_events.csv'),
            ('game_progress', 'dataset/game_progress.csv'),
            ('payment_transactions', 'dataset/payment_transactions.csv'),
            ('user_login', 'dataset/user_login.csv'),
            ('user_profile', 'dataset/user_profile.csv')
        ]
        
        for table_name, csv_file in tables_and_files:
            load_table_data(engine, table_name, csv_file)
            
        print("All data loaded successfully")
        
    except Exception as e:
        print(f"Error: {str(e)}")
    finally:
        if 'engine' in locals():
            engine.dispose()

if __name__ == "__main__":
    main()
