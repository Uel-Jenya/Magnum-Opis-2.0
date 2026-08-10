import os
import ctypes
import ctypes.wintypes
import dearpygui.dearpygui as dpg
import pickle
import multiprocess
import threading
import time
import re
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from overlay import run
from stockfish_bot import StockfishBot
from selenium.common import WebDriverException
from selenium.common.exceptions import InvalidCookieDomainException, UnableToSetCookieException
import tkinter as tk
from tkinter import filedialog
from config_manager import ConfigManager
import chess
import chess.engine

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROMEDRIVER_PATH = os.path.join(PROJECT_ROOT, "bin", "chromedriver.exe")
BUNDLED_CHROME_PATH = os.path.join(PROJECT_ROOT, "bin", "chrome-win64", "chrome.exe")


class ChessApp:

    def __init__(self):
        # Load persistent configuration
        self.config = ConfigManager()

        # Bot properties
        self.stockfish_path = self.config.get("stockfish_path", "")
        self.website = self.config.get("website", "Chess.com")
        self.move_to_play = self.config.get("move_to_play", 1)
        self.running = False
        self.opened_browser = False
        raw_colors = self.config.get("arrow_colors", {
            '1': [0, 255, 0, 122],
            '2': [255, 163, 0, 122],
            '3': [255, 0, 0, 122]
        })
        # JSON returns floats; convert to ints for QColor and DearPyGui.
        self.move_colors = {
            k: [int(v) for v in val] for k, val in raw_colors.items()
        }
        # UI properties
        self.errors = {
            1: "critical",
            2: "mild",
            3: "information"
        }

        # Used for closing the threads
        self.exit = False

        # The Selenium Chrome driver
        self.chrome = None

        self.chrome_url = None
        self.chrome_session_id = None

        # Used for the communication between the GUI
        # and the Stockfish Bot process
        self.stockfish_bot_pipe = None
        self.overlay_screen_pipe = None

        # The Stockfish Bot process
        self.stockfish_bot_process = None
        self.overlay_screen_process = None
        self.restart_after_stopping = False

        # Used for storing the match moves
        self.match_moves = []

        # Start the process checker thread
        process_checker_thread = threading.Thread(target=self.process_checker_thread)
        process_checker_thread.start()

        # Start the browser checker thread
        browser_checker_thread = threading.Thread(target=self.browser_checker_thread)
        browser_checker_thread.start()

        # Start the process communicator thread
        process_communicator_thread = threading.Thread(
            target=self.process_communicator_thread
        )
        process_communicator_thread.start()

        # Start the autostart watcher thread
        autostart_thread = threading.Thread(target=self.autostart_watcher_thread)
        autostart_thread.start()

        dpg.create_context()
        self.min_width = 400
        self.min_height = 550
        self.max_width = 750
        self.max_height = 550
        self.stockfish_settings_toggled = False
        self.auto_tuning = False

        with dpg.font_registry():
            # first argument ids the path to the .ttf or .otf file
            default_font = dpg.add_font(".\\bin\\Kanit-Regular.ttf", 20)
        # Set up window
        with dpg.window(label="Chess", no_close=True, tag="Primary Window", no_scrollbar=True):

            # Create a single table row with three child windows in different columns
            with dpg.group(horizontal=True):

                # Left Frame - Status and Controls
                with dpg.child_window(tag=1, border=False, no_scrollbar=True, pos=(10, 10)):

                    with dpg.group(horizontal=True):

                        with dpg.child_window(border=False, no_scrollbar=True, width=300):

                            with dpg.child_window(width=400, height=150, border=False):
                                with dpg.group(horizontal=True):
                                    dpg.add_text("Status:")
                                    self.status_text = dpg.add_text("Inactive", tag="status", color=[255, 0, 0])

                                with dpg.group(horizontal=True, horizontal_spacing=10):
                                    with dpg.child_window(width=150, border=False):
                                        dpg.add_radio_button(("Chess.com", "Lichess.org"),
                                                             callback=self.on_website_choice,
                                                             default_value=self.website)
                                        dpg.add_button(tag="open browser", label="Open Browser",
                                                       callback=self.on_open_browser_button_listener)
                                        dpg.add_button(tag="start", label="Start",
                                                       callback=self.on_start_button_listener, enabled=False)

                                    with dpg.child_window(width=150, border=False):
                                        dpg.add_checkbox(tag="manual mode", label="Manual Mode")
                                        dpg.add_checkbox(tag="mouseless mode", label="Mouseless Mode")
                                        dpg.add_checkbox(tag="puzzles", label="Non-stop puzzles")
                                        dpg.add_checkbox(tag="bongcloud", label="Bongcloud")
                                        dpg.add_checkbox(tag="autostart", label="Autostart")
                            with dpg.group(height=500):
                                dpg.add_separator()
                                with dpg.tree_node(label="Arrows"):
                                    dpg.add_separator(label="Arrow 1")
                                    dpg.add_checkbox(tag="show arrow 1", label="show", callback=self.on_show_arrow_toggle)
                                    dpg.add_color_edit(tag="edit 1", default_value=(0, 255, 0, 122),
                                                       no_alpha=True, no_label=True, callback=self.on_color_edit)

                                    dpg.add_separator(label="Arrow 2")
                                    dpg.add_checkbox(tag="show arrow 2", label="show", callback=self.on_show_arrow_toggle)
                                    dpg.add_color_edit(tag="edit 2", default_value=(255, 163, 0, 122),
                                                       no_alpha=True, no_label=True, callback=self.on_color_edit)

                                    dpg.add_separator(label="Arrow 3")
                                    dpg.add_checkbox(tag="show arrow 3", label="show", callback=self.on_show_arrow_toggle)
                                    dpg.add_color_edit(tag="edit 3", default_value=(255, 0, 0, 122),
                                                       no_alpha=True, no_label=True, callback=self.on_color_edit)

                                with dpg.tree_node(label="Settings"):

                                    with dpg.group(horizontal=True):
                                        dpg.add_text(default_value="Play")
                                        dpg.add_combo(["Best Move", "2nd Best Move", "3rd Best Move"],
                                                      tag="move select", callback=self.on_move_selected)

                                    dpg.add_separator(label="Timer")
                                    dpg.add_checkbox(tag="timer", label="Timer")
                                    self.timer_min_slider = dpg.add_slider_int(tag="min timer", label="MIN",
                                                                               clamped=True, min_value=0, max_value=20,
                                                                               default_value=2)
                                    self.timer_max_slider = dpg.add_slider_int(tag="max timer", label="MAX",
                                                                               min_value=0, max_value=20,
                                                                               default_value=15)
                                    dpg.add_separator(label="Mouse Speed")
                                    dpg.add_slider_float(tag="mouse min time", label="Min (s)",
                                                         min_value=0.1, max_value=5.0, default_value=1.0, width=130)
                                    dpg.add_slider_float(tag="mouse max time", label="Max (s)",
                                                         min_value=0.1, max_value=10.0, default_value=3.0, width=130)

                            dpg.add_separator()
                            dpg.add_checkbox(tag="load cookies", label="Load cookies")
                            dpg.add_button(label="Save cookies", callback=self.on_save_cookies_button_listener)
                            dpg.add_separator(label="Eval")
                            dpg.add_progress_bar(tag="eval", default_value=0.5, width=200)
                            dpg.add_text(tag="eval text", default_value="0")

                            dpg.add_text(tag="move eval1", default_value="move 1: 0", color=self.move_colors["1"][:3])
                            dpg.add_text(tag="move eval2", default_value="move 2: 0", color=self.move_colors["2"][:3])
                            dpg.add_text(tag="move eval3", default_value="move 3: 0", color=self.move_colors["3"][:3])

                        with dpg.child_window(no_scrollbar=True, border=False, width=50):
                            dpg.add_button(tag="toggle next", height=100, width=50, pos=(0, 225),
                                           arrow=True, direction=1, callback=self.togle_fish)

                # Right Frame - Stockfish Settings
                with dpg.child_window(tag=2, width=200, height=500, show=False, pos=(400, 0), border=False):
                    dpg.add_text("Stockfish Parameters")
                    dpg.add_slider_int(tag="skill level", label="Skill Level", min_value=1, max_value=20,
                                       default_value=20, width=90)
                    dpg.add_input_int(tag="hash", label="Hash (MB)", default_value=8, width=90)
                    dpg.add_slider_int(tag="depth", label="depth", min_value=1, max_value=20,
                                       default_value=6, width=90)

                    dpg.add_input_int(tag="threads", label="Threads", default_value=1, width=90)
                    dpg.add_input_int(tag="move overhead", label="Move Overhead", default_value=15, width=90)
                    dpg.add_slider_float(tag="analysis time", label="Analysis budget (s)",
                                         min_value=0.2, max_value=5.0, default_value=1.2,
                                         width=130, format="%.2f s")
                    dpg.add_checkbox(tag="limit elo", label="Limit Elo")
                    dpg.add_slider_int(tag="elo preset", label="Elo", min_value=700, max_value=3190,
                                       default_value=2000, width=90)
                    dpg.add_checkbox(tag="dynamic difficulty", label="Dynamic Difficulty")
                    dpg.add_button(tag="auto tune", label="Auto-tune this PC",
                                   callback=self.on_auto_tune_button_listener)

                    dpg.add_text(tag="auto tune status", default_value="Benchmarks Threads and memory safely.", wrap=180)
                    dpg.add_button(tag="select stockfish", label="Select Stockfish",
                                   callback=self.on_select_stockfish_button_listener)

                    with dpg.window(label="Select Fish", modal=True, show=False, tag="modal",
                                    no_title_bar=True, width=250):
                        dpg.add_text("", tag="modal text")
                        dpg.add_separator()
                        dpg.add_button(label="OK", width=75,
                                       callback=lambda: dpg.configure_item("modal", show=False), pos=(90, 70))

        # Apply saved config values to GUI widgets
        self.config.apply_to_gui()

        dpg.bind_font(default_font)

        # Themes
        with dpg.theme() as global_theme:
            # All components
            with dpg.theme_component(dpg.mvAll):
                # set colors
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, (0, 0, 0, 0), category=dpg.mvThemeCat_Core)
                dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (0, 0, 0, 0), category=dpg.mvThemeCat_Core)
                dpg.add_theme_color(dpg.mvThemeCol_Border, (115, 6, 37), category=dpg.mvThemeCat_Core)
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, (0, 0, 0, 0), category=dpg.mvThemeCat_Core)
                dpg.add_theme_color(dpg.mvThemeCol_CheckMark, (115, 6, 37), category=dpg.mvThemeCat_Core)

                # set style
                dpg.add_theme_style(dpg.mvStyleVar_FrameBorderSize, 1, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 5, category=dpg.mvThemeCat_Core)

            with dpg.theme_component(dpg.mvChildWindow):
                pass

            # Buttons
            with dpg.theme_component(dpg.mvButton):
                # color
                dpg.add_theme_color(dpg.mvThemeCol_Button, (92, 9, 33), category=dpg.mvThemeCat_Core)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (92, 9, 33), category=dpg.mvThemeCat_Core)

                # style
                dpg.add_theme_style(dpg.mvStyleVar_FrameBorderSize, 0, category=dpg.mvThemeCat_Core)

            with dpg.theme_component(dpg.mvSliderInt):
                dpg.add_theme_color(dpg.mvThemeCol_SliderGrab, (92, 9, 33), category=dpg.mvThemeCat_Core)
                dpg.add_theme_color(dpg.mvThemeCol_SliderGrabActive, (0, 0, 0, 0), category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 12)
                dpg.add_theme_style(dpg.mvStyleVar_GrabRounding, 12)
                dpg.add_theme_style(dpg.mvStyleVar_GrabMinSize, 20)

            # ---- Progress bar (eval bar) theme ----
            with dpg.theme_component(dpg.mvProgressBar):
                # The progress bar fill colour uses PlotHistogram.
                # Setting it to a maroon/dark red prevents the reddish default
                # from looking like an error when the bar is mid-range.
                dpg.add_theme_color(dpg.mvThemeCol_PlotHistogram, (140, 30, 50), category=dpg.mvThemeCat_Core)
                # Background of the unfilled portion
                dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (40, 40, 40), category=dpg.mvThemeCat_Core)

        dpg.bind_theme(global_theme)

        dpg.create_viewport(title="Chess", width=self.min_width, height=self.min_height)
        dpg.setup_dearpygui()
        dpg.set_primary_window("Primary Window", True)
        dpg.set_exit_callback(self.on_close_listener)
        dpg.show_viewport()
        
        # Exclude the DearPyGui window from Discord screen capture
        # while keeping it fully visible on the local monitor.
        self._exclude_from_capture("Chess")
        # Periodically re-apply capture protection.
        self._start_capture_protection_thread()
        
        # Start a background thread that listens for Ctrl+Shift+T to
        # bring the app window to the top of the Z-order.
        self._start_bring_to_front_listener()
        
        dpg.start_dearpygui()
        dpg.destroy_context()

    # Methods

    def togle_fish(self):
        if self.stockfish_settings_toggled is True:
            dpg.configure_item(2, show=False)
            dpg.set_viewport_width(self.min_width)
            self.stockfish_settings_toggled = False
            dpg.configure_item("toggle next", direction=1)
        else:
            dpg.configure_item(2, show=True)
            dpg.set_viewport_width(self.max_width)
            self.stockfish_settings_toggled = True
            dpg.configure_item("toggle next", direction=0)

    def on_close_listener(self):
        # Save config before exit
        self.config.sync_from_gui()
        self.config['website'] = self.website
        self.config['stockfish_path'] = self.stockfish_path
        self.config['move_to_play'] = self.move_to_play
        for rank in ('1', '2', '3'):
            color = self.move_colors.get(rank)
            if color:
                self.config.set_arrow_color(rank, color)
        self.config.save()
        # Set self.exit to True so that the threads will stop
        self.exit = True

    def process_checker_thread(self):
        while not self.exit:
            if (
                self.running
                and self.stockfish_bot_process is not None
                and not self.stockfish_bot_process.is_alive()
            ):
                self.on_stop_button_listener()
                if self.restart_after_stopping:
                    self.restart_after_stopping = False
                    self.on_start_button_listener()
            time.sleep(0.1)

    def browser_checker_thread(self):
        while not self.exit:
            try:
                if (
                    self.opened_browser
                    and self.chrome is not None
                    and "target window already closed"
                    in self.chrome.get_log("driver")[-1]["message"]
                ):
                    self.opened_browser = False
                    dpg.configure_item("start", label="Open Browser", enabled=True)
                    self.on_stop_button_listener()
                    self.chrome = None
            except IndexError:
                pass
            time.sleep(0.1)

    def process_communicator_thread(self):
        while not self.exit:
            try:
                if (
                    self.stockfish_bot_pipe is not None
                    and self.stockfish_bot_pipe.poll()
                ):
                    data = self.stockfish_bot_pipe.recv()
                    if data == "START":
                        dpg.configure_item("start", label="Stop",
                                           callback=self.on_stop_button_listener, enabled=True)
                    elif data == "STOP":
                        self.on_stop_button_listener()
                    elif data == "playeriswhite":
                        self.is_white = True
                    elif data == "playerisblack":
                        self.is_white = False
                    elif data[:9] == "moveEval1":
                        dpg.set_value("move eval1", "move 1: " + str(float(data[9:]) / 100))
                        dpg.configure_item("move eval1", color=self.move_colors["1"][:3])
                    elif data[:9] == "moveEval2":
                        dpg.set_value("move eval2", "move 2: " + str(float(data[9:]) / 100))
                        dpg.configure_item("move eval2", color=self.move_colors["2"][:3])
                    elif data[:9] == "moveEval3":
                        dpg.set_value("move eval3", "move 3: " + str(float(data[9:]) / 100))
                        dpg.configure_item("move eval3", color=self.move_colors["3"][:3])
                    elif data[:4] == "eval":
                        if data[:5] == "evalm":
                            eval = 'M in\n' + data[5:]
                            dpg.set_value("eval text", str(eval))
                        elif data[:5] == "evalp":
                            eval = data[5:]
                            eval_float = float(eval) / 1000
                            bar_value = max(0.0, min(1.0, 0.5 + eval_float / 2))
                            dpg.set_value("eval", bar_value)
                            dpg.set_value("eval text", str(eval_float))
                    elif data[:7] == "RESTART":
                        self.restart_after_stopping = True
                        self.stockfish_bot_pipe.send("DELETE")
                    elif data[:7] == "ERR_EXE":
                        message = "Stockfish path provided is not valid!"
                        self.popup(message, self.errors[1])
                    elif data[:8] == "ERR_PERM":
                        message = "Stockfish path provided is not executable!"
                        self.popup(message, self.errors[1])
                    elif data[:9] == "ERR_BOARD":
                        message = "Cant find board!"
                        self.popup(message, self.errors[1])
                    elif data[:9] == "ERR_COLOR":
                        message = "Cant find player color!"
                        self.popup(message, self.errors[1])
                    elif data[:9] == "ERR_MOVES":
                        message = "Cant find moves list!"
                        self.popup(message, self.errors[1])
                    elif data[:12] == "ERR_GAMEOVER":
                        message = "Game has already finished!"
                        self.popup(message, self.errors[1])
                    elif data == "windowfail":
                        self.on_stop_button_listener()
                        self.chrome.get(self.current_url)
                        self.on_start_button_listener()
            except (BrokenPipeError, OSError):
                self.stockfish_bot_pipe = None
                print("Pip Broken")
            time.sleep(0.1)

    def on_open_browser_button_listener(self):
        self.opening_browser = True
        dpg.configure_item("open browser", enabled=False, label="Opening")

        options = webdriver.ChromeOptions()
        if os.path.isfile(BUNDLED_CHROME_PATH):
            options.binary_location = BUNDLED_CHROME_PATH
        # Remove obvious automation switches
        options.add_experimental_option("excludeSwitches", [
            "enable-automation",
            "enable-logging",
            "disable-infobars",
        ])
        options.add_experimental_option("useAutomationExtension", False)
        # Blink features that flag automation
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--disable-translate")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-background-networking")
        options.add_argument("--disable-sync")
        options.add_argument("--disable-default-apps")
        options.add_argument("--disable-extensions-file-access-check")
        options.add_argument("--disable-component-update")
        options.add_argument("--no-first-run")
        options.add_argument("--no-service-autorun")
        # Remove the "Chrome is being controlled by automated test software" infobar
        options.add_argument("--disable-infobars")
        try:
            self.chrome = webdriver.Chrome(
                service=Service(executable_path=CHROMEDRIVER_PATH),
                options=options
            )
            # CDP stealth: inject JS before any page loads to mask automation
            self.chrome.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {
                    "source": """
                        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                        Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
                        Object.defineProperty(navigator, 'languages', { get: () => ['en-US','en'] });
                        window.chrome = { runtime: {} };
                        document.documentElement.setAttribute('webdriver', false);
                    """
                },
            )
        except WebDriverException:
            self.opening_browser = False
            dpg.configure_item("open browser", label="open browser", enabled=True)
            message = "chrome no found"
            self.popup(message, self.errors[3])
            return

        if self.website.replace(" ", "") == "Chess.com":
            self.chrome.get("https://www.chess.com")
        else:
            self.chrome.get("https://www.lichess.org")

        if dpg.get_value("load cookies") == True:
            try:
                cookies = pickle.load(open("cookies.pkl", "rb"))
                for cookie in cookies:
                    self.chrome.add_cookie(cookie)
                self.chrome.refresh()
            except FileNotFoundError:
                message = "Cookies not saved error"
                self.popup(message, self.errors[3])
            except InvalidCookieDomainException:
                message = "Unnable to load cookies"
                self.popup(message, self.errors[3])
            except UnableToSetCookieException:
                message = "Unnable to load cookies"
                self.popup(message, self.errors[3])

        self.chrome_url = self.chrome.service.service_url
        # Extra stealth: override headless/automation properties after page load
        try:
            self.chrome.execute_script(
                """
                Object.defineProperty(navigator, 'webdriver', { get: () => false });
                Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US','en'] });
                window.chrome = { runtime: {} };
                document.documentElement.setAttribute('webdriver', 'false');
                """
            )
        except Exception:
            pass
        self.chrome_session_id = self.chrome.session_id

        self.opening_browser = False
        self.opened_browser = True
        dpg.configure_item("open browser", label="Browser is opened", enabled=True)
        dpg.configure_item("start", enabled=True)

    def on_start_button_listener(self):
        if self.running or (
            self.stockfish_bot_process is not None and self.stockfish_bot_process.is_alive()
        ) or (
            self.overlay_screen_process is not None and self.overlay_screen_process.is_alive()
        ):
            dpg.configure_item("start", label="Stop", enabled=True,
                               callback=self.on_stop_button_listener)
            return

        dpg.configure_item("start", label="Starting...", enabled=False)
        if self.stockfish_path == "":
            return

        parent_conn, child_conn = multiprocess.Pipe()
        self.stockfish_bot_pipe = parent_conn
        st_ov_queue = multiprocess.Queue()

        limit_elo = dpg.get_value("limit elo") == True
        elo_preset = dpg.get_value("elo preset")

        params = {
            "Threads": dpg.get_value("threads"),
            "Hash": dpg.get_value("hash"),
            "Skill Level": dpg.get_value("skill level"),
            "Move Overhead": dpg.get_value("move overhead"),
            "UCI_LimitStrength": True if limit_elo else "false",
            "UCI_Elo": min(3190, elo_preset) if limit_elo else 3190,
        }
        if dpg.get_value("timer") == True:
            timer = (dpg.get_value("min timer"), dpg.get_value("max timer"))
        else:
            timer = None

        self.config.sync_from_gui()

        self.stockfish_bot_process = StockfishBot(
            self.chrome_url,
            self.chrome_session_id,
            self.website,
            child_conn,
            st_ov_queue,
            self.stockfish_path,
            dpg.get_value("manual mode") == True,
            dpg.get_value("mouseless mode") == True,
            dpg.get_value("puzzles") == True,
            dpg.get_value("bongcloud") == True,
            dpg.get_value("depth"),
            params,
            timer,
            self.move_to_play,
            dpg.get_value("analysis time"),
            limit_elo,
            elo_preset,
            dpg.get_value("dynamic difficulty") == True,
            mouse_move_min_time=dpg.get_value("mouse min time"),
            mouse_move_max_time=dpg.get_value("mouse max time"),
        )
        self.stockfish_bot_process.start()

        self.overlay_screen_process = multiprocess.Process(
            target=run, args=(st_ov_queue, self.move_colors)
        )
        self.overlay_screen_process.start()

        self.running = True
        dpg.configure_item("start", label="Stop", enabled=True,
                           callback=self.on_stop_button_listener)
        dpg.configure_item("status", default_value="Active", color=(0, 255, 0))

    def on_stop_button_listener(self):
        if self.stockfish_bot_process is not None:
            self.stockfish_bot_process.kill()
            self.stockfish_bot_process = None
        if self.stockfish_bot_pipe is not None:
            self.stockfish_bot_pipe.close()
            self.stockfish_bot_pipe = None
        if self.overlay_screen_process is not None:
            self.overlay_screen_process.kill()
            self.overlay_screen_process = None
        if self.overlay_screen_pipe is not None:
            self.overlay_screen_pipe.close()
            self.overlay_screen_pipe = None

        self.running = False
        dpg.configure_item("start", label="Start", enabled=True,
                           callback=self.on_start_button_listener)
        dpg.configure_item("status", default_value="Inactive", color=(255, 0, 0))

    def on_export_pgn_button_listener(self):
        f = filedialog.asksaveasfile(
            initialfile="match.pgn",
            defaultextension=".pgn",
            filetypes=[("Portable Game Notation", "*.pgn"), ("All Files", "*.*")],
        )
        if f is None:
            return
        data = ""
        for i in range(len(self.match_moves) // 2 + 1):
            if len(self.match_moves) % 2 == 0 and i == len(self.match_moves) // 2:
                continue
            data += str(i + 1) + ". "
            data += self.match_moves[i * 2] + " "
            if (i * 2) + 1 < len(self.match_moves):
                data += self.match_moves[i * 2 + 1] + " "
        f.write(data)
        f.close()

    def on_select_stockfish_button_listener(self):
        f = filedialog.askopenfilename()
        if f is None:
            return
        self.stockfish_path = f
        self.config['stockfish_path'] = f
        self.config.save()

    @staticmethod
    def _exclude_from_capture(window_title):
        """
        Use SetWindowDisplayAffinity with WDA_EXCLUDEFROMCAPTURE | WDA_MONITOR (0x13)
        AND DwmSetWindowAttribute with DWMWA_EXCLUDED_FROM_CAPTURE for dual-layer
        protection against Discord / OBS screen capture.
        """
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.FindWindowW(None, window_title)
            if hwnd:
                # Layer 1: SetWindowDisplayAffinity
                # WDA_EXCLUDEFROMCAPTURE | WDA_MONITOR = 0x13
                user32.SetWindowDisplayAffinity(hwnd, 0x13)
                # Layer 2: DWM exclusion attribute (Windows 10 2004+)
                try:
                    dwmapi = ctypes.windll.dwmapi
                    # DWMWA_EXCLUDED_FROM_CAPTURE = 33
                    excluded = ctypes.c_int(1)
                    dwmapi.DwmSetWindowAttribute(
                        ctypes.wintypes.HWND(hwnd), 33,
                        ctypes.byref(excluded), ctypes.sizeof(excluded)
                    )
                except Exception:
                    pass
        except Exception:
            pass

    def _start_capture_protection_thread(self):
        """Periodically re-apply capture protection (Windows can reset it)."""
        def protector():
            while not self.exit:
                self._exclude_from_capture("Chess")
                time.sleep(5)
        threading.Thread(target=protector, daemon=True).start()

    def autostart_watcher_thread(self):
        """Watch for game URLs and auto-start the bot when a game is detected."""
        while not self.exit:
            try:
                if (self.opened_browser and not self.running and
                    self.chrome is not None and
                    dpg.get_value("autostart") == True):
                    try:
                        url = self.chrome.current_url
                        if self._is_game_url(url):
                            self.on_start_button_listener()
                    except Exception:
                        pass
            except Exception:
                pass
            time.sleep(1.0)

    def _is_game_url(self, url):
        """Check if the current browser URL looks like an active game."""
        if not url:
            return False
        if self.website == "Chess.com":
            return ("live" in url or "computer" in url or
                    bool(re.search(r'game/\d+', url)))
        else:
            # Lichess game URLs contain /[a-zA-Z0-9]{8} or /game/export
            return bool(re.search(r'lichess\.org/[a-zA-Z0-9]{8}', url)) or "game" in url

    def _start_bring_to_front_listener(self):
        """Background thread that polls for Ctrl+Shift+T to bring the app to front."""
        def listener():
            user32 = ctypes.windll.user32
            VK_CONTROL = 0x11
            VK_SHIFT = 0x10
            VK_T = 0x54
            while not self.exit:
                # Check if Ctrl+Shift+T is held
                if (user32.GetAsyncKeyState(VK_CONTROL) & 0x8000 and
                    user32.GetAsyncKeyState(VK_SHIFT) & 0x8000 and
                    user32.GetAsyncKeyState(VK_T) & 0x8000):
                    self._bring_to_front()
                    time.sleep(0.3)  # debounce
                time.sleep(0.05)
        threading.Thread(target=listener, daemon=True).start()

    @staticmethod
    def _bring_to_front():
        """Bring the Chess app window to the top of the Z-order."""
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.FindWindowW(None, "Chess")
            if hwnd:
                # HWND_TOPMOST = -1, SWP_NOSIZE | SWP_NOMOVE = 0x0002 | 0x0001
                user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0002 | 0x0001)
                user32.SetForegroundWindow(hwnd)
        except Exception:
            pass

    @staticmethod
    def _available_memory_mb():
        """Return physical RAM without adding a third-party dependency."""
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong), ("memory_load", ctypes.c_ulong),
                ("total_phys", ctypes.c_ulonglong), ("avail_phys", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong), ("avail_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong), ("avail_virtual", ctypes.c_ulonglong),
                ("avail_extended_virtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.avail_phys // (1024 * 1024))
        return 1024

    def on_auto_tune_button_listener(self):
        """Benchmark Stockfish briefly and apply settings suited to this PC."""
        if self.auto_tuning:
            return
        if not self.stockfish_path or not os.path.isfile(self.stockfish_path):
            dpg.set_value("auto tune status", "Select a valid Stockfish executable first.")
            return

        self.auto_tuning = True
        dpg.configure_item("auto tune", enabled=False, label="Benchmarking...")
        dpg.set_value("auto tune status", "Testing Stockfish thread counts (about 2 seconds)...")
        threading.Thread(
            target=self._auto_tune_worker,
            args=(self.stockfish_path,),
            daemon=True,
            name="stockfish-auto-tune",
        ).start()

    def _auto_tune_worker(self, stockfish_path):
        logical_cpus = max(1, os.cpu_count() or 1)
        # More than eight engine threads has diminishing returns at the short
        # search times this app uses and can make the desktop less responsive.
        candidates = sorted({1, min(2, logical_cpus), min(4, logical_cpus), min(8, logical_cpus)})
        board = chess.Board("r1bq1rk1/pp2bppp/2n1pn2/2pp4/3P4/2PB1N2/PP3PPP/RNBQ1RK1 w - - 0 8")
        scores = {}

        try:
            for threads in candidates:
                engine = chess.engine.SimpleEngine.popen_uci(stockfish_path)
                try:
                    engine.configure({"Threads": threads, "Hash": 64, "UCI_LimitStrength": False})
                    started = time.perf_counter()
                    info = engine.analyse(board, chess.engine.Limit(time=0.35))
                    elapsed = max(time.perf_counter() - started, 0.001)
                    scores[threads] = info.get("nodes", 0) / elapsed
                finally:
                    engine.quit()

            best_threads = max(scores, key=scores.get)
            available_ram = self._available_memory_mb()
            # Leave substantial RAM for Chrome, the overlay and Windows.
            if available_ram < 2048:
                hash_mb = 32
            elif available_ram < 4096:
                hash_mb = 64
            elif available_ram < 8192:
                hash_mb = 128
            elif available_ram < 16384:
                hash_mb = 256
            else:
                hash_mb = 512

            dpg.set_value("threads", best_threads)
            dpg.set_value("hash", hash_mb)
            dpg.set_value(
                "auto tune status",
                f"Selected {best_threads} threads and {hash_mb} MB hash ({logical_cpus} logical CPUs).",
            )
            self.config.sync_from_gui()
            self.config.save()
        except Exception as exc:
            dpg.set_value("auto tune status", f"Auto-tune failed: {exc}")
        finally:
            self.auto_tuning = False
            dpg.configure_item("auto tune", enabled=True, label="Auto-tune this PC")

    def on_save_cookies_button_listener(self):
        pickle.dump(self.chrome.get_cookies(), open("cookies.pkl", "wb"))

    def on_website_choice(self, sender, app_data, user_data):
        self.website = app_data
        self.config['website'] = app_data
        self.config.save()

    def on_color_edit(self, sender, app_data, user_data):
        alpha = 122
        color = [int(i) for i in dpg.get_value(sender)[:3]]
        color.append(alpha)
        rank = sender.split(" ")[1]
        self.move_colors[rank] = color
        dpg.configure_item("move eval" + rank, color=color[:3])
        self.config.set_arrow_color(rank, color)
        self.config.save()

    def on_show_arrow_toggle(self, sender, app_data, user_data):
        """Save arrow checkbox state when toggled."""
        self.config.save()

    def on_move_selected(self, sender, app_data, user_data):
        if app_data == "Best Move":
            rank = "1"
        elif app_data == "2nd Best Move":
            rank = "2"
        elif app_data == "3rd Best Move":
            rank = "3"
        self.move_to_play = int(rank)
        self.config['move_to_play'] = int(rank)
        self.config.save()

    def popup(self, message, level):
        dpg.configure_item("modal", show=True)
        dpg.configure_item("modal text", default_value=message)
        if level == self.errors[1]:
            dpg.configure_item("open browser", enabled=True, label="Open Browser")
            dpg.configure_item("start", label="start",
                               callback=self.on_start_button_listener, enabled=True)


if __name__ == "__main__":
    ChessApp()
