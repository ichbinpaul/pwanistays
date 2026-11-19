"""Reviewed public copy, guarded by the listing facts used to write it."""
from copy import deepcopy
import uuid

AREA_GUIDES = {'Nyali': 'nyali', 'Diani': 'diani', 'Shanzu': 'shanzu'}


def apply_copy(snapshot, document):
    if not isinstance(document, dict) or type(document.get('version')) is not int or document['version'] != 1 or not isinstance(document.get('properties'), dict):
        raise ValueError('Invalid reviewed property copy')
    result = deepcopy(snapshot)
    entries = document['properties']
    for identity, entry in entries.items():
        if str(uuid.UUID(identity)) != identity or not isinstance(entry, dict):
            raise ValueError('Invalid copy identity')
        facts = entry.get('facts')
        if not isinstance(facts, dict) or any(not isinstance(facts.get(k), str) for k in ('title','location','unit_type')) or not isinstance(facts.get('amenities'), list) or any(not isinstance(a,str) for a in facts['amenities']):
            raise ValueError('Copy requires the public listing facts used to write it')
        if not isinstance(entry.get('summary'), str) or not 40 <= len(entry['summary']) <= 180:
            raise ValueError('Copy requires a concise plain-text search summary')
        if not isinstance(entry.get('paragraphs'),list) or len(entry['paragraphs']) < 2 or any(not isinstance(p,str) or not p.strip() for p in entry['paragraphs']):
            raise ValueError('Copy requires reviewed description paragraphs')
    applied, stale = [], []
    for row in result['properties']:
        entry = entries.get(row['id'])
        if not entry:
            continue
        facts = entry['facts']
        if any(row.get(k) != facts[k] for k in ('title','location','unit_type')) or not set(facts['amenities']).issubset(set(row.get('amenities',[]))):
            stale.append(row['id'])
            continue
        row['description'] = '\n\n'.join(p.strip() for p in entry['paragraphs'])
        row['seo_summary'] = entry['summary'].strip()
        applied.append(row['id'])
    return result, {'applied':applied,'needs_review':stale}
