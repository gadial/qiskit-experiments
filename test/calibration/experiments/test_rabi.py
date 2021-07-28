# This code is part of Qiskit.
#
# (C) Copyright IBM 2021.
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE.txt file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.

"""Test Rabi amplitude Experiment class."""

from typing import Tuple
import numpy as np

from qiskit import QuantumCircuit, execute, transpile
from qiskit.exceptions import QiskitError
from qiskit.circuit import Parameter
from qiskit.providers.basicaer import QasmSimulatorPy
from qiskit.test import QiskitTestCase
from qiskit.qobj.utils import MeasLevel
import qiskit.pulse as pulse

from qiskit_experiments.framework import ExperimentData, ParallelExperiment
from qiskit_experiments.library import Rabi, EFRabi

from qiskit_experiments.library.calibration.analysis.oscillation_analysis import OscillationAnalysis
from qiskit_experiments.data_processing.data_processor import DataProcessor
from qiskit_experiments.data_processing.nodes import Probability
from qiskit_experiments.test.mock_iq_backend import MockIQBackend


class RabiBackend(MockIQBackend):
    """A simple and primitive backend, to be run by the Rabi tests."""

    def __init__(
        self,
        iq_cluster_centers: Tuple[float, float, float, float] = (1.0, 1.0, -1.0, -1.0),
        iq_cluster_width: float = 1.0,
        amplitude_to_angle: float = np.pi,
    ):
        """Initialize the rabi backend."""
        self._amplitude_to_angle = amplitude_to_angle

        super().__init__(iq_cluster_centers, iq_cluster_width)

    @property
    def rabi_rate(self) -> float:
        """Returns the rabi rate."""
        return self._amplitude_to_angle / np.pi

    def _compute_probability(self, circuit: QuantumCircuit) -> float:
        """Returns the probability based on the rotation angle and amplitude_to_angle."""
        amp = next(iter(circuit.calibrations["Rabi"].keys()))[1][0]
        return np.sin(self._amplitude_to_angle * amp) ** 2


class TestRabiEndToEnd(QiskitTestCase):
    """Test the rabi experiment."""

    def test_rabi_end_to_end(self):
        """Test the Rabi experiment end to end."""

        test_tol = 0.01
        backend = RabiBackend()

        rabi = Rabi(1)
        rabi.set_experiment_options(amplitudes=np.linspace(-0.95, 0.95, 21))
        expdata = rabi.run(backend)
        expdata.block_for_results()
        result = expdata.analysis_results(0)

        self.assertEqual(result.quality, "good")
        self.assertTrue(abs(result.value.value[1] - backend.rabi_rate) < test_tol)

        backend = RabiBackend(amplitude_to_angle=np.pi / 2)

        rabi = Rabi(1)
        rabi.set_experiment_options(amplitudes=np.linspace(-0.95, 0.95, 21))
        expdata = rabi.run(backend)
        expdata.block_for_results()
        result = expdata.analysis_results(0)
        self.assertEqual(result.quality, "good")
        self.assertTrue(abs(result.value.value[1] - backend.rabi_rate) < test_tol)

        backend = RabiBackend(amplitude_to_angle=2.5 * np.pi)

        rabi = Rabi(1)
        rabi.set_experiment_options(amplitudes=np.linspace(-0.95, 0.95, 101))
        expdata = rabi.run(backend)
        expdata.block_for_results()
        result = expdata.analysis_results(0)
        self.assertEqual(result.quality, "good")
        self.assertTrue(abs(result.value.value[1] - backend.rabi_rate) < test_tol)

    def test_wrong_processor(self):
        """Test that we can override the data processing by giving a faulty data processor."""

        backend = RabiBackend()

        rabi = Rabi(1)

        fail_key = "fail_key"

        rabi.set_analysis_options(data_processor=DataProcessor(fail_key, []))
        rabi.set_run_options(shots=2)
        data = rabi.run(backend)
        data.block_for_results()
        result = data.analysis_results(0)

        self.assertTrue(f"The input key {fail_key} was not found" in result.extra["error_message"])


class TestEFRabi(QiskitTestCase):
    """Test the ef_rabi experiment."""

    def test_ef_rabi_end_to_end(self):
        """Test the EFRabi experiment end to end."""

        test_tol = 0.01
        backend = RabiBackend()
        qubit = 0

        # Note that the backend is not sophisticated enough to simulate an e-f
        # transition so we run the test with a tiny frequency shift, still driving the e-g transition.
        freq_shift = 0.01
        rabi = EFRabi(qubit)
        rabi.set_experiment_options(frequency_shift=freq_shift)
        rabi.set_experiment_options(amplitudes=np.linspace(-0.95, 0.95, 21))
        expdata = rabi.run(backend)
        expdata.block_for_results()
        result = expdata.analysis_results(0)
        result_data = result.extra

        self.assertEqual(result.quality, "good")
        self.assertTrue(abs(result_data["popt"][1] - backend.rabi_rate) < test_tol)

    def test_ef_rabi_circuit(self):
        """Test the EFRabi experiment end to end."""
        anharm = -330e6
        rabi12 = EFRabi(2)
        rabi12.set_experiment_options(amplitudes=[0.5], frequency_shift=anharm)
        circ = rabi12.circuits(RabiBackend())[0]

        with pulse.build() as expected:
            pulse.shift_frequency(anharm, pulse.DriveChannel(2))
            pulse.play(pulse.Gaussian(160, 0.5, 40), pulse.DriveChannel(2))
            pulse.shift_frequency(-anharm, pulse.DriveChannel(2))

        self.assertEqual(circ.calibrations["Rabi"][((2,), (0.5,))], expected)
        self.assertEqual(circ.data[0][0].name, "x")
        self.assertEqual(circ.data[1][0].name, "Rabi")


class TestRabiCircuits(QiskitTestCase):
    """Test the circuits generated by the experiment and the options."""

    def test_default_schedule(self):
        """Test the default schedule."""

        rabi = Rabi(2)
        rabi.set_experiment_options(amplitudes=[0.5])
        circs = rabi.circuits(RabiBackend())

        with pulse.build() as expected:
            pulse.play(pulse.Gaussian(160, 0.5, 40), pulse.DriveChannel(2))

        self.assertEqual(circs[0].calibrations["Rabi"][((2,), (0.5,))], expected)
        self.assertEqual(len(circs), 1)

    def test_user_schedule(self):
        """Test the user given schedule."""

        amp = Parameter("my_double_amp")
        with pulse.build() as my_schedule:
            pulse.play(pulse.Drag(160, amp, 40, 10), pulse.DriveChannel(2))
            pulse.play(pulse.Drag(160, amp, 40, 10), pulse.DriveChannel(2))

        rabi = Rabi(2)
        rabi.set_experiment_options(schedule=my_schedule, amplitudes=[0.5])
        circs = rabi.circuits(RabiBackend())

        assigned_sched = my_schedule.assign_parameters({amp: 0.5}, inplace=False)
        self.assertEqual(circs[0].calibrations["Rabi"][((2,), (0.5,))], assigned_sched)


class TestRabiAnalysis(QiskitTestCase):
    """Class to test the fitting."""

    def simulate_experiment_data(self, thetas, amplitudes, shots=1024):
        """Generate experiment data for Rx rotations with an arbitrary amplitude calibration."""
        circuits = []
        for theta in thetas:
            qc = QuantumCircuit(1)
            qc.rx(theta, 0)
            qc.measure_all()
            circuits.append(qc)

        sim = QasmSimulatorPy()
        result = execute(circuits, sim, shots=shots, seed_simulator=10).result()
        data = [
            {
                "counts": self._add_uncertainty(result.get_counts(i)),
                "metadata": {
                    "xval": amplitudes[i],
                    "meas_level": MeasLevel.CLASSIFIED,
                    "meas_return": "avg",
                },
            }
            for i, theta in enumerate(thetas)
        ]
        return data

    @staticmethod
    def _add_uncertainty(counts):
        """Ensure that we always have a non-zero sigma in the test."""
        for label in ["0", "1"]:
            if label not in counts:
                counts[label] = 1

        return counts

    def test_good_analysis(self):
        """Test the Rabi analysis."""
        experiment_data = ExperimentData()

        thetas = np.linspace(-np.pi, np.pi, 31)
        amplitudes = np.linspace(-0.25, 0.25, 31)
        expected_rate, test_tol = 2.0, 0.2

        experiment_data.add_data(self.simulate_experiment_data(thetas, amplitudes, shots=400))

        data_processor = DataProcessor("counts", [Probability(outcome="1")])

        result = OscillationAnalysis().run(
            experiment_data, data_processor=data_processor, plot=False
        )

        self.assertEqual(result[0].quality, "good")
        self.assertTrue(abs(result[0].value.value[1] - expected_rate) < test_tol)

    def test_bad_analysis(self):
        """Test the Rabi analysis."""
        experiment_data = ExperimentData()

        thetas = np.linspace(0.0, np.pi / 4, 31)
        amplitudes = np.linspace(0.0, 0.95, 31)

        experiment_data.add_data(self.simulate_experiment_data(thetas, amplitudes, shots=200))

        data_processor = DataProcessor("counts", [Probability(outcome="1")])

        result = OscillationAnalysis().run(
            experiment_data, data_processor=data_processor, plot=False
        )

        self.assertEqual(result[0].quality, "bad")


class TestCompositeExperiment(QiskitTestCase):
    """Test composite Rabi experiment."""

    def test_calibrations(self):
        """Test that the calibrations are preserved and that the circuit transpiles."""

        experiments = []
        for qubit in range(3):
            rabi = Rabi(qubit)
            rabi.set_experiment_options(amplitudes=[0.5])
            experiments.append(rabi)

        par_exp = ParallelExperiment(experiments)
        par_circ = par_exp.circuits()[0]

        # If the calibrations are not there we will not be able to transpile
        try:
            transpile(par_circ, basis_gates=["rz", "sx", "x", "cx"])
        except QiskitError as error:
            self.fail("Failed to transpile with error: " + str(error))

        # Assert that the calibration keys are in the calibrations of the composite circuit.
        for qubit in range(3):
            rabi_circuit = experiments[qubit].circuits()[0]
            cal_key = next(iter(rabi_circuit.calibrations["Rabi"].keys()))

            self.assertEqual(cal_key[0], (qubit,))
            self.assertTrue(cal_key in par_circ.calibrations["Rabi"])
