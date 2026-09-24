# -*- coding: utf-8 -*-
"""
Sound manager v2 for OrangeCat Desktop Pet — 16 source WAVs + 8 pre-rendered variants = 20 actions.

Architecture:
- 16 source WAVs in sounds/ (converted from MP3 at build time)
- 8 variant WAVs in sounds/variants/ (pre-rendered via ffmpeg at build time)
- orange_cat_sounds.json declares per-pool-item source + speed/pitch overrides
- At runtime: resolve source+variant path, load QSoundEffect, play
- No ffmpeg dependency at runtime — all variants are pre-built

Source reuse examples:
  - footsteps.wav → walk (speed=1.0) + run (variant footsteps_s1.15.wav)
  - lick.wav → groom (speed=1.0) + bath (variant lick_s1.1.wav)
  - purr.wav → purr (speed=1.0) + idle (variant purr_s0.85.wav)
  - soft_meow.wav → meow(1.0) + sit(0.9) + stretch(0.95,-0.2)
"""

import os, sys, json, time, random
from PyQt5.QtMultimedia import QSoundEffect
from PyQt5.QtCore import QUrl, QTimer


class SoundManager:
    """Sound manager v2: 16 source WAVs + 8 pre-rendered variants = 20 actions."""

    # Alias: potty_run uses walk sound, potty uses sit sound
    SOUND_ALIAS = {
        'potty_run': 'walk',
        'potty': 'sit',
    }

    DEFAULT_VOLUME = 0.5
    VOLUME_MIN, VOLUME_MAX, VOLUME_STEP = 0.0, 1.0, 0.1

    def __init__(self, parent=None):
        self._parent = parent
        self._effects = {}              # path -> QSoundEffect
        self._loaded = set()            # paths checked
        self._current_state = None
        self._current_primary = None
        self._current_secondary = None
        self._volume = self.DEFAULT_VOLUME
        self._muted = False
        self._cooldowns = {}
        self._delay_timers = {}
        self._secondary_timers = {}
        self._config = {}

        # Resolve paths
        self.SOUNDS_DIR = self._resolve_sounds_dir()
        self.VARIANTS_DIR = os.path.join(self.SOUNDS_DIR, 'variants')
        self.CONFIG_PATH = os.path.join(self.SOUNDS_DIR, 'config', 'orange_cat_sounds.json')
        self._volume_path = self._volume_cfg_path()

        # Load config
        self._load_config()

    @staticmethod
    def _resolve_sounds_dir():
        """Resolve sounds/ directory for dev, PyInstaller onefile, and macOS .app bundle."""
        if hasattr(sys, '_MEIPASS'):
            return os.path.join(sys._MEIPASS, 'sounds')
        if getattr(sys, 'frozen', False):
            return os.path.join(os.path.dirname(sys.executable), 'sounds')
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sounds')

    @staticmethod
    def _volume_cfg_path():
        """Volume config must be writable. In .app bundle, redirect to Application Support."""
        if getattr(sys, 'frozen', False):
            if sys.platform == 'darwin':
                _support = os.path.expanduser('~/Library/Application Support/OrangeCat')
                os.makedirs(_support, exist_ok=True)
                return os.path.join(_support, 'sound_config.json')
            return os.path.join(os.path.dirname(sys.executable), 'sound_config.json')
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sound_config.json')

    def _load_config(self):
        try:
            with open(self.CONFIG_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self._config = {k: v for k, v in data.items() if not k.startswith('_')}
        except Exception:
            self._config = {}

    def _cfg(self, state, key, default=None):
        return self._config.get(state, {}).get(key, default)

    def load_volume(self):
        try:
            with open(self._volume_path, 'r', encoding='utf-8') as f:
                d = json.load(f)
                self._volume = max(self.VOLUME_MIN, min(self.VOLUME_MAX,
                    float(d.get('volume', self.DEFAULT_VOLUME))))
                self._muted = bool(d.get('muted', False))
        except Exception:
            pass

    def save_volume(self):
        try:
            with open(self._volume_path, 'w', encoding='utf-8') as f:
                json.dump({'volume': self._volume, 'muted': self._muted}, f)
        except Exception:
            pass

    # ============================================================
    # Variant path resolution (no ffmpeg needed at runtime)
    # ============================================================

    def _variant_path(self, source, speed=1.0, pitch=0.0):
        """Resolve the WAV path for a source+speed+pitch combination.
        If speed=1.0 and pitch=0.0, return source WAV directly.
        Otherwise, look for a pre-rendered variant in sounds/variants/.
        Fallback to source WAV if variant not found."""
        if speed == 1.0 and pitch == 0.0:
            return os.path.join(self.SOUNDS_DIR, f'{source}.wav')

        # Build variant filename: {source}_s{speed}[_p{pitch}].wav
        s = round(speed, 3)
        p = round(pitch, 2)
        tag = f"s{s}"
        if p != 0.0:
            tag += f"_p{p}"
        vname = f"{source}_{tag}.wav"
        vpath = os.path.join(self.VARIANTS_DIR, vname)
        if os.path.isfile(vpath):
            return vpath

        # Fallback: source WAV (variant not pre-rendered)
        return os.path.join(self.SOUNDS_DIR, f'{source}.wav')

    def _resolve_pool_item_path(self, item, state_cfg):
        """Resolve a pool item to its WAV file path."""
        source = item.get('source', '')
        speed = item.get('speed', state_cfg.get('speed', 1.0))
        pitch = item.get('pitch', state_cfg.get('pitch', 0.0))
        return self._variant_path(source, speed, pitch)

    # ============================================================
    # Preloading
    # ============================================================

    def preload_all(self):
        """Preload all source + variant WAVs into QSoundEffects at startup."""
        from PyQt5.QtCore import QCoreApplication

        for state, cfg in self._config.items():
            for item in cfg.get('sound_pool', []):
                path = self._resolve_pool_item_path(item, cfg)
                self._preload_path(path)
            for item in cfg.get('secondary_pool', []):
                path = self._resolve_pool_item_path(item, cfg)
                self._preload_path(path)

        # Pump Qt event loop to finish async Loading→Ready
        for _ in range(50):
            QCoreApplication.processEvents()
        loading = [os.path.basename(p) for p, e in self._effects.items()
                   if e.status() == QSoundEffect.Loading]
        if loading:
            for _ in range(100):
                QCoreApplication.processEvents()
                if all(e.status() != QSoundEffect.Loading for e in self._effects.values()):
                    break

    def _preload_path(self, path):
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

    def _get_effect(self, path):
        if path not in self._loaded:
            self._preload_path(path)
        return self._effects.get(path)

    # ============================================================
    # Playback
    # ============================================================

    def _weighted_choice(self, pool):
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
        v = base_vol + random.uniform(-variation, variation)
        return max(0.0, min(1.0, v))

    def play(self, state):
        """Play sound for given state with full config support."""
        resolved = self.SOUND_ALIAS.get(state, state)

        if self._current_state and self._current_state != resolved:
            self._stop_current()

        self._current_state = resolved

        cfg = self._config.get(resolved, {})
        if not cfg:
            self._play_simple(resolved)
            return

        pool = cfg.get('sound_pool', [])
        if not pool:
            return

        if not self._can_play(resolved):
            return

        chosen = self._weighted_choice(pool)
        if not chosen:
            return

        base_vol = cfg.get('volume', 0.5)
        vol_var = cfg.get('volume_variation', 0.0)
        delay = cfg.get('delay', 0.0)
        is_loop = cfg.get('loop', True)

        vol = self._apply_volume(base_vol, vol_var)

        path = self._resolve_pool_item_path(chosen, cfg)
        if not path:
            return

        if delay > 0:
            timer = QTimer(self._parent)
            timer.setSingleShot(True)
            p, v, lp = path, vol, is_loop
            def _delayed_play(p=p, v=v, lp=lp):
                self._do_play(resolved, p, v, lp)
            timer.timeout.connect(_delayed_play)
            self._delay_timers[resolved] = timer
            timer.start(int(delay * 1000))
        else:
            self._do_play(resolved, path, vol, is_loop)

        self._maybe_play_secondary(resolved, cfg)
        self._cooldowns[resolved] = time.time()

    def _do_play(self, state, path, volume, is_loop):
        eff = self._get_effect(path)
        if eff is None:
            return

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
            from PyQt5.QtCore import QCoreApplication, QElapsedTimer
            tw = QElapsedTimer()
            tw.start()
            while eff.status() == QSoundEffect.Loading and tw.elapsed() < 2000:
                QCoreApplication.processEvents()
                if eff.status() == QSoundEffect.Ready:
                    break
            if eff.status() == QSoundEffect.Ready:
                if eff.isPlaying():
                    eff.stop()
                eff.play()
            else:
                def _on_ready(s, e=eff):
                    if s == QSoundEffect.Ready:
                        e.statusChanged.disconnect(_on_ready)
                        if e.isPlaying():
                            e.stop()
                        e.play()
                eff.statusChanged.connect(_on_ready)

    def _maybe_play_secondary(self, state, cfg):
        sec_pool = cfg.get('secondary_pool', [])
        if not sec_pool:
            return
        sec_prob = cfg.get('secondary_probability', 0.0)
        if random.random() > sec_prob:
            return
        sec_cooldown = cfg.get('secondary_cooldown', 10.0)
        sec_key = f'_sec_{state}'
        last = self._cooldowns.get(sec_key, 0)
        if time.time() - last < sec_cooldown:
            return

        chosen = self._weighted_choice(sec_pool)
        if not chosen:
            return
        sec_vol = cfg.get('secondary_volume', 0.4)
        path = self._resolve_pool_item_path(chosen, cfg)
        if not path:
            return

        delay_ms = int(random.uniform(500, 2000))
        timer = QTimer(self._parent)
        timer.setSingleShot(True)
        p, v = path, sec_vol
        def _play_sec(p=p, v=v):
            eff2 = self._get_effect(p)
            if eff2:
                eff2.setVolume(0.0 if self._muted else v)
                eff2.setLoopCount(1)
                if eff2.isPlaying():
                    eff2.stop()
                status = eff2.status()
                if status == QSoundEffect.Ready:
                    eff2.play()
                elif status == QSoundEffect.Loading:
                    from PyQt5.QtCore import QCoreApplication, QElapsedTimer
                    tw2 = QElapsedTimer()
                    tw2.start()
                    while eff2.status() == QSoundEffect.Loading and tw2.elapsed() < 1500:
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
                self._current_secondary = p
        timer.timeout.connect(_play_sec)
        self._secondary_timers[state] = timer
        timer.start(delay_ms)
        self._cooldowns[sec_key] = time.time()

    def _play_simple(self, state):
        path = os.path.join(self.SOUNDS_DIR, f'{state}.wav')
        if os.path.isfile(path):
            self._do_play(state, path, self._volume, True)

    # ============================================================
    # Stop / Volume / Mute
    # ============================================================

    def _stop_current(self):
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
        for timer in self._delay_timers.values():
            timer.stop()
        self._delay_timers.clear()
        for timer in self._secondary_timers.values():
            timer.stop()
        self._secondary_timers.clear()

    def stop(self):
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
        resolved = self.SOUND_ALIAS.get(state, state)
        if self._current_state == resolved:
            self._stop_current()
            self._current_state = None

    def set_volume(self, vol):
        self._volume = max(self.VOLUME_MIN, min(self.VOLUME_MAX, vol))
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
        """Return list of 11 source WAV file names."""
        return [
            'attention_meow.wav', 'eat.wav', 'footsteps.wav',
            'happy_meow.wav', 'lick.wav', 'normal_meow.wav',
            'purr.wav', 'scratch.wav', 'sleep.wav', 'soft_meow.wav', 'type.wav',
        ]
