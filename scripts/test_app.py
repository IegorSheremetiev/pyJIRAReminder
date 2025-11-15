import os
import sys
import pytest
import tempfile
import subprocess

def test_app_runs_without_errors(tmpdir):
    # Create a temporary config file
    config_path = tmpdir.join("test_config.enc")
    config_path.write("test_config_content")
    
    # Set environment variables
    os.environ["CONFIG_ENC_PATH"] = str(config_path)
    os.environ["LOCK_PATH"] = str(tmpdir.join("lockfile"))
    
    # Run the app
    result = subprocess.run(
        [sys.executable, "src/jira_reminder/app.py", "--logging"],
        capture_output=True, text=True
    )
    
    assert result.returncode == 0
    assert "Starting Jira Reminder" in result.stderr

def test_single_instance_or_exit(tmpdir):
    # First instance
    proc1 = subprocess.Popen(
        [sys.executable, "src/jira_reminder/app.py"],
        env=os.environ.copy()
    )
    
    # Second instance should exit
    proc2 = subprocess.Popen(
        [sys.executable, "src/jira_reminder/app.py"],
        env=os.environ.copy(),
        stderr=subprocess.PIPE
    )
    
    stderr = proc2.stderr.read()
    assert "Application is already running." in stderr
    proc2.wait()
    assert proc2.returncode != 0
    
    # Clean up
    proc1.terminate()
    proc2.terminate()

if __name__ == "__main__":
    pytest.main([__file__])
