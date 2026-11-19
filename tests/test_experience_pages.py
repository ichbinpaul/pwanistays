"""Generated experience content must retain each trip and escape public text."""
from copy import deepcopy
from html import escape
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import build_experience_pages as mod
class ExperienceTests(unittest.TestCase):
 def source(self):return json.loads((mod.R/'content/experience-trips.json').read_text())
 def test_all_existing_trips_remain_linked_to_their_quotation(self):
  source=self.source();pages=mod.render_pages(source)
  self.assertEqual(set(pages),{'coastal-cultural.html','safari.html','nairobi.html'})
  for group in source['categories']:
   html=pages[group['slug']+'.html'];self.assertEqual(html.count('class="trip-card"'),len(group['items']))
   for row in group['items']:self.assertIn('<h3>'+escape(row['title'])+'</h3>',html)
   self.assertIn('footer class="about-footer"',html)
 def test_content_is_escaped_in_body_and_structured_data(self):
  source=self.source();source['categories'][0]['items'][0]['title']='Sea <script>alert(1)</script> & boat'
  html=mod.render_pages(source)['coastal-cultural.html'];self.assertNotIn('<script>alert(1)</script>',html);self.assertIn('&lt;script&gt;',html);self.assertIn('\\u003cscript>',html)
 def test_empty_or_duplicate_trips_cannot_replace_a_page(self):
  for mode in ['empty','duplicate']:
   source=self.source();items=source['categories'][0]['items'];source['categories'][0]['items']=[] if mode=='empty' else [items[0],items[0]]
   with self.assertRaises(ValueError):mod.render_pages(source)
