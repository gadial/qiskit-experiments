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

# pylint: disable=missing-docstring

"""Test AnalysisResult."""

from unittest import mock
import json

import numpy as np

from qiskit.test import QiskitTestCase
from qiskit_experiments.database_service import DbAnalysisResultV1 as DbAnalysisResult
from qiskit_experiments.database_service.device_component import Qubit, Resonator, to_component
from qiskit_experiments.database_service.database_service import DatabaseServiceV1
from qiskit_experiments.database_service.exceptions import DbExperimentDataError


class TestDbAnalysisResult(QiskitTestCase):
    """Test the DbAnalysisResult class."""

    def test_analysis_result_attributes(self):
        """Test analysis result attributes."""
        attrs = {
            "name": "my_type",
            "device_components": [Qubit(1), Qubit(2)],
            "experiment_id": "1234",
            "result_id": "5678",
            "quality": "Good",
            "verified": False,
        }
        result = DbAnalysisResult(value={"foo": "bar"}, tags=["tag1", "tag2"], **attrs)
        self.assertEqual({"foo": "bar"}, result.value)
        self.assertEqual(["tag1", "tag2"], result.tags)
        for key, val in attrs.items():
            self.assertEqual(val, getattr(result, key))

    def test_save(self):
        """Test saving analysis result."""
        mock_service = mock.create_autospec(DatabaseServiceV1)
        result = self._new_analysis_result()
        result.service = mock_service
        result.save()
        mock_service.create_analysis_result.assert_called_once()

    def test_auto_save(self):
        """Test auto saving."""
        mock_service = mock.create_autospec(DatabaseServiceV1)
        result = self._new_analysis_result(service=mock_service)
        result.auto_save = True

        subtests = [
            # update function, update parameters, service called
            (setattr, (result, "tags", ["foo"])),
            (setattr, (result, "value", {"foo": "bar"})),
            (setattr, (result, "quality", "GOOD")),
            (setattr, (result, "verified", True)),
        ]

        for func, params in subtests:
            with self.subTest(func=func):
                func(*params)
                mock_service.update_analysis_result.assert_called_once()
                mock_service.reset_mock()

    def test_set_service_init(self):
        """Test setting service in init."""
        mock_service = mock.create_autospec(DatabaseServiceV1)
        result = self._new_analysis_result(service=mock_service)
        self.assertEqual(mock_service, result.service)

    def test_set_service_direct(self):
        """Test setting service directly."""
        mock_service = mock.create_autospec(DatabaseServiceV1)
        result = self._new_analysis_result()
        result.service = mock_service
        self.assertEqual(mock_service, result.service)

        with self.assertRaises(DbExperimentDataError):
            result.service = mock_service

    def test_set_data(self):
        """Test setting data."""
        result = self._new_analysis_result()
        result.value = {"foo": "new data"}
        self.assertEqual({"foo": "new data"}, result.value)

    def test_set_tags(self):
        """Test setting tags."""
        result = self._new_analysis_result()
        result.tags = ["new_tag"]
        self.assertEqual(["new_tag"], result.tags)

    def test_update_quality(self):
        """Test updating quality."""
        result = self._new_analysis_result(quality="BAD")
        result.quality = "GOOD"
        self.assertEqual("GOOD", result.quality)

    def test_update_verified(self):
        """Test updating verified."""
        result = self._new_analysis_result(verified=False)
        result.verified = True
        self.assertTrue(result.verified)

    def test_data_serialization(self):
        """Test result data serialization."""
        result = self._new_analysis_result(value={"complex": 2 + 3j, "numpy": np.zeros(2)})
        serialized = json.dumps(result._value, cls=result._json_encoder)
        self.assertIsInstance(serialized, str)
        self.assertTrue(json.loads(serialized))

    def test_source(self):
        """Test getting analysis result source."""
        result = self._new_analysis_result()
        self.assertIn("DbAnalysisResultV1", result.source["class"])
        self.assertTrue(result.source["qiskit_version"])

    def _new_analysis_result(self, **kwargs):
        """Return a new analysis result."""
        values = {
            "name": "some_type",
            "value": {"foo": "bar"},
            "device_components": ["Q1", "Q2"],
            "experiment_id": "1234",
        }
        values.update(kwargs)
        return DbAnalysisResult(**values)


class TestDeviceComponent(QiskitTestCase):
    """Test the DeviceComponent class."""

    def test_str(self):
        """Test string representation."""
        q1 = Qubit(1)
        r1 = Resonator(1)
        self.assertEqual("Q1", str(q1))
        self.assertEqual("R1", str(r1))

    def test_to_component(self):
        """Test converting string to component object."""
        q1 = to_component("Q1")
        self.assertIsInstance(q1, Qubit)
        self.assertEqual("Q1", str(q1))
        r1 = to_component("R1")
        self.assertIsInstance(r1, Resonator)
        self.assertEqual("R1", str(r1))
