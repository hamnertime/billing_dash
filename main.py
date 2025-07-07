import os
import sys
import subprocess
from flask import Flask, render_template, g, request, redirect, url_for, flash, session

# Use the sqlcipher3 library provided by the wheels package
try:
    from sqlcipher3 import dbapi2 as sqlite3
except ImportError:
    print("Error: sqlcipher3-wheels is not installed. Please install it using: pip install sqlcipher3-wheels", file=sys.stderr)
    sys.exit(1)


# --- Configuration ---
DATABASE = 'brainhair.db'
app = Flask(__name__)
# A secret key is required for server-side sessions
app.secret_key = os.urandom(24)

def get_db():
    """Connects to the encrypted database and unlocks it using the password from the session."""
    db = getattr(g, '_database', None)
    if db is None:
        if not os.path.exists(DATABASE):
            raise FileNotFoundError(f"Database file '{DATABASE}' not found. Please run init_db.py first.")

        master_password = session.get('db_password')
        if not master_password:
            raise ValueError("Database password not found in session.")

        db = g._database = sqlite3.connect(DATABASE)
        try:
            db.execute(f"PRAGMA key = '{master_password}';")
            db.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 1;")
            db.row_factory = sqlite3.Row
        except sqlite3.DatabaseError:
            db.close()
            g._database = None
            raise ValueError("Invalid master password.")

    return db

@app.teardown_appcontext
def close_connection(exception):
    """Closes the database at the end of the request."""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

@app.before_request
def require_login():
    """Checks that a password is in the session before allowing access to any page."""
    if 'db_password' not in session and request.endpoint not in ['login', 'static']:
        return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Displays the login page and handles password submission."""
    if request.method == 'POST':
        password_attempt = request.form.get('password')
        try:
            session['db_password'] = password_attempt
            db = get_db()
            flash('Database unlocked successfully!', 'success')
            return redirect(url_for('billing_dashboard'))
        except (ValueError, sqlite3.Error):
            session.pop('db_password', None)
            flash(f"Login failed: Invalid master password.", 'error')
            return redirect(url_for('login'))

    return render_template('login.html')

def query_db(query, args=(), one=False):
    """Helper function to query the database."""
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv

@app.route('/')
def billing_dashboard():
    """Main route to display the client billing dashboard."""
    try:
        clients_query = """
            SELECT
                c.account_number, c.name, c.contract_type, c.billing_plan,
                COUNT(DISTINCT CASE WHEN a.operating_system LIKE '%Server%' THEN a.id END) as server_count,
                COUNT(DISTINCT CASE WHEN a.operating_system NOT LIKE '%Server%' AND a.operating_system IS NOT NULL THEN a.id END) as workstation_count,
                COUNT(DISTINCT u.id) as user_count,
                COALESCE(bp.base_price, 0) as base_price,
                COALESCE(bp.per_user_cost, 0) as per_user_cost,
                COALESCE(bp.per_server_cost, 0) as per_server_cost,
                COALESCE(bp.per_workstation_cost, 0) as per_workstation_cost,
                COALESCE(bp.billed_by, 'Not Configured') as billed_by
            FROM companies c
            LEFT JOIN assets a ON c.account_number = a.company_account_number
            LEFT JOIN users u ON c.account_number = u.company_account_number
            LEFT JOIN billing_plans bp ON c.contract_type = bp.contract_type AND c.billing_plan = bp.billing_plan
            GROUP BY c.account_number ORDER BY c.name ASC;
        """
        clients_data = query_db(clients_query)

        clients_with_totals = []
        for client in clients_data:
            client_dict = dict(client)
            total = client_dict['base_price']
            if client_dict['billed_by'] == 'Per User':
                total += client_dict['user_count'] * client_dict['per_user_cost']
            elif client_dict['billed_by'] == 'Per Device':
                total += client_dict['workstation_count'] * client_dict['per_workstation_cost']
                total += client_dict['server_count'] * client_dict['per_server_cost']
            client_dict['total_bill'] = total
            clients_with_totals.append(client_dict)

        return render_template('billing.html', clients=clients_with_totals)
    except (ValueError, sqlite3.Error) as e:
        session.pop('db_password', None)
        flash(f"Database Error: {e}. Please log in again.", 'error')
        return redirect(url_for('login'))

# --- NEW ROUTE ---
@app.route('/client/<account_number>')
def client_settings(account_number):
    """Displays a detailed view for a single client."""
    try:
        # Query for the main company info
        client_info = query_db("SELECT * FROM companies WHERE account_number = ?", [account_number], one=True)
        if not client_info:
            flash(f"Client with account number {account_number} not found.", 'error')
            return redirect(url_for('billing_dashboard'))

        # Query for associated assets, users, and ticket hours
        assets = query_db("SELECT * FROM assets WHERE company_account_number = ? ORDER BY hostname", [account_number])
        users = query_db("SELECT * FROM users WHERE company_account_number = ? ORDER BY full_name", [account_number])
        ticket_hours = query_db("SELECT * FROM ticket_work_hours WHERE company_account_number = ? ORDER BY month DESC", [account_number])

        return render_template('client_settings.html', client=client_info, assets=assets, users=users, ticket_hours=ticket_hours)

    except (ValueError, sqlite3.Error) as e:
        session.pop('db_password', None)
        flash(f"Database Error: {e}. Please log in again.", 'error')
        return redirect(url_for('login'))


@app.route('/settings', methods=['GET', 'POST'])
def billing_settings():
    # ... (this function remains unchanged)
    try:
        db = get_db()
        if request.method == 'POST':
            plans_to_update = []
            num_plans = len([key for key in request.form if key.startswith('billed_by_')])

            for i in range(1, num_plans + 1):
                plans_to_update.append((
                    request.form.get(f'contract_type_{i}'),
                    request.form.get(f'billing_plan_{i}'),
                    request.form.get(f'billed_by_{i}'),
                    float(request.form.get(f'base_price_{i}', 0)),
                    float(request.form.get(f'per_user_cost_{i}', 0)),
                    float(request.form.get(f'per_server_cost_{i}', 0)),
                    float(request.form.get(f'per_workstation_cost_{i}', 0))
                ))

            db.executemany("""
                INSERT OR REPLACE INTO billing_plans
                (contract_type, billing_plan, billed_by, base_price, per_user_cost, per_server_cost, per_workstation_cost)
                VALUES (?, ?, ?, ?, ?, ?, ?);
            """, plans_to_update)
            db.commit()
            flash("Billing plan settings saved successfully!", 'success')
            return redirect(url_for('billing_settings'))

        all_plans_query = """
            SELECT DISTINCT
                c.contract_type, c.billing_plan,
                COALESCE(bp.billed_by, 'Per Device') as billed_by,
                COALESCE(bp.base_price, 0.0) as base_price,
                COALESCE(bp.per_user_cost, 0.0) as per_user_cost,
                COALESCE(bp.per_server_cost, 0.0) as per_server_cost,
                COALESCE(bp.per_workstation_cost, 0.0) as per_workstation_cost
            FROM companies c
            LEFT JOIN billing_plans bp
                ON c.contract_type = bp.contract_type AND c.billing_plan = bp.billing_plan
            ORDER BY c.contract_type, c.billing_plan;
        """
        all_plans = query_db(all_plans_query)
        return render_template('settings.html', all_plans=all_plans)
    except (ValueError, sqlite3.Error) as e:
        session.pop('db_password', None)
        flash(f"Database Error: {e}. Please log in again.", 'error')
        return redirect(url_for('login'))


@app.route('/run_script/<script_name>', methods=['POST'])
def run_script(script_name):
    # ... (this function remains unchanged)
    master_password = session.get('db_password')
    if not master_password:
        flash("Error: Session expired. Please log in again.", 'error')
        return redirect(url_for('login'))

    valid_scripts = {
        'sync_freshservice': 'pull_freshservice.py',
        'sync_datto': 'pull_datto.py',
        'set_freshservice_ids': 'set_account_numbers.py',
        'push_ids_to_datto': 'push_account_nums_to_datto.py'
    }

    script_to_run = valid_scripts.get(script_name)

    if not script_to_run or not os.path.exists(script_to_run):
        flash(f"Error: Script '{script_name}' not found or is not valid.", 'error')
        return redirect(url_for('billing_settings'))

    try:
        python_executable = sys.executable
        env = os.environ.copy()
        env['DB_MASTER_PASSWORD'] = master_password

        result = subprocess.run(
            [python_executable, script_to_run],
            capture_output=True, text=True, check=False, timeout=300,
            encoding='utf-8', errors='replace',
            env=env
        )

        output = f"--- Running {script_to_run} ---\n\n{result.stdout}\n{result.stderr}"

        if result.returncode == 0:
            flash(f"Script '{script_to_run}' executed successfully.", 'success')
        else:
            flash(f"❌ Script '{script_to_run}' finished with an error (exit code {result.returncode}).", 'error')

        flash(output, 'output')

    except subprocess.TimeoutExpired:
        flash(f"❌ Script '{script_to_run}' timed out after 5 minutes.", 'error')
    except Exception as e:
        flash(f"An unexpected error occurred: {e}", 'error')

    return redirect(url_for('billing_settings'))

if __name__ == '__main__':
    if not (os.path.exists('cert.pem') and os.path.exists('key.pem')):
        print("Error: SSL certificate (cert.pem) and key (key.pem) not found.", file=sys.stderr)
        print("Please run 'python generate_cert.py' to create them.", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(DATABASE):
        print(f"Error: Database '{DATABASE}' not found.", file=sys.stderr)
        print("Please run 'python init_db.py' to create and configure it first.", file=sys.stderr)
        sys.exit(1)

    app.run(debug=True, host='0.0.0.0', port=5002, ssl_context=('cert.pem', 'key.pem'))
