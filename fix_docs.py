import os, re

md_files = ['README.md']
for root, _, files in os.walk('docs'):
    for f in files:
        if f.endswith('.md'):
            md_files.append(os.path.join(root, f))

for file in md_files:
    with open(file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Replace em-dashes and corrupted chars
    content = content.replace('\u2014', '-')
    content = content.replace('â€”', '-')
    content = content.replace('â€', '-')
    
    # Replace img tags with markdown img tags
    content = re.sub(r'<figure class="doc-figure">', '<figure class="doc-figure" markdown="span">', content)
    content = re.sub(r'<img src="(assets/[^"]+)" alt="([^"]*)">', r'![\2](\1)', content)
    
    with open(file, 'w', encoding='utf-8') as f:
        f.write(content)
