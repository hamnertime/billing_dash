import sqlite3
import sys
import os

DB_FILE = "brainhair.db"

def create_database():
    """
    Initializes a new SQLite database with a table for billing plan configurations.
    """
    if os.path.exists(DB_FILE):
        print(f"Error: Database file '{DB_FILE}' already exists.", file=sys.stderr)
        print("Please remove it manually to re-create the database from scratch.", file=sys.stderr)
        sys.exit(1)

    con = None
    try:
        con = sqlite3.connect(DB_FILE)
        cur = con.cursor()
        cur.execute("PRAGMA foreign_keys = ON;")

        print("Creating 'companies' table...")
        cur.execute("""
            CREATE TABLE companies (
                account_number TEXT PRIMARY KEY NOT NULL,
                name TEXT NOT NULL UNIQUE,
                freshservice_id INTEGER UNIQUE,
                contract_type TEXT NOT NULL,
                billing_plan TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Active'
            )
        """)

        print("Creating 'assets' table...")
        cur.execute("""
            CREATE TABLE assets (
                id INTEGER PRIMARY KEY,
                company_account_number TEXT NOT NULL,
                datto_uid TEXT UNIQUE,
                hostname TEXT NOT NULL,
                friendly_name TEXT,
                device_type TEXT,
                status TEXT NOT NULL DEFAULT 'Active',
                date_added TEXT NOT NULL,
                operating_system TEXT,
                FOREIGN KEY (company_account_number) REFERENCES companies (account_number)
            )
        """)

        print("Creating 'users' table...")
        cur.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                company_account_number TEXT NOT NULL,
                freshservice_id INTEGER UNIQUE,
                full_name TEXT NOT NULL,
                email TEXT UNIQUE,
                status TEXT NOT NULL DEFAULT 'Active',
                date_added TEXT NOT NULL,
                FOREIGN KEY (company_account_number) REFERENCES companies (account_number)
            )
        """)

        # --- UPDATED TABLE ---
        print("Creating 'billing_plans' table with cost columns...")
        cur.execute("""
            CREATE TABLE billing_plans (
                contract_type TEXT NOT NULL,
                billing_plan TEXT NOT NULL,
                billed_by TEXT NOT NULL,
                base_price REAL NOT NULL DEFAULT 0.0,
                per_user_cost REAL NOT NULL DEFAULT 0.0,
                per_server_cost REAL NOT NULL DEFAULT 0.0,
                per_workstation_cost REAL NOT NULL DEFAULT 0.0,
                PRIMARY KEY (contract_type, billing_plan)
            )
        """)

        print("Creating 'billing_events' table...")
        cur.execute("""
            CREATE TABLE billing_events (
                id INTEGER PRIMARY KEY,
                company_account_number TEXT NOT NULL,
                event_date TEXT NOT NULL,
                description TEXT NOT NULL,
                notes TEXT,
                FOREIGN KEY (company_account_number) REFERENCES companies (account_number)
            )
        """)

        con.commit()
        print(f"\n✅ Success! Database '{DB_FILE}' created with the new schema.")

    except sqlite3.Error as e:
        print(f"An error occurred: {e}", file=sys.stderr)
        if con: con.close()
        if os.path.exists(DB_FILE): os.remove(DB_FILE)
        sys.exit(1)
    finally:
        if con: con.close()

if __name__ == "__main__":
    create_database()
