import os
import sys
import subprocess

def main():
    """
    Entry point for LLM-Cosmos.
    Launches the Streamlit visualization application.
    """
    # Get the absolute path to the app.py file
    base_dir = os.path.dirname(os.path.abspath(__file__))
    app_path = os.path.join(base_dir, "viz", "app.py")
    
    print(f"🌌 Launching LLM-Cosmos...")
    print(f"📂 App Path: {app_path}")
    
    # Run streamlit as a module
    try:
        subprocess.run([sys.executable, "-m", "streamlit", "run", app_path], check=True)
    except KeyboardInterrupt:
        print("\n👋 LLM-Cosmos stopped.")
    except Exception as e:
        print(f"❌ Error launching application: {e}")

if __name__ == "__main__":
    main()
