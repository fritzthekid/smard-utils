"""
Base analysis system ABC.

All four application classes (BioBatSys, SolBatSys, SmardAnalyseSys,
HomeBatSys) share the same run-loop structure.  A common abstract base
class lets the webapp treat them uniformly (L1) and expresses the shared
contract explicitly (L, D principles).
"""

from abc import ABC, abstractmethod
from concurrent.futures import ProcessPoolExecutor


class BaseAnalysisSys(ABC):
    """
    Abstract base for battery analysis systems.

    Subclasses implement _run_one() and run_analysis(); the base class
    provides the shared _make_executor() factory (D4).

    Attributes:
        basic_data_set (dict): Configuration dictionary.
        driver:               EnergyDriver instance (injectable, D2/D3).
        strategy:             BMSStrategy instance (injectable, D2/D3).
        results_df:           Final results DataFrame (set by run_analysis).
    """

    basic_data_set: dict

    @abstractmethod
    def _run_one(self, capacity, power) -> dict:
        """
        Run a single simulation and return a result dict.

        Args:
            capacity: Battery capacity (units depend on subclass)
            power:    Battery power  (units depend on subclass)

        Returns:
            Dict with at least capacity and power keys plus metric keys.
        """

    @abstractmethod
    def run_analysis(self, capacity_list=None, power_list=None):
        """
        Run analysis for all capacity/power combinations.

        Args:
            capacity_list: Iterable of capacities.
            power_list:    Iterable of powers (same length as capacity_list).
        """

    def _make_executor(self, n_workers: int) -> ProcessPoolExecutor:
        """
        Create a ProcessPoolExecutor (overridable for testing, D4).

        Args:
            n_workers: Maximum number of parallel workers.

        Returns:
            A ProcessPoolExecutor context manager.
        """
        return ProcessPoolExecutor(max_workers=n_workers)
