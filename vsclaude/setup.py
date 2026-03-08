from setuptools import setup, find_packages

setup(
    name="vsclaude",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "docker>=6.0.0",
    ],
    python_requires=">=3.8",
    entry_points={
        'console_scripts': [
            'vsclaude=vsclaude.cli:main',
        ],
    },
)