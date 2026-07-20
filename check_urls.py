import os, re, sys
os.environ['DJANGO_SETTINGS_MODULE'] = 'core.settings'

import django
django.setup()
from django.urls import reverse, NoReverseMatch

templates_dir = r'C:\Users\rafid\Downloads\LostFind\templates'
errors = []

for root, dirs, files in os.walk(templates_dir):
    for f in files:
        if f.endswith('.html'):
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8') as fh:
                content = fh.read()
            urls = re.findall(r"{% url ['\"]([\w:]+)['\"]", content)
            for u in urls:
                try:
                    reverse(u)
                except NoReverseMatch:
                    rel = os.path.relpath(path, templates_dir)
                    errors.append(f'{rel}: {u}')

if errors:
    print('Broken URL references found:')
    for e in errors:
        print(f'  {e}')
else:
    print('All URL references are valid!')
