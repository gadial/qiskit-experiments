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

"""Test drag calibration experiment."""

import numpy as np

from qiskit.test import QiskitTestCase
from qiskit.circuit import Parameter
from qiskit.pulse import DriveChannel, Drag
import qiskit.pulse as pulse
from qiskit.qobj.utils import MeasLevel
from qiskit import transpile

from qiskit_experiments.exceptions import CalibrationError
from qiskit_experiments.library import DragCal
from qiskit_experiments.test.mock_iq_backend import DragBackend


class TestDragEndToEnd(QiskitTestCase):
    """Test the drag experiment."""

    def setUp(self):
        """Setup some schedules."""
        super().setUp()

        beta = Parameter("β")

        with pulse.build(name="xp") as xp:
            pulse.play(Drag(duration=160, amp=0.208519, sigma=40, beta=beta), DriveChannel(0))

        with pulse.build(name="xm") as xm:
            pulse.play(Drag(duration=160, amp=-0.208519, sigma=40, beta=beta), DriveChannel(0))

        self.x_minus = xm
        self.x_plus = xp

    def test_end_to_end(self):
        """Test the drag experiment end to end."""

        test_tol = 0.05
        backend = DragBackend()

        drag = DragCal(1)

        drag.set_experiment_options(rp=self.x_plus, rm=self.x_minus)
        expdata = drag.run(backend)
        expdata.block_for_results()
        result = expdata.analysis_results(0)
        result_data = result.extra

        self.assertTrue(abs(result_data["popt"][4] - backend.ideal_beta) < test_tol)
        self.assertEqual(result.quality, "good")

        # Small leakage will make the curves very flat.
        backend = DragBackend(leakage=0.005)

        drag = DragCal(0)
        drag.set_analysis_options(p0={"beta": 1.2})
        drag.set_experiment_options(rp=self.x_plus, rm=self.x_minus)
        drag.set_run_options(meas_level=MeasLevel.KERNELED)
        exp_data = drag.run(backend)
        exp_data.block_for_results()
        result = exp_data.analysis_results(0)
        result_data = result.extra

        meas_level = exp_data.metadata()["job_metadata"][-1]["run_options"]["meas_level"]

        self.assertEqual(meas_level, MeasLevel.KERNELED)
        self.assertTrue(abs(result_data["popt"][4] - backend.ideal_beta) < test_tol)
        self.assertEqual(result.quality, "good")

        # Large leakage will make the curves oscillate quickly.
        backend = DragBackend(leakage=0.05)

        drag = DragCal(1)
        drag.set_run_options(shots=200)
        drag.set_experiment_options(betas=np.linspace(-4, 4, 31))
        drag.set_analysis_options(p0={"beta": 1.8, "freq0": 0.08, "freq1": 0.16, "freq2": 0.32})
        drag.set_experiment_options(rp=self.x_plus, rm=self.x_minus)
        exp_data = drag.run(backend)
        exp_data.block_for_results()
        result = exp_data.analysis_results(0)
        result_data = result.extra

        meas_level = exp_data.metadata()["job_metadata"][-1]["run_options"]["meas_level"]

        self.assertEqual(meas_level, MeasLevel.CLASSIFIED)
        self.assertTrue(abs(result_data["popt"][4] - backend.ideal_beta) < test_tol)
        self.assertEqual(result.quality, "good")


class TestDragCircuits(QiskitTestCase):
    """Test the circuits of the drag calibration."""

    def test_default_circuits(self):
        """Test the default circuit."""

        backend = DragBackend(leakage=0.005)

        drag = DragCal(0)
        drag.set_experiment_options(reps=[2, 4, 8])
        circuits = drag.circuits(DragBackend())

        for idx, expected in enumerate([4, 8, 16]):
            ops = transpile(circuits[idx * 51], backend).count_ops()
            self.assertEqual(ops["Rp"] + ops["Rm"], expected)

    def test_raise_multiple_parameter(self):
        """Check that the experiment raises with unassigned parameters."""

        beta = Parameter("β")
        amp = Parameter("amp")

        with pulse.build(name="xp") as xp:
            pulse.play(Drag(duration=160, amp=amp, sigma=40, beta=beta), DriveChannel(0))

        with pulse.build(name="xm") as xm:
            pulse.play(Drag(duration=160, amp=-amp, sigma=40, beta=beta), DriveChannel(0))

        backend = DragBackend(leakage=0.05)

        drag = DragCal(1)
        drag.set_experiment_options(betas=np.linspace(-3, 3, 21))
        drag.set_experiment_options(rp=xp, rm=xm)

        with self.assertRaises(CalibrationError):
            drag.run(backend).analysis_results(0)

    def test_raise_inconsistent_parameter(self):
        """Check that the experiment raises with unassigned parameters."""

        beta1 = Parameter("β")
        beta2 = Parameter("β")

        with pulse.build(name="xp") as xp:
            pulse.play(Drag(duration=160, amp=0.2, sigma=40, beta=beta1), DriveChannel(0))

        with pulse.build(name="xm") as xm:
            pulse.play(Drag(duration=160, amp=-0.2, sigma=40, beta=beta2), DriveChannel(0))

        backend = DragBackend(leakage=0.05)

        drag = DragCal(1)
        drag.set_experiment_options(betas=np.linspace(-3, 3, 21))
        drag.set_experiment_options(rp=xp, rm=xm)

        with self.assertRaises(CalibrationError):
            drag.run(backend).analysis_results(0)


class TestDragOptions(QiskitTestCase):
    """Test non-trivial options."""

    def test_reps(self):
        """Test that setting reps raises and error if reps is not of length three."""

        drag = DragCal(0)

        with self.assertRaises(CalibrationError):
            drag.set_experiment_options(reps=[1, 2, 3, 4])
