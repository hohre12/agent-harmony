"""Tests for verifier_code_quality — magic numbers, duplicate code,
unused imports, N+1 queries, hardcoded strings."""

import pytest
from unittest.mock import patch

from harmony.orchestrator import verifier_code_quality as vcq


# ---------------------------------------------------------------------------
# Magic numbers
# ---------------------------------------------------------------------------

class TestMagicNumbers:
    def test_python_detects_magic_number(self):
        sources = {"app.py": "x = 42\ny = x + 99\n"}
        result = vcq.verify_magic_numbers(sources)
        assert result["verified"]
        assert result["violation_count"] >= 1
        values = [v["value"] for v in result["violations"]]
        assert 42 in values or 99 in values

    def test_python_allows_common_values(self):
        sources = {"app.py": "x = 0\ny = 1\nz = -1\nstatus = 200\n"}
        result = vcq.verify_magic_numbers(sources)
        assert result["violation_count"] == 0

    def test_python_skips_constants(self):
        sources = {"app.py": "MAX_RETRIES = 5\nTIMEOUT_MS = 3000\n"}
        result = vcq.verify_magic_numbers(sources)
        assert result["violation_count"] == 0

    def test_python_skips_range(self):
        sources = {"app.py": "for i in range(10):\n    pass\n"}
        result = vcq.verify_magic_numbers(sources)
        assert result["violation_count"] == 0

    def test_js_detects_magic_number(self):
        sources = {"app.ts": "const x = 42;\nconst y = x + 99;\n"}
        result = vcq.verify_magic_numbers(sources)
        assert result["violation_count"] >= 1

    def test_js_skips_constants(self):
        sources = {"app.ts": "const MAX_RETRIES = 5;\n"}
        result = vcq.verify_magic_numbers(sources)
        assert result["violation_count"] == 0

    def test_excluded_files_skipped(self):
        sources = {"config.py": "PORT = 8080\nMAX = 42\n"}
        result = vcq.verify_magic_numbers(sources)
        assert result["violation_count"] == 0

    def test_empty_sources(self):
        result = vcq.verify_magic_numbers({})
        assert result["verified"]
        assert result["violation_count"] == 0


# ---------------------------------------------------------------------------
# Duplicate code
# ---------------------------------------------------------------------------

class TestDuplicateCode:
    def test_detects_cross_file_duplication(self):
        block = "a = get_data()\nb = transform(a)\nc = validate(b)\nd = save(c)\n"
        sources = {"a.py": block + "extra = 1\n", "b.py": block + "extra = 2\n"}
        result = vcq.verify_duplicate_code(sources)
        assert result["verified"]
        assert result["violation_count"] >= 1

    def test_ignores_short_blocks(self):
        block = "a = 1\nb = 2\nc = 3\n"  # only 3 lines, below threshold of 4
        sources = {"a.py": block, "b.py": block}
        result = vcq.verify_duplicate_code(sources)
        assert result["violation_count"] == 0

    def test_ignores_imports(self):
        block = "import os\nimport sys\nimport json\nimport re\n"
        sources = {"a.py": block + "x = 1\n", "b.py": block + "y = 2\n"}
        result = vcq.verify_duplicate_code(sources)
        assert result["violation_count"] == 0

    def test_ignores_test_files(self):
        block = "a = get_data()\nb = transform(a)\nc = validate(b)\nd = save(c)\n"
        sources = {"test_a.py": block, "test_b.py": block}
        result = vcq.verify_duplicate_code(sources)
        assert result["violation_count"] == 0


# ---------------------------------------------------------------------------
# Unused imports
# ---------------------------------------------------------------------------

class TestUnusedImports:
    def test_python_detects_unused(self):
        sources = {"app.py": "import os\nimport sys\nprint('hello')\n"}
        result = vcq.verify_unused_imports(sources)
        assert result["verified"]
        names = [v["import_name"] for v in result["violations"]]
        assert "os" in names
        assert "sys" in names

    def test_python_used_import_ok(self):
        sources = {"app.py": "import os\npath = os.path.join('a', 'b')\n"}
        result = vcq.verify_unused_imports(sources)
        names = [v["import_name"] for v in result["violations"]]
        assert "os" not in names

    def test_python_from_import_unused(self):
        sources = {"app.py": "from pathlib import Path\nx = 1\n"}
        result = vcq.verify_unused_imports(sources)
        names = [v["import_name"] for v in result["violations"]]
        assert "Path" in names

    def test_python_from_import_used(self):
        sources = {"app.py": "from pathlib import Path\np = Path('.')\n"}
        result = vcq.verify_unused_imports(sources)
        names = [v["import_name"] for v in result["violations"]]
        assert "Path" not in names

    def test_python_star_import_skipped(self):
        sources = {"app.py": "from os.path import *\njoin('a', 'b')\n"}
        result = vcq.verify_unused_imports(sources)
        assert result["violation_count"] == 0

    def test_python_init_file_skipped(self):
        sources = {"__init__.py": "from .module import MyClass\n"}
        result = vcq.verify_unused_imports(sources)
        assert result["violation_count"] == 0

    def test_python_noqa_skipped(self):
        sources = {"app.py": "import os  # noqa\nx = 1\n"}
        result = vcq.verify_unused_imports(sources)
        assert result["violation_count"] == 0

    def test_python_all_export(self):
        sources = {"app.py": "import os\n__all__ = ['os']\n"}
        result = vcq.verify_unused_imports(sources)
        names = [v["import_name"] for v in result["violations"]]
        assert "os" not in names

    def test_js_detects_unused(self):
        sources = {"app.ts": "import { useState, useEffect } from 'react';\nconst x = useState(0);\n"}
        result = vcq.verify_unused_imports(sources)
        names = [v["import_name"] for v in result["violations"]]
        assert "useEffect" in names

    def test_js_default_import_unused(self):
        sources = {"app.ts": "import React from 'react';\nconst x = 1;\n"}
        result = vcq.verify_unused_imports(sources)
        names = [v["import_name"] for v in result["violations"]]
        assert "React" in names

    def test_js_side_effect_import_skipped(self):
        sources = {"app.ts": "import './styles.css';\nconst x = 1;\n"}
        result = vcq.verify_unused_imports(sources)
        assert result["violation_count"] == 0


# ---------------------------------------------------------------------------
# N+1 queries
# ---------------------------------------------------------------------------

class TestNplus1Queries:
    def test_python_detects_query_in_loop(self):
        code = (
            "users = get_users()\n"
            "for user in users:\n"
            "    orders = session.query(Order).filter(user_id=user.id).all()\n"
        )
        sources = {"app.py": code}
        result = vcq.verify_nplus1_queries(sources)
        assert result["verified"]
        assert result["violation_count"] >= 1

    def test_python_ignores_dict_get(self):
        code = (
            "for item in items:\n"
            "    value = my_dict.get(item)\n"
        )
        sources = {"app.py": code}
        result = vcq.verify_nplus1_queries(sources)
        assert result["violation_count"] == 0

    def test_python_ignores_prefetch(self):
        code = (
            "for user in users:\n"
            "    data = user.prefetch_related('orders')\n"
        )
        sources = {"app.py": code}
        result = vcq.verify_nplus1_queries(sources)
        assert result["violation_count"] == 0

    def test_python_query_outside_loop_ok(self):
        code = "orders = session.query(Order).all()\nfor o in orders:\n    print(o)\n"
        sources = {"app.py": code}
        result = vcq.verify_nplus1_queries(sources)
        assert result["violation_count"] == 0

    def test_js_detects_await_in_loop(self):
        code = (
            "for (const user of users) {\n"
            "  const orders = await db.find({ userId: user.id });\n"
            "}\n"
        )
        sources = {"app.ts": code}
        result = vcq.verify_nplus1_queries(sources)
        assert result["violation_count"] >= 1

    def test_js_ignores_batch(self):
        code = (
            "for (const user of users) {\n"
            "  const orders = await db.insertMany(data);\n"
            "}\n"
        )
        sources = {"app.ts": code}
        result = vcq.verify_nplus1_queries(sources)
        assert result["violation_count"] == 0

    def test_skips_test_files(self):
        code = (
            "for user in users:\n"
            "    orders = session.query(Order).filter(user_id=user.id).all()\n"
        )
        sources = {"test_app.py": code}
        result = vcq.verify_nplus1_queries(sources)
        assert result["violation_count"] == 0


# ---------------------------------------------------------------------------
# Hardcoded strings
# ---------------------------------------------------------------------------

class TestHardcodedStrings:
    def test_detects_repeated_string(self):
        sources = {
            "a.py": 'x = "Hello World"\ny = "Hello World"\n',
            "b.py": 'z = "Hello World"\n',
        }
        result = vcq.verify_hardcoded_strings(sources)
        assert result["verified"]
        assert result["violation_count"] >= 1
        assert result["violations"][0]["string"] == "Hello World"

    def test_ignores_below_threshold(self):
        sources = {
            "a.py": 'x = "unique string one"\n',
            "b.py": 'y = "unique string two"\n',
        }
        result = vcq.verify_hardcoded_strings(sources)
        assert result["violation_count"] == 0

    def test_ignores_common_keys(self):
        sources = {
            "a.py": 'x = "name"\ny = "name"\n',
            "b.py": 'z = "name"\n',
        }
        result = vcq.verify_hardcoded_strings(sources)
        assert result["violation_count"] == 0

    def test_ignores_urls(self):
        sources = {
            "a.py": 'x = "https://api.example.com"\n',
            "b.py": 'y = "https://api.example.com"\n',
            "c.py": 'z = "https://api.example.com"\n',
        }
        result = vcq.verify_hardcoded_strings(sources)
        assert result["violation_count"] == 0

    def test_ignores_format_strings(self):
        sources = {
            "a.py": 'x = "Hello {name}"\n',
            "b.py": 'y = "Hello {name}"\n',
            "c.py": 'z = "Hello {name}"\n',
        }
        result = vcq.verify_hardcoded_strings(sources)
        assert result["violation_count"] == 0

    def test_skips_test_and_excluded_files(self):
        sources = {
            "test_a.py": 'x = "repeated"\ny = "repeated"\n',
            "config.py": 'z = "repeated"\n',
        }
        result = vcq.verify_hardcoded_strings(sources)
        assert result["violation_count"] == 0


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class TestVerifyCodeQuality:
    @patch.object(vcq, "_load_changed_sources", return_value={})
    def test_empty_project(self, mock_load):
        result = vcq.verify_code_quality(".")
        assert result["verified"]
        assert result["total_violations"] == 0

    @patch.object(vcq, "_load_changed_sources")
    def test_aggregates_violations(self, mock_load):
        mock_load.return_value = {
            "app.py": (
                "import os\nimport sys\n"
                "x = 42\ny = 99\n"
                'msg = "Hello World"\nmsg2 = "Hello World"\n'
            ),
            "app2.py": (
                'msg3 = "Hello World"\n'
                "z = 42\n"
            ),
        }
        result = vcq.verify_code_quality(".")
        assert result["verified"]
        assert result["total_violations"] > 0
        assert "magic_numbers" in result
        assert "unused_imports" in result
        assert "hardcoded_strings" in result
