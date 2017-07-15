#!/usr/bin/env python
"""
Ensures that every feature in a GeoJSON file has a "name" property.  (This
is the property that the MSF Dashboard expects to be present for every
region or point it shows on the map.)

If the "name" property is missing on a feature, it is filled in with the
value of any existing property named "NAME" or "Name", or otherwise with the
name of the finest-grained administrative level according to the properties
named "admin0Name", "admin1Name", "admin2Name", and so on.

Example usage:

    python geojson_add_names.py input.json output.json
"""
__version__ = '2017-07-15'

import json
import sys

name_keys = sum([['ADM%d_NAME' % i, 'admin%dName' % i] for i in range(6)], [])
name_keys += ['NAME', 'Name', 'name']

geojson = json.load(open(sys.argv[1]))
for feature in geojson['features']:
    props = feature.get('properties')
    if props and not props.get('name'):
        for key in reversed(name_keys):
            if props.get(key):
               props['name'] = props[key]
               break

with open(sys.argv[2], 'w') as file:
    json.dump(geojson, file, indent=2, sort_keys=True)
