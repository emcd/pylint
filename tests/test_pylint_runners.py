# Licensed under the GPL: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
# For details: https://github.com/PyCQA/pylint/blob/main/LICENSE
# Copyright (c) https://github.com/PyCQA/pylint/blob/main/CONTRIBUTORS.txt
# pylint: disable=missing-module-docstring, missing-function-docstring

from __future__ import annotations

import contextlib
import os
import pathlib
import shlex
import sys
from collections.abc import Sequence
from io import BufferedReader
from typing import Any, NoReturn
from unittest.mock import MagicMock, mock_open, patch

import pytest
from py._path.local import LocalPath

from pylint import run_epylint, run_pylint, run_pyreverse, run_symilar
from pylint.lint import Run
from pylint.testutils import GenericTestReporter as Reporter

if sys.version_info >= (3, 8):
    from typing import Protocol
else:
    from typing_extensions import Protocol


class _RunCallable(Protocol):  # pylint: disable=too-few-public-methods
    def __call__(self, argv: Sequence[str] | None = None) -> NoReturn | None:
        ...


@pytest.mark.parametrize(
    "runner", [run_epylint, run_pylint, run_pyreverse, run_symilar]
)
def test_runner(runner: _RunCallable, tmpdir: LocalPath) -> None:
    filepath = os.path.abspath(__file__)
    testargs = ["", filepath]
    with tmpdir.as_cwd():
        with patch.object(sys, "argv", testargs):
            with pytest.raises(SystemExit) as err:
                runner()
            assert err.value.code == 0


@pytest.mark.parametrize(
    "runner", [run_epylint, run_pylint, run_pyreverse, run_symilar]
)
def test_runner_with_arguments(runner: _RunCallable, tmpdir: LocalPath) -> None:
    """Check the runners with arguments as parameter instead of sys.argv."""
    filepath = os.path.abspath(__file__)
    testargs = [filepath]
    with tmpdir.as_cwd():
        with pytest.raises(SystemExit) as err:
            runner(testargs)
        assert err.value.code == 0


def test_pylint_argument_deduplication(
    tmpdir: LocalPath, tests_directory: pathlib.Path
) -> None:
    """Check that the Pylint runner does not over-report on duplicate
    arguments.

    See https://github.com/PyCQA/pylint/issues/6242 and
    https://github.com/PyCQA/pylint/issues/4053
    """
    filepath = str(tests_directory / "functional/t/too/too_many_branches.py")
    testargs = shlex.split("--report n --score n --max-branches 13")
    testargs.extend([filepath] * 4)
    exit_stack = contextlib.ExitStack()
    exit_stack.enter_context(tmpdir.as_cwd())
    exit_stack.enter_context(patch.object(sys, "argv", testargs))
    err = exit_stack.enter_context(pytest.raises(SystemExit))
    with exit_stack:
        run_pylint(testargs)
    assert err.value.code == 0


def test_pylint_run_jobs_equal_zero_dont_crash_with_cpu_fraction(
    tmpdir: LocalPath,
) -> None:
    """Check that the pylint runner does not crash if `pylint.lint.run._query_cpu`
    determines only a fraction of a CPU core to be available.
    """
    builtin_open = open

    def _mock_open(*args: Any, **kwargs: Any) -> BufferedReader:
        if args[0] == "/sys/fs/cgroup/cpu/cpu.cfs_quota_us":
            return mock_open(read_data=b"-1")(*args, **kwargs)  # type: ignore[no-any-return]
        if args[0] == "/sys/fs/cgroup/cpu/cpu.shares":
            return mock_open(read_data=b"2")(*args, **kwargs)  # type: ignore[no-any-return]
        return builtin_open(*args, **kwargs)  # type: ignore[no-any-return]

    pathlib_path = pathlib.Path

    def _mock_path(*args: str, **kwargs: Any) -> pathlib.Path:
        if args[0] == "/sys/fs/cgroup/cpu/cpu.shares":
            return MagicMock(is_file=lambda: True)
        return pathlib_path(*args, **kwargs)

    filepath = os.path.abspath(__file__)
    testargs = [filepath, "--jobs=0"]
    with tmpdir.as_cwd():
        with pytest.raises(SystemExit) as err:
            with patch("builtins.open", _mock_open):
                with patch("pylint.lint.run.Path", _mock_path):
                    Run(testargs, reporter=Reporter())
        assert err.value.code == 0
