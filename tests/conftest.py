import pytest
import os
from cloudra.session_class import Session
from datetime import datetime

@pytest.fixture
def mock_session(tmp_path):
    session_path = tmp_path / "test_session.json"
    return Session(id="test-session", path=str(session_path))

@pytest.fixture
def project_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
