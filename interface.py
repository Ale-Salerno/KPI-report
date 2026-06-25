# interface.py

import os
import platform
import subprocess
import sys
import logging
import webbrowser
from collections import defaultdict
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QGroupBox, QToolButton, QLineEdit,
    QPushButton, QFileDialog, QLabel,
    QTabWidget, QTableWidget, QTableWidgetItem, QMessageBox, QHeaderView,
    QTextEdit, QComboBox, QDialog, QDialogButtonBox
)
from PySide6.QtCore import Qt, QTimer, QSize, QUrl
from PySide6.QtGui import QIcon, QPalette, QColor, QDesktopServices
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineDownloadRequest, QWebEngineSettings

import config

try:
    from backend import run_backend_processing
except ImportError:
    print("Warning: Could not import 'run_backend_processing' from backend.py.")


    def run_backend_processing(platform_path, helpdesk_path):
        import time;
        time.sleep(2);
        return None

# --- Theme & Style Utilities (Omitted for brevity) ---
winreg = None
if platform.system().lower() == "windows":
    try:
        import winreg
    except ImportError:
        print("Note: 'winreg' module not available.")


def get_windows_accent_color_explorer_hex() -> str | None:
    if not winreg or platform.system().lower() != "windows": return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Accent") as key:
            value, _ = winreg.QueryValueEx(key, "AccentColorMenu");
            red, green, blue = (value & 0xFF), ((value >> 8) & 0xFF), ((value >> 16) & 0xFF)
            return f"#{red:02x}{green:02x}{blue:02x}"
    except Exception:
        return None


def detect_system_theme() -> str:
    if platform.system().lower() == "windows" and winreg:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
                if winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 1: return "light"
        except Exception:
            pass
    return "dark"


ICONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
if not os.path.exists(ICONS_DIR):
    os.makedirs(ICONS_DIR, exist_ok=True)
    for name in ["app", "folder", "run", "download", "save", "add", "remove", "arrow", "settings"]:
        for variant in ["light", "dark"]:
            icon_path = os.path.join(ICONS_DIR, f"{name}_{variant}.svg")
            if not os.path.exists(icon_path):
                with open(icon_path, "w") as f: f.write(
                    "<svg width='16' height='16'><rect width='16' height='16' style='fill:gray'/></svg>")


class DragDropLineEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent);
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls(): event.acceptProposedAction()

    def dropEvent(self, event):
        if event.mimeData().hasUrls(): self.setText(event.mimeData().urls()[0].toLocalFile())


# --- FIX: This custom class intercepts link clicks to open them externally ---
class CustomWebEnginePage(QWebEnginePage):
    def acceptNavigationRequest(self, url: QUrl, _type, isMainFrame: bool) -> bool:
        if _type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
            QDesktopServices.openUrl(url)
            return False  # Tell the widget we've handled this request
        return super().acceptNavigationRequest(url, _type, isMainFrame)


# --- Settings Dialog Class (Unchanged, omitted for brevity) ---
class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuration Settings")
        self.config_data = config.load_config()
        main_layout = QVBoxLayout(self)
        config_tabs = QTabWidget()
        main_layout.addWidget(config_tabs)
        goals_ui, self.goals_table = self._create_table_ui(["Year", "Q1", "Q2", "Q3", "Q4"]);
        config_tabs.addTab(goals_ui, "Revenue Goals")
        auto_goals_ui, self.auto_goals_table = self._create_table_ui(["Year", "Q1", "Q2", "Q3", "Q4"]);
        config_tabs.addTab(auto_goals_ui, "Automation Goals (%)")
        hours_ui, self.hours_table = self._create_table_ui(["Engineer Name", "Working Hours Ratio"]);
        config_tabs.addTab(hours_ui, "Working Hours")
        ipi_ui, self.ipi_table = self._create_table_ui(["Year", "Quarter", "Engineer Name", "IPI Value"]);
        config_tabs.addTab(ipi_ui, "IPI Values")
        idle_ui, self.idle_table = self._create_table_ui(["Year", "Quarter", "Engineer Name", "Idle Time (%)"]);
        config_tabs.addTab(idle_ui, "Idle Times")
        days_off_ui, self.days_off_table = self._create_monthly_days_off_ui()
        config_tabs.addTab(days_off_ui, "Days Off")
        customers_widget = self._create_customers_ui();
        config_tabs.addTab(customers_widget, "Automated Customers")
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept);
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)
        self._load_config_to_ui()
        tab_bar_width = config_tabs.tabBar().sizeHint().width()
        margins = self.layout().contentsMargins()
        required_width = tab_bar_width + margins.left() + margins.right() + 40
        self.setMinimumSize(required_width, 600)

    def _create_button(self, text, icon_name, on_click):
        button = QPushButton(text);
        button.setIcon(self.parent()._get_icon(icon_name));
        button.clicked.connect(on_click)
        return button

    def _create_table_ui(self, headers):
        widget = QWidget();
        layout = QVBoxLayout(widget);
        table = QTableWidget()
        table.setColumnCount(len(headers));
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch);
        table.setSortingEnabled(True)
        button_layout = QHBoxLayout()
        btn_add = self._create_button("Add Row", "add", lambda: table.insertRow(table.rowCount()))
        btn_remove = self._create_button("Remove Row", "remove", lambda: table.removeRow(table.currentRow()))
        button_layout.addStretch();
        button_layout.addWidget(btn_add);
        button_layout.addWidget(btn_remove)
        layout.addWidget(table);
        layout.addLayout(button_layout)
        return widget, table

    def _create_monthly_days_off_ui(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        table = QTableWidget()
        headers = ["Year", "Month", "Engineer Name", "Days Off"]
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setSortingEnabled(True)

        button_layout = QHBoxLayout()
        btn_add = self._create_button("Add Row", "add", lambda: self._add_days_off_row(table))
        btn_remove = self._create_button("Remove Row", "remove", lambda: table.removeRow(table.currentRow()))
        button_layout.addStretch()
        button_layout.addWidget(btn_add)
        button_layout.addWidget(btn_remove)

        layout.addWidget(table)
        layout.addLayout(button_layout)
        return widget, table

    def _add_days_off_row(self, table):
        row_position = table.rowCount()
        table.insertRow(row_position)
        months_combo = QComboBox()
        months = [datetime(2000, i, 1).strftime('%B') for i in range(1, 13)]
        months_combo.addItems(months)
        table.setCellWidget(row_position, 1, months_combo)
        year_item = self._create_table_item(str(datetime.now().year), is_numeric=True)
        table.setItem(row_position, 0, year_item)

    def _create_customers_ui(self):
        customers_widget = QWidget();
        customers_layout = QVBoxLayout(customers_widget)
        customers_selector_layout = QHBoxLayout();
        customers_selector_layout.addWidget(QLabel("Year:"))
        self.customers_year_combo = QComboBox();
        customers_selector_layout.addWidget(self.customers_year_combo)
        customers_selector_layout.addWidget(QLabel("Quarter:"));
        self.customers_quarter_combo = QComboBox()
        self.customers_quarter_combo.addItems(["Q1", "Q2", "Q3", "Q4"]);
        customers_selector_layout.addWidget(self.customers_quarter_combo)
        customers_selector_layout.addStretch();
        self.customers_text_edit = QTextEdit()
        customers_layout.addLayout(customers_selector_layout);
        customers_layout.addWidget(self.customers_text_edit)
        self.customers_year_combo.currentTextChanged.connect(self._update_customers_view)
        self.customers_quarter_combo.currentTextChanged.connect(self._update_customers_view)
        self.customers_text_edit.textChanged.connect(self._update_customers_data_from_view)
        return customers_widget

    def _create_table_item(self, text, is_numeric=False):
        item = QTableWidgetItem()
        if is_numeric:
            try:
                num_value = float(text);
                item.setData(Qt.ItemDataRole.DisplayRole, text);
                item.setData(
                    Qt.ItemDataRole.EditRole, num_value)
            except (ValueError, TypeError):
                item.setData(Qt.ItemDataRole.DisplayRole, text)
        else:
            item.setText(text)
        return item

    def _populate_days_off_table(self, table, data_dict):
        table.setSortingEnabled(False)
        table.setRowCount(0)
        row_idx = 0
        months = [datetime(2000, i, 1).strftime('%B') for i in range(1, 13)]
        for year, months_data in data_dict.items():
            for month, engineers in months_data.items():
                for engineer, value in engineers.items():
                    table.insertRow(row_idx)
                    table.setItem(row_idx, 0, self._create_table_item(str(year), True))
                    months_combo = QComboBox()
                    months_combo.addItems(months)
                    if month in months:
                        months_combo.setCurrentText(month)
                    table.setCellWidget(row_idx, 1, months_combo)
                    table.setItem(row_idx, 2, self._create_table_item(str(engineer)))
                    table.setItem(row_idx, 3, self._create_table_item(str(value), True))
                    row_idx += 1
        table.setSortingEnabled(True)

    def _load_config_to_ui(self):
        def populate_table(table, data, keys, numeric_cols=None):
            table.setSortingEnabled(False);
            table.setRowCount(0)
            for i, row_data in enumerate(data):
                table.insertRow(i)
                for j, key in enumerate(keys):
                    text = str(row_data.get(key, ""));
                    is_numeric = j in (numeric_cols or [])
                    table.setItem(i, j, self._create_table_item(text, is_numeric))
            table.setSortingEnabled(True)

        def populate_nested_table(table, data_dict, numeric_cols=None):
            table.setSortingEnabled(False);
            table.setRowCount(0);
            row_idx = 0
            for year, quarters in data_dict.items():
                for quarter, engineers in quarters.items():
                    for engineer, value in engineers.items():
                        table.insertRow(row_idx)
                        table.setItem(row_idx, 0, self._create_table_item(str(year), True));
                        table.setItem(row_idx, 1, self._create_table_item(str(quarter)))
                        table.setItem(row_idx, 2, self._create_table_item(str(engineer)));
                        table.setItem(row_idx, 3, self._create_table_item(str(value), 3 in (numeric_cols or [])))
                        row_idx += 1
            table.setSortingEnabled(True)

        flat_goals = [{'Year': y, **qs} for y, qs in self.config_data.get("goals", {}).items()];
        populate_table(self.goals_table, flat_goals, ["Year", "Q1", "Q2", "Q3", "Q4"], [0, 1, 2, 3, 4])
        flat_auto_goals = [{'Year': y, **qs} for y, qs in self.config_data.get("automation_goals", {}).items()];
        populate_table(self.auto_goals_table, flat_auto_goals, ["Year", "Q1", "Q2", "Q3", "Q4"], [0, 1, 2, 3, 4])
        hours_data = [{'Engineer Name': k, 'Working Hours Ratio': v} for k, v in
                      self.config_data.get("working_hours", {}).items()];
        populate_table(self.hours_table, hours_data, ["Engineer Name", "Working Hours Ratio"], [1])
        populate_nested_table(self.ipi_table, self.config_data.get("ipi", {}), [3]);
        populate_nested_table(self.idle_table, self.config_data.get("idle", {}), [3])
        self._populate_days_off_table(self.days_off_table, self.config_data.get("days_off", {}))
        customer_years = sorted(self.config_data.get("automated_customers", {}).keys())
        self.customers_year_combo.blockSignals(True);
        self.customers_year_combo.clear()
        if not customer_years: customer_years.append(str(datetime.now().year))
        self.customers_year_combo.addItems(customer_years);
        self.customers_year_combo.blockSignals(False);
        self._update_customers_view()

    def _save_ui_to_config(self):
        new_config = defaultdict(dict)
        try:
            def get_item_value(table, row, col, numeric=False):
                item = table.item(row, col);
                text = item.text().strip() if item else ""
                if not numeric: return text
                try:
                    return float(text)
                except (ValueError, TypeError):
                    return 0.0

            for table, key in [(self.goals_table, "goals"), (self.auto_goals_table, "automation_goals")]:
                data = {};
                for r in range(table.rowCount()):
                    year_str = get_item_value(table, r, 0)
                    if str(year_str).isdigit():
                        data[str(int(year_str))] = {"Q1": get_item_value(table, r, 1, numeric=True),
                                                    "Q2": get_item_value(table, r, 2, numeric=True),
                                                    "Q3": get_item_value(table, r, 3, numeric=True),
                                                    "Q4": get_item_value(table, r, 4, numeric=True)}
                new_config[key] = data
            hours_data = {}
            for r in range(self.hours_table.rowCount()):
                name = get_item_value(self.hours_table, r, 0)
                if name: hours_data[name] = get_item_value(self.hours_table, r, 1, numeric=True)
            new_config["working_hours"] = hours_data
            for table, key in [(self.ipi_table, "ipi"), (self.idle_table, "idle")]:
                data = defaultdict(lambda: defaultdict(dict))
                for r in range(table.rowCount()):
                    year, quarter, name, value = get_item_value(table, r, 0), get_item_value(table, r,
                                                                                             1), get_item_value(table,
                                                                                                                r,
                                                                                                                2), get_item_value(
                        table, r, 3, numeric=True)
                    if all([year, quarter, name]): data[str(int(year))][quarter][name] = value
                new_config[key] = data

            days_off_data = defaultdict(lambda: defaultdict(dict))
            for r in range(self.days_off_table.rowCount()):
                year = get_item_value(self.days_off_table, r, 0)
                month_widget = self.days_off_table.cellWidget(r, 1)
                name = get_item_value(self.days_off_table, r, 2)
                value = get_item_value(self.days_off_table, r, 3, numeric=True)
                month = month_widget.currentText() if month_widget else ""
                if all([year, month, name]):
                    days_off_data[str(int(year))][month][name] = value
            new_config["days_off"] = days_off_data

            new_config["automated_customers"] = self.config_data.get("automated_customers", {})
            if config.save_config(new_config):
                self.config_data = new_config;
                return True
            return False
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred while saving: {e}");
            return False

    def _update_customers_view(self):
        year, quarter = self.customers_year_combo.currentText(), self.customers_quarter_combo.currentText()
        if not year or not quarter: self.customers_text_edit.setText(""); return
        customers = self.config_data.get("automated_customers", {}).get(year, {}).get(quarter, [])
        self.customers_text_edit.blockSignals(True);
        self.customers_text_edit.setText("\n".join(customers));
        self.customers_text_edit.blockSignals(False)

    def _update_customers_data_from_view(self):
        year, quarter = self.customers_year_combo.currentText(), self.customers_quarter_combo.currentText()
        if not year or not quarter: return
        if "automated_customers" not in self.config_data: self.config_data["automated_customers"] = {}
        if year not in self.config_data["automated_customers"]: self.config_data["automated_customers"][year] = {}
        customers = [line.strip() for line in self.customers_text_edit.toPlainText().split("\n") if line.strip()]
        self.config_data["automated_customers"][year][quarter] = customers

    def accept(self):
        if self._save_ui_to_config():
            QMessageBox.information(self, "Success", "Configuration has been saved successfully.")
            super().accept()
        else:
            QMessageBox.warning(self, "Save Failed",
                                "Configuration was not saved. Please check for errors and try again.")


# --- Main Application Window ---
class KpiAppGui(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_theme = detect_system_theme()
        self.setWindowTitle("LE KPI Report Generator")
        self.setWindowIcon(self._get_icon("app"))
        self.setMinimumWidth(800)
        self.config_data = config.load_config()
        self.icon_widgets = {}
        self._build_ui()
        self._apply_stylesheet(self.current_theme)
        self.theme_change_timer = QTimer(self)
        self.theme_change_timer.timeout.connect(self._check_and_apply_theme_changes)
        self.theme_change_timer.start(2000)
        self.adjustSize()
        self.export_report_button.setEnabled(False)  # Initially disable export button

    def _get_icon(self, name: str) -> QIcon:
        variant = "dark" if self.current_theme == "dark" else "light"
        icon_path = os.path.join(ICONS_DIR, f"{name}_{variant}.svg")
        return QIcon(icon_path) if os.path.exists(icon_path) else QIcon()

    def _check_and_apply_theme_changes(self):
        new_theme = detect_system_theme()
        if new_theme != self.current_theme:
            self.current_theme = new_theme
            self._apply_stylesheet(self.current_theme)
            self.setWindowIcon(self._get_icon("app"))
            for button, icon_name in self.icon_widgets.items():
                button.setIcon(self._get_icon(icon_name))

    def _build_ui(self):
        central_widget = QWidget();
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.addWidget(self._create_input_group())
        self.report_groupbox = self._create_report_group()
        main_layout.addWidget(self.report_groupbox, 1)
        action_layout = QHBoxLayout()
        action_layout.addStretch()
        # Changed to _create_tool_button for icon-only display and hover effect
        self.settings_button = self._create_tool_button("settings", self._open_settings_dialog, "Settings")
        self.export_report_button = self._create_button("Export Report", "download", self._export_report,
                                                        is_action=True)
        self.btn_generate = self._create_button("Generate Report", "run", self._execute_report_generation,
                                                is_action=True)

        # Only apply minimum width to action buttons
        max_action_button_width = max(self.btn_generate.sizeHint().width(),
                                      self.export_report_button.sizeHint().width())
        self.btn_generate.setMinimumWidth(max_action_button_width)
        self.export_report_button.setMinimumWidth(max_action_button_width)

        action_layout.addWidget(self.settings_button)
        action_layout.addWidget(self.export_report_button)  # Export button placed before Generate button
        action_layout.addWidget(self.btn_generate)
        main_layout.addLayout(action_layout)

    def _create_input_group(self):
        groupbox = QGroupBox("CSV Reports");
        layout = QGridLayout(groupbox);
        layout.setSpacing(8)
        self.platform_path_edit = DragDropLineEdit()
        self.btn_browse_platform = self._create_tool_button("folder", self._browse_platform_csv, "Browse...")
        self.btn_download_platform = self._create_tool_button("download", self._open_platform_url, "Download page")
        layout.addWidget(QLabel("Platform:"), 0, 0);
        layout.addWidget(self.platform_path_edit, 0, 1)
        layout.addWidget(self.btn_browse_platform, 0, 2);
        layout.addWidget(self.btn_download_platform, 0, 3)
        self.helpdesk_path_edit = DragDropLineEdit()
        self.btn_browse_helpdesk = self._create_tool_button("folder", self._browse_helpdesk_csv, "Browse...")
        self.btn_download_helpdesk = self._create_tool_button("download", self._open_helpdesk_url, "Download page")
        layout.addWidget(QLabel("Helpdesk:"), 1, 0);
        layout.addWidget(self.helpdesk_path_edit, 1, 1)
        layout.addWidget(self.btn_browse_helpdesk, 1, 2);
        layout.addWidget(self.btn_download_helpdesk, 1, 3)
        layout.setColumnStretch(1, 1)
        return groupbox

    def _create_report_group(self):
        groupbox = QGroupBox("Report");
        layout = QVBoxLayout(groupbox)
        self.web_view = QWebEngineView()
        self.web_view.setPage(CustomWebEnginePage(self.web_view))
        self.web_view.loadFinished.connect(self._on_report_load_finished)
        self.web_view.page().profile().downloadRequested.connect(self._handle_download)
        self.web_view.settings().setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True)
        self.web_view.setMinimumHeight(400)
        layout.addWidget(self.web_view)
        groupbox.hide()
        return groupbox

    def _on_report_load_finished(self, ok):
        if ok:
            js_script = """
            var links = document.getElementsByTagName("a");
            for(var i=0; i<links.length; i++) {
                if (links[i].hasAttribute("target")) {
                    links[i].removeAttribute("target");
                }
            }
            """
            self.web_view.page().runJavaScript(js_script)
            self.export_report_button.setEnabled(True)  # Enable export button after report loads

    def _handle_download(self, download_item: QWebEngineDownloadRequest):
        suggested_path = os.path.join(os.path.expanduser("~"), "Downloads", download_item.downloadFileName())
        save_path, _ = QFileDialog.getSaveFileName(self, "Save Exported Report", suggested_path,
                                                   "HTML Files (*.html *.htm)")
        if save_path:
            download_item.setDownloadDirectory(os.path.dirname(save_path));
            download_item.setDownloadFileName(os.path.basename(save_path))
            download_item.accept()
            QMessageBox.information(self, "Download Started", f"The report will be saved to:\n{save_path}")

    def _create_button(self, text, icon_name, on_click, is_action=False):
        button = QPushButton(text)
        if is_action: button.setObjectName("actionButton")
        button.setIcon(self._get_icon(icon_name))
        self.icon_widgets[button] = icon_name
        button.clicked.connect(on_click)
        return button

    def _create_tool_button(self, icon_name, on_click, tooltip=""):
        button = QToolButton();
        button.setIcon(self._get_icon(icon_name))
        button.setToolTip(tooltip);
        self.icon_widgets[button] = icon_name;
        button.clicked.connect(on_click)
        return button

    def _open_settings_dialog(self):
        dialog = SettingsDialog(self)
        dialog.setStyleSheet(self.styleSheet())
        if dialog.exec() == QDialog.DialogCode.Accepted:
            print("Settings saved. Reloading config in main window.")
            self.config_data = config.load_config()

    def _execute_report_generation(self):
        p_path, h_path = self.platform_path_edit.text(), self.helpdesk_path_edit.text()
        if not (os.path.exists(p_path) and os.path.exists(h_path)):
            QMessageBox.warning(self, "Missing Files", "Please provide valid paths for both report files.")
            return

        self.btn_generate.setEnabled(False);
        self.btn_generate.setText("Generating...")
        self.export_report_button.setEnabled(False)  # Disable export during generation
        QApplication.processEvents()
        try:
            report_path = run_backend_processing(p_path, h_path)
            if report_path and os.path.exists(report_path):
                self.report_groupbox.show()
                self.web_view.setUrl(QUrl.fromLocalFile(os.path.abspath(report_path)))
                self.resize(self.width(), 800)
                self.btn_generate.setText("Done!")
                # Export button enabled in _on_report_load_finished
            else:
                self.report_groupbox.show();
                self.web_view.setHtml("<h1>Report Generation Failed</h1>");
                self.btn_generate.setText("Error!")
                self.export_report_button.setEnabled(False)  # Keep disabled on error
        except Exception as e:
            self.report_groupbox.show();
            self.web_view.setHtml(f"<h1>Error</h1><p>An error occurred:</p><pre>{e}</pre>");
            self.btn_generate.setText("Error!")
            self.export_report_button.setEnabled(False)  # Keep disabled on error
        QTimer.singleShot(2000, self._reset_ui_state)

    def _export_report(self):
        if not self.web_view.url().isValid() or self.web_view.url().isEmpty():
            QMessageBox.warning(self, "No Report", "No report is currently loaded to export.")
            return

        # Get the HTML content from the QWebEngineView
        def save_html_content(html_content):
            current_url = self.web_view.url()

            # Extract filename from the URL, if it's a local file
            if current_url.isLocalFile():
                suggested_filename = os.path.basename(current_url.toLocalFile())
            else:
                # Fallback to a default name if not a local file or no meaningful filename
                suggested_filename = f"LE_KPI_REPORT_{datetime.now().strftime('%Y-%m-%d')}.html"

            save_path, _ = QFileDialog.getSaveFileName(self, "Save Report As", suggested_filename,
                                                       "HTML Files (*.html *.htm);;All Files (*)")
            if save_path:
                try:
                    with open(save_path, "w", encoding="utf-8") as f:
                        f.write(html_content)
                    QMessageBox.information(self, "Export Successful", f"Report saved to:\n{save_path}")
                except Exception as e:
                    QMessageBox.critical(self, "Export Error", f"Failed to save report: {e}")
            else:
                QMessageBox.information(self, "Export Cancelled", "Report export was cancelled.")

        self.web_view.page().toHtml(save_html_content)

    def _reset_ui_state(self):
        self.btn_generate.setEnabled(True);
        self.btn_generate.setText(" Generate Report")
        # The export button's state is handled by _on_report_load_finished

    def _open_platform_url(self):
        webbrowser.open(
            "https://platform.languagewire.com/Job/List?JobStatus=Finished&AcceptedSupplierFullName=1109756%2C1112168%2C1025008%2C1184874%2C69827%2C1105500%2C1113395%2C1184870%2C1196079%2C1190670&Deadline=Thu%201%20Jan%202026%20~%20Thu%2031%20Dec%202026&page=1&sidx=JobId&sord=desc&rows=100&IsInitialSearchPerformed=true")

    def _open_helpdesk_url(self):
        webbrowser.open(
            "https://helpdesk.languagewire.com/helpdesk/Reporting/Summary?catSelect=9&periodType=0&dateFrom=2025-01-01T13%3A25&dateTo=2026-12-31T23%3A59&btnSearch=Build")

    def _browse_platform_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Platform CSV", "", "CSV Files (*.csv)");
        if path: self.platform_path_edit.setText(path)

    def _browse_helpdesk_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Helpdesk CSV", "", "CSV Files (*.csv)");
        if path: self.helpdesk_path_edit.setText(path)

    def _apply_stylesheet(self, theme_name: str):
        app_palette = QPalette()
        accent_hex = get_windows_accent_color_explorer_hex()
        highlight_color = QColor(accent_hex) if accent_hex and QColor(accent_hex).isValid() else QColor("#0078d7")
        if theme_name == "dark":
            app_palette.setColor(QPalette.ColorRole.Window, QColor("#2b2b2b"));
            app_palette.setColor(QPalette.ColorRole.WindowText, QColor("#e0e0e0"));
            app_palette.setColor(QPalette.ColorRole.Base, QColor("#222222"));
            app_palette.setColor(QPalette.ColorRole.Button, QColor("#3a3a3a"));
            app_palette.setColor(QPalette.ColorRole.Text, QColor("#e0e0e0"));
            app_palette.setColor(QPalette.ColorRole.ButtonText, QColor("#e0e0e0"));
            app_palette.setColor(QPalette.ColorRole.Highlight, highlight_color);
            app_palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"));
            app_palette.setColor(QPalette.ColorRole.Midlight, QColor("#444444"))
        else:
            app_palette.setColor(QPalette.ColorRole.Window, QColor("#f0f0f0"));
            app_palette.setColor(QPalette.ColorRole.WindowText, QColor("#000000"));
            app_palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"));
            app_palette.setColor(QPalette.ColorRole.Button, QColor("#e0e0e0"));
            app_palette.setColor(QPalette.ColorRole.Text, QColor("#000000"));
            app_palette.setColor(QPalette.ColorRole.ButtonText, QColor("#000000"));
            app_palette.setColor(QPalette.ColorRole.Highlight, highlight_color);
            app_palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"));
            app_palette.setColor(QPalette.ColorRole.Midlight, QColor("#dcdcdc"))
        if QApplication.instance(): QApplication.instance().setPalette(app_palette)
        accent_color = app_palette.color(QPalette.ColorRole.Highlight)
        hover_bg_color = accent_color.lighter(120) if theme_name == "dark" else accent_color.darker(120)
        arrow_svg_url = os.path.join(ICONS_DIR, f"arrow_{theme_name}.svg").replace("\\", "/")
        stylesheet = f"""
            QWidget {{font-family: 'Segoe UI Variable', 'Segoe UI', sans-serif; font-size: 10pt;}}
            QGroupBox {{margin-top: 10px; border: 1px solid palette(midlight); border-radius: 6px; padding-top: 10px;}}
            QGroupBox::title {{subcontrol-origin: margin; subcontrol-position: top left; left: 10px; padding: 0 5px;}}
            QLineEdit, QTextEdit, QComboBox {{background-color: palette(base); border: 1px solid palette(midlight); border-radius: 4px; padding: 4px 6px; min-height: 24px;}}
            QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: top right; width: 22px; border-left: 1px solid palette(midlight); border-top-right-radius: 3px; border-bottom-right-radius: 3px; }}
            QComboBox::down-arrow {{ image: url({arrow_svg_url}); width: 10px; height: 10px; }}
            QComboBox QAbstractItemView {{ background-color: palette(base); border: 1px solid palette(midlight); selection-background-color: palette(highlight); }}
            QToolButton {{background-color: transparent; border: 1px solid transparent; padding: 4px; border-radius: 4px;}}
            QToolButton:hover {{background-color: palette(light); border-color: palette(mid);}}
            QPushButton {{ background-color: palette(button); border: 1px solid palette(midlight); border-radius: 4px; padding: 6px 12px; font-weight: normal; font-size: 9pt; }}
            QPushButton:hover {{ background-color: palette(light); border-color: palette(highlight); }}
            QPushButton#actionButton {{ background-color: {accent_color.name()}; color: {app_palette.color(QPalette.ColorRole.HighlightedText).name()}; border: none; font-weight: bold; font-size: 11pt; padding: 8px 15px;}}
            QPushButton#actionButton:hover {{background-color: {hover_bg_color.name()};}}
            QPushButton#actionButton:disabled, QPushButton:disabled {{background-color: palette(button); color: palette(midlight);}}
            QDialogButtonBox QPushButton {{ font-weight: bold; padding: 8px 20px; }}
            QTabWidget::pane {{ border: none; }}
            QTabBar::tab {{
                background-color: palette(button); color: palette(button-text);
                padding: 7px 15px; margin-right: 1px; border: 1px solid palette(mid);
                border-bottom: none; border-top-left-radius: 5px; border-top-right-radius: 5px;
                min-width: 80px;
            }}
            QTabBar::tab:selected {{
                background-color: palette(window); color: palette(window-text);
                font-weight: bold; border-color: palette(mid);
                border-bottom-color: palette(window);
            }}
            QTabBar::tab:!selected:hover {{ background-color: palette(light); }}
            QHeaderView::section {{ background-color: palette(button); padding: 4px; border: 1px solid palette(midlight); font-weight: bold; }}
        """
        self.setStyleSheet(stylesheet)