# -*- coding: utf-8 -*-
"""
Sound manager for desktop pet — plays sound effects on state transitions.
Uses QSoundEffect (Qt5 multimedia) for cross-platform playback.

Architecture:
- Preloaded: all sounds loaded at startup to eliminate first-play delay
- WAV format (Windows QSoundEffect doesn't support OGG)
- Loop states loop their sound seamlessly; one-shot states play once
- Volume control via menu
- All sounds optional: missing files are silently skipped
"""

import os
from PyQt5.QtMultimedia import QSoundEffect
from PyQt5.QtCore import QUrl


SOUNDS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sounds')

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

# Default volume (0.0 - 1.0)
DEFAULT_VOLUME = 0.5
VOLUME_MIN, VOLUME_MAX, VOLUME_STEP = 0.0, 1.0, 0.1


class SoundManager:
    """Manages pet sound effects — preload, loop/oneshot, volume control."""

    def __init__(self, parent=None):
        self._parent = parent       # QObject parent for QSoundEffect (prevents GC)
        self._effects = {}          # resolved state -> QSoundEffect
        self._loaded = set()        # states checked (found or not)
        self._current = None        # currently playing resolved state name
        self._volume = DEFAULT_VOLUME
        self._muted = False
        self._volume_path = self._volume_cfg_path()

    @staticmethod
    def _volume_cfg_path():
        if getattr(__import__('sys'), 'frozen', False):
            return os.path.join(os.path.dirname(__import__('sys').executable), 'sound_config.json')
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sound_config.json')

    def load_volume(self):
        import json
        try:
            with open(self._volume_path, 'r', encoding='utf-8') as f:
                d = json.load(f)
                self._volume = max(VOLUME_MIN, min(VOLUME_MAX, float(d.get('volume', DEFAULT_VOLUME))))
                self._muted = bool(d.get('muted', False))
        except Exception:
            pass

    def save_volume(self):
        import json
        try:
            with open(self._volume_path, 'w', encoding='utf-8') as f:
                json.dump({'volume': self._volume, 'muted': self._muted}, f)
        except Exception:
            pass

    def preload_all(self):
        """Preload all sound effects at startup so there's no delay on first play.
        QSoundEffect.setSource is async — this starts loading early so sounds
        are ready by the time the user triggers an action."""
        all_states = set(LOOP_STATES) | set(ONESHOT_STATES) | set(SOUND_ALIAS.keys())
        for state in all_states:
            self._get_effect(state)

    def _get_effect(self, state):
        """Lazy-load QSoundEffect for state. Returns None if no sound file."""
        resolved = SOUND_ALIAS.get(state, state)
        if resolved in self._loaded:
            return self._effects.get(resolved)

        # Windows QSoundEffect only supports WAV; fall back to OGG on other platforms
        wav_path = os.path.join(SOUNDS_DIR, f'{resolved}.wav')
        ogg_path = os.path.join(SOUNDS_DIR, f'{resolved}.ogg')
        snd_path = wav_path if os.path.isfile(wav_path) else ogg_path
        if not os.path.isfile(snd_path):
            self._loaded.add(resolved)  # mark checked even if missing (don't retry)
            return None

        url = QUrl.fromLocalFile(snd_path)
        eff = QSoundEffect(self._parent)   # parent prevents GC
        eff.setSource(url)
        eff.setVolume(self._volume if not self._muted else 0.0)
        eff.setLoopCount(QSoundEffect.Infinite if resolved in LOOP_STATES else 1)
        self._effects[resolved] = eff
        self._loaded.add(resolved)
        return eff

    def play(self, state):
        """Play sound for given state. Stops previous looping sound."""
        resolved = SOUND_ALIAS.get(state, state)
        # Stop previous sound if it's different
        if self._current and self._current != resolved:
            prev_eff = self._effects.get(self._current)
            if prev_eff and prev_eff.isPlaying():
                prev_eff.stop()
        self._current = resolved
        eff = self._get_effect(state)
        if eff is None or self._muted:
            return
        # If still loading (async), schedule play when ready
        if eff.status() == QSoundEffect.Loading:
            eff.statusChanged.connect(lambda s, e=eff: e.play() if s == QSoundEffect.Ready else None)
            return
        # Restart if same state re-entered (one-shot needs replay)
        if eff.isPlaying() and resolved in ONESHOT_STATES:
            eff.stop()
        if not eff.isPlaying():
            eff.play()

    def stop(self):
        """Stop all sounds."""
        for eff in self._effects.values():
            if eff.isPlaying():
                eff.stop()
        self._current = None

    def stop_state(self, state):
        """Stop sound for specific state."""
        resolved = SOUND_ALIAS.get(state, state)
        eff = self._effects.get(resolved)
        if eff and eff.isPlaying():
            eff.stop()
        if self._current == resolved:
            self._current = None

    def set_volume(self, vol):
        self._volume = max(VOLUME_MIN, min(VOLUME_MAX, vol))
        for eff in self._effects.values():
            eff.setVolume(0.0 if self._muted else self._volume)
        self.save_volume()

    def toggle_mute(self):
        self._muted = not self._muted
        for eff in self._effects.values():
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
