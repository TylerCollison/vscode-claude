"""Setup script for build-env package."""

from setuptools import setup, find_packages

setup(
    name="build-env",
    version="0.1.0",
    description="Persistent Docker container environments for build commands",
    packages=find_packages(),
    install_requires=[
        "docker>=6.0.0",
    ],
    python_requires=">=3.8",
    entry_points={
        "console_scripts": [
            "build-env=build_env_cli:main",
        ],
    },
    py_modules=['build_env', 'build_env_cli', 'security'],
    author="Claude Code",
    author_email="noreply@anthropic.com",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Build Tools",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    keywords="docker build environment container",
    project_urls={
        "Source": "https://github.com/anthropic/cconx/tree/main/build-env",
    },
)