#!/usr/bin/env python3

import logging
import os
import shutil
import subprocess
import urllib.request

from email.utils import parsedate_to_datetime
from pathlib import Path, PurePath

from bs4 import BeautifulSoup

import requests


def update_file(url, path):
    logging.info('Downloading "%s" to "%s"', url, path)

    if path.exists() and not path.is_file():
        logging.error('File path "%s" exists and is no file', path)
        return

    r = None
    while not r:
        try:
            r = requests.head(url, allow_redirects=True)
        except requests.exceptions.InvalidSchema:
            pass

    last_modified = r.headers.get('Last-Modified', None)
    if not last_modified:
        logging.error('Url "%s" does not give Last-Modified, ignoring',
                      r.url)
        return

    try:
        timestamp = parsedate_to_datetime(last_modified).timestamp()
    except TypeError:
        logging.error('Cannot parse timestamp "%s", ignoring', last_modified)
        return

    local_timestamp = None
    if path.is_file():
        local_timestamp = path.stat().st_mtime

    if not local_timestamp or local_timestamp < timestamp:
        logging.debug('Remote file is newer, downloading')
        with urllib.request.urlopen(r.url) as response, \
                path.open('wb') as out_file:
            shutil.copyfileobj(response, out_file)
        os.utime(path, (timestamp, timestamp))
    else:
        logging.debug('Remote file is not newer')

    subprocess.run(['git', 'annex', 'add', str(path)])
    subprocess.run(['git', 'annex', 'addurl', url, '--file=' + str(path)])


def update(package, folder=None):
    logging.info('Updating package "%s"', package)
    url = 'http://ctan.org/pkg/' + package
    r = requests.get(url)

    if r.status_code != 200:
        logging.warning('Trying to fetch "%s" gave return code %d', url,
                        r.status_code)
        return

    if folder is None:
        folder = Path('.')

    directory = folder / Path(package)
    try:
        directory.mkdir(exist_ok=True)
    except FileExistsError:
        logging.warning('Path "%s" exists and is not a directory.', directory)
        return

    soup = BeautifulSoup(r.text, 'lxml')

    table = soup.find('table', class_='entry')
    documents = table.select('a.doc-pdf')

    for document in documents:
        file_name = document.text.strip().replace('\xad', '') + '.pdf'
        update_file(
            document.get('href'),
            directory / PurePath(file_name)
        )

    subprocess.run(['git', 'commit', '-m', 'Adding CTAN package: ' + package])


def main(packages_file, packages_folder, documents_file, documents_folder):
    packages_folder = Path(packages_folder)
    try:
        with open(packages_file, 'r') as f:
            for package in f:
                package = package.strip()
                if package.startswith('#') or not package:
                    continue
                update(package, packages_folder)
    except OSError:
        logging.error('Cannot read file "%s"', packages_file)

    documents_folder = Path(documents_folder)
    try:
        documents_folder.mkdir(exist_ok=True)
    except FileExistsError:
        logging.warning('Path "%s" exists and is not a directory.',
                        documents_folder)
        return
    try:
        with open(documents_file, 'r') as f:
            for document in f:
                document = document.strip()
                if document.startswith('#') or not document:
                    continue
                url, name = document.split(' ', 1)
                update_file(url, documents_folder / Path(name))
                subprocess.run(['git', 'commit', '-m',
                                'Adding URL: ' + document])
    except OSError:
        logging.error('Cannot read file "%s"', documents_file)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main('ctan.txt', 'ctan', 'documents.txt', 'documents')
