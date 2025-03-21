import pytest
import os
import sys

@pytest.fixture(scope="session")
def test_env():
    """Setup test environment variables"""
    old_env = dict(os.environ)
    os.environ.update({
        "TEST_MODE": "1",
        "USB_SCANNER_TEST": "1"
    })
    yield
    os.environ.clear()
    os.environ.update(old_env)

@pytest.fixture(scope="session")
def test_paths():
    """Setup test paths"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    test_data_dir = os.path.join(base_dir, "tests", "data")
    
    if not os.path.exists(test_data_dir):
        os.makedirs(test_data_dir)
        
    return {
        "base_dir": base_dir,
        "test_data_dir": test_data_dir
    }

