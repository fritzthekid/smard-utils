import os
import sys
import re
import pytest
import matplotlib.pyplot as plt

sys.path.append(f"{os.path.dirname(os.path.abspath(__file__))}/..")

from smard_utils.smard_analyse import Analyse
from smard_utils.smard_analyse import main

def test_basic():
    simple=Analyse()
    assert simple is not None

def test_main():
    # plt.ioff()
    main()

