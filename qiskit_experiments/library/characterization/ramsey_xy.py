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

"""Ramsey XY frequency characterization experiment."""
import warnings
from typing import List, Tuple, Dict, Optional, Sequence

import numpy as np
from qiskit import pulse
from qiskit.circuit import QuantumCircuit, Parameter, Gate
from qiskit.providers.backend import Backend
from qiskit.qobj.utils import MeasLevel

from qiskit_experiments.framework import BaseExperiment, Options, BackendTiming
from qiskit_experiments.framework.restless_mixin import RestlessMixin
from qiskit_experiments.library.characterization.analysis import RamseyXYAnalysis


class RamseyXY(BaseExperiment, RestlessMixin):
    r"""A sign-sensitive experiment to measure the frequency of a qubit.

    # section: overview

        This experiment differs from the :class:`~qiskit_experiments.characterization.\
        t2ramsey.T2Ramsey` since it is sensitive to the sign of the frequency offset from
        the main transition. This experiment consists of following two circuits:

        .. parsed-literal::

            (Ramsey X) The second pulse rotates by pi-half around the X axis

                       ┌────┐┌─────────────┐┌───────┐┌────┐ ░ ┌─┐
                  q_0: ┤ √X ├┤ Delay(τ[s]) ├┤ Rz(θ) ├┤ √X ├─░─┤M├
                       └────┘└─────────────┘└───────┘└────┘ ░ └╥┘
            measure: 1/════════════════════════════════════════╩═
                                                               0

            (Ramsey Y) The second pulse rotates by pi-half around the Y axis

                       ┌────┐┌─────────────┐┌───────────┐┌────┐ ░ ┌─┐
                  q_0: ┤ √X ├┤ Delay(τ[s]) ├┤ Rz(θ-π/2) ├┤ √X ├─░─┤M├
                       └────┘└─────────────┘└───────────┘└────┘ ░ └╥┘
            measure: 1/════════════════════════════════════════════╩═
                                                                   0

        The first and second circuits measure the expectation value along the -Y and X axes,
        respectively. This experiment therefore tracks the dynamics of the Bloch vector
        around the equator. The drive frequency of the control electronics defines a reference frame,
        which differs from the true qubit frequency by :math:`\Delta\omega`.
        The Hamiltonian during the
        ``Delay`` instruction is :math:`H^R = - \frac{1}{2} \Delta\omega` in the rotating frame,
        and the propagator will be :math:`U(\tau) = \exp(-iH^R\tau / \hbar)` where :math:`\tau` is the
        duration of the delay. By scanning this duration, we can get

        .. math::

            {\cal E}_x(\tau)
                = {\rm Re} {\rm Tr}\left( Y U \rho U^\dagger \right)
                &= - \cos(\Delta\omega\tau) = \sin(\Delta\omega\tau - \frac{\pi}{2}), \\
            {\cal E}_y(\tau)
                = {\rm Re} {\rm Tr}\left( X U \rho U^\dagger \right)
                &= \sin(\Delta\omega\tau),

        where :math:`\rho` is prepared by the first :math:`\sqrt{\rm X}` gate. Note that phase
        difference of these two outcomes :math:`{\cal E}_x, {\cal E}_y` depends on the sign and
        the magnitude of the frequency offset :math:`\Delta\omega`. By contrast, the measured
        data in the standard Ramsey experiment does not depend on the sign of :math:`\Delta\omega`,
        because :math:`\cos(-\Delta\omega\tau) = \cos(\Delta\omega\tau)`.

        The experiment also allows users to add a small frequency offset to better resolve
        any oscillations. This is implemented by a virtual Z rotation in the circuits. In the
        circuit above it appears as the delay-dependent angle θ(τ).

    # section: analysis_ref
        :class:`RamseyXYAnalysis`
    """

    @classmethod
    def _default_experiment_options(cls) -> Options:
        """Default values for the Ramsey XY experiment.

        Experiment Options:
            delays (list): The list of delays that will be scanned in the experiment, in seconds.
            osc_freq (float): A frequency shift in Hz that will be applied by means of
                a virtual Z rotation to increase the frequency of the measured oscillation.
        """
        options = super()._default_experiment_options()
        options.delays = np.linspace(0, 1.0e-6, 51)
        options.osc_freq = 2e6

        return options

    def __init__(
        self,
        physical_qubits: Sequence[int],
        backend: Optional[Backend] = None,
        delays: Optional[List] = None,
        osc_freq: float = 2e6,
    ):
        """Create new experiment.

        Args:
            physical_qubits: List containing the qubit on which to run the
                Ramsey XY experiment.
            backend: Optional, the backend to run the experiment on.
            delays: The delays to scan, in seconds.
            osc_freq: the oscillation frequency induced by the user through a virtual
                Rz rotation. This quantity is given in Hz.
        """
        super().__init__(physical_qubits, analysis=RamseyXYAnalysis(), backend=backend)

        if delays is None:
            delays = self.experiment_options.delays
        self.set_experiment_options(delays=delays, osc_freq=osc_freq)

    def _pre_circuit(self) -> QuantumCircuit:
        """Return a preparation circuit.

        This method can be overridden by subclasses e.g. to run on transitions other
        than the 0 <-> 1 transition.
        """
        return QuantumCircuit(1)

    def circuits(self) -> List[QuantumCircuit]:
        """Create the circuits for the Ramsey XY characterization experiment.

        Returns:
            A list of circuits with a variable delay.
        """
        timing = BackendTiming(self.backend)

        p_delay = Parameter("delay")

        rotation_angle = 2 * np.pi * self.experiment_options.osc_freq * p_delay

        if timing.delay_unit == "dt":
            rotation_angle = rotation_angle * timing.dt

        # Create the X and Y circuits.
        metadata = {
            "experiment_type": self._type,
            "qubits": self.physical_qubits,
            "osc_freq": self.experiment_options.osc_freq,
            "unit": "s",
        }

        ram_x = self._pre_circuit()
        ram_x.sx(0)
        ram_x.delay(p_delay, 0, timing.delay_unit)
        ram_x.rz(rotation_angle, 0)
        ram_x.sx(0)
        ram_x.measure_active()
        ram_x.metadata = metadata.copy()

        ram_y = self._pre_circuit()
        ram_y.sx(0)
        ram_y.delay(p_delay, 0, timing.delay_unit)
        ram_y.rz(rotation_angle - np.pi / 2, 0)
        ram_y.sx(0)
        ram_y.measure_active()
        ram_y.metadata = metadata.copy()

        circs = []
        for delay in self.experiment_options.delays:
            assigned_x = ram_x.assign_parameters(
                {p_delay: timing.round_delay(time=delay)}, inplace=False
            )
            assigned_x.metadata["series"] = "X"
            assigned_x.metadata["xval"] = timing.delay_time(time=delay)

            assigned_y = ram_y.assign_parameters(
                {p_delay: timing.round_delay(time=delay)}, inplace=False
            )
            assigned_y.metadata["series"] = "Y"
            assigned_y.metadata["xval"] = timing.delay_time(time=delay)

            circs.extend([assigned_x, assigned_y])

        return circs

    def _finalize(self):
        # Set initial guess for sinusoidal offset when meas level is 2.
        # This returns probability P1 thus offset=0.5 is obvious.
        # This guarantees reasonable fit especially when data contains only less than half cycle.
        meas_level = self.run_options.get("meas_level", MeasLevel.CLASSIFIED)
        if meas_level == MeasLevel.CLASSIFIED:
            init_guess = self.analysis.options.get("p0", {})
            if "base" not in init_guess:
                init_guess["base"] = 0.5
            self.analysis.set_options(p0=init_guess)

    def _metadata(self):
        metadata = super()._metadata()
        # Store measurement level and meas return if they have been
        # set for the experiment
        for run_opt in ["meas_level", "meas_return"]:
            if hasattr(self.run_options, run_opt):
                metadata[run_opt] = getattr(self.run_options, run_opt)
        return metadata


class StarkRamseyXY(BaseExperiment):
    """A sign-sensitive experiment to measure the frequency of a qubit under a pulsed Stark tone.

    # section: overview

        This experiment is a variant of :class:`.RamseyXY` with a pulsed Stark tone
        and consists of the following two circuits:

        .. parsed-literal::

            (Ramsey X)  The pulse before measurement rotates by pi-half around the X axis

                     ┌────┐┌────────┐┌───┐┌───────────────┐┌────────┐┌────┐┌─┐
                  q: ┤ √X ├┤ StarkV ├┤ X ├┤ StarkU(delay) ├┤ Rz(-π) ├┤ √X ├┤M├
                     └────┘└────────┘└───┘└───────────────┘└────────┘└────┘└╥┘
                c: 1/═══════════════════════════════════════════════════════╩═
                                                                            0

            (Ramsey Y) The pulse before measurement rotates by pi-half around the Y axis

                     ┌────┐┌────────┐┌───┐┌───────────────┐┌───────────┐┌────┐┌─┐
                  q: ┤ √X ├┤ StarkV ├┤ X ├┤ StarkU(delay) ├┤ Rz(-3π/2) ├┤ √X ├┤M├
                     └────┘└────────┘└───┘└───────────────┘└───────────┘└────┘└╥┘
                c: 1/══════════════════════════════════════════════════════════╩═
                                                                               0

        In principle, the sequence is a variant of :class:`.RamseyXY` circuit.
        However, the delay in between √X gates is replaced with an off-resonant drive.
        This off-resonant drive shifts the qubit frequency due to the
        Stark effect and causes it to accumulate phase during the
        Ramsey sequence. This frequency shift is a function of the
        offset of the Stark tone frequency from the qubit frequency
        and of the magnitude of the tone.

        Note that the Stark tone pulse (StarkU) takes the form of a flat-topped Gaussian envelope.
        The magnitude of the pulse varies in time during its rising and falling edges.
        It is difficult to characterize the net phase accumulation of the qubit during the
        edges of the pulse when the frequency shift is varying with the pulse amplitude.
        In order to simplify the analysis, an additional pulse (StarkV)
        involving only the edges of StarkU is added to the sequence.
        The sign of the phase accumulation is inverted for StarkV relative to that of StarkU
        by inserting an X gate in between the two pulses.

        This technique allows the experiment to accumulate only the net phase
        during the flat-top part of the StarkU pulse with constant magnitude.

    # section: analysis_ref
        :py:class:`RamseyXYAnalysis`

    # section: see_also
        :class:`qiskit_experiments.library.characterization.ramsey_xy.RamseyXY`

    # section: manual
        :doc:`/manuals/characterization/stark_experiment`

    """

    def __init__(
        self,
        physical_qubits: Sequence[int],
        backend: Optional[Backend] = None,
        **experiment_options,
    ):
        """Create new experiment.

        Args:
            physical_qubits: Index of physical qubit.
            backend: Optional, the backend to run the experiment on.
            experiment_options: Experiment options. See the class documentation or
                ``self._default_experiment_options`` for descriptions.
        """
        self._timing = None

        super().__init__(
            physical_qubits=physical_qubits,
            analysis=RamseyXYAnalysis(),
            backend=backend,
        )
        self.set_experiment_options(**experiment_options)

    @classmethod
    def _default_experiment_options(cls) -> Options:
        """Default experiment options.

        Experiment Options:
            stark_amp (float): A single float parameter to represent the magnitude of Stark tone
                and the sign of expected Stark shift.
                See :ref:`stark_tone_implementation` for details.
            stark_channel (PulseChannel): Pulse channel to apply Stark tones.
                If not provided, the same channel with the qubit drive is used.
                See :ref:`stark_channel_consideration` for details.
            stark_freq_offset (float): Offset of Stark tone frequency from the qubit frequency.
                This offset should be sufficiently large so that the Stark pulse
                does not Rabi drive the qubit.
                See :ref:`stark_frequency_consideration` for details.
            stark_sigma (float): Gaussian sigma of the rising and falling edges
                of the Stark tone, in seconds.
            stark_risefall (float): Ratio of sigma to the duration of
                the rising and falling edges of the Stark tone.
            min_freq (float): Minimum frequency that this experiment is guaranteed to resolve.
                Note that fitter algorithm :class:`.RamseyXYAnalysis` of this experiment
                is still capable of fitting experiment data with lower frequency.
            max_freq (float): Maximum frequency that this experiment can resolve.
            delays (list[float]): The list of delays if set that will be scanned in the
                experiment. If not set, then evenly spaced delays with interval
                computed from ``min_freq`` and ``max_freq`` are used.
                See :meth:`StarkRamseyXY.delays` for details.
        """
        options = super()._default_experiment_options()
        options.update_options(
            stark_amp=0.0,
            stark_channel=None,
            stark_freq_offset=80e6,
            stark_sigma=15e-9,
            stark_risefall=2,
            min_freq=5e6,
            max_freq=100e6,
            delays=None,
        )
        options.set_validator("stark_freq_offset", (0, np.inf))
        options.set_validator("stark_channel", pulse.channels.PulseChannel)
        return options

    def _set_backend(self, backend: Backend):
        super()._set_backend(backend)
        self._timing = BackendTiming(backend)

    def set_experiment_options(self, **fields):
        _warning_circuit_length = 300

        # Do validation for circuit number
        min_freq = fields.get("min_freq", None)
        max_freq = fields.get("max_freq", None)
        delays = fields.get("delays", None)
        if min_freq is not None and max_freq is not None:
            if delays:
                warnings.warn(
                    "Experiment option 'min_freq' and 'max_freq' are ignored "
                    "when 'delays' are explicitly specified.",
                    UserWarning,
                )
            else:
                n_expr_circs = 2 * int(2 * max_freq / min_freq)  # delays * (x, y)
                max_circs_per_job = None
                if self._backend_data:
                    max_circs_per_job = self._backend_data.max_circuits()
                if n_expr_circs > (max_circs_per_job or _warning_circuit_length):
                    warnings.warn(
                        f"Provided configuration generates {n_expr_circs} circuits. "
                        "You can set smaller 'max_freq' or larger 'min_freq' to reduce this number. "
                        "This experiment is still executable but your execution may consume "
                        "unnecessary long quantum device time, and result may suffer "
                        "device parameter drift in consequence of the long execution time.",
                        UserWarning,
                    )
        # Do validation for spectrum overlap to avoid real excitation
        stark_freq_offset = fields.get("stark_freq_offset", None)
        stark_sigma = fields.get("stark_sigma", None)
        if stark_freq_offset is not None and stark_sigma is not None:
            if stark_freq_offset < 1 / stark_sigma:
                warnings.warn(
                    "Provided configuration may induce coherent state exchange between qubit levels "
                    "because of the potential spectrum overlap. You can avoid this by "
                    "increasing the 'stark_sigma' or 'stark_freq_offset'. "
                    "Note that this experiment is still executable.",
                    UserWarning,
                )
            pass

        super().set_experiment_options(**fields)

    def delays(self) -> np.ndarray:
        """Delay values to use in circuits.

        .. note::

            The delays are computed with the ``min_freq`` and ``max_freq`` experiment options.
            The maximum point is computed from the ``min_freq`` to guarantee the result
            contains at least one Ramsey oscillation cycle at this frequency.
            The interval is computed from the ``max_freq`` to sample with resolution
            such that the Nyquist frequency is twice ``max_freq``.

        Returns:
            The list of delays to use for the different circuits based on the
            experiment options.

        Raises:
            ValueError: When ``min_freq`` is larger than ``max_freq``.
        """
        opt = self.experiment_options  # alias

        if opt.delays is None:
            if opt.min_freq > opt.max_freq:
                raise ValueError("Experiment option 'min_freq' must be smaller than 'max_freq'.")
            # Delay is longer enough to capture 1 cycle of the minimum frequency.
            # Fitter can still accurately fit samples shorter than 1 cycle.
            max_period = 1 / opt.min_freq
            # Inverse of interval should be greater than Nyquist frequency.
            sampling_freq = 2 * opt.max_freq
            interval = 1 / sampling_freq
            return np.arange(0, max_period, interval)
        return opt.delays

    def parameterized_circuits(self) -> Tuple[QuantumCircuit, QuantumCircuit]:
        """Create circuits with parameters for Ramsey XY experiment with Stark tone.

        Returns:
            Quantum template circuits for Ramsey X and Ramsey Y experiment.
        """
        opt = self.experiment_options  # alias
        param = Parameter("delay")

        # Pulse gates
        stark_v = Gate("StarkV", 1, [])
        stark_u = Gate("StarkU", 1, [param])

        # Note that Stark tone yields negative (positive) frequency shift
        # when the Stark tone frequency is higher (lower) than qubit f01 frequency.
        # This choice gives positive frequency shift with positive Stark amplitude.
        qubit_f01 = self._backend_data.drive_freqs[self.physical_qubits[0]]
        stark_freq = qubit_f01 - np.sign(opt.stark_amp) * opt.stark_freq_offset
        stark_amp = np.abs(opt.stark_amp)
        stark_channel = opt.stark_channel or pulse.DriveChannel(self.physical_qubits[0])
        ramps_dt = self._timing.round_pulse(time=2 * opt.stark_risefall * opt.stark_sigma)
        sigma_dt = ramps_dt / 2 / opt.stark_risefall

        with pulse.build() as stark_v_schedule:
            pulse.set_frequency(stark_freq, stark_channel)
            pulse.play(
                pulse.Gaussian(
                    duration=ramps_dt,
                    amp=stark_amp,
                    sigma=sigma_dt,
                    name="StarkV",
                ),
                stark_channel,
            )

        with pulse.build() as stark_u_schedule:
            pulse.set_frequency(stark_freq, stark_channel)
            pulse.play(
                pulse.GaussianSquare(
                    duration=ramps_dt + param,
                    amp=stark_amp,
                    sigma=sigma_dt,
                    risefall_sigma_ratio=opt.stark_risefall,
                    name="StarkU",
                ),
                stark_channel,
            )

        ram_x = QuantumCircuit(1, 1)
        ram_x.sx(0)
        ram_x.append(stark_v, [0])
        ram_x.x(0)
        ram_x.append(stark_u, [0])
        ram_x.rz(-np.pi, 0)
        ram_x.sx(0)
        ram_x.measure(0, 0)
        ram_x.metadata = {"series": "X"}
        ram_x.add_calibration(
            gate=stark_v,
            qubits=self.physical_qubits,
            schedule=stark_v_schedule,
        )
        ram_x.add_calibration(
            gate=stark_u,
            qubits=self.physical_qubits,
            schedule=stark_u_schedule,
        )

        ram_y = QuantumCircuit(1, 1)
        ram_y.sx(0)
        ram_y.append(stark_v, [0])
        ram_y.x(0)
        ram_y.append(stark_u, [0])
        ram_y.rz(-np.pi * 3 / 2, 0)
        ram_y.sx(0)
        ram_y.measure(0, 0)
        ram_y.metadata = {"series": "Y"}
        ram_y.add_calibration(
            gate=stark_v,
            qubits=self.physical_qubits,
            schedule=stark_v_schedule,
        )
        ram_y.add_calibration(
            gate=stark_u,
            qubits=self.physical_qubits,
            schedule=stark_u_schedule,
        )

        return ram_x, ram_y

    def circuits(self) -> List[QuantumCircuit]:
        """Create circuits.

        Returns:
            A list of circuits with a variable delay.
        """
        timing = BackendTiming(self.backend, min_length=0)

        ramx_circ, ramy_circ = self.parameterized_circuits()
        param = next(iter(ramx_circ.parameters))

        circs = []
        for delay in self.delays():
            valid_delay_dt = timing.round_pulse(time=delay)
            net_delay_sec = timing.pulse_time(time=delay)

            ramx_circ_assigned = ramx_circ.assign_parameters({param: valid_delay_dt}, inplace=False)
            ramx_circ_assigned.metadata["xval"] = net_delay_sec

            ramy_circ_assigned = ramy_circ.assign_parameters({param: valid_delay_dt}, inplace=False)
            ramy_circ_assigned.metadata["xval"] = net_delay_sec

            circs.extend([ramx_circ_assigned, ramy_circ_assigned])

        return circs

    def _metadata(self) -> Dict[str, any]:
        """Return experiment metadata for ExperimentData."""
        return {
            "stark_amp": self.experiment_options.stark_amp,
            "stark_freq_offset": self.experiment_options.stark_freq_offset,
        }
