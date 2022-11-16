# Copyright 2018 Google Inc
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Command line to manage stage files."""

import pathlib
import sys
import types
from typing import Union

import click

from cli.utils import constants
from cli.utils import shared
from cli.utils.constants import GCLOUD


def get_user_email(debug: bool = False) -> str:
  """Returns the user email configured in the gcloud config.

  Args:
    debug: Enables the debug mode on system calls.
  """
  cmd = f'{GCLOUD} config list --format="value(core.account)"'
  _, out, _ = shared.execute_command(
      'Retrieve gcloud current user',
      cmd,
      debug=debug,
      debug_uses_std_out=False)
  return out.strip()


@click.group()
def cli():
  """Manage multiple instances of CRMint."""


@cli.command('create')
@click.option('--stage_path', default=None)
@click.option('--debug/--no-debug', default=False)
def create(stage_path: Union[None, str], debug: bool) -> None:
  """Create new stage file."""
  click.echo(click.style('>>>> Create stage', fg='magenta', bold=True))

  if not stage_path:
    stage_path = shared.get_default_stage_path()
  else:
    stage_path = pathlib.Path(stage_path)

  if stage_path.exists():
    click.echo(click.style(f'This stage file "{stage_path}" already exists. '
                           f'List them all with: `$ crmint stages list`.',
                           fg='red',
                           bold=True))
  else:
    project_id = shared.get_current_project_id(debug=debug)
    gcloud_account_email = get_user_email(debug=debug)
    context = shared.default_stage_context(project_id, gcloud_account_email)
    shared.create_stage_file(stage_path, context)
    click.echo(click.style(f'Stage file created: {stage_path}', fg='green'))


@cli.command('list')
@click.option('--stage_dir', default=None)
def list_stages(stage_dir: Union[None, str]):
  """List your stages defined in cli/stages directory."""
  if stage_dir is None:
    stage_dir = constants.STAGE_DIR
  for stage_path in pathlib.Path(stage_dir).glob('*.tfvars'):
    click.echo(stage_path.stem)


@cli.command('migrate')
@click.option('--stage_path', default=None)
@click.option('--debug/--no-debug', default=False)
def migrate(stage_path: Union[None, str], debug: bool) -> None:
  """Migrate old stage file format to the latest one."""
  click.echo(click.style('Deprecated.', fg='blue', bold=True))
