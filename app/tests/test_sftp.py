#!/usr/bin/env python3
"""
SFTP Upload Test Script

Tests SFTP connectivity and file upload functionality.
Run with: python app/tests/test_sftp.py
"""
import os
import sys
import time
import paramiko
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv()


def test_ssh_banner(host: str, port: int, timeout: int = 10) -> dict:
    """Test if we can read the SSH banner from the server."""
    print(f"\n{'='*60}")
    print(f"1. Testing SSH Banner - {host}:{port}")
    print(f"{'='*60}")

    result = {
        "success": False,
        "banner": None,
        "error": None
    }

    try:
        # Use raw socket to test banner with timeout
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        print(f"   Connecting to {host}:{port}...")

        start_time = time.time()
        sock.connect((host, port))
        connect_time = time.time() - start_time
        print(f"   Connected in {connect_time:.2f}s")

        # Try to read banner
        banner = sock.recv(1024).decode('utf-8', errors='ignore').strip()
        sock.close()

        result["success"] = True
        result["banner"] = banner
        print(f"   Banner received:")
        print(f"   {banner}")

    except socket.timeout:
        result["error"] = f"Connection timeout after {timeout}s"
        print(f"   TIMEOUT: No response after {timeout}s")
    except ConnectionRefusedError:
        result["error"] = "Connection refused"
        print(f"   REFUSED: Server is not accepting connections")
    except Exception as e:
        result["error"] = str(e)
        print(f"   ERROR: {e}")

    return result


def test_sftp_connection(host: str, port: int, username: str, password: str) -> dict:
    """Test SFTP connection with proper timeout."""
    print(f"\n{'='*60}")
    print(f"2. Testing SFTP Connection")
    print(f"{'='*60}")
    print(f"   Host: {host}")
    print(f"   Port: {port}")
    print(f"   User: {username}")

    result = {
        "success": False,
        "error": None,
        "server_type": None
    }

    try:
        # Create SSH client with timeout
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        print(f"   Connecting...")
        start_time = time.time()

        # Connect with explicit timeout
        ssh.connect(
            hostname=host,
            port=port,
            username=username,
            password=password,
            timeout=15,
            banner_timeout=15,
            auth_timeout=15
        )

        connect_time = time.time() - start_time
        print(f"   Connected in {connect_time:.2f}s")

        # Get server info
        transport = ssh.get_transport()
        if transport:
            result["server_type"] = transport.remote_version
            print(f"   Server: {result['server_type']}")

        # Try to open SFTP
        print(f"   Opening SFTP subsystem...")
        sftp = ssh.open_sftp()
        print(f"   SFTP opened successfully")

        # List remote directory
        remote_path = os.getenv("REMOTE_PATH", "/").rstrip("/")
        try:
            files = sftp.listdir(remote_path)
            print(f"   Remote directory '{remote_path}' has {len(files)} items")
        except IOError:
            print(f"   Remote directory '{remote_path}' not found (will be created)")

        sftp.close()
        ssh.close()

        result["success"] = True
        print(f"   SUCCESS: All tests passed")

    except paramiko.ssh_exception.SSHException as e:
        result["error"] = f"SSH Error: {e}"
        print(f"   SSH ERROR: {e}")
    except paramiko.ssh_exception.AuthenticationException:
        result["error"] = "Authentication failed"
        print(f"   AUTH ERROR: Username or password incorrect")
    except TimeoutError:
        result["error"] = "Connection timeout"
        print(f"   TIMEOUT: Server did not respond in time")
    except Exception as e:
        result["error"] = str(e)
        print(f"   ERROR: {e}")

    return result


def test_sftp_upload(host: str, port: int, username: str, password: str,
                     local_file: str, remote_filename: str) -> dict:
    """Test actual file upload to SFTP."""
    print(f"\n{'='*60}")
    print(f"3. Testing SFTP File Upload")
    print(f"{'='*60}")

    # Expand user path
    local_file = os.path.expanduser(local_file)

    # Create test file if it doesn't exist
    if not os.path.exists(local_file):
        print(f"   Creating test file: {local_file}")
        Path(local_file).parent.mkdir(parents=True, exist_ok=True)
        with open(local_file, 'w') as f:
            f.write(f"SFTP Test File\nCreated: {datetime.now()}\n")

    print(f"   Local file: {local_file}")
    print(f"   Remote filename: {remote_filename}")

    result = {
        "success": False,
        "error": None,
        "remote_path": None
    }

    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        ssh.connect(
            hostname=host,
            port=port,
            username=username,
            password=password,
            timeout=15,
            banner_timeout=15
        )

        sftp = ssh.open_sftp()

        # Create remote directory structure
        remote_base = os.getenv("REMOTE_PATH", "/").rstrip("/")
        remote_full_path = f"{remote_base}/{remote_filename}"

        print(f"   Uploading to: {remote_full_path}")
        sftp.put(local_file, remote_full_path)

        # Verify upload
        try:
            attr = sftp.stat(remote_full_path)
            print(f"   File uploaded successfully")
            print(f"   Size: {attr.st_size} bytes")
        except IOError as e:
            print(f"   Warning: Could not verify upload: {e}")

        sftp.close()
        ssh.close()

        result["success"] = True
        result["remote_path"] = remote_full_path
        print(f"   SUCCESS: File uploaded")

    except Exception as e:
        result["error"] = str(e)
        print(f"   ERROR: {e}")

    return result


def main():
    print("\n" + "="*60)
    print("SFTP Upload Test Suite")
    print("="*60)

    # Get configuration
    host = os.getenv("SFTP_HOST")
    port = int(os.getenv("SFTP_PORT", "22"))
    username = os.getenv("SFTP_USER")
    password = os.getenv("SFTP_PASS")

    print(f"\nConfiguration:")
    print(f"  SFTP_HOST: {host}")
    print(f"  SFTP_PORT: {port}")
    print(f"  SFTP_USER: {username}")
    print(f"  SFTP_PASS: {password}")
    print(f"  REMOTE_PATH: {os.getenv('REMOTE_PATH', 'NOT SET')}")

    # Validate config
    if not all([host, port, username, password]):
        print("\nERROR: Missing SFTP configuration in .env file")
        print("Required: SFTP_HOST, SFTP_PORT, SFTP_USER, SFTP_PASS")
        return False

    # Run tests
    results = {}

    # Test 1: SSH Banner
    results["banner"] = test_ssh_banner(host, port)

    # Test 2: SFTP Connection
    results["connection"] = test_sftp_connection(host, port, username, password)

    # Test 3: File Upload (only if connection succeeded)
    if results["connection"]["success"]:
        test_filename = f"sftp_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        test_local_file = "~/settlements/test.txt"
        results["upload"] = test_sftp_upload(
            host, port, username, password,
            test_local_file, test_filename
        )
    else:
        results["upload"] = {"success": False, "error": "Skipped due to connection failure"}

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"  SSH Banner Test:      {'PASS' if results['banner']['success'] else 'FAIL'}")
    print(f"  SFTP Connection Test: {'PASS' if results['connection']['success'] else 'FAIL'}")
    print(f"  File Upload Test:     {'PASS' if results['upload']['success'] else 'FAIL'}")
    print(f"{'='*60}\n")

    # Recommendations
    if not results["banner"]["success"]:
        print("\nRECOMMENDATIONS:")
        print("  1. Check if the SFTP server is running")
        print("  2. Verify the host and port are correct")
        print(f"     Try: telnet {host} {port}")
        print("  3. Check firewall rules")
        print("  4. Verify FRP tunnel (vicp.io) is active")
    elif not results["connection"]["success"]:
        print("\nRECOMMENDATIONS:")
        print("  1. Verify username and password are correct")
        print("  2. Check if user has SFTP permissions")
        print("  3. Review server logs for authentication failures")

    return all(r["success"] for r in results.values())


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
