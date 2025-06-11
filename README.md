# Sims-Attack C2 Framework

A Command and Control (C2) framework for penetration testing and attack simulations. This project consists of a web-based C2 server and a botnet implant for Windows systems.

## Components

### C2 Server
- Web-based interface for managing implants
- Real-time command execution
- File transfer capabilities
- Screenshot capture and viewing
- Domain spread configuration
- Victim machine management

### Botnet Implant
- Standalone Windows executable
- Command execution
- File operations
- Screenshot capture
- Domain spread capabilities
- Secure communication with C2

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure the C2 server:
- Copy `.env.example` to `.env`
- Update the configuration variables

3. Run the C2 server:
```bash
python c2_server/app.py
```

4. Generate the implant:
```bash
python build_implant.py
```

## Security Notice

This tool is designed for authorized penetration testing and security research only. Always:
- Obtain proper authorization before testing
- Follow responsible disclosure practices
- Comply with applicable laws and regulations
- Use only in controlled environments

## Project Structure

```
sims-attack/
├── c2_server/           # C2 server application
│   ├── app.py          # Main server application
│   ├── static/         # Static files (CSS, JS)
│   └── templates/      # HTML templates
├── implant/            # Botnet implant code
│   ├── implant.py      # Main implant code
│   └── utils/          # Utility functions
├── build_implant.py    # Script to build the implant
├── requirements.txt    # Project dependencies
└── README.md          # This file
```

## Features

### C2 Server
- Web-based dashboard
- Real-time implant management
- Secure communication
- File transfer
- Command execution
- Screenshot capture
- Domain spread configuration

### Implant
- Standalone executable
- Command execution
- File operations
- Screenshot capture
- Domain spread
- Persistence mechanisms
- Anti-detection features

## License

This project is licensed under the MIT License - see the LICENSE file for details. 