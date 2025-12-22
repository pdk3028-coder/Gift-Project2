import sqlite3
import pandas as pd
from datetime import datetime
import hashlib # V10

DB_NAME = 'employees.db'

def get_db_connection():
    conn = sqlite3.connect(DB_NAME, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

# V10: Hash Helper
def hash_val(val):
    """Returns SHA-256 hash of the value."""
    return hashlib.sha256(str(val).encode()).hexdigest()

def init_db():
    """Initializes the database with the employees table and migrates if needed."""
    conn = get_db_connection()
    c = conn.cursor()
    
    # Create employees table
    c.execute('''
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            emp_id TEXT NOT NULL UNIQUE,
            ssn TEXT NOT NULL,
            address_main TEXT,
            address_main_detail TEXT,  -- Added in V2
            phone TEXT,
            emergency_contact TEXT,
            gift_address TEXT,
            gift_address_detail TEXT,  -- Added in V2
            gift_receiver TEXT,
            privacy_agreed INTEGER DEFAULT 0, -- Added in V3
            privacy_agreed_at TIMESTAMP,      -- Added in V3
            zipcode TEXT,                     -- Added in V8
            gift_zipcode TEXT,                -- Added in V8
            last_updated TIMESTAMP
        )
    ''')
    
    # Create system_settings table (V5)
    c.execute('''
        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    ''')
    
    # Migration for V2 & V3 & V8: Check if new columns exist
    cursor = c.execute("PRAGMA table_info(employees)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if 'address_main_detail' not in columns:
        print("Migrating: Adding address_main_detail column")
        c.execute("ALTER TABLE employees ADD COLUMN address_main_detail TEXT")
        
    if 'gift_address_detail' not in columns:
        print("Migrating: Adding gift_address_detail column")
        c.execute("ALTER TABLE employees ADD COLUMN gift_address_detail TEXT")

    if 'privacy_agreed' not in columns:
        print("Migrating: Adding privacy_agreed column")
        c.execute("ALTER TABLE employees ADD COLUMN privacy_agreed INTEGER DEFAULT 0")

    if 'privacy_agreed_at' not in columns:
        print("Migrating: Adding privacy_agreed_at column")
        c.execute("ALTER TABLE employees ADD COLUMN privacy_agreed_at TIMESTAMP")
        
    if 'zipcode' not in columns:
        print("Migrating: Adding zipcode column")
        c.execute("ALTER TABLE employees ADD COLUMN zipcode TEXT")
        
    if 'gift_zipcode' not in columns:
        print("Migrating: Adding gift_zipcode column")
        c.execute("ALTER TABLE employees ADD COLUMN gift_zipcode TEXT")

    # V13 Migration: selected_gift_id
    if 'selected_gift_id' not in columns:
        print("Migrating: Adding selected_gift_id column")
        c.execute("ALTER TABLE employees ADD COLUMN selected_gift_id INTEGER")
        
    # V13: Create gift_options table
    c.execute('''
        CREATE TABLE IF NOT EXISTS gift_options (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            image_path TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP
        )
    ''')

    # V10 Migration: Hash existing plain text SSNs
    # Check if 'ssn_hashed' flag setting exists, if not, migration might be needed
    # Actually, we can check a sample row. If len(ssn) < 64 (sha256 hex len), it's plaintext.
    print("Checking for SSN Migration (V10 Hashing)...")
    rows = c.execute("SELECT id, ssn FROM employees").fetchall()
    migrated_count = 0
    for row in rows:
        ssn = row['ssn']
        # SHA-256 hexdigest is 64 chars. If simpler, it's old format.
        # Support formats: 'xxxxxx-xxxxxxx' or just 'xxxxxxx'
        if len(ssn) < 64:
            if '-' in ssn:
                # Format: Front-Back. We want to store Front-Hash(Back) to preserve birthdate info?
                # Decision: Store full hash? No, user wants security.
                # Let's simple: We will store Hash(Back). We LOSE Front info (Birthdate).
                # But wait, if we lose birthdate, can we verify? Login uses EmpID+Back.
                # Verification: Hash(Input_Back). Compare with Stored.
                # If Stored is Hash(Back), we good.
                # If Stored is Front-Back, we change to Hash(Back).
                parts = ssn.split('-')
                if len(parts) > 1:
                    new_ssn = hash_val(parts[1])
                    c.execute("UPDATE employees SET ssn = ? WHERE id = ?", (new_ssn, row['id']))
                    migrated_count += 1
            else:
                # Assuming it is just back part
                new_ssn = hash_val(ssn)
                c.execute("UPDATE employees SET ssn = ? WHERE id = ?", (new_ssn, row['id']))
                migrated_count += 1
    
    if migrated_count > 0:
        print(f"Migrated {migrated_count} SSNs to SHA-256 Hashes.")

    conn.commit()
    conn.close()
    print(f"Database {DB_NAME} initialized/checked successfully.")

def get_setting(key, default='true'):
    """Retrieves a system setting."""
    conn = get_db_connection()
    row = conn.execute('SELECT value FROM system_settings WHERE key = ?', (key,)).fetchone()
    conn.close()
    return row['value'] if row else default

def set_setting(key, value):
    """Sets a system setting."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)', (key, value))
    conn.commit()
    conn.close()

def update_privacy_consent(emp_id):
    """Records that the user has agreed to the privacy policy."""
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

def get_employee_by_auth(emp_id, ssn_suffix):
    """
    Retrieves an employee by emp_id and checking if ssn ends with ssn_suffix.
    V10 Update: Checks against Hashed SSN.
    """
    conn = get_db_connection()
    # Join with gift_options to get selected gift details if any
    # Or just return employee row and fetch gift separately.
    # Let's just return raw employee row for auth.
    user = conn.execute('SELECT * FROM employees WHERE emp_id = ?', (emp_id,)).fetchone()
    conn.close()
    
    if user:
        db_ssn = user['ssn']
        # Convert input suffix to hash
        input_hash = hash_val(ssn_suffix)
        
        # Check direct match (V10 Hashed storage)
        if db_ssn == input_hash:
            return user
            
        # Fallback for legacy (if migration failed or mixed)
        # Check if db_ssn is plaintext and matches
        if len(db_ssn) < 64: 
             if '-' in db_ssn:
                 if db_ssn.split('-')[1] == ssn_suffix:
                     return user
             elif db_ssn == ssn_suffix:
                 return user
            
    return None

def update_employee_info(emp_id, data):
    """Updates employee information. Handles partial updates."""
    conn = get_db_connection()
    c = conn.cursor()
    
    # Construct dynamic query based on provided keys
    # This allows updating only Info or only Gift sections
    valid_keys = [
        'address_main', 'address_main_detail', 'zipcode', 'phone',
        'gift_address', 'gift_address_detail', 'gift_zipcode', 'gift_receiver',
        'selected_gift_id' # V13
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
    
    query = f"UPDATE employees SET {','.join(updates)} WHERE emp_id = ?"
    
    c.execute(query, tuple(values))
    conn.commit()
    conn.close()

def get_all_employees():
    """Returns all employees as a pandas DataFrame (for admin export)."""
    conn = get_db_connection()
    # V13 Join for export
    query = '''
    SELECT e.*, g.name as gift_name 
    FROM employees e
    LEFT JOIN gift_options g ON e.selected_gift_id = g.id
    '''
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def upsert_employees_from_excel(filepath):
    """
    Reads an Excel file and updates/inserts employees.
    Uses specific column indices based on user provided data layout (V7).
    - Zipcode: 55 -> 54 (Added in V8)
    V10 Update: Hashes SSN Back before storing. Discards Front.
    V11 Update: Force read as string to preserve leading zeros.
    """
    # V11: dtype=str to preserve leading zeros
    df = pd.read_excel(filepath, dtype=str)
    
    # Map by index
    # We create a new clean dataframe
    clean_df = pd.DataFrame()
    
    # Helper to safe access by iloc
    def get_col_data(col_idx):
        if col_idx < len(df.columns):
            return df.iloc[:, col_idx]
        return None

    # Function to clean typical Excel numeric artifacts (e.g. 1234.0 -> 1234)
    # V11: Since we read as str, .0 might not happen as often but still safe to keep
    def clean_str(series):
        if series is None:
            return pd.Series([''] * len(df))
            
        def convert_val(x):
            s = str(x).strip()
            if s.lower() in ['nan', 'none', '', 'nat']:
                return ''
            
            # V15 Fix: Only remove trailing .0 artifact. Do NOT cast to float/int
            # as that removes leading zeros (e.g. "0123" -> 123.0 -> "123")
            if s.endswith('.0'):
                return s[:-2]
            return s
                
        return series.apply(convert_val)

    clean_df['emp_id'] = clean_str(get_col_data(11))
    clean_df['name'] = clean_str(get_col_data(12))
    
    # V10: Store Hash(Back) only
    # ssn_front = clean_str(get_col_data(24)) # Not storing front anymore for privacy
    ssn_back = clean_str(get_col_data(26))
    
    # Apply hashing
    clean_df['ssn'] = ssn_back.apply(lambda x: hash_val(x) if x else '')
    
    clean_df['phone'] = clean_str(get_col_data(52))
    clean_df['address_main'] = clean_str(get_col_data(53))
    clean_df['zipcode'] = clean_str(get_col_data(54))
    
    # Clean up NaNs (redundant but safe)
    clean_df = clean_df.replace({'nan': '', 'None': ''})

    conn = get_db_connection()
    c = conn.cursor()
    
    count = 0
    for _, row in clean_df.iterrows():
        # Check if employee exists
        c.execute('SELECT id FROM employees WHERE emp_id = ?', (row['emp_id'],))
        exists = c.fetchone()
        
        if exists:
            # V10 Update: Update SSN with hash
            # V13 Update: Don't overwrite selected_gift_id on re-import
            c.execute('''
                UPDATE employees
                SET name = ?, ssn = ?, address_main = ?, zipcode = ?, phone = ?, last_updated = ?
                WHERE emp_id = ?
            ''', (row['name'], row['ssn'], row['address_main'], row['zipcode'], row['phone'], datetime.now(), row['emp_id']))
        else:
            c.execute('''
                INSERT INTO employees (name, emp_id, ssn, address_main, zipcode, phone, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (row['name'], row['emp_id'], row['ssn'], row['address_main'], row['zipcode'], row['phone'], datetime.now()))
        count += 1
        
    # Record upload time
    # deadlock fix: use same cursor instead of calling set_setting (which opens new conn)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.execute('INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)', ('last_upload_time', now_str))

    conn.commit()
    conn.close()
    return count

def reset_all_data():
    """V11: Deletes all employee data and resets settings."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM employees")
    c.execute("DELETE FROM system_settings")
    c.execute("DELETE FROM gift_options") # V13
    # Restore default settings if needed, or leave empty
    conn.commit()
    conn.close()

# V13: Gift CRUD
def add_gift_option(name, description, image_path):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO gift_options (name, description, image_path, created_at)
        VALUES (?, ?, ?, ?)
    ''', (name, description, image_path, datetime.now()))
    conn.commit()
    conn.close()

def get_gift_options():
    conn = get_db_connection()
    rows = conn.execute('SELECT * FROM gift_options WHERE is_active = 1').fetchall()
    conn.close()
    return [dict(row) for row in rows]

def delete_gift_option(gift_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM gift_options WHERE id = ?', (gift_id,))
    conn.commit()
    conn.close()

def get_gift_by_id(gift_id):
    conn = get_db_connection()
    row = conn.execute('SELECT * FROM gift_options WHERE id = ?', (gift_id,)).fetchone()
    conn.close()
    return dict(row) if row else None
    
    
if __name__ == '__main__':
    init_db()
