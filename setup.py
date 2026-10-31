from setuptools import setup, find_packages

setup(
    name="tanks-tactic",
    version="1.0.0",
    description="Battle City Tank Tactics - RTS & Micro Control Tank Game with AoE2 Scenario Editor",
    packages=find_packages(exclude=["tests*", "webui/static*"]),
    py_modules=["tanks", "editor"],
    install_requires=[
        "PyQt5>=5.15.0",
        "PyYAML>=6.0",
    ],
    entry_points={
        "console_scripts": [
            "tanks-game=tanks:main",
            "tanks-editor=editor.main:main",
        ],
    },
    python_requires=">=3.9",
)
