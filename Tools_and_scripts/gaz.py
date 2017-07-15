#!/usr/bin/env python
"""
Generates a gazetteer as an HTML file suitable for printing, and a menu tree
of locations in CSV format suitable for pasting into the "locations" tab of
a patient data input spreadsheet.  The first three arguments specify the
source CSV file and the two output files.

Example usage:

    python gaz.py wamm.csv gazetteer.html locations.csv

Optionally, subsequent arguments define the levels of the administrative
hierarchy, where each argument specifies the level abbreviation, level name,
and CSV column heading.

Example usage:

    python gaz.py wamm.csv gazetteer.html locations.csv D/District/loc_adm1 C/Chiefdom/loc_adm2 S/Section/loc_adm3 V/Village/VILLAGE_NAME

In the following description, the "leaf level" is the last specified level,
i.e. the finest level of the hierarchy.

A page is produced for each administrative division in every non-leaf level,
listing the division's children.  Non-leaf division names are assumed to be
unique among siblings; when the same non-leaf division name appears twice
in the CSV file under the same parent division, the rows are treated as
referring to the same division.  Leaf names are not assumed to be unique;
when the same leaf name appears twice in the CSV file under the same parent
division, they are treated as two separate siblings.
"""
__version__ = '2017-07-15'

import argparse
from collections import namedtuple
import csv
import datetime
import os
import re
import sys

Level = namedtuple('Level', ['name', 'abbr', 'key'])
Division = namedtuple('Division', ['name', 'path', 'children', 'row'])

ROOT = Division(name='', path=(), children=[], row={})
DEFAULT_LEVELS = []

DOCUMENT_TITLE = 'Gazetteer'

DOCUMENT_TEMPLATE = '''
<style>
{stylesheet}
</style>
<div class="page">
  <div class="cover">
    <div class="title">{title}</div>
    <div>Source: {filename}</div>
    <div>Version: {version}</div>
    <div class="contents">
      {contents}
    </div>
  </div>
</div>
{pages}
'''

STYLESHEET = '''
  div { font-family: helvetica neue, helvetica; font-size: 18pt; }
  th, td, th div, td div { font-size: 12pt; }
  .cover .title { font-weight: bold; }
  .page { margin: 1em; page-break-before: always; }
  .number { font-size: 60pt; float: right; }
  .ancestors { margin-bottom: 12pt; }
  .ancestor { font-size: 18pt; }
  .title { font-size: 24pt; margin: 0 0 1em; }
  .title .name { font-weight: bold; }
  .contents, .listing {
      clear: both;
      margin: 1em 0 0 0;
      padding: 1em;
      border: 0.25pt solid black;
  }
  .listing tr { vertical-align: baseline; }
  .listing th, .listing td {
      text-align: left;
      font-weight: normal;
      white-space: nowrap;
      page-break-inside: avoid;
  }
  .listing div.item { padding: 6pt 0; }
  .listing th { padding: 0 12pt 12pt 0; border-bottom: 0.25pt solid black; }
  .listing td { padding: 12pt 18pt 0 0; }
  .listing td:last-child { padding: 12pt 0 0 0; }
  .listing td.wrap { white-space: normal; }
  .listing th.name, .listing td.name { font-weight: bold; }
'''

CONTENT_ITEM_TEMPLATE = '''
  <div>{level.name} pages: {level.abbr}1 &ndash; {level.abbr}{count}</div>
'''

PAGE_TEMPLATE = '''
<div class="page">
  <div class="number">
    {level.abbr}{index}
  </div>
  <div class="ancestors">
    {ancestors}
  </div>
  <div class="title">
    {level.name}: <span class="name">{division.name}</span>
  </div>
  {listing}
</div>
'''

ANCESTOR_TEMPLATE = '''
  <div class="ancestor">
    {level.name}: <span class="name">{name}</span>
  </div>
'''

LISTING_TEMPLATE = LEAF_LISTING_TEMPLATE = '''
  <div class="listing">
    {items}
  </div>
'''

ITEM_TEMPLATE = LEAF_ITEM_TEMPLATE = '''
  <div class="item">
    {child.name} &mdash; {level.abbr}{index}
  </div>
'''

def fix_up_division(division):
    pass

def sort_divisions(divisions):
    return sorted(divisions, key=lambda division: division.path)

# Site-specific customizations begin here.

DEFAULT_LEVELS = [
    Level(name='District', abbr='D', key='loc_adm1'),
    Level(name='Chiefdom', abbr='C', key='loc_adm2'),
    Level(name='Section', abbr='S', key='loc_adm3'),
    Level(name='Village', abbr='V', key='VILLAGE_NAME'),
]

DOCUMENT_TITLE = 'Nixon Memorial Hospital Gazetteer'

LEAF_LISTING_TEMPLATE = '''
  <table cellpadding="0" cellspacing="0" class="listing">
    <tr class="headings">
      <th class="name">Village name</th>
      <th>Other names</th>
      <th>Village chief</th>
      <th>Meaning of village name</th>
    </tr>
    {items}
  </table>
'''

LEAF_ITEM_TEMPLATE = '''
    <tr class="item">
      <td class="name">{child.row[VILLAGE_NAME]}</td>
      <td>{child.row[VILLAGE_OTHER_NAMES]}</td>
      <td>{child.row[CHIEF_NAME]}</td>
      <td class="wrap">{child.row[VILLAGE_NAME_MEANING]}</td>
    </tr>
'''

def fit_length(text, max_length):
    if len(text) > max_length:
        return text[:max_length - 3] + '...'
    return text

def fix_up_division(division):
    others = []
    alt = division.row.get('ALT_VILLAGE_NAME', '').strip()
    if alt:
        others.append(fit_length(alt, 24))
    hist = division.row.get('HISTORICAL_NAME', '').strip()
    if hist:
        others.append('%s (old)' % fit_length(hist, 24))
    division.row['VILLAGE_OTHER_NAMES'] = '<br>'.join(others)

    chief_words = division.row.get('CHIEF_NAME', '').split()
    if chief_words[:1] == ['Chief']:
        chief_words[:1] = []
    if len(chief_words) > 2 and len(' '.join(chief_words)) > 20:
        chief_words[2:2] = ['<br>&nbsp;&nbsp;&nbsp;&nbsp;']
    division.row['CHIEF_NAME'] = ' '.join(chief_words)

def sort_divisions(divisions):
    return sorted(divisions, key=lambda division: [
        '~' if item in ['OTHER', '(other)'] else item for item in division.path])

# Site-specific customizations end here.

def normalize_name(name):
    if (name or '').strip() == 'OTHER':
        return '(other)'
    return ' '.join(re.sub(r'[<>&_]', ' ', name or '').split())

def read_divisions(file, levels):
    division_lists = [[] for level in levels]
    for row in csv.DictReader(file):
        names = [row[level.key].strip() or None for level in levels]
        node = ROOT
        for i, (level, name) in enumerate(zip(levels, names)):
            name = normalize_name(name)
            if not name:
                break
            for child in node.children:
                # Allow duplicate names only at the last level of hierarchy.
                if child.name == name and level is not levels[-1]:
                    break
            else:
                child = Division(
                    name=name, path=node.path + (name,), children=[], row=row)
                node.children.append(child)
                division_lists[i].append(child)
            node = child
    return division_lists

def sort_and_number_divisions(division_lists):
    sorted_division_lists = []
    indexes = {}
    for i, divisions in enumerate(division_lists):
        sorted_divisions = sort_divisions(divisions)
        for j, division in enumerate(sorted_divisions):
            indexes[division.path] = j + 1
        sorted_division_lists.append(sorted_divisions)
    return sorted_division_lists, indexes

def print_divisions(division_lists, indexes):
    for level, divisions in zip(levels, division_lists):
        print()
        print(level)
        for division in divisions:
            print('%s%d. %s' % (
                level.abbr, indexes[division.path], division.name))

def write_gazetteer(out_file, levels, division_lists, indexes, source_path):
    listing_template = LISTING_TEMPLATE
    item_template = ITEM_TEMPLATE
    pages = []
    for level, child_level, divisions in zip(
        levels, levels[1:], division_lists):
        if child_level is levels[-1]:
            listing_template = LEAF_LISTING_TEMPLATE
            item_template = LEAF_ITEM_TEMPLATE
        for division in divisions:
            items = []
            for child in sort_divisions(division.children):
                fix_up_division(child)
                items.append(item_template.format(
                    level=child_level,
                    child=child,
                    index=indexes[child.path]
                ))
            pages.append(PAGE_TEMPLATE.format(
                level=level,
                division=division,
                index=indexes[division.path],
                ancestors=''.join(
                    ANCESTOR_TEMPLATE.format(level=anc_level, name=anc_name)
                    for anc_level, anc_name in zip(levels, division.path[:-1])
                ),
                listing=listing_template.format(items=''.join(items))
            ))
    out_file.write(DOCUMENT_TEMPLATE.format(
        stylesheet=STYLESHEET,
        title=DOCUMENT_TITLE,
        pages=''.join(pages),
        filename=os.path.basename(source_path),
        version=datetime.datetime.utcfromtimestamp(
            os.path.getmtime(source_path)).strftime('%Y-%m-%d %H:%M:%S UTC'),
        contents=''.join(
            CONTENT_ITEM_TEMPLATE.format(level=level, count=len(divisions))
            for level, divisions in zip(levels[:-1], division_lists)
        )
    ))

def transpose(rows):
    width = max(len(row) for row in rows)
    return zip(*(row + [None]*(width - len(row)) for row in rows))

def write_csv_menu_tree(out_file, levels, division_lists):
    columns = []
    for divisions in [[ROOT]] + division_lists[:-1]:
        for division in divisions:
            names = [child.name for child in sort_divisions(division.children)]
            if divisions is division_lists[-2] and '(other)' not in names:
                names.append('(other)')
            columns.append(['/'.join(division.path)] + names)
    writer = csv.writer(out_file)
    for row in transpose(columns):
        writer.writerow(row)

def main(args):
    parser = argparse.ArgumentParser(description=(
        'gaz.py version %s: Generates an HTML gazetteer or a CSV menu tree.' %
        __version__))
    parser.add_argument('input', metavar='input.csv', help='CSV input file')
    parser.add_argument('gazetteer_output', metavar='gazetteer.html',
                        help='HTML output file')
    parser.add_argument('locations_output', metavar='locations.csv',
                        help='CSV location menu tree output file')
    parser.add_argument('levels', nargs='*', help='''
       Level specifications in abbr/name/key form, e.g. "D/District/loc_adm1"
    ''')
    if not sys.argv[1:]:
        sys.exit(parser.print_help())
    args = parser.parse_args()

    levels = [
        Level(name=name, abbr=abbr, key=key)
        for abbr, name, key in [spec.split('/') for spec in args.levels]
    ] if args.levels else DEFAULT_LEVELS

    division_lists = read_divisions(open(args.input), levels)
    division_lists, indexes = sort_and_number_divisions(division_lists)

    if args.gazetteer_output:
        with open(args.gazetteer_output, 'w') as out_file:
            write_gazetteer(out_file, levels, division_lists, indexes, args.input)
    if args.locations_output:
        with open(args.locations_output, 'w') as out_file:
            write_csv_menu_tree(out_file, levels, division_lists)

if __name__ == '__main__':
    main(sys.argv[1:])
