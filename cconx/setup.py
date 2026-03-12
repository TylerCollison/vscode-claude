from setuptools import setup, find_packages

setup(
    name="cconx",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "docker>=6.0.0",
        "pyyaml>=6.0.0",
    ],
    python_requires=">=3.8",
    entry_points={
        'console_scripts': [
            'cconx=cconx.cli:main',
        ],
    },
)