#!/bin/bash
echo "Installing vsclaude..."

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install package
pip install -e .

echo "Installation complete. Run: source venv/bin/activate"
echo "Then use: vsclaude --help"