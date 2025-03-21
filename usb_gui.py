#!/usr/bin/env python3
import sys
import io
import os
import time
import subprocess
import datetime
import logging
import atexit
from logging.handlers import RotatingFileHandler
from contextlib import redirect_stdout, contextmanager
from pathlib import Path

# Configure logging
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
LOG_BACKUP_COUNT = 5

# Create log directory if it doesn't exist
log_dir = Path(os.path.expanduser("~/Library/Logs/USB Scanner"))
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / 'usb_scanner.log'

# Create and configure file handler
file_handler = RotatingFileHandler(
    log_file,
    maxBytes=LOG_MAX_BYTES,
    backupCount=LOG_BACKUP_COUNT
)
file_handler.setFormatter(logging.Formatter(LOG_FORMAT))

# Create and configure console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter(LOG_FORMAT))

# Configure logger
logger = logging.getLogger('USB Scanner')
logger.setLevel(logging.DEBUG)
logger.addHandler(file_handler)
logger.addHandler(console_handler)
logger.propagate = False  # Prevent duplicate logs

logger.info("USB Scanner logging initialized")

def cleanup():
    """Clean up resources on application exit"""
    logger.info("Application shutting down...")
    try:
        # Deliberately avoid accessing USB devices during shutdown
        # Just ensure all file handles and resources are closed
        for handler in logger.handlers:
            handler.close()
    except Exception as e:
        print(f"Cleanup warning: {e}")
    logger.info("Cleanup completed")

# Register cleanup handler
atexit.register(cleanup)

# Import Qt modules with error handling
try:
    from PySide6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, 
                                QHBoxLayout, QPushButton, QTextEdit, 
                                QWidget, QLabel, QMessageBox, QProgressBar,
                                QStatusBar, QMenu, QMenuBar,
                                QFileDialog, QCheckBox)
    from PySide6.QtCore import Qt, QObject, Signal, Slot, QThread, QTimer
    from PySide6.QtGui import QIcon, QAction
    logger.info("Successfully imported PySide6 modules")
except ImportError as e:
    logger.error(f"Failed to import PySide6 modules: {e}")
    print(f"Error: Failed to import required Qt modules: {e}")
    sys.exit(1)

# Import USB functionality with error handling
try:
    import usbfind
    import usb.core
    import usb.util
    logger.info("Successfully imported USB modules")
except ImportError as e:
    logger.error(f"Failed to import USB modules: {e}")
    print(f"Error: Failed to import required USB modules: {e}")
    sys.exit(1)

class USBScanError(Exception):
    """Custom exception for USB scanning errors"""
    pass


def log_exception(e, message="An error occurred"):
    """Helper function to log exceptions with consistent formatting"""
    error_type = type(e).__name__
    error_msg = str(e)
    logger.error(f"{message}: {error_type} - {error_msg}", exc_info=True)
    return f"{message}: {error_type} - {error_msg}"
class OutputRedirector(io.StringIO):
    """Redirects stdout to capture printed output"""
    def __init__(self, text_widget, *args, **kwargs):
        super(OutputRedirector, self).__init__(*args, **kwargs)
        self.text_widget = text_widget
        self.old_stdout = sys.stdout

    def write(self, text):
        super(OutputRedirector, self).write(text)
        self.text_widget.append(text)
        # Ensure text is visible by scrolling to the bottom
        self.text_widget.verticalScrollBar().setValue(
            self.text_widget.verticalScrollBar().maximum()
        )

class ScanThread(QThread):
    """Thread for running USB scans in the background"""
    progress_signal = Signal(int)
    finished_signal = Signal()
    error_signal = Signal(str)
    
    def __init__(self, verbose=False, parent=None):
        super(ScanThread, self).__init__(parent)
        self.verbose = verbose
        self.output_buffer = io.StringIO()
        logger.debug(f"Scan thread initialized with verbose={self.verbose}")
        
    def run(self):
        logger.info(f"Starting USB scan thread (verbose={self.verbose})")
        try:
            # Redirect stdout to our buffer
            with redirect_stdout(self.output_buffer):
                # Reset usbfind global variables
                usbfind.Verbose = self.verbose
                usbfind.Busses = 'NONE'
                usbfind.BackEnd = 'NONE'
                
                logger.debug("Scanning USB devices...")
                # Simulate progress (since we can't easily track real progress)
                for i in range(101):
                    if i < 100:  # Only update progress if not finished
                        self.progress_signal.emit(i)
                        time.sleep(0.01)  # Small delay to simulate work
                    
                    # Run main function at 100%
                    if i == 100:
                        logger.debug("Executing usbfind.main()")
                        usbfind.main()
                        
            # Signal completion
            self.progress_signal.emit(100)
            logger.info("USB scan completed successfully")
            self.finished_signal.emit()
            
        except Exception as e:
            error_message = log_exception(e, "Error during USB scan")
            logger.error(f"Scan failed: {str(e)}")
            self.error_signal.emit(error_message)
class USBGui(QMainWindow):
    def __init__(self):
        super(USBGui, self).__init__()
        
        self.setWindowTitle("USB Device Security Scanner")
        self.resize(800, 600)
        # Set window icon if icon file exists
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Images/usb_icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        # Initialize member variables
        self.scan_thread = None
        self.auto_refresh_timer = None
        self.auto_refresh_active = False
        self.device_count = 0
        
        # Create menu bar
        self.create_menu_bar()
        
        # Create status bar
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Ready. No devices scanned yet.")
        
        # Main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        
        # Title label
        title_label = QLabel("USB Device Security Scanner")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)
        
        # Buttons layout
        button_layout = QHBoxLayout()
        main_layout.addLayout(button_layout)
        
        # Scan button (normal mode)
        self.scan_button = QPushButton("Scan USB Devices")
        self.scan_button.clicked.connect(self.scan_normal)
        button_layout.addWidget(self.scan_button)
        
        # Scan button (verbose mode)
        self.verbose_button = QPushButton("Scan USB Devices (Verbose)")
        self.verbose_button.clicked.connect(self.scan_verbose)
        button_layout.addWidget(self.verbose_button)
        
        # Clear button
        self.clear_button = QPushButton("Clear Output")
        self.clear_button.clicked.connect(self.clear_output)
        button_layout.addWidget(self.clear_button)
        
        # Auto-refresh checkbox
        self.auto_refresh_checkbox = QCheckBox("Auto-Refresh")
        self.auto_refresh_checkbox.setToolTip("Auto-refresh USB scan every 5 seconds")
        self.auto_refresh_checkbox.stateChanged.connect(self.toggle_auto_refresh)
        button_layout.addWidget(self.auto_refresh_checkbox)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)
        
        # Output text area
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        main_layout.addWidget(self.output_text)
        
    def create_menu_bar(self):
        """Create the menu bar with its menus and actions"""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("&File")
        
        save_action = QAction("&Save Log", self)
        save_action.setShortcut("Ctrl+S")
        save_action.setStatusTip("Save the current log to a file")
        save_action.triggered.connect(self.save_log)
        file_menu.addAction(save_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.setStatusTip("Exit the application")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Tools menu
        tools_menu = menubar.addMenu("&Tools")
        
        reset_action = QAction("&Reset USB", self)
        reset_action.setStatusTip("Reset USB subsystem")
        reset_action.triggered.connect(self.reset_usb)
        tools_menu.addAction(reset_action)
        
        # Help menu
        help_menu = menubar.addMenu("&Help")
        
        about_action = QAction("&About", self)
        about_action.setStatusTip("Show the application's About box")
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)
        
        doc_action = QAction("&Documentation", self)
        doc_action.setStatusTip("Show USB device documentation")
        doc_action.triggered.connect(self.show_documentation)
        help_menu.addAction(doc_action)
    
    def set_buttons_enabled(self, enabled):
        """Enable or disable buttons during scanning operations"""
        self.scan_button.setEnabled(enabled)
        self.verbose_button.setEnabled(enabled)
        self.clear_button.setEnabled(enabled)
        
    def update_progress(self, value):
        """Update the progress bar during a scan operation"""
        self.progress_bar.setValue(value)
        
    def scan_finished(self):
        """Handle scan completion"""
        try:
            # Hide progress bar
            self.progress_bar.setVisible(False)
            
            # Re-enable buttons
            self.set_buttons_enabled(True)
            
            # Get the text from the scan thread and update the output
            if self.scan_thread and hasattr(self.scan_thread, 'output_buffer'):
                output_text = self.scan_thread.output_buffer.getvalue()
                self.output_text.append(output_text)
            
            # Update device count
            self.update_device_count()
            
            # Update status
            status_msg = f"Scan complete. Found {self.device_count} USB device(s)."
            self.statusBar.showMessage(status_msg)
            logger.info(status_msg)
        except Exception as e:
            error_msg = log_exception(e, "Error processing scan results")
            self.statusBar.showMessage(f"Error: {error_msg}")
            self.output_text.append(f"\nError processing results: {error_msg}\n")
    
    def update_device_count(self):
        """Update the count of USB devices found"""
        # Count the devices by parsing the output text
        output = self.output_text.toPlainText()
        
        # Simple way to count USB devices (may need adjustment based on output format)
        if "No devices found" in output:
            self.device_count = 0
        else:
            # Count based on typical output patterns from usbfind.py
            # This is a simplistic approach and may need refinement
            lines = output.split('\n')
            device_lines = [line for line in lines if "Bus Location:" in line]
            self.device_count = len(device_lines)
        
        # Update status bar
        self.statusBar.showMessage(f"Found {self.device_count} USB device(s)")
        
    def handle_error(self, error_msg):
        """Handle errors that occur during scanning"""
        try:
            logger.error(f"Error handler called: {error_msg}")
            self.progress_bar.setVisible(False)
            self.set_buttons_enabled(True)
            
            self.output_text.append(f"\nERROR: {error_msg}\n")
            self.statusBar.showMessage(f"Error: {error_msg}")
            
            # Show error dialog for critical errors
            if "permission" in error_msg.lower() or "access" in error_msg.lower():
                QMessageBox.critical(self, "USB Access Error", 
                                    f"{error_msg}\n\nYou may need elevated permissions to access USB devices.")
            else:
                QMessageBox.warning(self, "Scan Error", error_msg)
                
        except Exception as e:
            # Fallback error handling if the error handler itself fails
            logger.critical(f"Error in error handler: {e}")
            print(f"Critical error in error handler: {e}")
            self.statusBar.showMessage("A critical error occurred")
        
    def scan_normal(self):
        """Run USB scan in normal mode using a separate thread"""
        try:
            logger.info("Starting USB scan in normal mode")
            self.output_text.clear()
            self.output_text.append("Starting USB scan in normal mode...\n")
            
            # Disable buttons during scan
            self.set_buttons_enabled(False)
            
            # Show and reset progress bar
            self.progress_bar.setValue(0)
            self.progress_bar.setVisible(True)
            
            # Create and start scan thread
            self.scan_thread = ScanThread(verbose=False, parent=self)
            self.scan_thread.progress_signal.connect(self.update_progress)
            self.scan_thread.finished_signal.connect(self.scan_finished)
            self.scan_thread.error_signal.connect(self.handle_error)
            self.scan_thread.start()
            logger.debug("Scan thread started")
        except Exception as e:
            error_msg = log_exception(e, "Failed to start normal scan")
            self.handle_error(error_msg)
        
    def scan_verbose(self):
        """Run USB scan in verbose mode using a separate thread"""
        try:
            logger.info("Starting USB scan in verbose mode")
            self.output_text.clear()
            self.output_text.append("Starting USB scan in verbose mode...\n")
            
            # Disable buttons during scan
            self.set_buttons_enabled(False)
            
            # Show and reset progress bar
            self.progress_bar.setValue(0)
            self.progress_bar.setVisible(True)
            
            # Create and start scan thread
            self.scan_thread = ScanThread(verbose=True, parent=self)
            self.scan_thread.progress_signal.connect(self.update_progress)
            self.scan_thread.finished_signal.connect(self.scan_finished)
            self.scan_thread.error_signal.connect(self.handle_error)
            self.scan_thread.start()
            logger.debug("Verbose scan thread started")
        except Exception as e:
            error_msg = log_exception(e, "Failed to start verbose scan")
            self.handle_error(error_msg)
        
    def clear_output(self):
        """Clear the output text area"""
        self.output_text.clear()
        self.statusBar.showMessage("Output cleared")

    def save_log(self):
        """Save the current log to a file"""
        try:
            # Get current timestamp for default filename
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            default_filename = f"usb_scan_{timestamp}.txt"
            
            # Open file dialog
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Log",
                default_filename,
                "Text Files (*.txt);;All Files (*)"
            )
            
            if file_path:
                # Save the text content to the selected file
                with open(file_path, 'w') as f:
                    f.write(self.output_text.toPlainText())
                
                self.statusBar.showMessage(f"Log saved to {file_path}")
                return True
            else:
                self.statusBar.showMessage("Log save cancelled")
                return False
                
        except Exception as e:
            error_msg = f"Error saving log: {str(e)}"
            self.statusBar.showMessage(error_msg)
            QMessageBox.warning(self, "Save Error", error_msg)
            return False
    
    def reset_usb(self):
        """Reset USB subsystem (platform specific)"""
        try:
            # Confirm with user
            response = QMessageBox.question(
                self,
                "Reset USB",
                "This will attempt to reset the USB subsystem, which may disconnect USB devices.\n\nContinue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if response != QMessageBox.Yes:
                self.statusBar.showMessage("USB reset cancelled")
                return
            
            # Platform specific USB reset commands
            if sys.platform.startswith('linux'):
                # For Linux, we can reset USB using various commands
                command = ['sudo', 'modprobe', '-r', 'usb-storage']
                result = subprocess.run(command, capture_output=True, text=True)
                time.sleep(1)
                command = ['sudo', 'modprobe', 'usb-storage']
                result = subprocess.run(command, capture_output=True, text=True)
                
                if result.returncode != 0:
                    raise Exception(f"Command failed: {result.stderr}")
                    
            elif sys.platform == 'darwin':  # macOS
                # macOS doesn't have a simple command line tool for USB reset
                # We'll need to use IOKit via Python bindings or a helper tool
                self.output_text.append("USB reset on macOS requires system-level access.\n")
                self.output_text.append("Try disconnecting and reconnecting USB devices manually.\n")
                self.statusBar.showMessage("USB reset not fully supported on macOS")
                return
                
            elif sys.platform.startswith('win'):  # Windows
                # For Windows, use devcon or similar
                self.output_text.append("USB reset on Windows requires system-level access.\n")
                self.output_text.append("Try using Device Manager to disable/enable USB controllers.\n")
                self.statusBar.showMessage("USB reset not fully supported on Windows")
                return
            
            self.output_text.append("USB subsystem reset attempted.\n")
            self.output_text.append("You may need to reconnect USB devices.\n")
            self.statusBar.showMessage("USB reset completed")
            
            # Scan again after a brief delay
            QTimer.singleShot(2000, self.scan_normal)
            
        except Exception as e:
            error_msg = f"Error resetting USB: {str(e)}"
            self.output_text.append(f"ERROR: {error_msg}\n")
            self.statusBar.showMessage(error_msg)
            QMessageBox.warning(self, "USB Reset Error", error_msg)

    def show_about_dialog(self):
        """Display information about the application"""
        about_text = (
            "<h2>USB Device Security Scanner</h2>"
            "<p>Version 1.0</p>"
            "<p>A tool for scanning, analyzing, and monitoring USB devices.</p>"
            "<p>Based on the USB Hacking toolkit by Merimetso-Code.</p>"
            "<p><a href='https://github.com/Merimetso-Code/USB-Hacking'>GitHub Repository</a></p>"
            "<p>© 2023 Merimetso Ltd.</p>"
        )
        
        QMessageBox.about(self, "About USB Scanner", about_text)
        self.statusBar.showMessage("About dialog displayed")

    def show_documentation(self):
        """Show documentation for USB hacking and security"""
        doc_text = (
            "<h2>USB Device Security Documentation</h2>"
            "<h3>USB Security Concepts</h3>"
            "<ul>"
            "<li><b>Vendor ID (VID)</b>: Unique identifier assigned to USB device manufacturers</li>"
            "<li><b>Product ID (PID)</b>: Identifies a specific product from a manufacturer</li>"
            "<li><b>Device Class</b>: Defines the type of device (HID, Mass Storage, etc.)</li>"
            "<li><b>Endpoint</b>: Communication channels within a USB device</li>"
            "</ul>"
            "<h3>Common Security Issues</h3>"
            "<ul>"
            "<li>Bad USB attacks - devices that masquerade as keyboards</li>"
            "<li>Data exfiltration via USB storage</li>"
            "<li>Hardware keyloggers</li>"
            "<li>USB device fingerprinting and tracking</li>"
            "</ul>"
            "<h3>Using This Tool</h3>"
            "<ul>"
            "<li>Regular scanning helps identify unexpected USB devices</li>"
            "<li>Verbose mode provides detailed information for security analysis</li>"
            "<li>Save logs to track USB device history</li>"
            "<li>Auto-refresh to monitor for new device connections</li>"
            "</ul>"
            "<p>For more information, visit: "
            "<a href='https://github.com/Merimetso-Code/USB-Hacking'>USB Hacking Repository</a></p>"
        )
        
        # Create a more sophisticated documentation dialog
        doc_dialog = QMessageBox(self)
        doc_dialog.setWindowTitle("USB Security Documentation")
        doc_dialog.setText(doc_text)
        doc_dialog.setTextFormat(Qt.RichText)
        doc_dialog.setIcon(QMessageBox.Information)
        doc_dialog.setStandardButtons(QMessageBox.Ok)
        doc_dialog.exec()
        self.statusBar.showMessage("Documentation displayed")

    def toggle_auto_refresh(self, state):
        """Enable or disable automatic refresh of USB device scan"""
        try:
            if state == Qt.Checked:
                # Start auto-refresh if it's not already running
                if not self.auto_refresh_active:
                    self.auto_refresh_active = True
                    self.output_text.append("Auto-refresh enabled (5 second intervals)\n")
                    self.statusBar.showMessage("Auto-refresh enabled")
                    
                    # Create and start timer if it doesn't exist
                    if not self.auto_refresh_timer:
                        self.auto_refresh_timer = QTimer(self)
                        self.auto_refresh_timer.timeout.connect(self.auto_refresh_scan)
                    
                    # Start the timer with 5 second interval
                    self.auto_refresh_timer.start(5000)
            else:
                # Stop auto-refresh
                if self.auto_refresh_active:
                    self.auto_refresh_active = False
                    if self.auto_refresh_timer:
                        self.auto_refresh_timer.stop()
                    
                    self.output_text.append("Auto-refresh disabled\n")
                    self.statusBar.showMessage("Auto-refresh disabled")
        except Exception as e:
            error_msg = f"Error toggling auto-refresh: {str(e)}"
            self.output_text.append(f"ERROR: {error_msg}\n")
            self.statusBar.showMessage(error_msg)
            self.auto_refresh_checkbox.setChecked(False)
            self.auto_refresh_active = False
            QMessageBox.warning(self, "Auto-Refresh Error", error_msg)

    def auto_refresh_scan(self):
        """Perform a scan when auto-refresh is triggered"""
        try:
            # Only start a new scan if a scan isn't already in progress
            if not self.scan_thread or not self.scan_thread.isRunning():
                self.output_text.append("\n--- Auto-refresh scan at " + 
                                      datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " ---\n")
                # Use normal (non-verbose) mode for auto-refresh to keep output manageable
                self.scan_normal()
            else:
                # Skip this cycle if a scan is already running
                self.statusBar.showMessage("Auto-refresh: waiting for current scan to complete")
        except Exception as e:
            error_msg = f"Auto-refresh error: {str(e)}"
            logger.error(error_msg)
            self.statusBar.showMessage(error_msg)
            # Disable auto-refresh on error
            self.auto_refresh_checkbox.setChecked(False)

def main():
    logger.info("Starting USB Scanner application")
    try:
        app = QApplication([])
        app.setApplicationName("USB Device Scanner")
        app.setApplicationVersion("1.0")
        
        # Create and show main window
        try:
            window = USBGui()
            window.show()
            logger.info("Main window created and displayed")
        except Exception as e:
            logger.error(f"Failed to create main window: {e}")
            QMessageBox.critical(None, "Startup Error",
                              f"Failed to initialize application window:\n{str(e)}")
            return 1
        
        # Run the application
        exit_code = app.exec()
        logger.info(f"Application exiting with code {exit_code}")
        
        # Ensure window is properly closed
        window.close()
        return exit_code
        
    except Exception as e:
        logger.error(f"Critical application error: {e}")
        print(f"Critical Error: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
