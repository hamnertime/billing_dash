import sqlite3
import os
import sys
from flask import Flask, render_template, g, request, redirect, url_for, flash
import subprocess

# --- Configuration ---
DATABASE = 'brainhair.db'
app = Flask(__name__)
app.secret_key = os.urandom(24)

def get_db():
    """Connects to the database."""
    db = getattr(g, '_database', None)
    if db is None:
        if not os.path.exists(DATABASE):
            raise FileNotFoundError(f"Database file '{DATABASE}' not found.")
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    """Closes the database at the end of the request."""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def query_db(query, args=(), one=False):
    """Helper function to query the database."""
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv

@app.route('/')
def billing_dashboard():
    """Main route to display the client billing dashboard."""
    clients_query = """
        SELECT
            c.name, c.contract_type, c.billing_plan,
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

@app.route('/settings', methods=['GET', 'POST'])
def billing_settings():
    """Route to display and update billing plan configurations."""
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

@app.route('/run_script/<script_name>', methods=['POST'])
def run_script(script_name):
    """Executes a predefined Python script and shows the output."""
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
        # --- THE FIX IS HERE ---
        # We explicitly set the encoding to 'utf-8' to handle emojis and other characters.
        result = subprocess.run(
            [python_executable, script_to_run],
            capture_output=True, text=True, check=False, timeout=300,
            encoding='utf-8', errors='replace'
        )

        output = f"--- Running {script_to_run} ---\n\n{result.stdout}\n{result.stderr}"

        if result.returncode == 0:
            flash(f" Script '{script_to_run}' executed successfully.", 'success')
        else:
            flash(f"❌ Script '{script_to_run}' finished with an error (exit code {result.returncode}).", 'error')

        flash(output, 'output')

    except subprocess.TimeoutExpired:
        flash(f"❌ Script '{script_to_run}' timed out after 5 minutes.", 'error')
    except Exception as e:
        flash(f"An unexpected error occurred: {e}", 'error')

    return redirect(url_for('billing_settings'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5002)
