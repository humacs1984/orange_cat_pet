# -*- coding: utf-8 -*-
"""
Sound manager for OrangeCat Desktop Pet — advanced sound system with:
- Sound pools (random selection from multiple WAV files per action)
- Probability-based playback (not every animation triggers sound)
- Cooldown timers (prevent annoying repetition)
- Delayed playback (sync sound with animation events)
- Volume variation and pitch variation
- Secondary sound pools (rare additional sounds like soft meow during bath)
- Seamless loop support with fade in/out
- JSON configuration (orange_cat_sounds.json)

Architecture:
- Preloaded: all primary sounds loaded at startup
- QSoundEffect (Qt5 Multimedia) for cross-platform playback
- WAV format only (Windows QSoundEffect doesn't support OGG)
"""

import os, sys, json, time, random, math
from PyQt5.QtMultimedia import QSoundEffect
from PyQt5.QtCore import QUrl, QTimer


class SoundManager:
    """Advanced sound manager for OrangeCat Desktop Pet."""

    # Paths — resolved lazily for PyInstaller compatibility
    @staticmethod
    def _app_dir():
        """Get the application directory (works in both dev and PyInstaller bundle).
        - PyInstaller onefile: sys._MEIPASS points to temp extraction dir (has sounds/)
        - PyInstaller onedir/BUNDLE: sys._MEIPASS points to Contents/MacOS/ (has sounds/)
        - Dev: __file__'s directory
        """
        if hasattr(sys, '_MEIPASS'):
            return sys._MEIPASS
        if getattr(sys, 'frozen', False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))

    SOUNDS_DIR = None  # set in __init__
    CONFIG_PATH = None  # set in __init__

    # States with looping sounds (must match ANIMS loop=True exactly)
    LOOP_STATES = {
        'idle', 'walk', 'run', 'eat', 'meow', 'purr', 'groom',
        'sleep', 'sit', 'scratch', 'dance', 'beg', 'bath', 'surprised', 'wave', 'type',
    }

    # One-shot states (must match ANIMS loop=False exactly)
    ONESHOT_STATES = {'happy', 'roll', 'stretch', 'play_dead'}

    # Alias: potty_run uses walk sound, potty uses sit sound
    SOUND_ALIAS = {
        'potty_run': 'walk',
        'potty': 'sit',
    }

    DEFAULT_VOLUME = 0.5
    VOLUME_MIN, VOLUME_MAX, VOLUME_STEP = 0.0, 1.0, 0.1

    def __init__(self, parent=None):
        self._parent = parent           # QObject parent for QSoundEffect (prevents GC)
        self._effects = {}              # file_path -> QSoundEffect
        self._loaded = set()            # file paths checked (found or not)
        self._current_state = None      # currently playing action state name
        self._current_primary = None    # currently playing primary file path
        self._current_secondary = None  # currently playing secondary file path
        self._volume = self.DEFAULT_VOLUME
        self._muted = False
        self._cooldowns = {}            # state -> last_play_timestamp
        self._delay_timers = {}         # state -> QTimer (for delayed playback)
        self._secondary_timers = {}     # state -> QTimer (for delayed secondary)
        self._config = {}               # loaded JSON config
        # Resolve paths at init time (works in dev, PyInstaller onefile, and .app bundle)
        self.SOUNDS_DIR = os.path.join(self._app_dir(), 'sounds')
        self.CONFIG_PATH = os.path.join(self.SOUNDS_DIR, 'config', 'orange_cat_sounds.json')
        self._volume_path = self._volume_cfg_path()

        # Load config
        self._load_config()

    @staticmethod
    def _volume_cfg_path():
        """Volume config must be writable. In .app bundle, the bundle dir is read-only on macOS."""
        if getattr(sys, 'frozen', False):
            if sys.platform == 'darwin':
                # macOS: write to Application Support (bundle is read-only)
                _support = os.path.expanduser('~/Library/Application Support/OrangeCat')
                os.makedirs(_support, exist_ok=True)
                return os.path.join(_support, 'sound_config.json')
            return os.path.join(os.path.dirname(sys.executable), 'sound_config.json')
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sound_config.json')

    def _load_config(self):
        """Load sound configuration from JSON."""
        try:
            with open(self.CONFIG_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # Strip _meta and _note fields
            self._config = {k: v for k, v in data.items() if not k.startswith('_')}
        except Exception:
            self._config = {}

    def _cfg(self, state, key, default=None):
        """Get a config value for a state."""
        return self._config.get(state, {}).get(key, default)

    def load_volume(self):
        try:
            with open(self._volume_path, 'r', encoding='utf-8') as f:
                d = json.load(f)
                self._volume = max(self.VOLUME_MIN, min(self.VOLUME_MAX, float(d.get('volume', self.DEFAULT_VOLUME))))
                self._muted = bool(d.get('muted', False))
        except Exception:
            pass

    def save_volume(self):
        try:
            with open(self._volume_path, 'w', encoding='utf-8') as f:
                json.dump({'volume': self._volume, 'muted': self._muted}, f)
        except Exception:
            pass

    def preload_all(self):
        """Preload all primary sound files from config at startup.
        v121: Process Qt events to ensure QSoundEffect finishes Loading->Ready
        before the first play() call, eliminating the 'no sound at startup' bug."""
        from PyQt5.QtCore import QCoreApplication
        for state in self._config:
            pool = self._cfg(state, 'sound_pool', [])
            for item in pool:
                self._preload_file(item['file'])
            # Also preload secondary pool
            sec_pool = self._cfg(state, 'secondary_pool', [])
            for item in sec_pool:
                self._preload_file(item['file'])
        # Pump Qt event loop so QSoundEffect can finish async Loading->Ready
        for _ in range(50):
            QCoreApplication.processEvents()
        # Verify: log any effects still in Loading state
        loading = [os.path.basename(p) for p, e in self._effects.items()
                   if e.status() == QSoundEffect.Loading]
        if loading:
            # Pump more if needed
            for _ in range(100):
                QCoreApplication.processEvents()
                if all(e.status() != QSoundEffect.Loading for e in self._effects.values()):
                    break

    def _preload_file(self, filename):
        """Preload a single WAV file into QSoundEffect."""
        path = os.path.join(self.SOUNDS_DIR, filename)
        if path in self._loaded:
            return
        if not os.path.isfile(path):
            self._loaded.add(path)
            return
        url = QUrl.fromLocalFile(path)
        eff = QSoundEffect(self._parent)
        eff.setSource(url)
        eff.setVolume(self._volume if not self._muted else 0.0)
        self._effects[path] = eff
        self._loaded.add(path)

    def _get_effect(self, filename):
        """Get or lazy-load QSoundEffect for a filename. Returns (effect, path) or None."""
        path = os.path.join(self.SOUNDS_DIR, filename)
        if path not in self._loaded:
            self._preload_file(filename)
        eff = self._effects.get(path)
        return eff, path

    def _weighted_choice(self, pool):
        """Select an item from a weighted pool."""
        if not pool:
            return None
        total = sum(item.get('weight', 1) for item in pool)
        r = random.uniform(0, total)
        acc = 0
        for item in pool:
            acc += item.get('weight', 1)
            if r <= acc:
                return item
        return pool[-1]

    def _can_play(self, state):
        """Check if a state can play sound (probability + cooldown)."""
        prob = self._cfg(state, 'probability', 1.0)
        if random.random() > prob:
            return False
        cooldown = self._cfg(state, 'cooldown', 0)
        if cooldown > 0:
            last = self._cooldowns.get(state, 0)
            if time.time() - last < cooldown:
                return False
        return True

    def _apply_volume(self, base_vol, variation):
        """Apply random volume variation."""
        v = base_vol + random.uniform(-variation, variation)
        return max(0.0, min(1.0, v))

    def play(self, state):
        """Play sound for given state with full config support."""
        resolved = self.SOUND_ALIAS.get(state, state)

        # Stop previous sound if different state
        if self._current_state and self._current_state != resolved:
            self._stop_current()

        self._current_state = resolved

        # Check config
        cfg = self._config.get(resolved, {})
        if not cfg:
            # Fallback: try to play {state}.wav directly
            self._play_simple(resolved)
            return

        pool = cfg.get('sound_pool', [])
        if not pool:
            return  # Silent action (e.g. play_dead)

        # Probability + cooldown check
        if not self._can_play(resolved):
            return

        # Select from pool
        chosen = self._weighted_choice(pool)
        if not chosen:
            return

        base_vol = cfg.get('volume', 0.5)
        vol_var = cfg.get('volume_variation', 0.0)
        delay = cfg.get('delay', 0.0)
        is_loop = cfg.get('loop', resolved in self.LOOP_STATES)

        vol = self._apply_volume(base_vol, vol_var)

        if delay > 0:
            # Delayed playback
            timer = QTimer(self._parent)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda: self._do_play(resolved, chosen['file'], vol, is_loop))
            self._delay_timers[resolved] = timer
            timer.start(int(delay * 1000))
        else:
            self._do_play(resolved, chosen['file'], vol, is_loop)

        # Handle secondary pool (e.g. soft meow during bath)
        self._maybe_play_secondary(resolved)

        # Update cooldown
        self._cooldowns[resolved] = time.time()

    def _do_play(self, state, filename, volume, is_loop):
        """Actually play a sound file."""
        result = self._get_effect(filename)
        if result is None or result[0] is None:
            return
        eff, path = result

        # Stop previous primary if same state
        if self._current_primary and self._current_primary != path:
            old = self._effects.get(self._current_primary)
            if old and old.isPlaying():
                old.stop()

        self._current_primary = path
        eff.setVolume(0.0 if self._muted else volume)
        eff.setLoopCount(QSoundEffect.Infinite if is_loop else 1)

        status = eff.status()
        if status == QSoundEffect.Ready:
            if eff.isPlaying():
                eff.stop()
            eff.play()
        elif status == QSoundEffect.Loading:
            # v121-fix: In EXE (PyInstaller), first load can be slow due to
            # _MEI extraction. Pump the event loop synchronously with a short
            # timeout so the sound plays immediately instead of being silently
            # dropped if the async handler fires too late.
            from PyQt5.QtCore import QCoreApplication, QElapsedTimer
            timer_wait = QElapsedTimer()
            timer_wait.start()
            waited = False
            while eff.status() == QSoundEffect.Loading and timer_wait.elapsed() < 2000:
                QCoreApplication.processEvents()
                if eff.status() == QSoundEffect.Ready:
                    waited = True
                    break
            if eff.status() == QSoundEffect.Ready:
                if eff.isPlaying():
                    eff.stop()
                eff.play()
            else:
                # Still loading after timeout — async fallback
                def _on_ready(s, e=eff):
                    if s == QSoundEffect.Ready:
                        e.statusChanged.disconnect(_on_ready)
                        if e.isPlaying():
                            e.stop()
                        e.play()
                eff.statusChanged.connect(_on_ready)

    def _maybe_play_secondary(self, state):
        """Possibly play a secondary sound (e.g. soft meow during bath)."""
        sec_pool = self._cfg(state, 'secondary_pool', [])
        if not sec_pool:
            return
        sec_prob = self._cfg(state, 'secondary_probability', 0.0)
        if random.random() > sec_prob:
            return
        sec_cooldown = self._cfg(state, 'secondary_cooldown', 10.0)
        sec_key = f'_sec_{state}'
        last = self._cooldowns.get(sec_key, 0)
        if time.time() - last < sec_cooldown:
            return

        chosen = self._weighted_choice(sec_pool)
        if not chosen:
            return
        sec_vol = self._cfg(state, 'secondary_volume', 0.4)
        # Play secondary with a small random delay (0.5-2s into the action)
        delay_ms = int(random.uniform(500, 2000))

        timer = QTimer(self._parent)
        timer.setSingleShot(True)
        f = chosen['file']
        v = sec_vol
        def _play_sec():
            result = self._get_effect(f)
            if result and result[0]:
                eff2, p2 = result
                eff2.setVolume(0.0 if self._muted else v)
                eff2.setLoopCount(1)
                if eff2.isPlaying():
                    eff2.stop()
                status = eff2.status()
                if status == QSoundEffect.Ready:
                    eff2.play()
                elif status == QSoundEffect.Loading:
                    from PyQt5.QtCore import QCoreApplication, QElapsedTimer
                    tw = QElapsedTimer()
                    tw.start()
                    while eff2.status() == QSoundEffect.Loading and tw.elapsed() < 1500:
                        QCoreApplication.processEvents()
                    if eff2.status() == QSoundEffect.Ready:
                        eff2.play()
                    else:
                        def _on_ready2(s, e=eff2):
                            if s == QSoundEffect.Ready:
                                e.statusChanged.disconnect(_on_ready2)
                                if e.isPlaying():
                                    e.stop()
                                e.play()
                        eff2.statusChanged.connect(_on_ready2)
                self._current_secondary = p2
        timer.timeout.connect(_play_sec)
        self._secondary_timers[state] = timer
        timer.start(delay_ms)
        self._cooldowns[sec_key] = time.time()

    def _play_simple(self, state):
        """Fallback: play {state}.wav directly without config."""
        wav_path = os.path.join(self.SOUNDS_DIR, f'{state}.wav')
        ogg_path = os.path.join(self.SOUNDS_DIR, f'{state}.ogg')
        if os.path.isfile(wav_path):
            self._do_play(state, f'{state}.wav', self._volume, state in self.LOOP_STATES)
        elif os.path.isfile(ogg_path):
            self._do_play(state, f'{state}.ogg', self._volume, state in self.LOOP_STATES)

    def _stop_current(self):
        """Stop currently playing primary and secondary sounds."""
        if self._current_primary:
            eff = self._effects.get(self._current_primary)
            if eff and eff.isPlaying():
                eff.stop()
            self._current_primary = None

        if self._current_secondary:
            eff = self._effects.get(self._current_secondary)
            if eff and eff.isPlaying():
                eff.stop()
            self._current_secondary = None

        # Cancel pending delay timers
        for state, timer in self._delay_timers.items():
            timer.stop()
        self._delay_timers.clear()
        for state, timer in self._secondary_timers.items():
            timer.stop()
        self._secondary_timers.clear()

    def stop(self):
        """Stop all sounds."""
        for eff in self._effects.values():
            if eff.isPlaying():
                eff.stop()
        self._current_primary = None
        self._current_secondary = None
        self._current_state = None
        for timer in list(self._delay_timers.values()):
            timer.stop()
        self._delay_timers.clear()
        for timer in list(self._secondary_timers.values()):
            timer.stop()
        self._secondary_timers.clear()

    def stop_state(self, state):
        """Stop sound for specific state."""
        resolved = self.SOUND_ALIAS.get(state, state)
        if self._current_state == resolved:
            self._stop_current()
            self._current_state = None

    def set_volume(self, vol):
        self._volume = max(self.VOLUME_MIN, min(self.VOLUME_MAX, vol))
        # Note: per-play volume is set at play time; global volume scales in play()
        # For immediate effect on currently playing sounds:
        for eff in self._effects.values():
            if eff.isPlaying():
                eff.setVolume(0.0 if self._muted else self._volume)
        self.save_volume()

    def toggle_mute(self):
        self._muted = not self._muted
        for eff in self._effects.values():
            if eff.isPlaying():
                eff.setVolume(0.0 if self._muted else self._volume)
        self.save_volume()
        return self._muted

    @property
    def volume(self):
        return self._volume

    @property
    def muted(self):
        return self._muted

    @staticmethod
    def expected_sounds():
        """Return list of expected sound file names for all 20 actions."""
        base = ['idle', 'walk', 'run', 'eat', 'meow', 'purr', 'groom',
                'sleep', 'sit', 'scratch', 'happy', 'roll', 'dance', 'stretch',
                'beg', 'bath', 'surprised', 'play_dead', 'wave', 'type']
        return [f'{s}.wav' for s in base]
