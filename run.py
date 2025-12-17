"""
WiFi Gaming Monitor - Launcher
Starts both the web dashboard and desktop overlay
"""

import subprocess
import sys
import os
import time
import webbrowser
from threading import Thread

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def run_web_server():
    """Start the Flask web server"""
    from app import start_server
    start_server(host='127.0.0.1', port=5555)


def run_overlay():
    """Start the desktop overlay"""
    from overlay import main
    main()


def main():
    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║            WiFi Gaming Monitor v1.0                       ║
    ║                                                           ║
    ║   Professional Network Diagnostics for Gaming             ║
    ╚═══════════════════════════════════════════════════════════╝
    """)

    print("Select mode:")
    print("  1. Web Dashboard only")
    print("  2. Desktop Overlay only")
    print("  3. Both (Web + Overlay)")
    print()

    choice = input("Enter choice (1/2/3) [default: 1]: ").strip() or "1"

    if choice == "1":
        print("\nStarting Web Dashboard...")
        print("Opening http://127.0.0.1:5555 in browser...")
        time.sleep(1)
        webbrowser.open('http://127.0.0.1:5555')
        run_web_server()

    elif choice == "2":
        print("\nStarting Desktop Overlay...")
        run_overlay()

    elif choice == "3":
        print("\nStarting Web Dashboard and Desktop Overlay...")

        # Start web server in background thread
        web_thread = Thread(target=run_web_server, daemon=True)
        web_thread.start()

        time.sleep(2)
        webbrowser.open('http://127.0.0.1:5555')

        # Run overlay in main thread (Tkinter requirement)
        run_overlay()

    else:
        print("Invalid choice. Starting web dashboard...")
        run_web_server()


if __name__ == '__main__':
    main()
