import os
import shutil

from textwrap import dedent
from traitlets import List, Bool, observe

from .baseapp import BaseNbConvertApp, nbconvert_aliases, nbconvert_flags
from ..preprocessors import (
    AssignLatePenalties, ClearOutput, DeduplicateIds, OverwriteCells, SaveAutoGrades,
    Execute, LimitOutput, OverwriteKernelspec, CheckCellMetadata)
from ..api import Gradebook, MissingEntry
from .. import utils

aliases = {}
aliases.update(nbconvert_aliases)
aliases.update({
})

flags = {}
flags.update(nbconvert_flags)
flags.update({
    'create': (
        {'AutogradeApp': {'create_student': True}},
        "Create an entry for the student in the database, if one does not already exist."
    ),
    'no-execute': (
        {
            'Execute': {'enabled': False},
            'ClearOutput': {'enabled': False}
        },
        "Don't execute notebooks and clear output when autograding."
    ),
})


class AutogradeApp(BaseNbConvertApp):

    name = u'nbgrader-autograde'
    description = u'Autograde a notebook by running it'

    aliases = aliases
    flags = flags

    examples = """
        Autograde submitted assignments. This takes one argument for the
        assignment id, and then (by default) autogrades assignments from the
        following directory structure:

            submitted/*/{assignment_id}/*.ipynb

        and saves the autograded files to the corresponding directory in:

            autograded/{student_id}/{assignment_id}/{notebook_id}.ipynb

        The student IDs must already exist in the database. If they do not, you
        can tell `nbgrader autograde` to add them on the fly by passing the
        --create flag.

        Note that the assignment must also be present in the database. If it is
        not, you should first create it using `nbgrader assign`. Then, during
        autograding, the cells that contain tests for the students' answers will
        be overwritten with the master version of the tests that is saved in the
        database (this prevents students from modifying the tests in order to
        improve their score).

        To grade all submissions for "Problem Set 1":

            nbgrader autograde "Problem Set 1"

        To grade only the submission by student with ID 'Hacker':

            nbgrader autograde "Problem Set 1" --student Hacker

        To grade only the notebooks that start with '1':

            nbgrader autograde "Problem Set 1" --notebook "1*"

        By default, student submissions are re-executed and their output cleared.
        For long running notebooks, it can be useful to disable this with the
        '--no-execute' flag:

            nbgrader autograde "Problem Set 1" --no-execute

        Note, however, that doing so will not guarantee that students' solutions
        are correct. If you use this flag, you should make sure you manually
        check all solutions. For example, if a student saved their notebook with
        all outputs cleared, then using --no-execute would result in them
        receiving full credit on all autograded problems.
        """

    create_student = Bool(
        False,
        help=dedent(
            """
            Whether to create the student at runtime if it does not
            already exist.
            """
        )
    ).tag(config=True)

    _sanitizing = True

    @property
    def _input_directory(self):
        if self._sanitizing:
            return self.coursedir.submitted_directory
        else:
            return self.coursedir.autograded_directory

    @property
    def _output_directory(self):
        return self.coursedir.autograded_directory

    export_format = 'notebook'

    sanitize_preprocessors = List([
        ClearOutput,
        DeduplicateIds,
        OverwriteKernelspec,
        OverwriteCells,
        CheckCellMetadata
    ])
    autograde_preprocessors = List([
        Execute,
        LimitOutput,
        SaveAutoGrades,
        AssignLatePenalties,
        CheckCellMetadata
    ])

    preprocessors = List([])

    def init_assignment(self, assignment_id, student_id):
        super(AutogradeApp, self).init_assignment(assignment_id, student_id)

        # try to get the student from the database, and throw an error if it
        # doesn't exist
        student = {}
        for s in self.db_students:
            if s['id'] == student_id:
                student = s.copy()
                break

        if student or self.create_student:
            if 'id' in student:
                del student['id']
            self.log.info("Creating/updating student with ID '%s': %s", student_id, student)
            with Gradebook(self.coursedir.db_url) as gb:
                gb.update_or_create_student(student_id, **student)

        else:
            with Gradebook(self.coursedir.db_url) as gb:
                try:
                    gb.find_student(student_id)
                except MissingEntry:
                    self.fail("No student with ID '%s' exists in the database", student_id)

        # make sure the assignment exists
        with Gradebook(self.coursedir.db_url) as gb:
            try:
                gb.find_assignment(assignment_id)
            except MissingEntry:
                self.fail("No assignment with ID '%s' exists in the database", assignment_id)

        # try to read in a timestamp from file
        src_path = self._format_source(assignment_id, student_id)
        timestamp = self.coursedir.get_existing_timestamp(src_path)
        with Gradebook(self.coursedir.db_url) as gb:
            if timestamp:
                submission = gb.update_or_create_submission(
                    assignment_id, student_id, timestamp=timestamp)
                self.log.info("%s submitted at %s", submission, timestamp)

                # if the submission is late, print out how many seconds late it is
                if timestamp and submission.total_seconds_late > 0:
                    self.log.warning("%s is %s seconds late", submission, submission.total_seconds_late)
            else:
                submission = gb.update_or_create_submission(assignment_id, student_id)

        # copy files over from the source directory
        self.log.info("Overwriting files with master versions from the source directory")
        dest_path = self._format_dest(assignment_id, student_id)
        source_path = self.coursedir.format_path(self.coursedir.source_directory, '.', assignment_id)
        source_files = utils.find_all_files(source_path, self.coursedir.ignore + ["*.ipynb"])

        # copy them to the build directory
        for filename in source_files:
            dest = os.path.join(dest_path, os.path.relpath(filename, source_path))
            if not os.path.exists(os.path.dirname(dest)):
                os.makedirs(os.path.dirname(dest))
            if os.path.exists(dest):
                os.remove(dest)
            self.log.info("Copying %s -> %s", filename, dest)
            shutil.copy(filename, dest)

        # ignore notebooks that aren't in the database
        notebooks = []
        with Gradebook(self.coursedir.db_url) as gb:
            for notebook in self.notebooks:
                notebook_id = os.path.splitext(os.path.basename(notebook))[0]
                try:
                    gb.find_notebook(notebook_id, assignment_id)
                except MissingEntry:
                    self.log.warning("Skipping unknown notebook: %s", notebook)
                    continue
                else:
                    notebooks.append(notebook)
        self.notebooks = notebooks
        if len(self.notebooks) == 0:
            self.fail("No notebooks found, did you forget to run 'nbgrader assign'?")

    def _init_preprocessors(self):
        self.exporter._preprocessors = []
        if self._sanitizing:
            preprocessors = self.sanitize_preprocessors
        else:
            preprocessors = self.autograde_preprocessors

        for pp in preprocessors:
            self.exporter.register_preprocessor(pp)

    def convert_single_notebook(self, notebook_filename):
        self.log.info("Sanitizing %s", notebook_filename)
        self._sanitizing = True
        self._init_preprocessors()
        super(AutogradeApp, self).convert_single_notebook(notebook_filename)

        notebook_filename = os.path.join(self.writer.build_directory, os.path.basename(notebook_filename))
        self.log.info("Autograding %s", notebook_filename)
        self._sanitizing = False
        self._init_preprocessors()
        try:
            super(AutogradeApp, self).convert_single_notebook(notebook_filename)
        finally:
            self._sanitizing = True
