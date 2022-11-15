"""Tests for cli.commands.stages."""

import os
import pathlib
import shutil
import subprocess
from unittest import mock

from absl.testing import absltest
from click import testing

from cli.commands import bundle
from cli.commands import cloud
from cli.utils import constants
from cli.utils import shared
from cli.utils import test_helpers

DATA_DIR = os.path.join(os.path.dirname(__file__), '../testdata')


def _datafile(filename):
  return os.path.join(DATA_DIR, filename)


class BundleTest(absltest.TestCase):

  def setUp(self):
    super().setUp()
    side_effect_run = test_helpers.mock_subprocess_result_side_effect()
    self.enter_context(
        mock.patch.object(
            subprocess, 'run', autospec=True, side_effect=side_effect_run))
    tf_plan_file = _datafile('tfplan_with_vpc.json')
    with open(tf_plan_file, 'rb') as f:
      tf_plan_content = f.read()
    self.enter_context(
        mock.patch.object(
            cloud,
            'terraform_show_plan',
            autospec=True,
            return_value=tf_plan_content))
    # `create_tempfile` needs access to --test_tmpdir, however in the OSS world
    # pytest doesn't run `absltest.main`, so we need to init flags ourselves.
    test_helpers.initialize_flags_with_defaults()
    # Overrides the default stage directory with a custom temporary directory.
    tmp_stage_dir = self.create_tempdir('stage_dir')
    self.enter_context(
        mock.patch.object(constants, 'STAGE_DIR', tmp_stage_dir.full_path))
    self.enter_context(
        mock.patch.object(
            shared,
            'get_current_project_id',
            autospec=True,
            return_value='dummy_project_with_vpc'))
    self.enter_context(
        mock.patch.object(
            shared,
            'get_user_email',
            autospec=True,
            return_value='user@example.com'))
    self.enter_context(
        mock.patch.object(
            shared,
            'get_region',
            autospec=True,
            return_value='us-central1'))

  def test_can_run_install_without_stage_file(self):
    runner = testing.CliRunner()
    result = runner.invoke(bundle.install, catch_exceptions=False)
    self.assertEqual(result.exit_code, 0, msg=result.output)
    self.assertIn('>>>> Create stage', result.output)
    self.assertIn('Stage file created:', result.output)
    self.assertIn('>>>> Checklist', result.output)
    self.assertIn('>>>> Setup', result.output)

  def test_can_run_install_with_existing_stage_file(self):
    shutil.copyfile(
        _datafile('dummy_project_with_vpc.tfvars'),
        pathlib.Path(constants.STAGE_DIR, 'dummy_project_with_vpc.tfvars'))
    runner = testing.CliRunner()
    result = runner.invoke(bundle.install, catch_exceptions=False)
    self.assertEqual(result.exit_code, 0, msg=result.output)
    self.assertIn('>>>> Create stage', result.output)
    self.assertRegex(result.output, 'This stage file ".*" already exists.')
    self.assertIn('>>>> Checklist', result.output)
    self.assertIn('>>>> Setup', result.output)

if __name__ == '__main__':
  absltest.main()
