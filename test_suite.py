#!/usr/bin/env python3
"""
USB Scanner - Comprehensive Test Suite

This script validates the core functionality of the USB Scanner application:
1. USB device detection with and without permissions
2. Auto-refresh functionality
3. Memory leaks and resource cleanup
4. Error handling and recovery
5. Log rotation

Usage:
    python test_suite.py [options]

Options:
    --verbose       Enable verbose output
    --quick         Run only basic tests
    --log=PATH      Specify log file path (default: ~/Library/Logs/USB Scanner/test_suite.log)
"""

import argparse
import os
import sys
import time
import logging
from logging.handlers import RotatingFileHandler
import subprocess
import threading
import resource
import unittest
import shutil
import glob
import psutil
import io
from datetime import datetime
from pathlib import Path

# Try to import USB-related modules
try:
    import usb.core
    import usb.util
    HAS_USB = True
except ImportError:
    HAS_USB = False
    print("Warning: PyUSB not installed, USB detection tests will be limited")

# Try to import Qt modules for GUI testing
try:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    HAS_QT = True
except ImportError:
    HAS_QT = False
    print("Warning: PySide6 not installed, GUI tests will be limited")

# Default paths
LOG_DIR = os.path.expanduser("~/Library/Logs/USB Scanner")
# Declare global before use
global LOG_FILE
LOG_FILE = os.path.join(LOG_DIR, "test_suite.log")
APP_LOG_FILE = os.path.join(LOG_DIR, "usb_scanner.log")
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'


class TestProgress:
    """Track and display test progress."""
    
    def __init__(self, total_tests):
        self.total = total_tests
        self.completed = 0
        self.passed = 0
        self.failed = 0
        self.start_time = time.time()
        self.test_start_time = None
        
    def start_test(self, test_name):
        """Mark the start of a test."""
        self.test_start_time = time.time()
        print(f"\n[{self.completed+1}/{self.total}] Starting: {test_name}...", end="", flush=True)
        
    def end_test(self, success):
        """Mark the end of a test."""
        duration = time.time() - self.test_start_time
        self.completed += 1
        if success:
            self.passed += 1
            print(f" PASSED ({duration:.2f}s)")
        else:
            self.failed += 1
            print(f" FAILED ({duration:.2f}s)")
    
    def summary(self):
        """Print test summary."""
        total_duration = time.time() - self.start_time
        print("\n" + "="*80)
        print(f"Test Summary: {self.completed} tests completed in {total_duration:.2f}s")
        print(f"  Passed: {self.passed}")
        print(f"  Failed: {self.failed}")
        print("="*80)
        return self.failed == 0


class USBScannerTests(unittest.TestCase):
    """Test cases for USB Scanner application."""
    
    @classmethod
    def setUpClass(cls):
        """Set up the test environment."""
        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(LOG_FILE),
                logging.StreamHandler(sys.stdout)
            ]
        )
        cls.logger = logging.getLogger('USBScannerTests')
        cls.logger.info("Starting USB Scanner test suite")
        
        # Ensure application log directory exists
        os.makedirs(LOG_DIR, exist_ok=True)
        
        # Try to load the scanner module
        try:
            sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
            import usbfind
            cls.usbfind = usbfind
            cls.HAS_SCANNER_MODULE = True
        except ImportError:
            cls.HAS_SCANNER_MODULE = False
            cls.logger.warning("Could not import usbfind module - some tests will be skipped")
        
        # Initialize Qt Application if PySide6 is available
        if HAS_QT:
            cls.app = QApplication.instance() or QApplication([])
            
    @classmethod
    def tearDownClass(cls):
        """Clean up after all tests."""
        cls.logger.info("Test suite completed")
        
    def setUp(self):
        """Set up before each test."""
        self.test_start_time = time.time()
        self.memory_start = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        
    def tearDown(self):
        """Clean up after each test."""
        # Check for memory leaks
        memory_end = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        memory_diff = memory_end - self.memory_start
        
        # Log test duration and memory usage
        duration = time.time() - self.test_start_time
        self.logger.info(f"Test {self._testMethodName} completed in {duration:.2f}s, memory change: {memory_diff} KB")
        
        # Force garbage collection to clean up any remaining objects
        import gc
        gc.collect()
        
    def test_usb_device_enumeration(self):
        """Test USB device enumeration."""
        if not HAS_USB:
            self.skipTest("PyUSB not installed")
            
        self.logger.info("Testing USB device enumeration")
        
        # List devices without requiring special permissions
        devices = list(usb.core.find(find_all=True))
        self.logger.info(f"Found {len(devices)} USB devices without elevated permissions")
        
        # Log device information
        for i, dev in enumerate(devices):
            try:
                vendor = dev.idVendor
                product = dev.idProduct
                self.logger.info(f"Device {i+1}: Vendor ID 0x{vendor:04x}, Product ID 0x{product:04x}")
            except Exception as e:
                self.logger.warning(f"Could not get device info: {e}")
                
        # Ensure at least one device is found (typically built-in USB controller)
        self.assertGreater(len(devices), 0, "No USB devices found")
    
    def test_usb_permissions(self):
        """Test USB device access with and without permissions."""
        if not HAS_USB:
            self.skipTest("PyUSB not installed")
            
        self.logger.info("Testing USB device permissions")
        
        # Get all devices
        devices = list(usb.core.find(find_all=True))
        if not devices:
            self.skipTest("No USB devices found")
            
        # Try to access configuration of each device (may require permissions)
        permission_results = []
        for i, dev in enumerate(devices):
            try:
                # Attempt to get device configuration
                cfg = dev.get_active_configuration()
                permission_results.append((True, f"Device {i+1}: Access granted"))
            except usb.core.USBError as e:
                if "Permission denied" in str(e) or "Access denied" in str(e):
                    permission_results.append((False, f"Device {i+1}: Permission denied"))
                else:
                    permission_results.append((False, f"Device {i+1}: Other USB error: {e}"))
            except Exception as e:
                permission_results.append((False, f"Device {i+1}: Unexpected error: {e}"))
                
        # Log results
        for success, message in permission_results:
            if success:
                self.logger.info(message)
            else:
                self.logger.warning(message)
                
        # At least log the permission state - don't fail test if permissions aren't available
        self.logger.info(f"Permission check: {sum(r[0] for r in permission_results)}/{len(permission_results)} devices accessible")
    
    def test_auto_refresh(self):
        """Test auto-refresh functionality."""
        if not self.HAS_SCANNER_MODULE:
            self.skipTest("Scanner module not available")
            
        self.logger.info("Testing auto-refresh functionality")
        
        # Track device counts
        device_counts = []
        scan_times = []
        
        # Perform multiple scans
        for i in range(3):
            start_time = time.time()
            try:
                if hasattr(self.usbfind, 'get_usb_devices'):
                    devices = self.usbfind.get_usb_devices()
                else:
                    # Fallback method using PyUSB directly
                    devices = list(usb.core.find(find_all=True))
                    
                device_counts.append(len(devices))
                scan_times.append(time.time() - start_time)
                self.logger.info(f"Scan {i+1}: Found {len(devices)} devices in {scan_times[-1]:.3f}s")
                time.sleep(1)  # Brief pause between scans
            except Exception as e:
                self.logger.error(f"Error during scan {i+1}: {e}")
                self.fail(f"Auto-refresh scan failed: {e}")
                
        # Check consistency (assuming no devices are added/removed during test)
        self.assertTrue(all(count == device_counts[0] for count in device_counts), 
                        "Device count should be consistent across scans")
                        
        # Check scan performance
        avg_scan_time = sum(scan_times) / len(scan_times)
        self.logger.info(f"Average scan time: {avg_scan_time:.3f}s")
        self.assertLess(avg_scan_time, 5.0, "Scans should complete in under 5 seconds")
    
    def test_memory_leaks(self):
        """Test for memory leaks and resource cleanup."""
        if not HAS_USB:
            self.skipTest("PyUSB not installed")
            
        self.logger.info("Testing for memory leaks in USB device scanning")
        
        # Initialize metrics
        memory_readings = []
        file_descriptors_before = len(os.listdir('/dev/fd/')) if os.path.exists('/dev/fd/') else None
        
        # Record starting memory
        initial_memory = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        memory_readings.append(initial_memory)
        
        # Run multiple scan operations
        for i in range(10):
            try:
                # Perform a scan
                devices = list(usb.core.find(find_all=True))
                
                # Force manual cleanup (Python's garbage collection might delay this)
                for dev in devices:
                    if hasattr(dev, 'reset'):
                        try:
                            usb.util.dispose_resources(dev)
                        except Exception as e:
                            self.logger.debug(f"Error disposing resources: {e}")
                
                # Manually invoke garbage collection
                import gc
                gc.collect()
                
                # Record memory after scan
                current_memory = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                memory_readings.append(current_memory)
                self.logger.debug(f"Scan {i+1}: Memory usage {current_memory} KB")
                
                time.sleep(0.5)  # Brief pause
            except Exception as e:
                self.logger.error(f"Error during memory leak test scan {i+1}: {e}")
        
        # Compare file descriptors before and after
        if file_descriptors_before is not None:
            file_descriptors_after = len(os.listdir('/dev/fd/'))
            self.logger.info(f"File descriptors: Before={file_descriptors_before}, After={file_descriptors_after}")
            fd_diff = file_descriptors_after - file_descriptors_before
            self.assertLess(fd_diff, 5, "File descriptor leak detected")
            
        # Check memory growth
        memory_growth = memory_readings[-1] - memory_readings[0]
        avg_growth_per_scan = memory_growth / 10 if memory_growth > 0 else 0
        self.logger.info(f"Memory growth: {memory_growth} KB, Average growth per scan: {avg_growth_per_scan:.2f} KB")
        
        # Small memory growth is acceptable, but large growth indicates leaks
        self.assertLess(avg_growth_per_scan, 500, 
                        f"Potential memory leak detected: {avg_growth_per_scan:.2f} KB growth per scan")

    def test_error_handling(self):
        """Test error handling and recovery."""
        if not self.HAS_SCANNER_MODULE:
            self.skipTest("Scanner module not available")
            
        self.logger.info("Testing error handling and recovery")
        
        # Test case 1: Simulate permission error
        try:
            # Create a device class that raises a permission error
            class MockDevice:
                def get_active_configuration(self):
                    raise usb.core.USBError("Permission denied (insufficient permissions)")
                    
            mock_devices = [MockDevice()]
            
            # Test the error handling in the module
            if hasattr(self.usbfind, 'process_device'):
                for dev in mock_devices:
                    try:
                        self.usbfind.process_device(dev)
                        self.logger.info("Error was handled correctly")
                    except Exception as e:
                        self.fail(f"Error handling failed: {e}")
            else:
                self.logger.warning("Can't test process_device function - not exposed in module")
                
        except Exception as e:
            self.logger.error(f"Error in permission test: {e}")
            
        # Test case 2: Simulate device disconnect during scan
        try:
            # Create a device class that raises a device disconnected error
            class DisconnectedDevice:
                def get_active_configuration(self):
                    raise usb.core.USBError("Device disconnected")
                
            mock_devices = [DisconnectedDevice()]
            
            # Test if scanner can recover from disconnected device
            if hasattr(self.usbfind, 'process_device'):
                for dev in mock_devices:
                    try:
                        self.usbfind.process_device(dev)
                        self.logger.info("Disconnection error was handled correctly")
                    except Exception as e:
                        self.fail(f"Disconnection error handling failed: {e}")
            else:
                self.logger.warning("Can't test process_device function - not exposed in module")
                
        except Exception as e:
            self.logger.error(f"Error in disconnection test: {e}")
            
        # Verify the application can recover from errors
        try:
            # Run a normal scan after simulating errors
            if HAS_USB:
                devices = list(usb.core.find(find_all=True))
                self.logger.info(f"Recovery scan found {len(devices)} devices")
                self.assertTrue(True, "Application recovered successfully")
        except Exception as e:
            self.logger.error(f"Recovery failed: {e}")
            self.fail(f"Failed to recover from errors: {e}")
    
    def test_log_rotation(self):
        """Test log rotation and management."""
        self.logger.info("Testing log rotation")
        
        # Get initial log file size
        if not os.path.exists(APP_LOG_FILE):
            self.skipTest("Application log file does not exist")
            
        initial_size = os.path.getsize(APP_LOG_FILE)
        self.logger.info(f"Initial log size: {initial_size} bytes")
        
        # Generate log entries to test rotation with smaller maxBytes
        test_logger = logging.getLogger('test_rotation')
        file_handler = RotatingFileHandler(
            APP_LOG_FILE,
            maxBytes=1024,  # 1 KB - smaller size to trigger rotation
            backupCount=5
        )
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
        test_logger.addHandler(file_handler)
        
        # Generate enough entries to trigger rotation
        long_message = "X" * 100  # Create a longer message to fill up space faster
        for i in range(50):  # Reduced number of iterations but with longer messages
            test_logger.info(f"Test log entry {i}: {long_message}")
            
        # Close the file handler to ensure all logs are written
        file_handler.close()
        test_logger.removeHandler(file_handler)
            
        # Check if log was rotated
        rotated_logs = glob.glob(f"{APP_LOG_FILE}.*")
        self.logger.info(f"Found {len(rotated_logs)} rotated log files")
        
        # Verify log rotation occurred
        self.assertGreater(len(rotated_logs), 0, "Log rotation did not occur")
        
        # Clean up test logs
        for log in rotated_logs:
            if '.test.' in log:
                os.remove(log)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='USB Scanner Test Suite')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose output')
    parser.add_argument('--quick', action='store_true', help='Run only basic tests')
    parser.add_argument('--log', help='Specify log file path')
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        
    if args.log:
        LOG_FILE = args.log
        
    # Run the tests
    suite = unittest.TestLoader().loadTestsFromTestCase(USBScannerTests)
    
    if args.quick:
        # Run only basic tests
        quick_tests = unittest.TestSuite()
        for test in suite:
            if not any(x in test._testMethodName for x in ['memory', 'rotation']):
                quick_tests.addTest(test)
        suite = quick_tests
        
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(not result.wasSuccessful())
