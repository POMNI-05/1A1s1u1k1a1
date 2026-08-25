from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tax_calculators.validation import CalculatorError
from v1.job_config import get_policy_year


class JobConfigTests(unittest.TestCase):
    def test_unsupported_year_in_job_config_is_rejected(self):
        with TemporaryDirectory() as folder:
            config_path = Path(folder) / "job_config.json"
            config_path.write_text(json.dumps({"ato_policy_year": "2027"}), encoding="utf-8")
            with patch.dict(os.environ, {"TAX_JOB_CONFIG_PATH": str(config_path)}, clear=False):
                with self.assertRaisesRegex(CalculatorError, "Unsupported income year '2027'"):
                    get_policy_year()


if __name__ == "__main__":
    unittest.main()
