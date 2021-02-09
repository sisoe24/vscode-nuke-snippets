"""Generate nuke snippets from online documentation."""
import os
import json
import logging
import textwrap

from typing import Generator
from typing import Union

import requests
import regex
from bs4 import BeautifulSoup


# TODO: convert double quotes to single quotes?

logging.basicConfig(format='%(levelname)s: %(message)15s',
                    filename='log/report.log', filemode='w',
                    level=logging.INFO)

SNIPPETS = {}


def clean_header(function: str) -> str:
    """Clean function header text.

    Some functions arguments are splitted into multiple lines, so they need
    to be put back together and clean the empty spaces left.

    Args:
        function (str): function text to clean.

    Returns:
        str: function header text 1 line.
    """
    logging.debug('Header to clean: %s', function)

    func_header = ' '.join(textwrap.wrap(function))

    patterns = {
        r'\s{2,}': ' ',
        r'self,?': ''
    }

    for pattern, sub in patterns.items():
        func_header = regex.sub(pattern, sub, func_header)

    logging.info('Header: %s', func_header)

    return func_header


def clean_description(function: str) -> str:
    """Clean function description text.

    Args:
        function (str): function text to clean.

    Returns:
        str: function description text 1 line.
    """
    logging.debug("Description to clean: %s", function)

    patterns = {
        r'source\scode': '',
        r'(\n){2,}': '\n\n'
    }

    for pattern, sub in patterns.items():
        function = regex.sub(pattern, sub, function.strip())

    logging.info('Description: %s', function)
    return function


def insert_placeholders(args: str, body: str) -> str:
    """Insert placeholder sign "$" to arguments inside the snippets body.

    Args:
        body (str): body snippet

    Returns:
        str: body snippet with placeholders
    """
    args_list = [arg.strip() for arg in args.split(',')]
    logging.debug('Args list: %s', args_list)
    placeholders_list = []

    for index, arg in enumerate(args_list, 1):
        placeholder = "${%i:%s}" % (index, arg)

        # if argument is a keyword
        if keywords := regex.search(r'(\w+=)(.+)', arg):
            keyword, arg = keywords.groups()
            placeholder = "%s${%i:%s}" % (keyword, index, arg)

        placeholders_list.append(placeholder)

    body = body.replace(f'({args})', f'({", ".join(placeholders_list)})')

    logging.debug('Args placeholder: %s', placeholders_list)
    logging.info('New Header: %s', body)
    return body


def extract_args(function: str) -> str:
    """Extract function arguments.

    Args:
        function (str): function text to extract arguments.

    Returns:
        str: new function text with placeholder arguments.
    """
    if args := regex.search(r'(?<=\()(.+)(?=\))', function):
        function = insert_placeholders(args.group(), function)
    return function


def snippets_template(title: str, prefix: str, body: str, description: str) -> dict:
    """Vscode snippets template.

    Args:
        module (str): nuke module of the method
        title (str): title of the snippet
        prefix (str): prefix of the snippet
        body (str): body of the snippet
        description (str): description of the snippet

    Returns:
        dict: [description]
    """
    return {
        title: {
            "prefix": prefix,
            "body": body,
            "description": description
        }
    }


def function_details(page: BeautifulSoup) -> Generator:
    """Get the functions information in from the page details."""
    for child in page.find_all('table', attrs={'class': 'details'}):
        yield child.text.strip()


def functions(page: BeautifulSoup, section: str) -> Generator:
    """Get the functions information in from the table.

    @param section: this is a function.
    """
    table = page.find('a', attrs={'name': f'section-{section}'})
    function_table = table.next_element.next_element
    func_summary = function_table.findChildren(
        'td', attrs={'class': 'summary'})

    summary_returns = ""
    index = 0
    for summary in func_summary:
        summary = summary.text

        if (index % 2) == 0:
            summary_returns = summary
        else:
            if regex.search(r'\w', summary_returns):
                summary_returns = regex.sub(
                    r'\n', ' ', summary_returns, regex.ENHANCEMATCH)
                summary = f"{summary}Returns ->\b{summary_returns}"

        index += 1
        yield summary.strip()


def class_link_page(page: BeautifulSoup) -> Generator:
    """Extract link reference for nuke classes.

    Args:
        page (BeautifulSoup): BeautifulSoup object to parse.

    Yields:
        [str]: nuke class link reference
    """
    section = page.find('a', attrs={'name': 'section-Classes'})
    class_section = section.next_element.next_element

    for i in class_section.findChildren('a'):
        link = i.get('href')
        if not link.startswith('#'):
            yield str(link)


def generate_snippets(page, module, section):
    for generator in (functions(page, section), function_details(page)):
        for text in generator:
            logging.info('\n')
            logging.debug(text)

            if func := regex.match(r'^(.+?\))\n(.+)', text, regex.S):
                logging.debug('Regex match for: %s = %s', text, func)

                func_header = clean_header(func.group(1))

                # XXX: ignore dunder methods for now?
                if func_header.startswith('__'):
                    continue

                func_description = clean_description(func.group(2))
                func_new_header = extract_args(func_header)

                SNIPPETS.update(snippets_template(
                    title=f'{module}.{func_header}',
                    prefix=f'{module}.{func_header}',
                    body=f'{module}.{func_new_header}',
                    description=func_description
                ))

            if regex.search('Variables Details', text):
                break


def parse_nuke_module(reference_url: str):
    """Parse and extract snippets from nuke main module web page

    Args:
        reference_url (str): web starting page of nuke modules

    Returns:
        generator: a generator with nuke classes links.
    """
    nuke_url = reference_url + '/nuke-module.html'
    html_text = requests.get(nuke_url).text
    soup = BeautifulSoup(html_text, 'html.parser')

    generate_snippets(soup, 'nuke', section='Functions')

    return class_link_page(soup)


def parse_class_module(reference_url: str, links: Union[Generator, list]):
    """Parse and extract snippets from the nuke classes module web page.

    Args:
        reference_url (str): web link of the page to parse
        links (str): web link of the page to parse
    """
    for link in links:

        class_link = os.path.join(reference_url, link)

        html_text = requests.get(class_link).text
        soup = BeautifulSoup(html_text, 'html.parser')

        class_module = link.replace('-class.html', '') + '()'

        print(f'==> DEBUG: class_module: {class_module}')

        generate_snippets(soup, class_module, section='InstanceMethods')


def generate_json(snippets: dict, filename=''):
    """Create json snippets file.

    Args:
        snippets (dict): vscode snippets to write into json
        filename (str, optional): optional filename. Defaults to ''.
    """
    snippets_filepath = f'snippets/{filename}snippets.code-snippets'

    with open(snippets_filepath, 'w') as snippets_file:
        snippets_file.write("{}")
        snippets_file.seek(0)
        json.dump(snippets, snippets_file, indent=4)


def main():
    """Execute main."""
    reference_url = 'https://learn.foundry.com/nuke/developers/70/pythonreference'
    class_links = parse_nuke_module(reference_url)
    parse_class_module(reference_url, class_links)
    generate_json(SNIPPETS)


if __name__ == '__main__':
    main()
