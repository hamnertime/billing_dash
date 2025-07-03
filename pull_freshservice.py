import requests
import base64
import json
import os
import sys
import sqlite3
import time
from datetime import datetime, timezone

# --- Configuration ---
TOKEN_FILE = "./token.txt"
DB_FILE = "brainhair.db"
FRESHSERVICE_DOMAIN = "integotecllc.freshservice.com"
ACCOUNT_NUMBER_FIELD = "account_number"
COMPANIES_PER_PAGE = 100

# --- API Functions ---
def read_api_key(file_path):
    """Reads the API key from the specified file."""
    try:
        with open(file_path, 'r') as f: return f.read().strip()
    except FileNotFoundError:
        print(f"Error: Token file '{file_path}' not found.", file=sys.stderr)
        sys.exit(1)

def get_all_companies(base_url, headers):
    """Fetches all companies (departments) from the Freshservice API."""
    print("Fetching companies from Freshservice...")
    all_companies, page = [], 1
    endpoint = f"{base_url}/api/v2/departments"
    while True:
        try:
            params = {'page': page, 'per_page': COMPANIES_PER_PAGE}
            response = requests.get(endpoint, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            companies_on_page = data.get('departments', [])
            if not companies_on_page: break
            all_companies.extend(companies_on_page)
            page += 1
        except requests.exceptions.RequestException as e:
            print(f"Error fetching Freshservice companies: {e}", file=sys.stderr)
            return None
    print(f" Found {len(all_companies)} companies in Freshservice.")
    return all_companies

def get_all_users(base_url, headers):
    """
    Fetches ALL users (requesters) from the Freshservice API.
    The API does not allow filtering by company, so we must fetch all and map them later.
    """
    print("\nFetching all users from Freshservice (this may take a moment)...")
    all_users, page = [], 1
    endpoint = f"{base_url}/api/v2/requesters"
    while True:
        params = {'page': page, 'per_page': 100}
        try:
            print(f"-> Fetching user page {page}...")
            response = requests.get(endpoint, headers=headers, params=params, timeout=30)
            if response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 5))
                print(f"   -> Rate limit exceeded, waiting {retry_after}s...")
                time.sleep(retry_after)
                continue
            response.raise_for_status()
            data = response.json()
            users_on_page = data.get('requesters', [])
            if not users_on_page: break
            all_users.extend(users_on_page)
            page += 1
        except requests.exceptions.RequestException as e:
            print(f"   -> Error fetching users on page {page}: {e}", file=sys.stderr)
            return None
    print(f" Found {len(all_users)} total users in Freshservice.")
    return all_users

# --- Database Functions ---
def populate_companies_database(db_connection, companies_data):
    """Populates the companies table."""
    cur = db_connection.cursor()
    companies_to_insert = []
    for company in companies_data:
        custom_fields = company.get('custom_fields', {})
        account_number = custom_fields.get(ACCOUNT_NUMBER_FIELD)
        if not account_number:
            print(f"Warning: Skipping company '{company.get('name')}' because it lacks an Account Number.", file=sys.stderr)
            continue
        companies_to_insert.append((
            str(account_number),
            company.get('name'),
            company.get('id'),
            custom_fields.get('type_of_client', 'Unknown'),
            custom_fields.get('plan_selected', 'Unknown')
        ))

    if not companies_to_insert:
        print("No valid companies with account numbers found to process.")
        return

    print(f"\nAttempting to insert/update {len(companies_to_insert)} companies...")
    cur.executemany("""
        INSERT INTO companies (account_number, name, freshservice_id, contract_type, billing_plan)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(account_number) DO UPDATE SET
            name=excluded.name,
            freshservice_id=excluded.freshservice_id,
            contract_type=excluded.contract_type,
            billing_plan=excluded.billing_plan;
    """, companies_to_insert)
    print(f"-> Successfully inserted/updated {cur.rowcount} companies.")

def populate_users_database(db_connection, users_to_insert):
    """Populates the users table."""
    if not users_to_insert:
        print("No users to insert into the database.")
        return

    cur = db_connection.cursor()
    print(f"\nAttempting to insert/update {len(users_to_insert)} users...")
    cur.executemany("""
        INSERT INTO users (company_account_number, freshservice_id, full_name, email, status, date_added)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(freshservice_id) DO UPDATE SET
            company_account_number=excluded.company_account_number,
            full_name=excluded.full_name,
            email=excluded.email,
            status=excluded.status;
    """, users_to_insert)
    print(f"-> Successfully inserted/updated {cur.rowcount} users.")

# --- Main Execution ---
if __name__ == "__main__":
    print(" Freshservice Company & User Syncer")
    print("==========================================")
    if not os.path.exists(DB_FILE):
        sys.exit(f"Error: Database file '{DB_FILE}' not found. Run init_db.py first.")

    API_KEY = read_api_key(TOKEN_FILE)
    auth_str = f"{API_KEY}:X"
    encoded_auth = base64.b64encode(auth_str.encode()).decode()
    headers = {"Content-Type": "application/json", "Authorization": f"Basic {encoded_auth}"}

    # 1. Get all companies and all users from Freshservice
    companies = get_all_companies(f"https://{FRESHSERVICE_DOMAIN}", headers)
    users = get_all_users(f"https://{FRESHSERVICE_DOMAIN}", headers)

    if not companies or users is None:
        sys.exit("Could not fetch data from Freshservice. Aborting.")

    # --- Create a map for easy lookup: freshservice_id -> account_number ---
    company_id_to_account_map = {
        c.get('id'): (c.get('custom_fields') or {}).get(ACCOUNT_NUMBER_FIELD)
        for c in companies
    }

    # --- Prepare user data for insertion ---
    all_users_to_insert = []
    print("\n--- Mapping Users to Companies ---")
    for user in users:
        # A user can belong to multiple departments (companies)
        department_ids = user.get('department_ids') or []
        for dept_id in department_ids:
            account_num = company_id_to_account_map.get(dept_id)
            if account_num:
                all_users_to_insert.append((
                    str(account_num),
                    user.get('id'),
                    f"{user.get('first_name', '')} {user.get('last_name', '')}".strip(),
                    user.get('primary_email'),
                    'Active' if user.get('active', False) else 'Inactive',
                    user.get('created_at', datetime.now(timezone.utc).isoformat())
                ))
                # We only need to link the user to the first valid company we find
                break

    print(f"Mapped {len(all_users_to_insert)} user-company links.")

    # --- Database Operations ---
    con = sqlite3.connect(DB_FILE)
    try:
        # 2. Populate companies table first
        populate_companies_database(con, companies)

        # 3. Populate users table in a single transaction
        populate_users_database(con, all_users_to_insert)

        # 4. Commit all changes
        con.commit()
        print("\n All database operations committed successfully.")

    except sqlite3.Error as e:
        print(f"\n❌ Database error occurred: {e}", file=sys.stderr)
        print("Rolling back all changes.", file=sys.stderr)
        con.rollback()
        sys.exit(1)
    finally:
        if con:
            con.close()

    print("\nScript finished.")
