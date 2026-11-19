"""Copy must track its source facts and guides must track live inventory."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from content_copy import apply_copy
from build_location_guides import render_guides
from build_property_previews import render_property
ROOT=Path(__file__).resolve().parents[1]

class CopyTests(unittest.TestCase):
    def setUp(self):
        self.doc=json.loads((ROOT/'content/property-copy.json').read_text())
        self.id,self.entry=next(iter(self.doc['properties'].items()))
        self.row={'id':self.id,**deepcopy(self.entry['facts']),'description':'Original public description',
            'url':'https://pwanistays.com/stays/'+self.id+'/', 'images':['https://example.supabase.co/photo.jpg']}
        self.source={'version':1,'properties':[self.row]}

    def test_reviewed_copy_is_public_and_does_not_mutate_source(self):
        before=deepcopy(self.source)
        updated,status=apply_copy(self.source,self.doc)
        self.assertEqual(self.source,before)
        self.assertEqual(status['applied'],[self.id])
        self.assertEqual(updated['properties'][0]['seo_summary'],self.entry['summary'])
        self.assertEqual(updated['properties'][0]['description'],'\n\n'.join(self.entry['paragraphs']))
        self.assertEqual(updated['properties'][0]['url'],self.row['url'])

    def test_changed_facts_skip_stale_copy_but_extra_amenities_are_safe(self):
        for field in ['title','location','unit_type','amenities']:
            source=deepcopy(self.source)
            source['properties'][0][field]=[] if field=='amenities' else 'Changed'
            updated,status=apply_copy(source,self.doc)
            self.assertEqual(status['needs_review'],[self.id])
            self.assertEqual(updated['properties'][0]['description'],'Original public description')
            self.assertNotIn('seo_summary',updated['properties'][0])
        self.source['properties'][0]['amenities'].append('New verified feature')
        self.assertEqual(apply_copy(self.source,self.doc)[1]['applied'],[self.id])

    def test_malformed_copy_cannot_publish(self):
        for field,value in [('summary',None),('summary','x'*181),('paragraphs',[]),('facts',{})]:
            doc=deepcopy(self.doc);doc['properties'][self.id][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):apply_copy(self.source,doc)

    def test_metadata_uses_summary_while_visible_copy_keeps_paragraphs(self):
        updated,_=apply_copy(self.source,self.doc)
        html=render_property((ROOT/'property.html').read_text(),updated['properties'][0])
        self.assertIn('id="propertyAbout"',html)
        self.assertNotIn('id="propertyAbout" hidden',html)
        self.assertIn('content="'+self.entry['summary']+'"',html)
        self.assertIn(self.entry['paragraphs'][0],html)
        self.assertIn('/guides/nyali/',html)

class GuideTests(unittest.TestCase):
    def test_guides_link_only_their_active_area_and_keep_canonical_identity(self):
        document=json.loads((ROOT/'content/location-guides.json').read_text())
        source=json.loads((ROOT/'catalogue/properties.json').read_text())
        pages=render_guides(source,document)
        self.assertEqual(set(pages),{'index.html','nyali/index.html','diani/index.html','shanzu/index.html'})
        for guide in document['guides']:
            html=pages[guide['slug']+'/index.html']
            self.assertIn('href="https://pwanistays.com/guides/'+guide['slug']+'/"',html)
            for row in source['properties']:
                self.assertEqual('href="'+row['url'].removeprefix('https://pwanistays.com')+'"' in html,row['location']==guide['location'])
        reduced=deepcopy(source);reduced['properties']=[r for r in source['properties'] if r['location']!='Diani']
        html=render_guides(reduced,document)['diani/index.html']
        self.assertIn('0 listed units',html)
        self.assertNotIn('<li><a href="/stays/',html)

if __name__=='__main__':unittest.main()
