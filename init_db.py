import sys
import os
import getpass

# This is provided by the sqlcipher3-wheels package
try:
    from sqlcipher3 import dbapi2 as sqlite3
except ImportError:
    print("Error: sqlcipher3-wheels is not installed. Please install it using: pip install sqlcipher3-wheels", file=sys.stderr)
    sys.exit(1)


DB_FILE = "brainhair.db"

def create_database():
    """
    Initializes a new encrypted SQLite database, prompts for a master password
    and API keys, and creates the necessary schema.
    """
    if os.path.exists(DB_FILE):
        print(f"Error: Database file '{DB_FILE}' already exists.", file=sys.stderr)
        print("Please remove it manually to re-create the database from scratch.", file=sys.stderr)
        sys.exit(1)

    print("--- Database and API Key Setup ---")
    # 1. Get Master Password
    master_password = getpass.getpass("Enter a master password for the new encrypted database: ")
    if not master_password:
        print("Error: Master password cannot be empty.", file=sys.stderr)
        sys.exit(1)

    # 2. Get API Keys
    print("\nEnter your Freshservice API credentials:")
    freshservice_key = getpass.getpass("  - Freshservice API Key: ")
    if not freshservice_key:
        print("Error: Freshservice API Key cannot be empty.", file=sys.stderr)
        sys.exit(1)

    print("\nEnter your Datto RMM API credentials:")
    datto_endpoint = input("  - Datto RMM API Endpoint (e.g., https://api.rmm.datto.com): ")
    datto_key = getpass.getpass("  - Datto RMM Public Key: ")
    datto_secret = getpass.getpass("  - Datto RMM Secret Key: ")
    if not all([datto_endpoint, datto_key, datto_secret]):
        print("Error: All Datto RMM credentials are required.", file=sys.stderr)
        sys.exit(1)


    con = None
    try:
        # Connect and set the password for the new database
        con = sqlite3.connect(DB_FILE)
        cur = con.cursor()
        # This PRAGMA encrypts the database
        cur.execute(f"PRAGMA key = '{master_password}';")
        cur.execute("PRAGMA foreign_keys = ON;")

        # --- Create Schema ---
        print("\nCreating database schema...")
        print("Creating 'api_keys' table...")
        cur.execute("""
            CREATE TABLE api_keys (
                service TEXT PRIMARY KEY NOT NULL,
                api_key TEXT NOT NULL,
                api_secret TEXT,
                api_endpoint TEXT
            )
        """)

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

        print("Creating 'billing_plans' table...")
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

        # --- NEW TABLE FOR TICKET HOURS ---
        print("Creating 'ticket_work_hours' table...")
        cur.execute("""
            CREATE TABLE ticket_work_hours (
                company_account_number TEXT NOT NULL,
                month TEXT NOT NULL, -- e.g., '2025-06'
                hours REAL NOT NULL,
                PRIMARY KEY (company_account_number, month),
                FOREIGN KEY (company_account_number) REFERENCES companies (account_number)
            )
        """)


        # --- Insert API Keys ---
        print("\nStoring API keys in the encrypted database...")
        cur.execute(
            "INSERT INTO api_keys (service, api_key) VALUES (?, ?)",
            ("freshservice", freshservice_key)
        )
        cur.execute(
            "INSERT INTO api_keys (service, api_endpoint, api_key, api_secret) VALUES (?, ?, ?, ?)",
            ("datto", datto_endpoint, datto_key, datto_secret)
        )

        con.commit()
        print(f"\n✅ Success! Encrypted database '{DB_FILE}' created and configured.")
        print("IMPORTANT: You must now use the DB_MASTER_PASSWORD environment variable to run the app and scripts.")
        print("Example: set DB_MASTER_PASSWORD=your_password_here")

    except sqlite3.Error as e:
        print(f"\n❌ An error occurred: {e}", file=sys.stderr)
        if con: con.close()
        # Clean up the failed DB file
        if os.path.exists(DB_FILE): os.remove(DB_FILE)
        sys.exit(1)
    finally:
        if con: con.close()

if __name__ == "__main__":
    create_database()
