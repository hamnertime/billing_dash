import requests
import base64
import json
import os
import sys
import sqlite3
from datetime import datetime, timezone

# --- Configuration ---
TOKEN_FILE = "./datto_token.txt"
DB_FILE = "brainhair.db"
DATTO_VARIABLE_NAME = "AccountNumber"

# --- API Functions ---
def read_datto_creds():
    try:
        with open(TOKEN_FILE, 'r') as f:
            lines = [line.strip() for line in f.readlines()]
            return lines[0], lines[1], lines[2]
    except FileNotFoundError:
        print(f"Error: Datto token file '{TOKEN_FILE}' not found.", file=sys.stderr)
        sys.exit(1)

def get_datto_access_token(api_endpoint, api_key, api_secret_key):
    token_url = f"{api_endpoint}/auth/oauth/token"
    payload = {'grant_type': 'password', 'username': api_key, 'password': api_secret_key}
    headers = {'Content-Type': 'application/x-www-form-urlencoded', 'Authorization': 'Basic cHVibGljLWNsaWVudDpwdWJsaWM='}
    try:
        response = requests.post(token_url, headers=headers, data=payload, timeout=30)
        response.raise_for_status()
        return response.json().get("access_token")
    except requests.exceptions.RequestException as e:
        print(f"Error getting Datto access token: {e}", file=sys.stderr)
        return None

def make_api_request(api_endpoint, access_token, api_request_path):
    all_items = []
    next_page_url = f"{api_endpoint}/api{api_request_path}"
    headers = {'Authorization': f'Bearer {access_token}'}
    while next_page_url:
        try:
            response = requests.get(next_page_url, headers=headers, timeout=30)
            response.raise_for_status()
            response_data = response.json()
            items_on_page = response_data.get('items') or response_data.get('sites') or response_data.get('devices')
            if items_on_page is None: break
            all_items.extend(items_on_page)
            next_page_url = response_data.get('pageDetails', {}).get('nextPageUrl') or response_data.get('nextPageUrl')
        except requests.exceptions.RequestException as e:
            print(f"An error occurred during API request for {api_request_path}: {e}", file=sys.stderr)
            return None
    return all_items

def get_site_variable(api_endpoint, access_token, site_uid, variable_name):
    request_url = f"{api_endpoint}/api/v2/site/{site_uid}/variables"
    headers = {'Authorization': f'Bearer {access_token}'}
    try:
        response = requests.get(request_url, headers=headers, timeout=30)
        if response.status_code == 404: return None
        response.raise_for_status()
        variables = response.json().get("variables", [])
        for var in variables:
            if var.get("name") == variable_name:
                return var.get("value")
        return None
    except requests.exceptions.RequestException:
        return None

# --- Database Function ---
def populate_assets_database(assets_to_insert):
    con = None
    try:
        con = sqlite3.connect(DB_FILE)
        cur = con.cursor()
        print(f"\nAttempting to insert/update {len(assets_to_insert)} assets into the database...")
        cur.executemany("""
            INSERT INTO assets (company_account_number, datto_uid, hostname, friendly_name, device_type, operating_system, status, date_added)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(datto_uid) DO UPDATE SET
                company_account_number=excluded.company_account_number,
                hostname=excluded.hostname,
                friendly_name=excluded.friendly_name,
                device_type=excluded.device_type,
                operating_system=excluded.operating_system,
                status=excluded.status;
        """, assets_to_insert)
        con.commit()
        print(f" Successfully inserted/updated {cur.rowcount} assets in '{DB_FILE}'.")
    except sqlite3.Error as e:
        print(f"\n❌ Database error: {e}", file=sys.stderr)
        if con: con.rollback()
        sys.exit(1)
    finally:
        if con: con.close()

# --- Main Execution ---
if __name__ == "__main__":
    print(" Datto RMM Data Syncer")
    print("==========================================")
    if not os.path.exists(DB_FILE):
        sys.exit(f"Error: Database file '{DB_FILE}' not found. Please run the new init_db.py script first.")

    endpoint, api_key, secret_key = read_datto_creds()
    token = get_datto_access_token(endpoint, api_key, secret_key)
    if not token: sys.exit("\n❌ Failed to obtain access token.")

    sites = make_api_request(endpoint, token, "/v2/account/sites")
    if sites is None: sys.exit("\nCould not retrieve sites list.")
    print(f"\nFound {len(sites)} total sites in Datto.")

    assets_to_insert = []
    print("\n--- Processing Sites and Devices ---")
    for i, site in enumerate(sites, 1):
        site_uid, site_name = site.get('uid'), site.get('name')
        if not site_uid: continue

        print(f"-> ({i}/{len(sites)}) Processing site: '{site_name}'")

        account_number = get_site_variable(endpoint, token, site_uid, DATTO_VARIABLE_NAME)
        if not account_number:
            print(f"   -> Skipping: No '{DATTO_VARIABLE_NAME}' variable found.")
            continue

        print(f"   -> Found Account Number: {account_number}. Fetching devices...")
        devices_in_site = make_api_request(endpoint, token, f"/v2/site/{site_uid}/devices")

        if devices_in_site:
            print(f"   -> Found {len(devices_in_site)} devices. Preparing for DB insert.")
            for device in devices_in_site:
                creation_ms = device.get('creationDate')
                date_added_str = datetime.fromtimestamp(creation_ms / 1000, tz=timezone.utc).isoformat() if creation_ms else None
                assets_to_insert.append((
                    account_number,
                    device.get('uid'),
                    device.get('hostname'),
                    device.get('description'),
                    (device.get('deviceType') or {}).get('category'),
                    device.get('operatingSystem'),
                    'Active',
                    date_added_str
                ))

    if assets_to_insert:
        populate_assets_database(assets_to_insert)
    else:
        print("\nNo devices found with linked account numbers. DB not modified.")

    print("\nScript finished.")
