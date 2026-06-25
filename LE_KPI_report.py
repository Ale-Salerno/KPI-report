# LE_KPI_report.py

import pandas as pd
from datetime import datetime
import re
import numpy as np
import os
import json


def load_and_process_helpdesk_data(helpdesk_csv_path: str):
    """
    Reads a specific helpdesk export file and processes it to calculate
    revenue and prepare data for pending tickets.
    """
    try:
        print(f"Processing helpdesk CSV file: '{helpdesk_csv_path}'")
        # Load csv, ensuring all columns are read as strings initially to avoid type errors
        df_helpdesk = pd.read_csv(helpdesk_csv_path, sep=',', encoding='utf-8-sig', skiprows=1, dtype=str)

        # FIX 1: Clean up column names (remove extra spaces)
        df_helpdesk.columns = df_helpdesk.columns.str.strip()

        # Debug: Print columns to see what we actually have
        print(f"Found columns: {list(df_helpdesk.columns)}")

        # FIX 2: Flexible Renaming (Add variations if your CSV uses different names)
        rename_map = {
            'Time Spent': 'time_spent',
            'Handled by': 'handled_by',
            'Close Date': 'close_date',
            'Closed Date': 'close_date',  # Added alternative
            'Date Closed': 'close_date',  # Added alternative
            'Date': 'creation_date',
            'TicketID': 'ticket_id',
            'Ticket ID': 'ticket_id',  # Added alternative
            'URL': 'url',
            'Status': 'status',
            'Subject': 'subject'
        }
        df_helpdesk.rename(columns=rename_map, inplace=True)

        # Check if critical columns exist
        required_cols = ['close_date', 'creation_date', 'vendor_name']

        # If 'close_date' is missing, create it as NaT (Not a Time) to prevent crash
        if 'close_date' not in df_helpdesk.columns:
            print(
                "Warning: 'Close Date' column missing in Helpdesk CSV. Treating all tickets as open/unpaid for this report.")
            df_helpdesk['close_date'] = pd.NaT

        engineer_map = {
            'aba': 'Artem Bandura', 'alse': 'Alejandro Serrano Vázquez', 'macp': 'Maciej Palyska',
            'vipa': 'Victor Parra García', 'mafp': 'Manuel Fajardo del Peral', 'vama': 'Vanessa Martagón García',
            'pafo': 'Patrick Follaco', 'emci': 'Emmanuel Cinneri', 'alsa': 'Alessandro Salerno'
        }

        if 'handled_by' in df_helpdesk.columns:
            # Extract the user code (e.g., 'domain\aba' -> 'aba')
            df_helpdesk['handled_by_code'] = df_helpdesk['handled_by'].astype(str).str.split('\\').str[
                -1].str.lower().str.strip()
            df_helpdesk['vendor_name'] = df_helpdesk['handled_by_code'].map(engineer_map)
        else:
            df_helpdesk['vendor_name'] = None
            df_helpdesk['vendor_name'] = None

        df_helpdesk.dropna(subset=['vendor_name'], inplace=True)

        def parse_duration_to_hours(duration_str):
            if not isinstance(duration_str, str): return 0
            try:
                # Handle formats like "1h 30m" or "01:30:00"
                parts = list(map(int, duration_str.split(':')))
                if len(parts) == 3:
                    h, m, s = parts
                    return h + (m / 60.0) + (s / 3600.0)
                elif len(parts) == 2:  # MM:SS
                    m, s = parts
                    return (m / 60.0) + (s / 3600.0)
                return 0
            except (ValueError, IndexError):
                return 0

        df_helpdesk['total_hours'] = df_helpdesk['time_spent'].astype(str).apply(parse_duration_to_hours)
        df_helpdesk['helpdesk_revenue'] = df_helpdesk['total_hours'] * 20

        # Convert date columns
        df_helpdesk['creation_date'] = pd.to_datetime(df_helpdesk['creation_date'], errors='coerce')
        df_helpdesk['close_date'] = pd.to_datetime(df_helpdesk['close_date'], errors='coerce')

        # Filter out rows with no creation date
        df_helpdesk.dropna(subset=['creation_date'], inplace=True)

        # Use CLOSE date for revenue accounting.
        df_helpdesk['quarter'] = df_helpdesk['close_date'].dt.to_period('Q').astype(str)
        df_helpdesk['month_num'] = df_helpdesk['close_date'].dt.month

        # Use CREATION date to build lists of tickets.
        df_helpdesk['creation_quarter'] = df_helpdesk['creation_date'].dt.to_period('Q').astype(str)
        df_helpdesk['creation_month_num'] = df_helpdesk['creation_date'].dt.month

        # Return only columns that exist
        cols_to_return = [
            'vendor_name', 'quarter', 'month_num', 'helpdesk_revenue',
            'ticket_id', 'url', 'status', 'subject', 'time_spent',
            'creation_date', 'close_date', 'creation_quarter', 'creation_month_num'
        ]
        # Ensure we only return columns that are actually in the dataframe
        final_cols = [c for c in cols_to_return if c in df_helpdesk.columns]

        return df_helpdesk[final_cols]

    except FileNotFoundError:
        print(f"Error: Helpdesk CSV file not found at '{helpdesk_csv_path}'. Helpdesk data will be unavailable.")
        return pd.DataFrame()
    except Exception as e:
        print(f"An error occurred while processing helpdesk data: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()


def generate_le_report(csv_path: str, output_path: str, config: dict, helpdesk_data: pd.DataFrame):
    """
    Reads Localization Engineering job data and generates a polished HTML report with enhanced KPI metrics.
    """
    try:
        df = pd.read_csv(csv_path)
    except FileNotFoundError:
        print(f"Error: The file '{csv_path}' was not found.")
        return

    # --- 1. Data Processing and Initial Setup ---
    config_goals = config.get('goals', {})
    working_hours_mapping = config.get('working_hours', {})
    automation_goals = config.get('automation_goals', {})

    standard_prices = {
        'Advanced File Preparation': 20, 'Source File Preparation': 10,
        'Target File Creation': 5, 'Final Target Compilation': 20
    }

    le_team_names = [
        "Artem Bandura", "Manuel Fajardo del Peral", "Vanessa Martagón García",
        "Alessandro Salerno", "Victor Parra García", "Alejandro Serrano Vázquez",
        "Maciej Palyska", "Patrick Follaco", "Emmanuel Cinneri",
        "LanguageWire Engineers Team"
    ]

    job_type_mapping = {
        'Additional Fee': 'Add-Fee', 'Advanced File Preparation': 'Adv-Prep', 'Alignment': 'Align',
        'Consultancy Services': 'Cnst', 'DTP for target preview': 'DTP-Prev', 'Final Target Compilation': 'Post',
        'License - API': 'API-Lic', 'Post-editing of Machine Translation': 'PEMT', 'Pre-DTP': 'Pre-DTP',
        'QA Check': 'QA', 'Source File Preparation': 'Prep', 'TB Management': 'TB-Mgmt',
        'TM Management': 'TM-Mgmt', 'Target File Creation': 'Tgt-File', 'Translation': 'L10n',
        'Translation 2.0': 'L10n_2_0'
    }

    if 'Job Type' in df.columns:
        unique_job_types = df['Job Type'].dropna().unique()
        new_types_found = False
        for job_type in unique_job_types:
            if job_type not in job_type_mapping:
                if not new_types_found:
                    print("\n---")
                    print("Info: New job types detected. Generating short names dynamically.")
                    new_types_found = True
                words = re.split(r'[\s/-]', job_type)
                if len(words) > 1:
                    short_name = "".join(word[0] for word in words if word).upper()
                else:
                    short_name = job_type[:4].capitalize()
                original_short_name = short_name
                counter = 2
                while short_name in job_type_mapping.values():
                    short_name = f"{original_short_name}{counter}"
                    counter += 1
                job_type_mapping[job_type] = short_name
                print(f"  - Mapped '{job_type}' to '{short_name}'")
        if new_types_found:
            print("---\n")

    df.rename(columns={
        'Vendor Name': 'vendor_name', 'Vendor Price, EUR , Amount': 'price_eur',
        'Job Type': 'job_type', 'Deadline': 'deadline', 'Entity': 'entity', 'ID': 'id'
    }, inplace=True)
    df = df[df['vendor_name'].isin(le_team_names)].copy()
    df['vendor_name'] = df['vendor_name'].str.strip()
    if 'entity' in df.columns: df['entity'] = df['entity'].str.strip()
    df['job_type_short'] = df['job_type'].replace(job_type_mapping)
    df['deadline_dt'] = pd.to_datetime(df['deadline'], errors='coerce')
    df.dropna(subset=['deadline_dt'], inplace=True)
    df['quarter'] = df['deadline_dt'].dt.to_period('Q').astype(str)
    df['month'] = df['deadline_dt'].dt.strftime('%B')
    df['month_num'] = df['deadline_dt'].dt.month
    df['year'] = df['deadline_dt'].dt.year.astype(str)
    df['price_eur'] = pd.to_numeric(df['price_eur'], errors='coerce').fillna(0)

    all_job_types_short = sorted(df['job_type_short'].unique())
    quarters = sorted(df['quarter'].unique())

    # --- 2. HTML Generation and Helper Functions ---
    hideable_columns = {
        'Revenue vs Goal': 'kpi_card_revenue_vs_goal', 'Automation Ratio Card': 'kpi_card_automation_ratio',
        'Revenue Source Split': 'kpi_card_revenue_split', 'Team Performance Card': 'kpi_card_team_performance',
        'Revenue Goal Card': 'kpi_card_revenue_goal_stacked', 'Total Tasks Card': 'kpi_card_total_tasks_stacked',
        'Total KPI Card': 'kpi_card_total_kpi_stacked', 'Daily Revenue Chart': 'kpi_card_daily_revenue',
        'Engineer Name': 'col_engineer_name',
        'Days Off': 'col_days_off',
        'Idle Time': 'col_idle_time',
        'Performance (Real vs. IPI)': 'col_perf_bar', 'Automation Ratio': 'col_auto_ratio',
        'Basic KPI': 'col_basic_kpi',
        'KPI with IPI': 'col_kpi_ipi', 'Helpdesk Revenue': 'col_helpdesk_revenue', 'Revenue (EUR)': 'col_revenue',
        'Total Jobs': 'col_total_jobs'
    }
    for job_type in all_job_types_short:
        safe_class_suffix = re.sub(r'[^a-zA-Z0-9_-]', '', job_type)
        hideable_columns[job_type] = f"col_job_{safe_class_suffix}"

    hidden_by_default = ['Basic KPI', 'Idle Time', 'KPI with IPI', 'API-Lic', 'Add-Fee', 'DTP-Prev', 'Pre-DTP']
    column_toggle_html = "".join([
        f"<label><input type='checkbox' {'checked' if name not in hidden_by_default else ''} data-col-class='{css_class}' onchange='toggleColumn(this)'> {name}</label>"
        for name, css_class in hideable_columns.items()])

    # Generate Engineer Toggle HTML
    all_engineer_names = sorted([name for name in df['vendor_name'].unique() if
                                 name in le_team_names and name != "LanguageWire Engineers Team"])
    engineer_toggle_html = ""
    for name in all_engineer_names:
        safe_class = f"engineer-row-{re.sub(r'[^a-zA-Z0-9]', '', name).lower()}"
        # User request: Victor Parra García switched off by default
        is_checked = 'checked' if "Victor Parra García" not in name else ''
        engineer_toggle_html += f"<label><input type='checkbox' {is_checked} data-row-class='{safe_class}' onchange='toggleRow(this)'> {name}</label>"

    def generate_donut_card(card_class, title, current_value, goal_value, is_percent=False):
        percentage = (current_value / goal_value) * 100 if goal_value > 0 else 0
        gradient_percentage = min(percentage, 100)
        if is_percent:
            center_text, value_text_1, value_text_2 = f"{current_value:.1f}%", f"{current_value:.1f}%", f"{goal_value:.1f}%"
            legend_label_1, legend_label_2 = "Current Ratio", "Target Ratio"
        else:
            center_text = f"{percentage:.1f}%<span>vs Goal</span>"
            value_text_1, value_text_2 = f"€{current_value:,.2f}", f"€{max(0, goal_value - current_value):,.2f}"
            legend_label_1, legend_label_2 = "Revenue", "Remaining"
        return f"""<div class="kpi-card donut-card {card_class}"><div class="donut-title">{title}</div><div class="donut-chart" style="background: conic-gradient(var(--color-golden) 0% {gradient_percentage:.2f}%, var(--color-ok) {gradient_percentage:.2f}% 100%);"><div class="center-text">{center_text}</div></div><ul class="legend"><li><span class="dot" style="background-color:var(--color-golden)"></span><span class="label-text">{legend_label_1}</span><span class="value-text">{value_text_1}</span></li><li><span class="dot" style="background-color:var(--color-ok)"></span><span class="label-text">{legend_label_2}</span><span class="value-text">{value_text_2}</span></li></ul></div>"""

    def generate_revenue_split_donut(platform_revenue, helpdesk_revenue, card_class=""):
        total_revenue = platform_revenue + helpdesk_revenue
        platform_perc = (platform_revenue / total_revenue) * 100 if total_revenue > 0 else 0
        center_text = f"{platform_perc:.1f}%<span>Platform</span>"
        return f"""<div class="kpi-card donut-card revenue-split-donut-card {card_class}"><div class="donut-title">Revenue Source Split</div><div class="donut-chart" style="background: conic-gradient(var(--color-golden) 0% {platform_perc:.2f}%, var(--color-ok) {platform_perc:.2f}% 100%);"><div class="center-text">{center_text}</div></div><ul class="legend"><li><span class="dot" style="background-color:var(--color-golden)"></span><span class="label-text">Platform</span><span class="value-text">€{platform_revenue:,.2f}</span></li><li><span class="dot" style="background-color:var(--color-ok)"></span><span class="label-text">Helpdesk</span><span class="value-text">€{helpdesk_revenue:,.2f}</span></li></ul></div>"""

    def generate_team_performance_donut(team_perf_percent, real_ipi_val, target_ipi_val, card_class=""):
        gradient_percentage = min((real_ipi_val / target_ipi_val) * 100 if target_ipi_val > 0 else 0, 100)
        center_text = f"{team_perf_percent:.1f}%<span>vs Target</span>"
        return f"""<div class="kpi-card donut-card team-performance-donut-card {card_class}"><div class="donut-title">Team Performance (IPI)</div><div class="donut-chart" style="background: conic-gradient(var(--color-golden) 0% {gradient_percentage:.2f}%, var(--color-ok) {gradient_percentage:.2f}% 100%);"><div class="center-text">{center_text}</div></div><ul class="legend"><li><span class="dot" style="background-color:var(--color-golden)"></span><span class="label-text">Team Real IPI</span><span class="value-text">{real_ipi_val:,.2f}</span></li><li><span class="dot" style="background-color:var(--color-ok)"></span><span class="label-text">Team Target IPI</span><span class="value-text">{target_ipi_val:,.2f}</span></li></ul></div>"""

    def generate_table_rows(data, job_types_list):
        rows_html = ""
        if data.empty: return f"<tr><td colspan='{len(hideable_columns) + len(job_types_list)}'>No LE data available.</td></tr>"
        for vendor_name, row in data.iterrows():
            job_type_tds = "".join([
                f"<td class='{hideable_columns.get(job_type, '')}' data-sort-value='{int(row.get(job_type, 0))}'>{int(row.get(job_type, 0))}</td>"
                for job_type in job_types_list])
            ipi, real_ipi = row.get('ipi_numeric', 0), row.get('real_ipi', 0)
            performance_percent = (real_ipi / ipi) * 100 if ipi > 0 else 0
            bar_color_class = 'perf-bar-good' if performance_percent >= 100 else (
                'perf-bar-ok' if performance_percent >= 80 else 'perf-bar-bad')
            perf_bar_html = f"""<div class="perf-bar-container"><div class="perf-bar-label">Real: {real_ipi:.2f} (Target: {ipi:.2f}) - <strong>{performance_percent:.0f}%</strong></div><div class="perf-bar-track"><div class="perf-bar-value {bar_color_class}" style="width: {min(performance_percent, 120):.2f}%;"></div></div></div>"""

            auto_ratio = row.get('automation_ratio', 0)
            auto_bar_label = f"{auto_ratio:.1f}% Automated"
            auto_bar_html = f"""<div class="perf-bar-container"><div class="perf-bar-label">{auto_bar_label}</div><div class="perf-bar-track"><div class="perf-bar-value auto-bar-value" style="width: {min(auto_ratio, 100):.2f}%;"></div></div></div>"""

            revenue_str, idle_time_str = f"€{row['total_revenue_eur']:,.2f}", f"{row.get('idle_time', 0)}%"
            days_off_str = f"{int(row.get('days_off', 0))}"
            basic_kpi_str, kpi_with_ipi_str = f"€{row.get('basic_kpi', 0):,.2f}", f"€{row.get('kpi_with_ipi', 0):,.2f}"
            helpdesk_revenue_str = f"€{row.get('helpdesk_revenue', 0):,.2f}"

            # Apply engineer-specific class and clear data for Team row
            safe_engineer_class = f"engineer-row-{re.sub(r'[^a-zA-Z0-9]', '', vendor_name).lower()}"
            if vendor_name == "LanguageWire Engineers Team":
                row_class_attr = " class='fixed-row'"
                perf_bar_html, auto_bar_html, basic_kpi_str, kpi_with_ipi_str, idle_time_str, helpdesk_revenue_str, days_off_str = [
                                                                                                                                       ""] * 7
            else:
                row_class_attr = f" class='{safe_engineer_class}'"

            rows_html += f"""<tr{row_class_attr}>
<td class='{hideable_columns['Engineer Name']}' data-sort-value='{vendor_name}'>{vendor_name}</td>
<td class='{hideable_columns['Days Off']}' data-sort-value="{row.get('days_off', -1)}">{days_off_str}</td>
<td class='{hideable_columns['Idle Time']}' data-sort-value="{row.get('idle_time', -1)}">{idle_time_str}</td>
<td class='{hideable_columns['Performance (Real vs. IPI)']}' data-sort-value="{performance_percent}">{perf_bar_html}</td>
<td class='{hideable_columns['Automation Ratio']}' data-sort-value="{auto_ratio}">{auto_bar_html}</td>
<td class='{hideable_columns['Basic KPI']}' data-sort-value="{row.get('basic_kpi', -1)}">{basic_kpi_str}</td>
<td class='{hideable_columns['KPI with IPI']}' data-sort-value="{row.get('kpi_with_ipi', -1)}">{kpi_with_ipi_str}</td>
<td class='{hideable_columns['Helpdesk Revenue']}' data-sort-value="{row.get('helpdesk_revenue', 0)}">{helpdesk_revenue_str}</td>
<td class='col_revenue' data-sort-value="{row['total_revenue_eur']}">{revenue_str}</td>
<td class='col_total_jobs' data-sort-value="{row['total_jobs']}">{int(row['total_jobs'])}</td>{job_type_tds}
</tr>"""

        totals = data.sum(numeric_only=True)
        total_row_html = f"""
            <tr class='total-row fixed-row'>
                <td class='{hideable_columns['Engineer Name']}'><strong>TOTAL</strong></td>
                <td class='{hideable_columns['Days Off']}'></td>
                <td class='{hideable_columns['Idle Time']}'></td>
                <td class='{hideable_columns['Performance (Real vs. IPI)']}'></td>
                <td class='{hideable_columns['Automation Ratio']}'></td>
                <td class='{hideable_columns['Basic KPI']}'>€{totals.get('basic_kpi', 0):,.2f}</td>
                <td class='{hideable_columns['KPI with IPI']}'>€{totals.get('kpi_with_ipi', 0):,.2f}</td>
                <td class='{hideable_columns['Helpdesk Revenue']}'>€{totals.get('helpdesk_revenue', 0):,.2f}</td>
                <td class='col_revenue'>€{totals.get('total_revenue_eur', 0):,.2f}</td>
                <td class='col_total_jobs'>{int(totals.get('total_jobs', 0))}</td>
                {''.join([f"<td class='{hideable_columns.get(job_type, '')}'>{int(totals.get(job_type, 0))}</td>" for job_type in job_types_list])}
            </tr>
        """
        return rows_html + total_row_html

    # --- 3. Main Report Generation Loop ---
    main_nav_buttons_html, main_content_panels_html = "", ""
    for i, quarter in enumerate(quarters):
        quarter_id = f"q_{re.sub(r'[^a-zA-Z0-9]', '', quarter)}"
        is_main_active = i == 0
        main_nav_buttons_html += f"<button class='main-tab-link {'active' if is_main_active else ''}' onclick='openView(event, \"{quarter_id}\", \"main\")'>{quarter}</button>"

        quarter_df, sub_nav_html, sub_panels_html = df[df['quarter'] == quarter].copy(), "", ""
        year_str, q_str = quarter[:4], quarter[4:]
        ipi_mapping = config.get('ipi', {}).get(year_str, {}).get(q_str, {})
        idle_time_mapping = config.get('idle', {}).get(year_str, {}).get(q_str, {})
        days_off_config_year = config.get('days_off', {}).get(year_str, {})
        automated_customers = config.get('automated_customers', {}).get(year_str, {}).get(q_str, [])
        automated_customers_set = {str(c).strip().lower() for c in automated_customers}
        goal_mapping = {f'{year_str}{q}': float(str(val).replace(',', '')) for q, val in
                        config_goals.get(year_str, {}).items()}
        automation_goal_mapping = {f'{year_str}{q}': float(val) for q, val in
                                   automation_goals.get(year_str, {}).items()}
        month_names = sorted(quarter_df['month'].unique(), key=lambda m: datetime.strptime(m, "%B").month)
        sub_views = ['Quarter Overall'] + month_names

        def calculate_actual_basic_kpi(vendor, idle_percent, days_off_val, year, quarter_full_str, month_name_str):
            """Calculates a prorated KPI based on actual business days worked."""
            if pd.isna(idle_percent) or pd.isna(days_off_val) or vendor == "LanguageWire Engineers Team":
                return 0

            # Get engineer-specific working hours ratio
            working_hours_ratio = working_hours_mapping.get(vendor, 1.0)
            if isinstance(working_hours_ratio, dict):
                working_hours_ratio = working_hours_ratio.get(quarter_full_str[4:], 1.0)

            year_num = int(year)
            # Determine period start and end dates
            if month_name_str == 'Quarter Overall':
                q_num = int(quarter_full_str[5:])
                start_date = pd.to_datetime(f'{year_num}-{(q_num - 1) * 3 + 1}-01')
                end_date = start_date + pd.offsets.QuarterEnd(0)
            else:
                month_num = datetime.strptime(month_name_str, "%B").month
                start_date = pd.to_datetime(f'{year_num}-{month_num}-01')
                end_date = start_date + pd.offsets.MonthEnd(0)

            total_business_days = len(pd.bdate_range(start=start_date, end=end_date))
            actual_work_days = max(0, total_business_days - days_off_val)

            # Daily KPI target (assuming 3200 is monthly target for an avg of 21 business days)
            daily_kpi_target = 3200 / 21.0

            period_kpi = daily_kpi_target * actual_work_days * (1 - (idle_percent / 100)) * working_hours_ratio
            return period_kpi

        for j, sub_view in enumerate(sub_views):
            is_sub_active, sub_view_id = j == 0, f"{quarter_id}_{re.sub(r'[^a-zA-Z0-9]', '', sub_view)}"
            sub_nav_html += f"<button class='sub-tab-link {'active' if is_sub_active else ''}' onclick='openView(event, \"{sub_view_id}\", \"sub\", \"{quarter_id}\")'>{sub_view}</button>"

            data_for_view = (
                quarter_df if sub_view == 'Quarter Overall' else quarter_df[quarter_df['month'] == sub_view]).copy()
            sub_panel_content = ""

            if not data_for_view.empty:
                job_type_counts = data_for_view.pivot_table(index='vendor_name', columns='job_type_short', values='id',
                                                            aggfunc='count', fill_value=0)
                summary_agg = data_for_view.groupby('vendor_name').agg(total_revenue_eur=('price_eur', 'sum'),
                                                                       total_jobs=('id', 'count'))
                full_summary = pd.merge(summary_agg, job_type_counts, on='vendor_name', how='left').fillna(0)

                total_platform_revenue_view = full_summary['total_revenue_eur'].sum()
                total_helpdesk_revenue_view = 0
                total_helpdesk_tickets_view = 0
                helpdesk_for_lists = pd.DataFrame()
                helpdesk_for_revenue = pd.DataFrame()

                if not helpdesk_data.empty:
                    # Check if 'close_date' is valid before filtering
                    if 'close_date' in helpdesk_data.columns and not helpdesk_data['close_date'].isna().all():
                        if sub_view == 'Quarter Overall':
                            helpdesk_for_revenue = helpdesk_data[helpdesk_data['quarter'] == quarter]
                        else:
                            helpdesk_for_revenue = helpdesk_data[(helpdesk_data['quarter'] == quarter) & (
                                    helpdesk_data['month_num'] == data_for_view['month_num'].iloc[0])]

                    if not helpdesk_for_revenue.empty:
                        helpdesk_for_revenue_resolved = helpdesk_for_revenue[
                            helpdesk_for_revenue['status'] == 'Resolved']
                        if not helpdesk_for_revenue_resolved.empty:
                            total_helpdesk_revenue_view = helpdesk_for_revenue_resolved['helpdesk_revenue'].sum()
                            helpdesk_summary = helpdesk_for_revenue_resolved.groupby('vendor_name').agg(
                                helpdesk_revenue=('helpdesk_revenue', 'sum')).reset_index()
                            full_summary = full_summary.reset_index().merge(helpdesk_summary, on='vendor_name',
                                                                            how='left').set_index('vendor_name')
                            full_summary['helpdesk_revenue'] = full_summary['helpdesk_revenue'].fillna(0)
                        else:
                            full_summary['helpdesk_revenue'] = 0
                    else:
                        full_summary['helpdesk_revenue'] = 0

                    if sub_view == 'Quarter Overall':
                        helpdesk_for_lists = helpdesk_data[helpdesk_data['creation_quarter'] == quarter]
                    else:
                        helpdesk_for_lists = helpdesk_data[(helpdesk_data['creation_quarter'] == quarter) & (
                                helpdesk_data['creation_month_num'] == data_for_view['month_num'].iloc[0])]
                    total_helpdesk_tickets_view = len(helpdesk_for_lists)
                else:
                    full_summary['helpdesk_revenue'] = 0

                full_summary['idle_time'] = full_summary.index.map(idle_time_mapping.get)
                full_summary['ipi'] = full_summary.index.map(ipi_mapping.get)

                # Aggregate monthly days off for the current view (monthly or quarterly)
                if sub_view == 'Quarter Overall':
                    q_num = int(q_str[1])
                    months_in_quarter = [datetime(2000, (q_num - 1) * 3 + m, 1).strftime('%B') for m in [1, 2, 3]]
                    days_off_for_view = {
                        eng: sum(days_off_config_year.get(m, {}).get(eng, 0) for m in months_in_quarter)
                        for eng in full_summary.index
                    }
                else:
                    days_off_for_view = {
                        eng: days_off_config_year.get(sub_view, {}).get(eng, 0) for eng in full_summary.index
                    }
                full_summary['days_off'] = full_summary.index.map(days_off_for_view).fillna(0)

                full_summary['basic_kpi'] = [
                    calculate_actual_basic_kpi(vendor, full_summary.loc[vendor, 'idle_time'],
                                               full_summary.loc[vendor, 'days_off'], year_str, quarter, sub_view) for
                    vendor in full_summary.index]

                full_summary['ipi_numeric'] = pd.to_numeric(full_summary['ipi'], errors='coerce').fillna(1.0)
                full_summary['kpi_with_ipi'] = full_summary['basic_kpi'] * full_summary['ipi_numeric']
                full_summary['real_ipi'] = (
                        (full_summary['total_revenue_eur'] + full_summary['helpdesk_revenue']) / full_summary[
                    'basic_kpi']).replace([np.inf, -np.inf], 0).fillna(0)
                automated_df = data_for_view[data_for_view['entity'].str.lower().isin(automated_customers_set)]
                automated_revenue_per_engineer = automated_df.groupby('vendor_name')['price_eur'].sum()
                full_summary['automated_revenue'] = full_summary.index.map(automated_revenue_per_engineer).fillna(0)
                full_summary['automation_ratio'] = (full_summary['automated_revenue'] / full_summary[
                    'total_revenue_eur']).replace([np.inf, -np.inf], 0).fillna(0) * 100
                le_summary = pd.concat([full_summary[full_summary.index != "LanguageWire Engineers Team"].sort_values(
                    'total_revenue_eur', ascending=False),
                    full_summary[full_summary.index == "LanguageWire Engineers Team"]])

                sv_total_revenue = le_summary['total_revenue_eur'].sum() + le_summary.get('helpdesk_revenue', 0).sum()
                sv_total_jobs = le_summary['total_jobs'].sum()
                grand_total_tasks = sv_total_jobs + total_helpdesk_tickets_view

                revenue_goal = goal_mapping.get(quarter, 0) / (1 if sub_view == 'Quarter Overall' else 3)
                automation_goal = automation_goal_mapping.get(quarter, 0)
                total_automated_revenue = \
                    data_for_view[data_for_view['entity'].str.lower().isin(automated_customers_set)]['price_eur'].sum()
                automation_ratio = (
                                           total_automated_revenue / total_platform_revenue_view) * 100 if total_platform_revenue_view > 0 else 0

                summary_for_perf = le_summary[le_summary.index != 'LanguageWire Engineers Team']
                total_actual_revenue = (
                        summary_for_perf['total_revenue_eur'] + summary_for_perf.get('helpdesk_revenue', 0)).sum()
                total_basic_kpi_sum = summary_for_perf['basic_kpi'].sum()
                total_target_revenue = summary_for_perf['kpi_with_ipi'].sum()

                team_real_ipi = total_actual_revenue / total_basic_kpi_sum if total_basic_kpi_sum > 0 else 0
                team_target_ipi = total_target_revenue / total_basic_kpi_sum if total_basic_kpi_sum > 0 else 0
                team_performance_percent = (team_real_ipi / team_target_ipi) * 100 if team_target_ipi > 0 else 0

                revenue_donut_html = generate_donut_card(f"revenue-donut-card {hideable_columns['Revenue vs Goal']}",
                                                         "Revenue vs Goal", sv_total_revenue, revenue_goal, False)
                automation_donut_html = generate_donut_card(
                    f"automation-donut-card {hideable_columns['Automation Ratio Card']}", "Automation Ratio",
                    automation_ratio, automation_goal, True)
                revenue_split_donut_html = generate_revenue_split_donut(total_platform_revenue_view,
                                                                        total_helpdesk_revenue_view,
                                                                        card_class=hideable_columns[
                                                                            'Revenue Source Split'])
                team_performance_donut_html = generate_team_performance_donut(team_performance_percent, team_real_ipi,
                                                                              team_target_ipi,
                                                                              card_class=hideable_columns[
                                                                                  'Team Performance Card'])

                kpi_goal_html = f'<div class="kpi-card kpi-goal-card {hideable_columns["Revenue Goal Card"]}"><div class="label">Revenue Goal</div><div class="value">€{revenue_goal:,.2f}</div></div>'
                kpi_jobs_html = f'<div class="kpi-card kpi-jobs-card {hideable_columns["Total Tasks Card"]}"><div class="label">Total Tasks Processed</div><div class="value">{int(grand_total_tasks):,}</div><p class="card-subtitle">Jobs: {int(sv_total_jobs):,} | Tickets: {int(total_helpdesk_tickets_view):,}</p></div>'
                total_kpi_card_html = f'<div class="kpi-card kpi-total-ipi-card {hideable_columns["Total KPI Card"]}"><div class="label">Total KPI w/IPI</div><div class="value">€{total_target_revenue:,.2f}</div></div>'

                overview_donuts_html = f'<div class="overview-grid">{revenue_donut_html}{automation_donut_html}{revenue_split_donut_html}{team_performance_donut_html}</div>'
                kpi_stack_html = f'<div class="kpi-stack-grid">{kpi_goal_html}{kpi_jobs_html}{total_kpi_card_html}</div>'

                # --- START: Daily Revenue Progress Chart ---
                daily_chart_html = ''
                if revenue_goal > 0:
                    # Calculate num_workdays based on the fixed calendar period (Quarter or Month)
                    year = int(quarter[:4])
                    q_num = int(quarter[5:])
                    if sub_view == 'Quarter Overall':
                        period_start = pd.to_datetime(f'{year}-{(q_num - 1) * 3 + 1}-01')
                        period_end = period_start + pd.offsets.QuarterEnd(1)
                    else:  # It's a month
                        period_start = datetime.strptime(f"{sub_view} {year}", "%B %Y")
                        period_end = period_start + pd.offsets.MonthEnd(1)

                    num_workdays = len(pd.bdate_range(start=period_start, end=period_end))

                    # Determine the date range of actual data for chart visualization
                    start_date, end_date = pd.NaT, pd.NaT
                    if not data_for_view.empty:
                        start_date = data_for_view['deadline_dt'].min()
                        end_date = data_for_view['deadline_dt'].max()

                    if not helpdesk_for_revenue.empty:
                        # Safely get dates only if close_date exists
                        if 'close_date' in helpdesk_for_revenue.columns and not helpdesk_for_revenue[
                            'close_date'].isna().all():
                            start_date_hd = helpdesk_for_revenue['close_date'].min()
                            end_date_hd = helpdesk_for_revenue['close_date'].max()
                            if pd.isna(start_date) or start_date_hd < start_date: start_date = start_date_hd
                            if pd.isna(end_date) or end_date_hd > end_date: end_date = end_date_hd

                    # Proceed if there is data to display and workdays in the period
                    if pd.notna(start_date) and pd.notna(end_date) and num_workdays > 0:
                        daily_goal = revenue_goal / num_workdays

                        platform_daily = data_for_view[data_for_view['deadline_dt'].dt.dayofweek < 5].groupby(
                            data_for_view['deadline_dt'].dt.date)['price_eur'].sum()

                        daily_revenue = platform_daily

                        if not helpdesk_for_revenue.empty:
                            if 'close_date' in helpdesk_for_revenue.columns and not helpdesk_for_revenue[
                                'close_date'].isna().all():
                                hd_for_rev_daily = helpdesk_for_revenue.dropna(subset=['close_date'])
                                helpdesk_daily = \
                                hd_for_rev_daily[hd_for_rev_daily['close_date'].dt.dayofweek < 5].groupby(
                                    hd_for_rev_daily['close_date'].dt.date)['helpdesk_revenue'].sum()
                                daily_revenue = daily_revenue.add(helpdesk_daily, fill_value=0)

                        # The chart's x-axis is built from the actual data's date range
                        chart_x_axis_days = pd.bdate_range(start=start_date, end=end_date)
                        daily_revenue = daily_revenue.reindex(chart_x_axis_days.date, fill_value=0)

                        chart_bars_html = ''
                        for day, revenue in daily_revenue.items():
                            percent_of_goal = (revenue / daily_goal) * 100 if daily_goal > 0 else 0
                            bar_height_percent = min(100, (revenue / daily_goal) * 50)
                            bar_class = 'daily-bar-over' if revenue >= daily_goal else ''
                            percent_text = f"<span class='over'>{percent_of_goal - 100:.0f}% over</span>" if revenue >= daily_goal else f"<span class='under'>{100 - percent_of_goal:.0f}% left</span>"
                            chart_bars_html += f"""<div class="daily-bar-wrapper"><div class="daily-bar {bar_class}" style="height: {bar_height_percent}%;"><div class="bar-percentage">{percent_text}</div></div><div class="bar-date-label">{pd.to_datetime(day).strftime('%a %d-%b')}</div></div>"""

                        total_content_width = (len(chart_x_axis_days) * 55) + ((len(chart_x_axis_days) - 1) * 5)
                        daily_chart_class = hideable_columns['Daily Revenue Chart']
                        daily_chart_html = f"""<div class="daily-chart-card {daily_chart_class}"><h3>Daily Revenue Progress (€{daily_goal:,.2f} goal/day, {num_workdays} days)</h3><div class="daily-chart-container"><div class="daily-chart-content" style="min-width: {total_content_width}px;"><div class="daily-goal-line"></div>{chart_bars_html}</div></div></div>"""
                # --- END: Daily Revenue Progress Chart ---

                overview_section_html = f"{overview_donuts_html}{kpi_stack_html}{daily_chart_html}"

                fixed_headers = ['Engineer Name', 'Days Off', 'Idle Time', 'Performance (Real vs. IPI)',
                                 'Automation Ratio', 'Basic KPI', 'KPI with IPI', 'Helpdesk Revenue',
                                 'Revenue (EUR)', 'Total Jobs']
                team_performance_headers = fixed_headers + all_job_types_short

                team_table_header_html = "".join([
                    f'<th class="{hideable_columns.get(header, "")}" onclick="sortTable(\'performance-table-{sub_view_id}\', {i})">{header} ⇅</th>'
                    for i, header in enumerate(team_performance_headers)])

                team_table_content = f"<div class='filter-container'><input onkeyup=\"filterTable(this, 'performance-table-{sub_view_id}', 0)\" placeholder='Filter by Engineer...'></div><div class='table-container'><table id='performance-table-{sub_view_id}'><thead><tr>{team_table_header_html}</tr></thead><tbody>{generate_table_rows(le_summary, all_job_types_short)}</tbody></table></div>"
                team_table_html = f"""
                <details class="collapsible-card" open>
                    <summary><h3>Localization Engineering Team Performance</h3></summary>
                    <div class="collapsible-content">
                        {team_table_content}
                    </div>
                </details>
                """

                zero_price_df = data_for_view[data_for_view['price_eur'] == 0][
                    ['id', 'job_type', 'price_eur', 'vendor_name', 'entity']]
                zero_price_rows_html = "".join([
                    f"""<tr><td><a href="https://platform.languagewire.com/Job/{row['id']}" target="_blank">{row['id']}</a></td><td>{row['job_type']}</td><td>€{row['price_eur']:.2f}</td><td>{row['vendor_name']}</td><td>{row['entity']}</td></tr>"""
                    for _, row in zero_price_df.iterrows()])
                zero_price_section_html = f"""<details class="collapsible-card"><summary><h3>Jobs With Zero Price</h3></summary><div class="collapsible-content"><div class="filter-container"><input onkeyup="filterTable(this, 'zero-price-table-{sub_view_id}', 0)" placeholder="Filter by ID..."><input onkeyup="filterTable(this, 'zero-price-table-{sub_view_id}', 1)" placeholder="Filter by Type..."><input onkeyup="filterTable(this, 'zero-price-table-{sub_view_id}', 3)" placeholder="Filter by Engineer..."><input onkeyup="filterTable(this, 'zero-price-table-{sub_view_id}', 4)" placeholder="Filter by Customer..."></div><div class="table-container"><table id="zero-price-table-{sub_view_id}"><thead><tr><th onclick="sortTable('zero-price-table-{sub_view_id}', 0)">Job ID ⇅</th><th onclick="sortTable('zero-price-table-{sub_view_id}', 1)">Job Type ⇅</th><th onclick="sortTable('zero-price-table-{sub_view_id}', 2)">Price ⇅</th><th onclick="sortTable('zero-price-table-{sub_view_id}', 3)">Engineer ⇅</th><th onclick="sortTable('zero-price-table-{sub_view_id}', 4)">Customer ⇅</th></tr></thead><tbody>{zero_price_rows_html}</tbody></table></div></div></details>"""

                conditions = [(data_for_view['job_type'] == job_type) & (data_for_view['price_eur'] < price) & (
                        data_for_view['price_eur'] != 0) for job_type, price in standard_prices.items()]
                wrong_price_df = pd.DataFrame()
                if conditions:
                    wrong_price_mask = np.logical_or.reduce(conditions)
                    sophos_exclusion_mask = ~((data_for_view['entity'].str.lower() == 'sophos limited') & (
                            data_for_view['job_type'] == 'Source File Preparation') & (
                                                      data_for_view['price_eur'] >= 5))
                    final_mask = wrong_price_mask & sophos_exclusion_mask
                    wrong_price_df = data_for_view[final_mask][
                        ['id', 'job_type', 'price_eur', 'vendor_name', 'entity']]

                wrong_price_rows_html = "".join([
                    f"""<tr><td><a href="https://platform.languagewire.com/Job/{row['id']}" target="_blank">{row['id']}</a></td><td>{row['job_type']}</td><td>€{row['price_eur']:.2f}</td><td>{row['vendor_name']}</td><td>{row['entity']}</td></tr>"""
                    for _, row in wrong_price_df.iterrows()])
                wrong_price_section_html = f"""<details class="collapsible-card"><summary><h3>Jobs With Wrong Price</h3></summary><div class="collapsible-content"><div class="filter-container"><input onkeyup="filterTable(this, 'wrong-price-table-{sub_view_id}', 0)" placeholder="Filter by ID..."><input onkeyup="filterTable(this, 'wrong-price-table-{sub_view_id}', 1)" placeholder="Filter by Type..."><input onkeyup="filterTable(this, 'wrong-price-table-{sub_view_id}', 3)" placeholder="Filter by Engineer..."><input onkeyup="filterTable(this, 'wrong-price-table-{sub_view_id}', 4)" placeholder="Filter by Customer..."></div><div class="table-container"><table id="wrong-price-table-{sub_view_id}"><thead><tr><th onclick="sortTable('wrong-price-table-{sub_view_id}', 0)">Job ID ⇅</th><th onclick="sortTable('wrong-price-table-{sub_view_id}', 1)">Job Type ⇅</th><th onclick="sortTable('wrong-price-table-{sub_view_id}', 2)">Price ⇅</th><th onclick="sortTable('wrong-price-table-{sub_view_id}', 3)">Engineer ⇅</th><th onclick="sortTable('wrong-price-table-{sub_view_id}', 4)">Customer ⇅</th></tr></thead><tbody>{wrong_price_rows_html}</tbody></table></div></div></details>"""

                pending_tickets_html = ""
                if not helpdesk_for_lists.empty:
                    pending_mask = (helpdesk_for_lists['status'] != 'Resolved') | (
                            helpdesk_for_lists['time_spent'] == '00:00:00') | (
                                       pd.isna(helpdesk_for_lists['close_date']))
                    pending_df = helpdesk_for_lists[pending_mask].copy()
                    pending_rows_html = "".join([
                        f"""<tr><td><a href="{row['url']}" target="_blank">{row['ticket_id']}</a></td><td>{row['subject']}</td><td>{row['status']}</td><td>{row['time_spent']}</td><td>{'Yes' if pd.notna(row['close_date']) else 'No'}</td><td>{row['vendor_name']}</td></tr>"""
                        for _, row in pending_df.iterrows()])
                    pending_tickets_html = f"""<details class="collapsible-card"><summary><h3>Pending Helpdesk Tickets</h3></summary><div class="collapsible-content"><div class="filter-container"><input onkeyup="filterTable(this, 'pending-tickets-table-{sub_view_id}', 0)" placeholder="Filter by Ticket ID..."><input onkeyup="filterTable(this, 'pending-tickets-table-{sub_view_id}', 1)" placeholder="Filter by Subject..."><input onkeyup="filterTable(this, 'pending-tickets-table-{sub_view_id}', 2)" placeholder="Filter by Status..."><input onkeyup="filterTable(this, 'pending-tickets-table-{sub_view_id}', 4)" placeholder="Filter by Closed (Yes/No)..."><input onkeyup="filterTable(this, 'pending-tickets-table-{sub_view_id}', 5)" placeholder="Filter by Engineer..."></div><div class="table-container"><table id="pending-tickets-table-{sub_view_id}"><thead><tr><th onclick="sortTable('pending-tickets-table-{sub_view_id}', 0)">Ticket ID ⇅</th><th onclick="sortTable('pending-tickets-table-{sub_view_id}', 1)">Subject ⇅</th><th onclick="sortTable('pending-tickets-table-{sub_view_id}', 2)">Status ⇅</th><th onclick="sortTable('pending-tickets-table-{sub_view_id}', 3)">Time Spent ⇅</th><th onclick="sortTable('pending-tickets-table-{sub_view_id}', 4)">Closed ⇅</th><th onclick="sortTable('pending-tickets-table-{sub_view_id}', 5)">Engineer ⇅</th></tr></thead><tbody>{pending_rows_html}</tbody></table></div></div></details>"""

                def generate_ranking_columns(df, col, is_money, automated_customers_lookup_set):
                    sorted_df, cols_html = df.sort_values(col, ascending=False), ""
                    if sorted_df.empty: return ""
                    header_html = f'<li class="ranking-header-item"><span>Customer</span><span>{"Revenue" if is_money else "Jobs"}</span><span>Auto</span></li>'
                    for chunk in np.array_split(sorted_df, 4):
                        if chunk.empty: continue
                        list_html = header_html
                        for entity, row in chunk.iterrows():
                            value = f"€{row[col]:,.2f}" if is_money else f"{int(row[col])} jobs"
                            is_automated = str(entity).lower() in automated_customers_lookup_set
                            automation_class, emoji = ('automated', '✅') if is_automated else (
                                'not-automated', '❌')
                            list_html += f"<li class='{automation_class}'><span>{entity}</span><span>{value}</span><span class='emoji-cell'>{emoji}</span></li>"
                        cols_html += f'<ul class="ranking-list">{list_html}</ul>'
                    return cols_html

                money_cols_html = generate_ranking_columns(
                    data_for_view.groupby('entity').agg(total_revenue=('price_eur', 'sum')), 'total_revenue',
                    True,
                    automated_customers_set)
                jobs_cols_html = generate_ranking_columns(
                    data_for_view.groupby('entity').agg(total_jobs=('id', 'count')), 'total_jobs', False,
                    automated_customers_set)
                ranking_controls_html = f"""<div class="ranking-controls"><nav class="sub-tab-nav"><button class="sub-tab-link active" onclick="toggleRankingView(event, 'by-money', 'ranking_{sub_view_id}')">By Money</button><button class="sub-tab-link" onclick="toggleRankingView(event, 'by-jobs', 'ranking_{sub_view_id}')">By Jobs</button></nav><nav class="sub-tab-nav"><button class="sub-tab-link active" onclick="filterRanking(event, 'all', 'ranking_{sub_view_id}')">All</button><button class="sub-tab-link" onclick="filterRanking(event, 'automated', 'ranking_{sub_view_id}')">Automated</button><button class="sub-tab-link" onclick="filterRanking(event, 'not-automated', 'ranking_{sub_view_id}')">Not Automated</button></nav></div>"""
                ranking_card_html = f"""<div id="ranking_{sub_view_id}" class="ranking-card"><div class="ranking-content by-money">{money_cols_html}</div><div class="ranking-content by-jobs" style="display:none;">{jobs_cols_html}</div></div>"""
                customer_ranking_section_html = f"""<details class="collapsible-card"><summary><h3>Customer Ranking</h3></summary><div class="collapsible-content">{ranking_controls_html}{ranking_card_html}</div></details>"""

                all_jobs_rows_html = "".join([
                    f"""<tr><td><a href="https://platform.languagewire.com/Job/{row['id']}" target="_blank">{row['id']}</a></td><td>{row['job_type']}</td><td>€{row['price_eur']:.2f}</td><td>{row['vendor_name']}</td><td>{row['entity']}</td><td>{row['deadline_dt'].strftime('%Y-%m-%d')}</td></tr>"""
                    for _, row in data_for_view.iterrows()])
                all_jobs_section_html = f"""<details class="collapsible-card"><summary><h3>All Platform Jobs List</h3></summary><div class="collapsible-content"><div class="filter-container"><input onkeyup="filterTable(this, 'all-jobs-table-{sub_view_id}', 0)" placeholder="Filter by ID..."><input onkeyup="filterTable(this, 'all-jobs-table-{sub_view_id}', 1)" placeholder="Filter by Type..."><input onkeyup="filterTable(this, 'all-jobs-table-{sub_view_id}', 3)" placeholder="Filter by Engineer..."><input onkeyup="filterTable(this, 'all-jobs-table-{sub_view_id}', 4)" placeholder="Filter by Customer..."><input onkeyup="filterTable(this, 'all-jobs-table-{sub_view_id}', 5)" placeholder="Filter by Date (YYYY-MM-DD)..."></div><div class="table-container"><table id="all-jobs-table-{sub_view_id}"><thead><tr><th onclick="sortTable('all-jobs-table-{sub_view_id}', 0)">Job ID ⇅</th><th onclick="sortTable('all-jobs-table-{sub_view_id}', 1)">Job Type ⇅</th><th onclick="sortTable('all-jobs-table-{sub_view_id}', 2)">Price ⇅</th><th onclick="sortTable('all-jobs-table-{sub_view_id}', 3)">Engineer ⇅</th><th onclick="sortTable('all-jobs-table-{sub_view_id}', 4)">Customer ⇅</th><th onclick="sortTable('all-jobs-table-{sub_view_id}', 5)">Date ⇅</th></tr></thead><tbody>{all_jobs_rows_html}</tbody></table></div></div></details>"""

                all_tickets_section_html = ""
                if not helpdesk_for_lists.empty:
                    all_tickets_rows_html = "".join([
                        f"""<tr><td><a href="{row['url']}" target="_blank">{row['ticket_id']}</a></td><td>{row['subject']}</td><td>{row['status']}</td><td>{row['time_spent']}</td><td>{'Yes' if pd.notna(row['close_date']) else 'No'}</td><td>{row['vendor_name']}</td><td>{row['creation_date'].strftime('%Y-%m-%d')}</td></tr>"""
                        for _, row in helpdesk_for_lists.iterrows()])
                    all_tickets_section_html = f"""
                    <details class="collapsible-card">
                        <summary><h3>All Helpdesk Tickets List</h3></summary>
                        <div class="collapsible-content">
                            <div class="filter-container">
                                <input onkeyup="filterTable(this, 'all-tickets-table-{sub_view_id}', 0)" placeholder="Filter by Ticket ID...">
                                <input onkeyup="filterTable(this, 'all-tickets-table-{sub_view_id}', 1)" placeholder="Filter by Subject...">
                                <input onkeyup="filterTable(this, 'all-tickets-table-{sub_view_id}', 2)" placeholder="Filter by Status...">
                                <input onkeyup="filterTable(this, 'all-tickets-table-{sub_view_id}', 4)" placeholder="Filter by Closed (Yes/No)...">
                                <input onkeyup="filterTable(this, 'all-tickets-table-{sub_view_id}', 5)" placeholder="Filter by Engineer...">
                                <input onkeyup="filterTable(this, 'all-tickets-table-{sub_view_id}', 6)" placeholder="Filter by Date (YYYY-MM-DD)...">
                            </div>
                            <div class="table-container">
                                <table id="all-tickets-table-{sub_view_id}">
                                    <thead>
                                        <tr>
                                            <th onclick="sortTable('all-tickets-table-{sub_view_id}', 0)">Ticket ID ⇅</th>
                                            <th onclick="sortTable('all-tickets-table-{sub_view_id}', 1)">Subject ⇅</th>
                                            <th onclick="sortTable('all-tickets-table-{sub_view_id}', 2)">Status ⇅</th>
                                            <th onclick="sortTable('all-tickets-table-{sub_view_id}', 3)">Time Spent ⇅</th>
                                            <th onclick="sortTable('all-tickets-table-{sub_view_id}', 4)">Closed ⇅</th>
                                            <th onclick="sortTable('all-tickets-table-{sub_view_id}', 5)">Engineer ⇅</th>
                                            <th onclick="sortTable('all-tickets-table-{sub_view_id}', 6)">Date ⇅</th>
                                        </tr>
                                    </thead>
                                    <tbody>{all_tickets_rows_html}</tbody>
                                </table>
                            </div>
                        </div>
                    </details>
                    """

                sub_panel_content = f"<h2>{sub_view} Performance ({quarter})</h2>{overview_section_html}{team_table_html}{zero_price_section_html}{wrong_price_section_html}{pending_tickets_html}{customer_ranking_section_html}{all_jobs_section_html}{all_tickets_section_html}"
            else:
                sub_panel_content = f"<h2>No data available for {sub_view} in {quarter}</h2>"
            sub_panels_html += f"<div id='{sub_view_id}' class='sub-tab-content' style='display: {'block' if is_sub_active else 'none'};'>{sub_panel_content}</div>"

        main_content_panels_html += f"""<div id="{quarter_id}" class="main-tab-content" style="display: {'block' if is_main_active else 'none'};"><nav class="sub-tab-nav">{sub_nav_html}</nav><div class="sub-tab-panels-container">{sub_panels_html}</div></div>"""

    # --- 4. Final HTML Assembly ---
    html_template = f"""
    <!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Localization Engineering KPI Report</title>
    <link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{ --bg-color: #f8f9fa; --card-bg: #FFFFFF; --text-color: #040A1E; --muted-text: #667085; --border-color: #eaecf0; --shadow-color: rgba(16, 24, 40, 0.05); --header-bg: #f9fafb; --row-hover-bg: #f5faff; --color-golden: #537FFF; --color-good: #12B76A; --color-ok: #FE8523; --color-bad: #F04438; }}
        @media (prefers-color-scheme: dark) {{ :root {{ --bg-color: #040A1E; --card-bg: #1B243D; --text-color: #FFFFFF; --muted-text: #98A2B3; --border-color: #344054; --shadow-color: rgba(0, 0, 0, 0.2); --header-bg: #040A1E; --row-hover-bg: #2d3a4c; }} }}
        * {{ box-sizing: border-box; }} body {{ font-family: 'Inter', sans-serif; margin: 0; background-color: var(--bg-color); color: var(--text-color); font-size: 14px;}}
        .container {{ max-width: 100%; margin: 0 auto; padding: 20px 40px; }}
        .report-header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px;}}
        .report-header h1 {{ font-size: 28px; font-weight: 700; margin: 0; }} .report-header p {{ font-size: 14px; color: var(--muted-text); margin-top: 8px; line-height: 1.6;}}
        .export-button {{ background-color: var(--color-golden); color: #FFFFFF; border: none; padding: 10px 20px; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; transition: background-color 0.2s; }}
        .export-button:hover {{ background-color: #4565D2; }}
        h2 {{ font-size: 20px; font-weight: 700; margin: 40px 0 20px 0; border-bottom: 1px solid var(--border-color); padding-bottom: 10px; }}
        h3 {{ font-size: 16px; font-weight: 600; margin: 30px 0 15px 0; }}
        .kpi-card {{ display: flex; flex-direction: column; justify-content: center; background: var(--card-bg); padding: 24px; border-radius: 12px; border: 1px solid var(--border-color); box-shadow: 0 1px 2px var(--shadow-color); }}
        .kpi-card .label {{ font-size: 14px; font-weight: 500; color: var(--muted-text); margin-bottom: 8px; }} .kpi-card .value {{ font-size: 32px; font-weight: 700; color: var(--text-color); }}
        .kpi-jobs-card .value {{ margin-bottom: 5px; }} .card-subtitle {{ font-size: 13px; color: var(--muted-text); margin: 0; font-weight: 400; }}
        .table-container {{ background: var(--card-bg); border-radius: 12px; border: 1px solid var(--border-color); box-shadow: 0 1px 2px var(--shadow-color); overflow-x: auto; margin-top: 15px; }}
        table {{ width: 100%; border-collapse: collapse; }} th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--border-color); vertical-align: middle; white-space: nowrap; }}
        th {{ background-color: var(--header-bg); font-weight: 600; color: var(--muted-text); font-size: 12px; }}
        th[onclick] {{ cursor: pointer; }} td strong {{ font-weight: 700;}} tbody tr:last-child td {{ border-bottom: none; }} tbody tr:hover:not(.fixed-row) {{ background-color: var(--row-hover-bg); }}
        .total-row td {{ font-weight: 700; border-top: 2px solid var(--border-color); background-color: var(--header-bg); }}
        td a {{ color: var(--color-golden); text-decoration: none; }} td a:hover {{ text-decoration: underline; }}
        th:not(:first-child), td:not(:first-child) {{ text-align: right; }}
        .main-tab-nav {{ border: 1px solid var(--border-color); border-radius: 10px; margin: 20px 0; display: inline-flex; overflow: hidden; box-shadow: 0 1px 2px var(--shadow-color); flex-wrap: wrap; }}
        .main-tab-nav button {{ background-color: var(--card-bg); border: none; border-right: 1px solid var(--border-color); padding: 14px 24px; font-size: 16px; font-weight: 500; color: var(--muted-text); transition: all 0.2s ease; cursor: pointer; }}
        .main-tab-nav button:last-child {{ border-right: none; }}
        .main-tab-nav button.active {{ background-color: var(--color-golden); color: #FFFFFF; font-weight: 600; }}
        .main-tab-nav button:hover:not(.active) {{ background-color: var(--row-hover-bg); }}
        .main-tab-content, .sub-tab-content {{ display: none; animation: fadeIn 0.5s; }} @keyframes fadeIn {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
        .sub-tab-nav {{ border: 1px solid var(--border-color); border-radius: 8px; margin: 0; display: inline-flex; overflow: hidden; flex-wrap: wrap; }}
        .sub-tab-nav button {{ background: var(--card-bg); border: none; outline: none; cursor: pointer; padding: 10px 16px; font-size: 14px; font-weight: 500; color: var(--muted-text); transition: all 0.3s ease; border-right: 1px solid var(--border-color); }}
        .sub-tab-nav button:last-child {{ border-right: none; }}
        .sub-tab-nav button:hover {{ background-color: var(--row-hover-bg); }} .sub-tab-nav button.active {{ background-color: var(--color-golden); color: #FFFFFF; font-weight: 600; }}
        .overview-grid {{ display: grid; gap: 20px; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }}
        .kpi-stack-grid {{ display: grid; gap: 20px; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); margin-top: 20px; }}
        .donut-card {{ display: flex; flex-direction: column; justify-content: space-between; }}
        .donut-title {{ font-size: 16px; font-weight: 600; color: var(--text-color); margin-bottom: 15px; text-align: center; }}
        .donut-chart {{ position: relative; width: 180px; height: 180px; border-radius: 50%; margin: 0 auto; flex-shrink: 0;}}
        .donut-chart .center-text {{ position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); text-align: center; font-weight: 700; font-size: 28px; }}
        .donut-chart .center-text span {{ display: block; font-size: 14px; font-weight: 500; color: var(--muted-text); }}
        .donut-chart::before {{ content: ''; position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); width: 120px; height: 120px; background: var(--card-bg); border-radius: 50%; transition: background-color 0.3s; }}
        .legend {{ list-style: none; padding: 0; margin: 20px 0 0; width: 100%; }}
        .legend li {{ display: flex; align-items: center; margin-bottom: 16px; font-size: 16px; }} .legend li:last-child {{ margin-bottom: 0; }}
        .legend .dot {{ width: 12px; height: 12px; border-radius: 50%; margin-right: 12px; flex-shrink: 0; }}
        .legend .label-text {{ color: var(--muted-text); font-size: 15px; }} .legend .value-text {{ font-weight: 600; white-space: nowrap; margin-left: auto; padding-left: 15px; }}
        .perf-bar-container {{ width: 160px; margin-left: auto; }}
        .perf-bar-label {{ font-size: 11px; color: var(--muted-text); margin-bottom: 4px; }}
        .perf-bar-track {{ width: 100%; height: 18px; background-color: var(--border-color); border-radius: 9px; overflow: hidden; }}
        .perf-bar-value {{ height: 100%; border-radius: 9px; transition: width 0.5s ease-in-out;}}
        .perf-bar-good {{ background-color: var(--color-good); }} .perf-bar-ok {{ background-color: var(--color-golden); }} .perf-bar-bad {{ background-color: var(--color-ok); }}
        .auto-bar-value {{ background-color: var(--color-golden); }}

        /* --- MODIFIED: Styles for Toggle Bars --- */
        .toggle-container {{ display: flex; flex-direction: column; gap: 10px; margin-bottom: 20px; }}
        .column-toggle, .engineer-toggle {{ background-color: var(--card-bg); padding: 10px 20px; border-radius: 8px; border: 1px solid var(--border-color); font-size: 12px; display: flex; flex-wrap: wrap; gap: 15px; }}
        /* --- END MODIFIED --- */

        .column-toggle label, .engineer-toggle label {{ cursor: pointer; display: flex; align-items: center; gap: 5px; }}
        .ranking-card {{ background-color: var(--card-bg); border: 1px solid var(--border-color); border-radius: 12px; padding: 24px; margin-top: 20px; }}
        .ranking-controls {{ display: flex; gap: 20px; align-items: center; flex-wrap: wrap; }}
        .ranking-content {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px;}} .ranking-list {{ list-style: none; padding: 0; margin: 0; }}
        .ranking-list li {{ display: grid; grid-template-columns: 1fr auto 50px; gap: 10px; align-items: center; padding: 8px 0; font-size: 13px; border-bottom: 1px solid var(--border-color); }}
        .ranking-list li.ranking-header-item {{ font-weight: 600; color: var(--muted-text); border-bottom-width: 2px; }}
        .ranking-list li.ranking-header-item span:nth-child(3) {{ text-align: center; }}
        .ranking-list li:last-child {{ border-bottom: none; }} .ranking-list li span:first-child {{ font-weight: 500; padding-right: 10px; }}
        .ranking-list li span:nth-child(2) {{ color: var(--muted-text); font-weight: 500; text-align: right; }}
        .ranking-list li .emoji-cell {{ text-align: center; font-size: 16px; }}
        .filter-container {{ display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 15px; }}
        .filter-container input {{ flex: 1 1 180px; padding: 8px 12px; border: 1px solid var(--border-color); border-radius: 6px; background-color: var(--card-bg); color: var(--text-color); }}
        #pending-tickets-table-undefined th:not(:first-child), #pending-tickets-table-undefined td:not(:first-child) {{ text-align: left; }}
        [id^='all-tickets-table'] th, [id^='all-tickets-table'] td {{ text-align: left !important; }}
        .collapsible-card {{ background: transparent; border: none; padding: 0; margin-top: 20px; box-shadow: none; }}
        .collapsible-card summary {{ cursor: pointer; font-weight: 600; list-style: none; padding: 10px 0; border-bottom: 1px solid var(--border-color); }}
        .collapsible-card summary::-webkit-details-marker {{ display: none; }}
        .collapsible-card summary h3 {{ display: inline-block; margin: 0; font-size: 16px; }}
        .collapsible-card summary::before {{ content: '▶'; margin-right: 10px; font-size: 12px; display: inline-block; transition: transform 0.2s; }}
        .collapsible-card[open] > summary::before {{ transform: rotate(90deg); }}
        .collapsible-content {{ padding-top: 20px; }}
        .section-description {{ font-size: 12px; color: var(--muted-text); margin-top: 0; margin-bottom: 15px; }}

        /* Styles for Daily Revenue Chart */
        .daily-chart-card {{ background: var(--card-bg); padding: 24px; border-radius: 12px; border: 1px solid var(--border-color); box-shadow: 0 1px 2px var(--shadow-color); margin-top: 20px; }}
        .daily-chart-card h3 {{ margin: 0 0 15px; }}
        .daily-chart-container {{ position: relative; overflow-x: auto; background-color: var(--header-bg); border: 1px solid var(--border-color); border-radius: 8px; padding: 20px 0 10px 0; min-height: 200px; }}
        .daily-chart-content {{ position: relative; display: flex; align-items: stretch; gap: 5px; height: 160px; }}
        .daily-goal-line {{ position: absolute; left: 0; width: 100%; bottom: 60%; border-top: 1.5px dashed var(--color-ok); z-index: 1; }}
        .daily-bar-wrapper {{ flex: 1; min-width: 55px; display: flex; flex-direction: column; justify-content: flex-end; text-align: center; }}
        .daily-bar {{ position: relative; width: 80%; margin: 0 auto; border-radius: 4px 4px 0 0; transition: height 0.3s ease-out; z-index: 2; background-color: var(--color-golden); }}
        .daily-bar.daily-bar-over {{ background-color: var(--color-good); }}
        .bar-percentage {{ position: absolute; top: -18px; width: 100%; left: 0; font-size: 11px; font-weight: bold; white-space: nowrap; }}
        .bar-percentage .over {{ color: var(--color-good); }}
        .bar-percentage .under {{ color: var(--color-ok); }}
        .bar-date-label {{ font-size: 10px; color: var(--muted-text); margin-top: 6px; white-space: nowrap; }}
        .daily-bar-spacer {{ min-width: 15px; }}

        @media (prefers-color-scheme: dark) {{ .total-row td {{ border-top-color: #FFFFFF; }} }}

        @media (max-width: 1400px) {{
            .ranking-content {{ grid-template-columns: repeat(2, 1fr); }}
        }}
        @media (max-width: 992px) {{
            .ranking-content {{ grid-template-columns: repeat(2, 1fr); }}
            .report-header {{ flex-direction: column; align-items: stretch; gap: 15px; }}
        }}
        @media (max-width: 768px) {{
            .container {{ padding: 20px 15px; }}
            .ranking-content {{ grid-template-columns: 1fr; }}
            .donut-chart {{ width: 160px; height: 160px; }}
            .donut-chart::before {{ width: 110px; height: 110px; }}
        }}
    </style></head><body><div class="container">
        <header class="report-header"><div><h1>Localization Engineering KPI Report</h1><p><b>Generated on:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p></div><button id="exportButton" class="export-button" onclick="exportReport()">Export Current View</button></header>

        <div class="toggle-container">
            <div class="column-toggle"><strong>Toggle Columns:</strong>{column_toggle_html}</div>
            <div class="engineer-toggle"><strong>Toggle Engineers:</strong>{engineer_toggle_html}</div>
        </div>
        <nav class="main-tab-nav">{main_nav_buttons_html}</nav>
        <main>{main_content_panels_html}</main>
    </div><script>
        const sorters = {{}};
        function openView(evt, viewId, level, parentId) {{
            let i, content, links;
            if (level === 'main') {{ content = document.getElementsByClassName("main-tab-content"); links = document.getElementsByClassName("main-tab-link"); }}
            else {{ const parentElement = document.getElementById(parentId); content = parentElement.getElementsByClassName("sub-tab-content"); links = parentElement.getElementsByClassName("sub-tab-link"); }}
            for (i = 0; i < content.length; i++) {{ content[i].style.display = "none"; }}
            for (i = 0; i < links.length; i++) {{ links[i].className = links[i].className.replace(" active", ""); }}
            document.getElementById(viewId).style.display = "block";
            if(evt) evt.currentTarget.className += " active";
        }}
        function toggleColumn(checkboxElem) {{ const colClass = checkboxElem.dataset.colClass; document.querySelectorAll('.' + colClass).forEach(el => el.style.display = checkboxElem.checked ? "" : "none"); }}

        // --- NEW: Function to toggle engineer rows ---
        function toggleRow(checkboxElem) {{
            const rowClass = checkboxElem.dataset.rowClass;
            document.querySelectorAll('.' + rowClass).forEach(el => el.style.display = checkboxElem.checked ? "" : "none");
        }}
        // --- END NEW ---

        function toggleRankingView(evt, viewToShow, containerId) {{ const container = document.getElementById(containerId); const nav = evt.currentTarget.parentElement; nav.querySelectorAll('.sub-tab-link').forEach(el => el.classList.remove('active')); evt.currentTarget.classList.add('active'); container.querySelectorAll('.ranking-content').forEach(el => el.style.display = 'none'); container.querySelector('.' + viewToShow).style.display = 'grid';}}

        function exportReport() {{
            const activeMainTab = document.querySelector('.main-tab-link.active');
            const activeContentPanel = document.querySelector('.main-tab-content[style*="display: block"]');
            const activeSubTab = activeContentPanel ? activeContentPanel.querySelector('.sub-tab-link.active') : null;
            const activeSubContentPanel = activeContentPanel ? activeContentPanel.querySelector('.sub-tab-content[style*="display: block"]') : null;
            if (!activeSubContentPanel) {{ alert('Could not find an active view to export.'); return; }}
            const quarterText = activeMainTab ? activeMainTab.textContent.trim() : 'Report';
            const viewText = activeSubTab ? activeSubTab.textContent.trim().replace(/\\s+/g, '_') : 'View';
            const reportTitle = `Localization Engineering KPI Report - ${{quarterText}} (${{activeSubTab.textContent.trim()}})`;
            const newDoc = document.implementation.createHTMLDocument(reportTitle);
            newDoc.head.innerHTML = document.head.innerHTML;
            const newContainer = document.createElement('div'); newContainer.className = 'container'; newDoc.body.appendChild(newContainer);
            const headerClone = document.querySelector('.report-header').cloneNode(true);
            headerClone.querySelector('#exportButton').remove(); headerClone.querySelector('h1').textContent = reportTitle; newContainer.appendChild(headerClone);

            // --- MODIFIED: Clone toggle bars into export ---
            const toggleContainerClone = document.querySelector('.toggle-container');
            if (toggleContainerClone) {{
                newContainer.appendChild(toggleContainerClone.cloneNode(true));
            }}
            // --- END MODIFIED ---

            const contentClone = activeSubContentPanel.cloneNode(true); contentClone.style.display = 'block';

            const originalDetails = activeSubContentPanel.querySelectorAll('details');
            const clonedDetails = contentClone.querySelectorAll('details');
            originalDetails.forEach((originalDetail, index) => {{
                if (clonedDetails[index] && !originalDetail.open) {{
                    clonedDetails[index].remove();
                }}
            }});

            contentClone.querySelectorAll('.filter-container, .ranking-controls').forEach(el => el.remove());

            // --- MODIFIED: Remove toggle bars from *inside* the cloned content (if they were there) ---
            contentClone.querySelectorAll('.toggle-container, .column-toggle, .engineer-toggle').forEach(el => el.remove());
            // --- END MODIFIED ---

            newContainer.appendChild(contentClone);
            const htmlString = new XMLSerializer().serializeToString(newDoc);
            const blob = new Blob(['<!DOCTYPE html>' + htmlString], {{ type: 'text/html' }});
            const a = document.createElement('a'); a.download = `LE_KPI_Report_${{quarterText}}_${{viewText}}.html`; a.href = URL.createObjectURL(blob);
            document.body.appendChild(a); a.click(); document.body.removeChild(a); URL.revokeObjectURL(a.href);
        }}

        function sortTable(tableId, n) {{
            const table = document.getElementById(tableId);
            let tbody = table.tBodies[0];
            if (!tbody) return;

            const key = `${{tableId}}-${{n}}`;
            const dir = sorters[key] === 'asc' ? 'desc' : 'asc';
            sorters[key] = dir;

            let rowsToSort = Array.from(tbody.querySelectorAll("tr:not(.fixed-row)"));
            let fixedRows = Array.from(tbody.querySelectorAll("tr.fixed-row"));

            rowsToSort.sort((a, b) => {{
                let cellA = a.cells[n], cellB = b.cells[n];
                if (!cellA || !cellB) return 0;
                let valA = cellA.dataset.sortValue !== undefined ? cellA.dataset.sortValue : (cellA.textContent || cellA.innerText);
                let valB = cellB.dataset.sortValue !== undefined ? cellB.dataset.sortValue : (cellB.textContent || cellB.innerText);
                const isNumeric = !isNaN(parseFloat(valA)) && isFinite(valA) && !isNaN(parseFloat(valB)) && isFinite(valB);
                if (isNumeric) {{
                    valA = parseFloat(valA);
                    valB = parseFloat(valB);
                }} else {{
                    valA = String(valA).trim().toLowerCase();
                    valB = String(valB).trim().toLowerCase();
                }}
                if (valA < valB) return dir === 'asc' ? -1 : 1;
                if (valA > valB) return dir === 'asc' ? 1 : -1;
                return 0;
            }});

            rowsToSort.forEach(row => tbody.appendChild(row));
            fixedRows.forEach(row => tbody.appendChild(row));
        }}
        function filterTable(inputElem, tableId, colIndex) {{
             const filter = inputElem.value.toUpperCase();
             const table = document.getElementById(tableId);
             const tbody = table.getElementsByTagName("tbody")[0];
             const tr = tbody.getElementsByTagName("tr");
             for (let i = 0; i < tr.length; i++) {{
                 if (tr[i].classList.contains('fixed-row')) continue;
                 const td = tr[i].getElementsByTagName("td")[colIndex];
                 if (td) {{
                     const cellText = (td.textContent || td.innerText).toUpperCase();
                     if (cellText.indexOf(filter) > -1) {{
                         tr[i].style.display = "";
                     }} else {{
                         tr[i].style.display = "none";
                     }}
                 }}
             }}
        }}
        function filterRanking(evt, filterClass, containerId) {{ const nav = evt.currentTarget.parentElement; nav.querySelectorAll('.sub-tab-link').forEach(el => el.classList.remove('active')); evt.currentTarget.classList.add('active'); const container = document.getElementById(containerId); const listItems = container.querySelectorAll('.ranking-list li:not(.ranking-header-item)'); listItems.forEach(li => {{ if (filterClass === 'all' || li.classList.contains(filterClass)) {{ li.style.display = 'grid'; }} else {{ li.style.display = 'none'; }} }}); }}

        // --- MODIFIED: Apply engineer toggles on page load ---
        document.addEventListener("DOMContentLoaded", function() {{ 
            document.querySelectorAll('.column-toggle input[type="checkbox"]').forEach(checkbox => toggleColumn(checkbox)); 
            document.querySelectorAll('.engineer-toggle input[type="checkbox"]').forEach(checkbox => toggleRow(checkbox)); 
            const firstMainTab = document.querySelector('.main-tab-link'); 
            if(firstMainTab) {{ firstMainTab.click(); }} 
        }});
        // --- END MODIFIED ---
    </script></body></html>
    """

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_template)
    print(f"\nLE report with all improvements generated at: {output_path}")