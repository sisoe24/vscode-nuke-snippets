import os
import json
import pathlib
import textwrap
import requests

from bs4 import BeautifulSoup
from requests.api import get

import regex

import logging


logging.basicConfig(format='%(levelname)s: %(message)15s',
                    filename='log/report.log', level=logging.INFO)

def snippets(title='', prefix='', body='', description=''):
    return {
        title: {
            "prefix": 'nuke.' + str(prefix),
            "body": 'nuke.' + body,
            "description": description
        }
    }


def insert_placeholders(args, body):
    """Insert placeholder sign "$" to arguments inside the snippets body.
    Args:
        body (str): body snippet

    Returns:

        str: body snippet with placeholders
    """
    args_list = [arg.strip() for arg in args.split(',')]
    for index, arg in enumerate(args_list, 1):
        placeholders = "${%i:%s}" % (index, arg)
        body = body.replace(arg, placeholders, 1)

    return body


def clean_body(body: str) -> str:
    patterns = {
        r'self': '',
    }
    for pattern, sub in patterns.items():
        body = regex.sub(pattern, sub, body)

    return body


def format_body(body: str) -> str:
    """Perform some formatting/cleaning of the snippet body code.
    Args: 
        body (str)

    Returns: 
        str: formatted/cleaned body code.
    """
    body = clean_body(body)

    if args := regex.search(r'(?<=\().+(?=\))', body):
        body = insert_placeholders(args.group(), body)
    return body


class NukeWebParser:
    def __init__(self, url, module):
        self._html_text = requests.get(url).text
        self._soup = BeautifulSoup(self._html_text, 'html.parser')
        self.module = module

    def get_table(self, section):
        table = self._soup.find('a', attrs={'name': f'section-{section}'})
        return table.next_element.next_element

    def class_link_pages(self):
        for i in self.get_table('Classes').findChildren('a'):
            yield i.get('href')

    def snippets(self, title='', prefix='', body='', description=''):
        return {
            title: {
                "prefix": self.module + str(prefix),
                "body": self.module + str(body),
                "description": description
            }
        }

    def export_snippets(self, section):
        if section == 'functions':
            section = self.get_table('Functions')
        elif section == 'classes':
            section = self.get_table('InstanceMethods')

        snippets_holder = {}
        for n in section.findChildren('tr'):
            index = 0
            for i in n.findChildren('td', attrs={'class': 'summary'}):

                line = regex.sub(r'source\scode', '', i.text.strip(), regex.M)
                line = ' '.join(textwrap.wrap(line))
                line = regex.sub(r'\s{2,}', ' ', line)

                if regex.search(r'^$', line):
                    index += 1
                    continue

                if index == 1:
                    func = regex.match(r'(.+?\))(?=\s)(.+)', line)
                    logging.debug(func)

                    func_body = ''
                    func_desc = ''

                    if func:
                        func_body = func.group(1)
                        func_desc = func.group(2).strip()

                    snippets_holder.update(
                        self.snippets(title=func_desc,
                                      prefix=func_body,
                                      body=format_body(func_body),
                                      description=func_desc))
                index += 1
        return snippets_holder


def generate_snippets(snippets, filename=''):
    """Create json snippets file."""
    snippets_filepath = f'snippets/{filename}snippets.code-snippets'

    with open(snippets_filepath, 'w') as snippets_file:
        snippets_file.write("{}")
        snippets_file.seek(0)
        json.dump(snippets, snippets_file, indent=4)


list(map(lambda file: os.remove(file), pathlib.Path('snippets').glob('*snippets')))

nuke_base_url = 'https://learn.foundry.com/nuke/developers/70/pythonreference'
nuke_url = nuke_base_url + '/nuke-module.html#activeViewer'

nuke = NukeWebParser(nuke_url, 'nuke.')
function_snippets = nuke.export_snippets('functions')


# for link in nuke.class_link_pages():
#     if link.startswith('nuke'):
#         class_page = nuke_base_url + '/' + link

#         module_name = link.replace('-class.html', '')
#         print(module_name)

#         nuke_class = NukeWebParser(class_page, module_name + '.')
#         classes_snippets = nuke_class.export_snippets('classes')
#         function_snippets.update(classes_snippets)

generate_snippets(function_snippets)
