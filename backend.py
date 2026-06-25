# backend.py

from datetime import datetime
import os

from LE_KPI_report import load_and_process_helpdesk_data, generate_le_report
import config


def run_backend_processing(platform_csv_path, helpdesk_csv_path):
    """
    The core logic for processing data and generating the report.
    This function is called by the GUI and returns the path to the generated report.
    """
    print("--- Starting Backend Report Generation ---")

    app_config = config.load_config()
    if not app_config:
        raise ValueError("Configuration is missing or corrupt.")
    print("Successfully loaded configuration.")

    print("-" * 30)
    helpdesk_data = load_and_process_helpdesk_data(helpdesk_csv_path)

    report_date = datetime.now().strftime('%Y-%m-%d')
    output_dir = os.path.dirname(os.path.abspath(__file__))
    output_filename = os.path.join(output_dir, f"LE_KPI_REPORT_{report_date}.html")

    generate_le_report(
        csv_path=platform_csv_path,
        output_path=output_filename,
        config=app_config,
        helpdesk_data=helpdesk_data
    )

    print("--- Backend Processing Finished ---")

    return output_filename