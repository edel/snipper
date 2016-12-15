import os
import json
import re

from prompt_toolkit.completion import Completer, Completion

from .snippet import Snippet


__all__ = (
    'SnippetFilesCompleter',
)


class PathCompleter(Completer):
    collection = []

    def get_completions(self, document, complete_event):
        # https://github.com/dbcli/pgcli/blob/master/pgcli/pgcompleter.py#L336
        word_before_cursor = document.get_word_before_cursor(WORD=True)
        text_len = len(word_before_cursor)
        collection = self.fuzzyfinder(word_before_cursor, self.collection)
        matches = []

        for item in collection:
            matches.append(
                Completion(item, start_position=-text_len)
            )

        return matches

    @staticmethod
    def fuzzyfinder(user_input, collection):
        # http://blog.amjith.com/fuzzyfinder-in-10-lines-of-python
        suggestions = []
        pattern = '.*?'.join(user_input)   # Converts 'djm' to 'd.*?j.*?m'
        regex = re.compile(pattern, re.IGNORECASE)  # Compiles a regex.
        for item in collection:
            match = regex.search(item)   # Checks if the current item matches the regex.
            if match:
                suggestions.append((len(match.group()), match.start(), item))

        return [x for _, _, x in sorted(suggestions)]


class SnippetFilesCompleter(PathCompleter):

    def __init__(self, config):
        super(SnippetFilesCompleter, self).__init__()

        with open(os.path.join(config.config.get('metadata_file')), 'r') as file:
            data = json.loads(file.read())
            for item in data['values']:
                snippet_id = item['id']
                snippet = Snippet(config, item['owner']['username'], snippet_id)
                if not snippet.get_path():
                    continue

                file_dir = os.path.split(snippet.get_path())[1]
                for file_name in snippet.get_files():
                    file_path_relative = os.path.join(item['owner']['username'], file_dir, file_name)
                    self.collection.append(file_path_relative)


class SnippetDirCompleter(PathCompleter):

    def __init__(self, config):
        super(SnippetDirCompleter, self).__init__()

        with open(os.path.join(config.config.get('metadata_file')), 'r') as file:
            data = json.loads(file.read())
            for item in data['values']:
                snippet_id = item['id']
                snippet = Snippet(config, item['owner']['username'], snippet_id)
                snippet_dir_name = os.path.split(snippet.repo_path)[1]

                self.collection.append(os.path.join(item['owner']['username'], snippet_dir_name))
