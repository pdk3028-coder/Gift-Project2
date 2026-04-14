import sqlite3
import pandas as pd
from datetime import datetime
import os

basedir = os.path.abspath(os.path.dirname(__file__))
DB_NAME = os.path.join(basedir, 'employees.db')

def get_db_connection():
    conn = sqlite3.connect(DB_NAME, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    # Create employees table
    c.execute('''
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            emp_id TEXT NOT NULL UNIQUE,
            gender TEXT,
            top_size TEXT,
            top_color TEXT,
            bottom_size TEXT,
            bottom_color TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_updated TIMESTAMP
        )
    ''')
    
    # Create system_settings table
    c.execute('''
        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    ''')
    
    conn.commit()
    conn.close()
    print(f"Database {DB_NAME} initialized successfully.")

def get_setting(key, default='true'):
    conn = get_db_connection()
    row = conn.execute('SELECT value FROM system_settings WHERE key = ?', (key,)).fetchone()
    conn.close()
    return row['value'] if row else default

def set_setting(key, value):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)', (key, value))
    conn.commit()
    conn.close()

def update_privacy_consent(emp_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        UPDATE employees
        SET privacy_agreed = 1,
            privacy_agreed_at = ?
        WHERE emp_id = ?
    ''', (datetime.now(), emp_id))
    conn.commit()
    conn.close()

def get_employee_by_auth(emp_id):
    """
    Retrieves an employee by emp_id only.
    """
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM employees WHERE emp_id = ?', (emp_id,)).fetchone()
    conn.close()
    
    return user

def update_employee_info(emp_id, data):
    """Updates employee information. Handles partial updates."""
    conn = get_db_connection()
    c = conn.cursor()
    
    valid_keys = [
        'gender', 'top_size', 'top_color', 'bottom_size', 'bottom_color'
    ]
    
    updates = []
    values = []
    
    for key in valid_keys:
        if key in data:
            updates.append(f"{key} = ?")
            values.append(data[key])
            
    updates.append("last_updated = ?")
    values.append(datetime.now())
    values.append(emp_id)
    
    if updates:
        query = f"UPDATE employees SET {','.join(updates)} WHERE emp_id = ?"
        c.execute(query, tuple(values))
        conn.commit()
    conn.close()

def get_all_employees():
    """Returns all employees as a pandas DataFrame (for admin export)."""
    conn = get_db_connection()
    query = 'SELECT * FROM employees'
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def upsert_employees_from_excel(filepath):
    """
    Reads an Excel file and updates/inserts employees.
    Uses specific column indices based on user provided data layout.
    """
    df = pd.read_excel(filepath, dtype=str)
    clean_df = pd.DataFrame()
    
    def get_col_data(col_idx):
        if col_idx < len(df.columns):
            return df.iloc[:, col_idx]
        return None

    def clean_str(series):
        if series is None:
            return pd.Series([''] * len(df))
            
        def convert_val(x):
            s = str(x).strip()
            if s.lower() in ['nan', 'none', '', 'nat']:
                return ''
            if s.endswith('.0'):
                return s[:-2]
            return s
                
        return series.apply(convert_val)

    clean_df['emp_id'] = clean_str(get_col_data(11))
    clean_df['name'] = clean_str(get_col_data(12))
    
    clean_df = clean_df.replace({'nan': '', 'None': ''})

    conn = get_db_connection()
    c = conn.cursor()
    
    count = 0
    for _, row in clean_df.iterrows():
        if not row['emp_id'] or not row['name']:
            continue
            
        c.execute('SELECT id FROM employees WHERE emp_id = ?', (row['emp_id'],))
        exists = c.fetchone()
        
        if exists:
            c.execute('''
                UPDATE employees
                SET name = ?, last_updated = ?
                WHERE emp_id = ?
            ''', (row['name'], datetime.now(), row['emp_id']))
        else:
            c.execute('''
                INSERT INTO employees (name, emp_id, last_updated)
                VALUES (?, ?, ?)
            ''', (row['name'], row['emp_id'], datetime.now()))
        count += 1
        
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.execute('INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)', ('last_upload_time', now_str))

    conn.commit()
    conn.close()
    return count

def reset_all_data():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM employees")
    c.execute("DELETE FROM system_settings")
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
