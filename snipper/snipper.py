import os
from os import path
import json
import getpass
import glob
import logging
import sys

import click
from prompt_toolkit import prompt

from api import SnippetApi
from snippet import Snippet
from completer import SnippetFilesCompleter, SnippetDirCompleter
import utils

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

        click.secho('Config file updated: {}'.format(self.file), fg='green')

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
        fg='blue')

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

            if verbose == SnipperConfig.verbose_detailed:
                # Show files in snippet
                snippet = Snippet(config, item['owner']['username'], item['id'])
                snippet_path = snippet.get_path()

                if not snippet_path:
                    msg = '[{}] Snippet does not exist in file system. Please `pull` changes'
                    click.secho(msg.format(item['id']), fg='red')

                    continue

                onlyfiles = snippet.get_files()
                for file_name in onlyfiles:
                    click.secho(os.path.join(item['owner']['username'], snippet_path, file_name))


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

        # If directory name which end with snippet_id exist, pull changes
        matched_pats = glob.glob(path.join(repo_parent, '*{}'.format(snippet_id)))
        if matched_pats:
            Snippet.pull(matched_pats[0])
        else:
            Snippet.clone_by_snippet_id(config, snippet_id)

    click.secho('Local snippets updated and new snippets downloaded from Bitbucket', fg='blue')


def _open_snippet_file(ctx, param, relative_path):
    """Open snippet file with default editor"""

    if not relative_path or ctx.resilient_parsing:
        return

    file_path = os.path.join(ctx.obj.get('snippet_home'), relative_path)

    if os.path.exists(file_path):
        click.edit(filename=file_path)
    else:
        click.secho('File not exist. Exiting ...', fg='red')

    ctx.exit()

@cli.command(name='edit', help='Edit snippet file')
@click.option('--fuzzy', is_flag=True, default=True, help='Open fuzzy file finder')
@click.argument('FILE_PATH', type=click.Path(), required=False, is_eager=True, expose_value=False, callback=_open_snippet_file)
@pass_config
@click.pass_context
def edit_snippet_file(context, config, file_path=None, **kwargs):
    selected_file = prompt('[Add/Edit file] > ', completer=SnippetFilesCompleter(config))
    file_path = os.path.join(config.get('snippet_home'), selected_file)

    click.edit(filename=file_path)

@cli.command(name='new', help='Create new snippet')
@click.option('--title', help='Snippet title', prompt='Snippet title')
@click.option('--filename', help='File name', default='note.md', prompt='File name')
@click.option('--private/--public', default=True, prompt='Private snippet', help='Make private/public snippet')
@click.option('--hg/--git', default=True, prompt='Use mercurial(n for git)', help='Choice scm. Default hg')
@pass_config
@click.pass_context
def new_snippet(context, config, **kwargs):
    pass

@cli.command(name='add', help='Create new snippet from file[s]')
@click.option('--title', help='Snippet title', prompt='Snippet title')
@click.option('--private/--public', default=True, prompt='Private snippet', help='Make private/public snippet')
@click.option('--hg/--git', default=True, prompt='Use mercurial(n for git)', help='Choice scm. Default hg')
@click.option('--file', help='Create snippet from file', multiple=True)
@pass_config
@click.pass_context
def add_snippet(context, config, **kwargs):

    api = SnippetApi()
    api.set_config(config)

    scm = 'hg' if kwargs.get('hg') else 'git'

    click.secho('Snippet creating...', fg='blue')

    response = api.create_snippet(
        utils.open_files(kwargs.get('file')),
        kwargs.get('private', False),
        kwargs.get('title', None),
        scm,
    )

    if response.ok:
        snippet_metadata = response.json()

        Snippet.add_snippet_metadata(config, snippet_metadata)
        Snippet.clone_by_snippet_id(config, snippet_metadata['id'])

    click.secho('New snippets cloned from Bitbucket', fg='green')


if __name__ == '__main__':
    cli()
