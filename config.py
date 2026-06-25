import json
import os
import sys
import platform

def get_app_data_dir(app_name="LE_KPIs_App"):
    """
    Returns the appropriate application data directory based on the OS.
    Creates the directory if it doesn't exist.
    """
    if platform.system() == "Windows":
        path = os.path.join(os.getenv('APPDATA'), app_name)
    elif platform.system() == "Darwin": # macOS
        path = os.path.join(os.path.expanduser('~/Library/Application Support'), app_name)
    else: # Linux/Unix
        path = os.path.join(os.path.expanduser('~/.config'), app_name) # Common for config files

    os.makedirs(path, exist_ok=True) # Ensure the directory exists
    return path

# Define the configuration file name
CONFIG_FILE_NAME = 'config_le.json'

def load_config():
    """
    Loads the configuration.
    1. It first attempts to load from a user-specific application data directory
       (where modified configs would be saved).
    2. If not found or readable there, it falls back to loading the default
       bundled config from the PyInstaller temporary directory (sys._MEIPASS)
       or the development script's directory.
    3. If neither is found or an error occurs, it returns a default empty structure.
    """
    app_data_dir = get_app_data_dir()
    user_config_path = os.path.join(app_data_dir, CONFIG_FILE_NAME)

    # Attempt 1: Load from user-specific config path
    if os.path.exists(user_config_path):
        try:
            with open(user_config_path, 'r', encoding='utf-8') as f:
                print(f"Loading configuration from user path: {user_config_path}")
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error loading user config from {user_config_path}: {e}. Falling back to bundled config.")

    # Attempt 2: If user config not found or failed, try to load from the bundled path
    # This is the default config shipped with the app.
    if getattr(sys, 'frozen', False):
        # Running inside a PyInstaller bundle, use _MEIPASS
        bundled_base_path = sys._MEIPASS
    else:
        # Running in development environment, use script's directory
        bundled_base_path = os.path.dirname(os.path.abspath(__file__))

    bundled_config_path = os.path.join(bundled_base_path, CONFIG_FILE_NAME)

    if os.path.exists(bundled_config_path):
        try:
            with open(bundled_config_path, 'r', encoding='utf-8') as f:
                print(f"Loading configuration from bundled/dev path: {bundled_config_path}")
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error loading bundled/dev config from {bundled_config_path}: {e}. Returning default config.")

    # If neither found/loaded, return a default empty structure
    print("Warning: Configuration file not found in user data or bundled path. Returning default config.")
    return {
        "goals": {},
        "working_hours": {},
        "automation_goals": {},
        "ipi": {},
        "idle": {},
        "days_off": {},
        "automated_customers": {}
    }

def save_config(data):
    """
    Saves the given data dictionary to the user-specific application data directory.
    Returns True on success, False on failure.
    """
    app_data_dir = get_app_data_dir()
    user_config_path = os.path.join(app_data_dir, CONFIG_FILE_NAME)

    try:
        # The get_app_data_dir function already ensures the directory exists
        with open(user_config_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"Configuration saved to: {user_config_path}")
        return True # Indicate success
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error saving configuration to {user_config_path}: {e}")
        # The UI will display the specific error message based on this failure.
        return False # Indicate failure