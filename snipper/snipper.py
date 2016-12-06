import os
from os import path
import json
import getpass
import glob
import logging
import sys
import re

import click
from prompt_toolkit import prompt

from api import SnippetApi
from snippet import Snippet
from completer import SnippetFilesCompleter, SnippetDirCompleter

DEFAULT_SNIPPER_HOME = path.expanduser('~/.snippets')
DEFAULT_SNIPPER_CONFIG = path.join(DEFAULT_SNIPPER_HOME, 'config.json')
SNIPPET_METADATA_FILE = path.join(DEFAULT_SNIPPER_HOME, 'metadata.json')


logger = logging.getLogger('snipper')
logger.setLevel(logging.DEBUG)  # TODO: set with --verbose param
ch = logging.StreamHandler(sys.stdout)
logger.addHandler(ch)


class SnipperConfig(object):
    verbose_short = 'short'
    verbose_detailed = 'detailed'

    def __init__(self, file):
        self.file = file
        self.config = {}
        self.config['verbose'] = self.verbose_short

        with open(self.file, 'r') as file:
            conf_content = json.loads(file.read())

        for key, value in conf_content.items():
            self.config[key] = value

    def get(self, key):
        return self.config[key]

    def set(self, key, value):
        self.config[key] = value

    def save_to_file(self):
        with open(self.file, 'w') as file:
            file.write(json.dumps(self.config, indent=4))

        logger.info('Config file updated: %s', self.file)

    def file_exists(self):
        return path.exists(self.file)


pass_config = click.make_pass_decorator(SnipperConfig)  # pylint: disable-msg=C0103


@click.group()
@click.option('--home', default=DEFAULT_SNIPPER_HOME, type=click.Path(), help='Snippet directory path. ({})'.format(DEFAULT_SNIPPER_HOME))
@click.option('--config-file', default=DEFAULT_SNIPPER_CONFIG, type=click.Path(), help='Snipper config.json file path. ({})'.format(DEFAULT_SNIPPER_CONFIG))
@click.pass_context
def cli(ctx, home, config_file, **kwargs): # pylint: disable-msg=W0613

    # Create a SnippetConfig object and remember it as as the context object.  From
    # this point onwards other commands can refer to it by using the
    # @pass_config decorator.

    if not path.exists(config_file):
        click.secho('Configuration file not found. Plase give me your settings.', fg='red')
        init_snipper(home=home)

    config = SnipperConfig(config_file)
    config.set('snippet_home', home)
    config.set('metadata_file', SNIPPET_METADATA_FILE)

    ctx.obj = config

    api = SnippetApi()
    api.set_config(config)


def init_snipper(home):
    config_file = path.join(home, 'config.json')
    if path.exists(config_file) and not click.confirm('Config file already exist. Overwrite it'):
        return

    home = click.prompt('Where to keep snippets on local', default=home)
    username = click.prompt('Bitbucket username')
    click.secho(
        """Password using for authenticating to Bitbucket API.
        You can create an App Password on Bitbucket settings page.
        """,
        fg='green')

    password = getpass.getpass('Bitbucket Password:')

    # Create snippet home dir
    if not path.exists(home):
        os.makedirs(home)

    # Create config file

    if not path.exists(config_file):
        with open(config_file, 'w+') as file:
            file.write('{}')

    config = SnipperConfig(config_file)
    config.set('snippet_home', home)
    config.set('username', username)
    config.set('password', password)
    config.set('verbose', SnipperConfig.verbose_detailed)

    config.save_to_file()


@cli.command(name='ls')
@click.option('-v', 'verbose', flag_value=SnipperConfig.verbose_short, help='Provides short listing')
@click.option(
    '-vv',
    'verbose',
    default=True,
    flag_value=SnipperConfig.verbose_detailed,
    help='Provides the most detailed listing'
)
@pass_config
@click.pass_context
def list_snippets(context, config, verbose, **kwargs):
    """List local snippets"""
    config.verbose = verbose

    with open(path.join(SNIPPET_METADATA_FILE), 'r') as file:
        data = json.loads(file.read())
        for item in data['values']:
            snippet_id = item['id']
            snippet_title = item['title']

            if verbose == SnipperConfig.verbose_detailed:
                # Show files in snippet
                snippet = Snippet(config, item['owner']['username'], snippet_id)
                snippet_dir = os.path.split(snippet.repo_path)[1]

                onlyfiles = snippet.get_files()
                for file_name in onlyfiles:
                    click.secho(os.path.join(item['owner']['username'], snippet_dir, file_name))


@cli.command(name='pull')
@pass_config
@click.pass_context
def pull_local_snippets(context, config, **kwargs):
    """
    Update local snippets from Bitbucket.
    Pull existing snippets change and clone new snippets if exists.
    """

    api = SnippetApi()
    api.set_config(config)
    res = api.get_all()

    with open(path.join(SNIPPET_METADATA_FILE), 'w') as file:
        file.write(json.dumps(res))

    for item in res['values']:
        owner_username = item['owner']['username']
        snippet_id = item['id']
        repo_parent = path.join(DEFAULT_SNIPPER_HOME, owner_username)

        # Find snippet dirs which ends with specified snippet_id for checking
        # snippet cloned before

        # If directory name which end with snippet_id exist pull changes
        matched_pats = glob.glob(path.join(repo_parent, '*{}'.format(snippet_id)))
        if matched_pats:
            Snippet.pull(matched_pats[0])
        else:
            # Clone repo over ssh (1)
            clone_url = item['links']['clone'][1]['href']
            clone_to = path.join(repo_parent, snippet_id)

            if item['title']:
                # Create dir name for snippet for clonning
                # Using title for readablity(<slugified snippet_title>-<snippet_id>)

                slugified_title = re.sub(r'\W+', '-', item['title']).lower()
                clone_to = path.join(repo_parent, "{}-{}".format(slugified_title, snippet_id))

            Snippet.clone(clone_url, clone_to=clone_to)

    click.secho('Local snippets updated and new snippets downloaded from Bitbucket', fg='blue')


def _open_snippet(ctx, param, relative_path):
    """Open snippet file with default editor"""

    if not relative_path or ctx.resilient_parsing:
        return

    file_path = os.path.join(ctx.obj.get('snippet_home'), relative_path)

    if os.path.exists(file_path):
        click.edit(filename=file_path)
    else:
        click.secho('File not exist. Exiting ...', fg='red')

    ctx.exit()

@cli.command(name='edit', help='Edit snippet')
@click.option('--fuzzy', is_flag=True, default=True, help='Open fuzzy file finder')
@click.argument('FILE', type=click.Path(), required=False, is_eager=True, expose_value=False, callback=_open_snippet)
@pass_config
@click.pass_context
def update_local_snippets(context, config, file_path='', **kwargs):
    selected_file = prompt('[Fuzzy file finder] > ', completer=SnippetFilesCompleter(config))
    file_path = os.path.join(config.get('snippet_home'), selected_file)

    click.edit(filename=file_path)

if __name__ == '__main__':
    cli()
