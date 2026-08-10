import json
import os


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(PROJECT_ROOT, "config")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

DEFAULT_CONFIG = {
    "stockfish_path": "",
    "website": "Chess.com",
    "move_to_play": 1,
    "manual_mode": False,
    "mouseless_mode": False,
    "non_stop_puzzles": False,
    "bongcloud": False,
    "timer_enabled": False,
    "mouse_move_min_time": 1.0,
    "mouse_move_max_time": 3.0,
    "timer_min": 2,
    "timer_max": 15,
    "load_cookies": False,
    "show_arrow_1": False,
    "show_arrow_2": False,
    "show_arrow_3": False,
    "elo_preset": 2000,
    "limit_elo": False,
    "dynamic_difficulty": False,
    "autostart": False,
    "stockfish_settings": {
        "skill_level": 20,
        "hash": 128,
        "depth": 6,
        "threads": 4,
        "move_overhead": 15,
        "analysis_time_budget": 1.2
    },
    "arrow_colors": {
        "1": [0, 255, 0, 122],
        "2": [255, 163, 0, 122],
        "3": [255, 0, 0, 122]
    },
    "window": {
        "x": None,
        "y": None,
        "width": 400,
        "height": 550
    }
}



def get_bundled_stockfish_path():
    """Return the path to a bundled stockfish executable, or None."""
    exe_name = "stockfish-windows-x86-64-avx2.exe"
    for subdir in (PROJECT_ROOT, os.path.join(PROJECT_ROOT, "stockfish-windows-x86-64-avx2")):
        candidate = os.path.join(subdir, exe_name)
        if os.path.isfile(candidate):
            return candidate
    return None


class ConfigManager:
    """Persistent configuration stored as JSON in the config/ directory."""

    def __init__(self):
        self.data = dict(DEFAULT_CONFIG)
        self._load()

    def _load(self):
        if not os.path.isfile(CONFIG_PATH):
            self._detect_stockfish()
            self.save()
            return
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
                loaded = json.load(fh)
            self._deep_merge(self.data, loaded)
            self._detect_stockfish()
        except (json.JSONDecodeError, OSError):
            self.data = dict(DEFAULT_CONFIG)
            self._detect_stockfish()

    def save(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, indent=2)

    @staticmethod
    def _deep_merge(dest, source):
        for key, value in source.items():
            if key in dest and isinstance(dest[key], dict) and isinstance(value, dict):
                ConfigManager._deep_merge(dest[key], value)
            else:
                dest[key] = value

    def _detect_stockfish(self):
        configured = self.data.get("stockfish_path", "")
        if not configured or not os.path.isfile(configured):
            bundled = get_bundled_stockfish_path()
            if bundled is not None:
                self.data["stockfish_path"] = bundled

    def __getitem__(self, key):
        return self.data[key]

    def get(self, key, default=None):
        return self.data.get(key, default)

    def __setitem__(self, key, value):
        self.data[key] = value

    def update(self, *args, **kwargs):
        self.data.update(*args, **kwargs)

    def set_stockfish_setting(self, name, value):
        self.data.setdefault("stockfish_settings", {})[name] = value

    def set_arrow_color(self, rank, rgba):
        self.data.setdefault("arrow_colors", {})[str(rank)] = [int(v) for v in rgba]

    def set_window_size(self, width, height):
        self.data.setdefault("window", {})["width"] = width
        self.data.setdefault("window", {})["height"] = height

    def set_window_pos(self, x, y):
        self.data.setdefault("window", {})["x"] = x
        self.data.setdefault("window", {})["y"] = y

    def apply_to_gui(self):
        """Restore all saved values into the live GUI widgets."""
        import dearpygui.dearpygui as dpg
        for rank in ("1", "2", "3"):
            color = self.data.get("arrow_colors", {}).get(rank)
            if color:
                dpg.configure_item(f"edit {rank}", default_value=tuple(int(v) for v in color))
        dpg.set_value("manual mode", self.data.get("manual_mode", False))
        dpg.configure_item("manual mode", default_value=self.data.get("manual_mode", False))
        dpg.set_value("mouseless mode", self.data.get("mouseless_mode", False))
        dpg.configure_item("mouseless mode", default_value=self.data.get("mouseless_mode", False))
        dpg.set_value("puzzles", self.data.get("non_stop_puzzles", False))
        dpg.configure_item("puzzles", default_value=self.data.get("non_stop_puzzles", False))
        dpg.set_value("bongcloud", self.data.get("bongcloud", False))
        dpg.configure_item("bongcloud", default_value=self.data.get("bongcloud", False))
        dpg.set_value("timer", self.data.get("timer_enabled", False))
        dpg.configure_item("timer", default_value=self.data.get("timer_enabled", False))
        dpg.set_value("load cookies", self.data.get("load_cookies", False))
        dpg.configure_item("load cookies", default_value=self.data.get("load_cookies", False))
        dpg.set_value("show arrow 1", self.data.get("show_arrow_1", False))
        dpg.configure_item("show arrow 1", default_value=self.data.get("show_arrow_1", False))
        dpg.set_value("show arrow 2", self.data.get("show_arrow_2", False))
        dpg.configure_item("show arrow 2", default_value=self.data.get("show_arrow_2", False))
        dpg.set_value("show arrow 3", self.data.get("show_arrow_3", False))
        dpg.configure_item("show arrow 3", default_value=self.data.get("show_arrow_3", False))
        dpg.set_value("limit elo", self.data.get("limit_elo", False))
        dpg.configure_item("limit elo", default_value=self.data.get("limit_elo", False))
        dpg.set_value("elo preset", self.data.get("elo_preset", 2000))
        dpg.configure_item("elo preset", default_value=self.data.get("elo_preset", 2000))
        dpg.set_value("dynamic difficulty", self.data.get("dynamic_difficulty", False))
        dpg.configure_item("dynamic difficulty", default_value=self.data.get("dynamic_difficulty", False))
        dpg.set_value("autostart", self.data.get("autostart", False))
        dpg.configure_item("autostart", default_value=self.data.get("autostart", False))
        dpg.set_value("mouse min time", self.data.get("mouse_move_min_time", 1.0))
        dpg.set_value("mouse max time", self.data.get("mouse_move_max_time", 3.0))
        move_map = {1: "Best Move", 2: "2nd Best Move", 3: "3rd Best Move"}

        move_val = move_map.get(self.data.get("move_to_play", 1), "Best Move")
        dpg.set_value("move select", move_val)
        dpg.configure_item("move select", default_value=move_val)
        dpg.set_value("min timer", self.data.get("timer_min", 2))
        dpg.set_value("max timer", self.data.get("timer_max", 15))
        sf = self.data.get("stockfish_settings", {})
        dpg.set_value("skill level", sf.get("skill_level", 20))
        dpg.configure_item("skill level", default_value=sf.get("skill_level", 20))
        dpg.set_value("hash", sf.get("hash", 8))
        dpg.set_value("depth", sf.get("depth", 6))
        dpg.configure_item("depth", default_value=sf.get("depth", 6))
        dpg.set_value("threads", sf.get("threads", 1))
        dpg.set_value("move overhead", sf.get("move_overhead", 15))
        dpg.set_value("analysis time", sf.get("analysis_time_budget", 1.2))

    def sync_from_gui(self):
        """Read current GUI widget values back into self.data."""
        import dearpygui.dearpygui as dpg
        self.data["manual_mode"] = dpg.get_value("manual mode") == True
        self.data["mouseless_mode"] = dpg.get_value("mouseless mode") == True
        self.data["non_stop_puzzles"] = dpg.get_value("puzzles") == True
        self.data["bongcloud"] = dpg.get_value("bongcloud") == True
        self.data["timer_enabled"] = dpg.get_value("timer") == True
        self.data["load_cookies"] = dpg.get_value("load cookies") == True
        self.data["timer_min"] = dpg.get_value("min timer")
        self.data["timer_max"] = dpg.get_value("max timer")
        app_data = dpg.get_value("move select")
        rank = {"Best Move": 1, "2nd Best Move": 2, "3rd Best Move": 3}.get(app_data, 1)
        self.data["move_to_play"] = rank
        for rank in ("1", "2", "3"):
            color = dpg.get_value(f"edit {rank}")
            self.data.setdefault("arrow_colors", {})[rank] = [int(c) for c in color[:3]] + [122]
        self.data["show_arrow_1"] = dpg.get_value("show arrow 1") == True
        self.data["show_arrow_2"] = dpg.get_value("show arrow 2") == True
        self.data["show_arrow_3"] = dpg.get_value("show arrow 3") == True
        self.data["limit_elo"] = dpg.get_value("limit elo") == True
        self.data["elo_preset"] = dpg.get_value("elo preset")
        self.data["dynamic_difficulty"] = dpg.get_value("dynamic difficulty") == True
        self.data["autostart"] = dpg.get_value("autostart") == True
        self.data["mouse_move_min_time"] = dpg.get_value("mouse min time")
        self.data["mouse_move_max_time"] = dpg.get_value("mouse max time")
        sf = self.data.setdefault("stockfish_settings", {})
        sf["skill_level"] = dpg.get_value("skill level")
        sf["hash"] = dpg.get_value("hash")
        sf["depth"] = dpg.get_value("depth")
        sf["threads"] = dpg.get_value("threads")
        sf["move_overhead"] = dpg.get_value("move overhead")
        sf["analysis_time_budget"] = dpg.get_value("analysis time")