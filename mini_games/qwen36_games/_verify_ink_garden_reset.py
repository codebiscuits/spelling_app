#!/usr/bin/env python3
import re
from pathlib import Path
p = Path('/home/ross/Stuff/Documents/Coding/2026/spelling_app/mini_games/Ink_garden.html')
html = p.read_text(encoding='utf-8')
assert html.startswith('<!DOCTYPE html>'), 'not html'
assert re.search(r'<script>', html), 'missing script tag'
assert re.search(r'\(\(\s*(?:=>|\(\)\s*=>)\s*\{', html), 'missing self-contained script'
# Controls top-left
assert 'top:16px;left:16px' in html, 'controls not top-left'
# Reset pill bottom-centre
assert 'bottom:24px;left:50%;transform:translateX(-50%)' in html, 'reset pill not bottom-centre'
# reset() handler resets all fields and reseeding
assert 'function reset() {' in html, 'reset function missing'
assert 'seedGarden()' in html, 'seedGarden missing after reset'
assert 'brush = 14' in html, 'brush should revert to 14'
assert 'pN = 0' in html, 'pN should clear'
assert 'vx.fill(0); vy.fill(0);' in html, 'velocity field should clear'
assert 'dens.fill(0);' in html, 'density should clear'
# single file no external assets
assert '<link rel=' not in html, 'no link rel allowed'
assert "src='http" not in html and 'src="http' not in html, 'no external src allowed'
assert "href='http" not in html and 'href="http' not in html, 'no external href allowed'
print('ok')
