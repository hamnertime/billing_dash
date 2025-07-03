# **Billing Dashboard**

This project provides a web-based dashboard for managing client billing information by integrating data from Freshservice (for company and user data) and Datto RMM (for asset data). It calculates estimated monthly billing based on configurable plans and allows for the synchronization of data between these platforms.

## **Features**

* **Freshservice Integration**:  
  * Pulls company (department) and user (requester) data.  
  * Assigns unique account numbers to Freshservice companies if they don't already have one.  
* **Datto RMM Integration**:  
  * Pulls site and device (asset) data.  
  * Pushes Freshservice account numbers to corresponding Datto RMM sites as custom variables.  
* **Billing Calculation**: Calculates estimated monthly billing for each client based on:  
  * Base price.  
  * Per-user cost.  
  * Per-server cost.  
  * Per-workstation cost.  
  * Configurable billing models (e.g., "Per User", "Per Device").  
* **Web Dashboard**: A Flask-based web interface to:  
  * View client billing summaries.  
  * Configure billing plans and pricing.  
  * Manually trigger data synchronization scripts.  
* **SQLite Database**: Stores synchronized data and billing configurations locally.

## **Prerequisites**

Before you begin, ensure you have the following installed:

* **Python 3.x**: The project is written in Python.  
* **pip**: Python package installer (usually comes with Python).  
* **Freshservice API Key**: An API key from your Freshservice instance with sufficient permissions to read companies/departments, requesters, and update company custom fields.  
* **Datto RMM API Credentials**: API endpoint, public key, and secret key for your Datto RMM instance with permissions to read sites, devices, and manage site variables.

## **Setup**

Follow these steps to get the project up and running:

### **1\. Clone the Repository**

git clone https://github.com/ruapotato/billing\_dash.git  
cd billing\_dash

### **2\. Create Credential Files**

For security, API keys and tokens are read from external files that are excluded from version control (.gitignore prevents them from being committed).

* token.txt (for Freshservice):  
  Create a file named token.txt in the root directory of the project. This file should contain only your Freshservice API key.  
  YOUR\_FRESHSERVICE\_API\_KEY\_HERE

* datto\_token.txt (for Datto RMM):  
  Create a file named datto\_token.txt in the root directory of the project. This file should contain three lines: your Datto RMM API endpoint, public key, and secret key.  
  YOUR\_DATTO\_RMM\_API\_ENDPOINT  
  YOUR\_DATTO\_RMM\_PUBLIC\_KEY  
  YOUR\_DATTO\_RMM\_SECRET\_KEY

  **Example datto\_token.txt content:**  
  https://api.rmm.datto.com  
  your\_public\_key\_string  
  your\_secret\_key\_string

### **3\. Install Python Dependencies**

Install the required Python libraries using pip:

`pip install Flask requests`

### **4\. Initialize the Database**

The project uses an SQLite database (brainhair.db). You need to create the database schema before running the application.

`python init\_db.py`

If you ever need to reset the database, delete the brainhair.db file and run init\_db.py again.

## **Usage**

### **1\. Run the Flask Application**

Start the web server:

`python main.py`

The application will typically run on http://127.0.0.1:5002/. Open this URL in your web browser.

### **2\. Navigate the Dashboard**

* **Home Page (/)**: Displays the billing dashboard with client names, contract types, device counts, user counts, and calculated total bills.  
* **Settings Page (/settings)**: Allows you to configure the billing plans. You can define base\_price, per\_user\_cost, per\_server\_cost, and per\_workstation\_cost for each unique contract\_type and billing\_plan combination found in your Freshservice companies. You can also select how each plan is billed\_by (e.g., 'Per User', 'Per Device').

### **3\. Synchronize Data**

From the settings page, you can trigger the synchronization scripts:

* **Sync Freshservice**: Runs pull\_freshservice.py to fetch companies and users from Freshservice and populate the local database.  
* **Sync Datto RMM**: Runs pull\_datto.py to fetch sites and devices from Datto RMM and populate the local database.  
* **Set Freshservice Account IDs**: Runs set\_account\_numbers.py to assign unique account numbers to Freshservice companies that don't have one.  
* **Push IDs to Datto**: Runs push\_account\_nums\_to\_datto.py to take the Freshservice account numbers and push them as custom variables to the corresponding Datto RMM sites.

It's recommended to run the sync scripts in a logical order, for example:

1. Set Freshservice Account IDs (if needed)  
2. Sync Freshservice  
3. Sync Datto RMM  
4. Push IDs to Datto

## **Project Structure**

* main.py: The Flask application, handles web routes, database interactions for the dashboard, and script execution.  
* init\_db.py: Initializes the SQLite database schema.  
* pull\_freshservice.py: Fetches company and user data from Freshservice API and stores it in the database.  
* pull\_datto.py: Fetches site and device data from Datto RMM API and stores it in the database.  
* set\_account\_numbers.py: Assigns unique account numbers to Freshservice companies.  
* push\_account\_nums\_to\_datto.py: Pushes Freshservice account numbers to Datto RMM site variables.  
* token.txt: (User-created) Stores Freshservice API key.  
* datto\_token.txt: (User-created) Stores Datto RMM API credentials.  
* brainhair.db: (Generated) The SQLite database file.  
* .gitignore: Specifies files to be ignored by Git (e.g., \*.db, \*.txt for credentials).  
* templates/: Contains HTML templates for the Flask application.  
  * billing.html: The main dashboard view.  
  * settings.html: The billing plan configuration and script execution view.

