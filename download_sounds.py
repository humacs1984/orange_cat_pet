# -*- coding: utf-8 -*-
"""Download real sound effects from BigSoundBank (CC0, free, no login, direct download).
URL pattern: https://bigsoundbank.com/UPLOAD/mp3/{id}.mp3"""
import os, subprocess, time, urllib.request, json

SOUNDS_DIR = r"D:\Hermes workspace\orange_cat_pet\sounds"
os.makedirs(SOUNDS_DIR, exist_ok=True)

BSB = "https://bigsoundbank.com"

# BigSoundBank sound IDs mapped to pet actions
# Cat sounds: https://bigsoundbank.com/search?q=cat&CatID=ANMLCat
# Other categories searched manually
SOUND_MAP = {
    # Cat vocalizations
    'idle':      {'id': '0436', 'desc': 'Cat Purr (11s, realistic male cat purr)', 'search': 'cat purr'},
    'purr':      {'id': '0981', 'desc': 'Cat Purring #2 (different purr from idle)', 'search': 'cat purring'},
    'meow':      {'id': '1890', 'desc': 'Meow Cat #2', 'search': 'cat meow'},
    'sleep':     {'id': '1010', 'desc': 'Cat Purring #3 (soft, for sleep)', 'search': 'cat purring soft'},
    'surprised': {'id': '0494', 'desc': 'Little Meow of a Cat #1', 'search': 'little meow'},
    'beg':       {'id': '0926', 'desc': 'Cat Meow Made with Mouth', 'search': 'cat meow mouth'},
    'happy':     {'id': '0390', 'desc': 'Mewing kitten 3 weeks', 'search': 'kitten mewing'},
    'groom':     {'id': '0098', 'desc': 'Small mewing of a cat (grooming-like)', 'search': 'small mewing'},
    # Non-cat specific (footsteps, water, etc.)
    'walk':      {'id': '0436', 'desc': 'Cat Purr for walk ambience', 'search': 'cat'},
    'run':       {'id': '1891', 'desc': 'Meow cat #3 (energetic)', 'search': 'cat energetic'},
    'eat':       {'id': '1890', 'desc': 'Meow Cat #2 (eating vocalization)', 'search': 'cat eat'},
    'scratch':   {'id': '0817', 'desc': 'Two Cats Fighting (scratching)', 'search': 'cat fighting'},
    'dance':     {'id': '1898', 'desc': 'Meow Cat #10', 'search': 'cat meow'},
    'stretch':   {'id': '1475', 'desc': 'Little meow of a cat #5 (stretch yawn)', 'search': 'cat yawn'},
    'sit':       {'id': '1901', 'desc': 'Meow Cat #13', 'search': 'cat meow'},
    'bath':      {'id': '0436', 'desc': 'Cat Purr (bath complaint)', 'search': 'cat bath'},
    'wave':      {'id': '1895', 'desc': 'Meow cat #7', 'search': 'cat meow short'},
    'type':      {'id': '0436', 'desc': 'Cat Purr (typing ambience)', 'search': 'cat keyboard'},
    'play_dead': {'id': '1887', 'desc': 'Growling cat #3 (thud-like)', 'search': 'cat growl'},
    'roll':      {'id': '1480', 'desc': 'Little meow of a cat #10', 'search': 'cat meow short'},
}

# Actually, let me search for more appropriate non-cat sounds from other categories
# BigSoundBank has: footsteps, water, impact/thud, etc.
# Let me refine the mapping with better category matches

def download_bsb(sound_id, dest_path, fmt='mp3'):
    """Download from BigSoundBank"""
    url = f"{BSB}/UPLOAD/{fmt}/{sound_id}.{fmt}"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            with open(dest_path, 'wb') as f:
                f.write(resp.read())
        return os.path.getsize(dest_path) > 500
    except Exception as e:
        print(f"  Error: {e}")
        return False

def to_wav(src, dst, sr=22050):
    """Convert to WAV"""
    cmd = ['ffmpeg', '-y', '-i', src, '-ar', str(sr), '-ac', '1', '-vn', dst]
    r = subprocess.run(cmd, capture_output=True, timeout=30)
    return r.returncode == 0

def get_duration(path):
    r = subprocess.run(['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
                        '-of', 'csv=p=0', path], capture_output=True, timeout=10)
    try: return float(r.stdout.decode().strip())
    except: return 0

# First, let me search BigSoundBank for more appropriate non-cat sounds
# by scraping search pages
def search_bsb(query):
    """Search BigSoundBank and return sound IDs"""
    url = f"{BSB}/search?q={urllib.parse.quote(query)}"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
        # Find sound IDs from URLs like /something-sXXXX.html
        import re
        ids = re.findall(r'-s(\d+)\.html', html)
        return list(dict.fromkeys(ids))  # unique, preserve order
    except Exception as e:
        print(f"  Search error: {e}")
        return []

import urllib.parse

# Search for non-cat sounds we need
print("=== Searching BigSoundBank for specific sounds ===")
search_results = {}
searches = {
    'walk': 'footsteps',
    'run': 'running footsteps',
    'eat': 'chewing eating',
    'scratch': 'scratch scraping',
    'bath': 'water splash',
    'play_dead': 'thud impact fall',
    'roll': 'rolling',
    'stretch': 'yawn',
    'type': 'keyboard typing',
    'dance': 'bounce tap',
    'wave': 'whoosh swipe',
    'sit': 'thud soft landing',
}

for action, query in searches.items():
    print(f"  {action}: searching '{query}'...", end=' ', flush=True)
    ids = search_bsb(query)
    print(f"found {len(ids)} sounds: {ids[:5]}")
    search_results[action] = ids
    time.sleep(0.3)

# Now map the best sound IDs for each action
print("\n=== Downloading sounds ===")

# Final mapping with best BigSoundBank sound IDs
FINAL_MAP = {}

# Cat sounds (direct from ANMLCat category)
FINAL_MAP['idle'] = '0436'      # Cat Purr (11s, realistic)
FINAL_MAP['purr'] = '0981'      # Cat Purring #2 
FINAL_MAP['meow'] = '1890'      # Meow Cat #2
FINAL_MAP['sleep'] = '1010'     # Cat Purring #3
FINAL_MAP['surprised'] = '0494' # Little Meow #1
FINAL_MAP['beg'] = '0926'       # Cat Meow Made with Mouth
FINAL_MAP['happy'] = '0390'     # Mewing kitten 3 weeks
FINAL_MAP['groom'] = '0098'     # Small mewing of a cat
FINAL_MAP['stretch'] = '1475'   # Little meow #5

# Non-cat sounds from search results
for action, ids in search_results.items():
    if action not in FINAL_MAP and ids:
        FINAL_MAP[action] = ids[0]

# Download all
results = {}
for action, sid in FINAL_MAP.items():
    wav_path = os.path.join(SOUNDS_DIR, f'{action}.wav')
    tmp_mp3 = os.path.join(SOUNDS_DIR, f'_tmp_{action}.mp3')
    print(f"{action}: downloading BSB #{sid}...", end=' ', flush=True)
    
    if download_bsb(sid, tmp_mp3):
        if to_wav(tmp_mp3, wav_path):
            os.remove(tmp_mp3)
            dur = get_duration(wav_path)
            sz = os.path.getsize(wav_path)
            print(f"OK {sz:,}B ({dur:.1f}s)")
            results[action] = 'ok'
        else:
            print("convert FAIL")
            if os.path.exists(tmp_mp3): os.remove(tmp_mp3)
            results[action] = 'convert_fail'
    else:
        print("download FAIL")
        results[action] = 'download_fail'
    
    time.sleep(0.2)

print(f"\n=== Summary ===")
ok = sum(1 for v in results.values() if v == 'ok')
print(f"Downloaded: {ok}/20")
for a, s in results.items():
    if s != 'ok':
        print(f"  MISSING: {a} ({s})")

# Check for duplicates
import hashlib
md5s = {}
for f in sorted(os.listdir(SOUNDS_DIR)):
    if f.endswith('.wav'):
        with open(os.path.join(SOUNDS_DIR, f), 'rb') as fh:
            h = hashlib.md5(fh.read()).hexdigest()
        if h in md5s:
            print(f"DUPLICATE: {f} == {md5s[h]}")
        md5s[h] = f
print(f"Unique: {len(md5s)}")

print(f"\nFinal sounds:")
total = 0
for f in sorted(os.listdir(SOUNDS_DIR)):
    if f.endswith('.wav'):
        p = os.path.join(SOUNDS_DIR, f)
        sz = os.path.getsize(p)
        dur = get_duration(p)
        total += sz
        print(f"  {f}: {sz:,}B ({dur:.1f}s)")
print(f"Total: {total:,}B = {total/1024:.0f}KB")
