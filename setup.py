from setuptools import setup, find_packages
import os
from setuptools.command.test import test as TestCommand
import sys

# Read the version from __init__.py
def get_version():
    version_file = os.path.join(os.path.dirname(__file__), "smard_utils", "__init__.py")
    with open(version_file, "r") as f:
        for line in f:
            if line.startswith("__version__"):
                delim = '"' if '"' in line else "'"
                return line.split(delim)[1]
    raise RuntimeError("Unable to find version string.")

class PyTest(TestCommand):
    user_options = []

    def initialize_options(self):
        TestCommand.initialize_options(self)

    def finalize_options(self):
        TestCommand.finalize_options(self)
        self.test_args = []
        self.test_suite = True

    def run_tests(self):
        import pytest
        errno = pytest.main(self.test_args)
        sys.exit(errno)

setup(
    name="smard-utils",
    version=get_version(),
    packages=find_packages(),
    install_requires=[
        "pandas",
        "numpy",
        "matplotlib",
        "seaborn",
    ],
    tests_require=["pytest","pytest-cov"],
    cmdclass={"test": PyTest},
    entry_points={
        "console_scripts": [
            "smard=smard_utils.smard_analyse:main",
            "biobatsys=smard_utils.biobatsys:main",
            "solbatsys=smard_utils.solbatsys:main",
            "senec=smard_utils.senec_analyes:main",
        ],
    },
    author="Eduard Moser",
    author_email="eduard.moser@gmx.de",
    description="Utilities for the Marktstammdatenregister",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/fritzthekid/smard-utils",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
)
