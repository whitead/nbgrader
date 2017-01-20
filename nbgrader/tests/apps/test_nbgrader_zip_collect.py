import os
import pytest
import zipfile

from textwrap import dedent
from os.path import join

from .base import BaseTestApp
from .. import run_nbgrader
from ...utils import rmtree, parse_utc


@pytest.fixture
def archive_dir(request, course_dir):
    path = os.path.join(course_dir, "downloaded", "ps1", "archive")
    os.makedirs(path)

    def fin():
        rmtree(path)
    request.addfinalizer(fin)

    return path


def _count_zip_files(path):
    with zipfile.ZipFile(path, 'r') as zip_file:
        return len(zip_file.namelist())


class TestNbGraderZipCollect(BaseTestApp):

    def _make_notebook(self, dest, *args):
        notebook = '{}_{}_attempt_{}_{}.ipynb'.format(*args)
        self._empty_notebook(join(dest, notebook))

    def test_help(self):
        """Does the help display without error?"""
        run_nbgrader(["zip_collect", "--help-all"])

    def test_no_archive_dir(self, db, course_dir):
        # Should fail with no archive_directory
        run_nbgrader(["zip_collect", "ps1"], retcode=1)

    def test_empty_archive_dir(self, db, course_dir, archive_dir):
        # Should fail with empty archive_directory and no extracted_directory
        run_nbgrader(["zip_collect", "ps1"], retcode=1)

        # Should not fail with empty archive_directory and existing
        # extracted_directory
        os.makedirs(join(archive_dir, "..", "extracted"))
        run_nbgrader(["zip_collect", "ps1"])

    def test_extract_single_notebook(self, db, course_dir, archive_dir):
        extracted_dir = join(archive_dir, "..", "extracted")
        self._make_notebook(archive_dir,
                'ps1', 'hacker', '2016-01-30-15-30-10', 'problem1.ipynb')

        run_nbgrader(["zip_collect", "ps1"])
        assert os.path.isdir(extracted_dir)
        assert len(os.listdir(extracted_dir)) == 1

        # Run again should fail
        run_nbgrader(["zip_collect", "ps1"], retcode=1)
        assert os.path.isdir(extracted_dir)
        assert len(os.listdir(extracted_dir)) == 1

        # Run again with --force flag should pass
        run_nbgrader(["zip_collect", "--force", "ps1"])
        assert os.path.isdir(extracted_dir)
        assert len(os.listdir(extracted_dir)) == 1

    def test_extract_sub_dir_single_notebook(self, db, course_dir, archive_dir):
        extracted_dir = join(archive_dir, "..", "extracted")
        self._make_notebook(join(archive_dir, 'hacker'),
                'ps1', 'hacker', '2016-01-30-15-30-10', 'problem1')

        run_nbgrader(["zip_collect", "ps1"])
        assert os.path.isdir(extracted_dir)
        assert os.path.isdir(join(extracted_dir, "hacker"))
        assert len(os.listdir(join(extracted_dir, "hacker"))) == 1

    def test_extract_archive(self, db, course_dir, archive_dir):
        extracted_dir = join(archive_dir, "..", "extracted")
        archive = join(archive_dir, "notebooks.zip")
        self._copy_file(join("files", "notebooks.zip"), archive)

        run_nbgrader(["zip_collect", "ps1"])
        assert os.path.isdir(extracted_dir)
        assert len(os.listdir(extracted_dir)) == _count_zip_files(archive)

    def test_extract_archive_copies(self, db, course_dir, archive_dir):
        extracted_dir = join(archive_dir, "..", "extracted")
        archive1 = join(archive_dir, "notebooks.zip")
        archive1 = join(archive_dir, "notebooks_copy.zip")

        self._copy_file(join("files", "notebooks.zip"), archive1)
        self._copy_file(join("files", "notebooks.zip"), archive1)

        run_nbgrader(["zip_collect", "ps1"])
        nfiles = _count_zip_files(archive1)
        assert os.path.isdir(extracted_dir)
        assert len(os.listdir(extracted_dir)) == nfiles

    def test_collect_single_notebook(self, db, course_dir, archive_dir):
        extracted_dir = join(archive_dir, "..", "extracted")
        submitted_dir = join(course_dir, "submitted")
        self._make_notebook(archive_dir,
                'ps1', 'hacker', '2016-01-30-15-30-10', 'problem1')

        with open("nbgrader_config.py", "a") as fh:
            fh.write(dedent(
                """
                c.FileNameCollectorPlugin.named_regexp = (
                    r".+_(?P<student_id>\w+)_attempt_(?P<timestamp>[0-9\-]+)_(?P<file_id>\w+)"
                )
                """
            ))

        run_nbgrader(["zip_collect", "--update-db", "ps1"])
        assert os.path.isdir(extracted_dir)
        assert len(os.listdir(extracted_dir)) == 1

        assert os.path.isdir(submitted_dir)
        assert os.path.isfile(join(submitted_dir, "hacker", "ps1", 'problem1.ipynb'))
        assert os.path.isfile(join(submitted_dir, "hacker", "ps1", 'timestamp.txt'))
        assert len(os.listdir(join(submitted_dir, "hacker", "ps1"))) == 2

    def test_collect_single_notebook_attempts(self, db, course_dir, archive_dir):
        extracted_dir = join(archive_dir, "..", "extracted")
        submitted_dir = join(course_dir, "submitted")
        self._make_notebook(archive_dir,
                'ps1', 'hacker', '2016-01-30-15-30-10', 'problem1')
        self._make_notebook(archive_dir,
                'ps1', 'hacker', '2016-01-30-15-40-10', 'problem1')
        self._make_notebook(archive_dir,
                'ps1', 'hacker', '2016-01-30-15-50-10', 'problem1')

        with open('plugin.py', 'w') as fh:
            fh.write(dedent("""
                from nbgrader.plugins import FileNameCollectorPlugin

                class CustomPlugin(FileNameCollectorPlugin):
                    def collect(self, submitted_file):
                        info = super(CustomPlugin, self).collect(submitted_file)
                        if info is not None:
                            info.timestamp = '{}-{}-{} {}:{}:{}'.format(
                                *tuple(info.timestamp.split('-'))
                            )
                        return info
                """
            ))

        with open("nbgrader_config.py", "a") as fh:
            fh.write(dedent("""
                c.ZipCollectApp.collector_plugin = 'plugin.CustomPlugin'
                c.FileNameCollectorPlugin.named_regexp = (
                    r".+_(?P<student_id>\w+)_attempt_(?P<timestamp>[0-9\-]+)_(?P<file_id>\w+)"
                )
                """
            ))

        print(os.listdir('.'))
        run_nbgrader(["zip_collect", "--update-db", "ps1"])
        assert os.path.isdir(extracted_dir)
        assert len(os.listdir(extracted_dir)) == 3

        assert os.path.isdir(submitted_dir)
        assert os.path.isfile(join(submitted_dir, "hacker", "ps1", 'problem1.ipynb'))
        assert os.path.isfile(join(submitted_dir, "hacker", "ps1", 'timestamp.txt'))
        assert len(os.listdir(join(submitted_dir, "hacker", "ps1"))) == 2

        with open(join(submitted_dir, "hacker", "ps1", 'timestamp.txt')) as ts:
            timestamp = ts.read()

    def test_collect_sub_dir_single_notebook(self, db, course_dir, archive_dir):
        extracted_dir = join(archive_dir, "..", "extracted")
        submitted_dir = join(course_dir, "submitted")
        self._make_notebook(extracted_dir,
                'ps1', 'hacker', '2016-01-30-15-30-10', 'problem1')
        self._make_notebook(join(extracted_dir, 'bitdiddle'),
                'ps1', 'bitdiddle', '2016-01-30-15-30-10', 'problem1')

        with open("nbgrader_config.py", "a") as fh:
            fh.write(dedent(
                """
                c.FileNameCollectorPlugin.named_regexp = (
                    r".+_(?P<student_id>\w+)_attempt_(?P<timestamp>[0-9\-]+)_(?P<file_id>\w+)"
                )
                """
            ))

        run_nbgrader(["zip_collect", "--update-db", "ps1"])
        assert os.path.isdir(extracted_dir)
        assert os.path.isdir(submitted_dir)
        assert len(os.listdir(submitted_dir)) == 2

        assert os.path.isfile(join(submitted_dir, "hacker", "ps1", 'problem1.ipynb'))
        assert os.path.isfile(join(submitted_dir, "hacker", "ps1", 'timestamp.txt'))
        assert len(os.listdir(join(submitted_dir, "hacker", "ps1"))) == 2

        assert os.path.isfile(join(submitted_dir, "bitdiddle", "ps1", 'problem1.ipynb'))
        assert os.path.isfile(join(submitted_dir, "bitdiddle", "ps1", 'timestamp.txt'))
        assert len(os.listdir(join(submitted_dir, "bitdiddle", "ps1"))) == 2

    def test_collect_invalid_notebook(self, db, course_dir, archive_dir):
        extracted_dir = join(archive_dir, "..", "extracted")
        submitted_dir = join(course_dir, "submitted")
        self._empty_notebook(join(course_dir, 'source', 'ps1', 'problem1.ipynb'))

        with open("nbgrader_config.py", "a") as fh:
            fh.write(dedent(
                """
                c.NbGrader.db_assignments = [dict(name="ps1")]
                c.FileNameCollectorPlugin.named_regexp = (
                    r".+_(?P<student_id>\w+)_attempt_(?P<timestamp>[0-9\-]+)_(?P<file_id>\w+)"
                )
                """
            ))

        run_nbgrader(["assign", "ps1"])

        self._make_notebook(archive_dir,
                'ps1', 'hacker', '2016-01-30-15-30-10', 'myproblem1')

        # Should get collected without --strict flag
        run_nbgrader(["zip_collect", "--update-db", "ps1"])
        assert os.path.isdir(extracted_dir)
        assert len(os.listdir(extracted_dir)) == 1

        assert os.path.isdir(submitted_dir)
        assert os.path.isfile(join(submitted_dir, "hacker", "ps1", 'myproblem1.ipynb'))
        assert os.path.isfile(join(submitted_dir, "hacker", "ps1", 'timestamp.txt'))
        assert len(os.listdir(join(submitted_dir, "hacker", "ps1"))) == 2

        # Re-run with --strict flag
        self._make_notebook(archive_dir,
                'ps1', 'hacker', '2016-01-30-15-30-10', 'problem1')

        run_nbgrader(["zip_collect", "--force", "--strict", "--update-db", "ps1"])
        assert os.path.isdir(extracted_dir)
        assert len(os.listdir(extracted_dir)) == 2

        assert os.path.isdir(submitted_dir)
        assert os.path.isfile(join(submitted_dir, "hacker", "ps1", 'problem1.ipynb'))
        assert os.path.isfile(join(submitted_dir, "hacker", "ps1", 'timestamp.txt'))
        assert len(os.listdir(join(submitted_dir, "hacker", "ps1"))) == 2
