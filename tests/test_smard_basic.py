import os
import sys
import re
import pytest
import matplotlib.pyplot as plt

sys.path.append(f"{os.path.dirname(os.path.abspath(__file__))}/..")

from smard_utils.smard_analyse import Analyse
from smard_utils.smard_analyse import main as smart_main
from smard_utils.biobatsys import main as biobatsys_main
from smard_utils.solbatsys import main as solbatsys_main
from smard_utils.senec_analyes import main as senec_main

test_dir = os.path.dirname(os.path.abspath(__file__))

def test_basic():
    simple=Analyse()
    assert simple is not None

def test_smart_main():
    smart_main({"pytest_path":f"{test_dir}/tmp"})

def test_biosatsys_main():
    biobatsys_main({"pytest_path":f"{test_dir}/tmp"})

def test_solbatsys_main():
    solbatsys_main({"pytest_path":f"{test_dir}/tmp"})

def test_senec_main():
    senec_main({"pytest_path":f"{test_dir}/tmp"})
    senec_main({"pytest_path":f"{test_dir}/tmp","file_path":f"{test_dir}/../data/senec_data/2020-combine.csv"})
