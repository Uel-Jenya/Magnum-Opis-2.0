import random
import threading
import multiprocess
import pyautogui
import time
import sys
import os
import math
import ctypes
import chess
import re
from grabbers.chesscom_grabber import ChesscomGrabber
from grabbers.lichess_grabber import LichessGrabber
from utilities import char_to_num
from threading import Timer
from selenium.common.exceptions import NoSuchWindowException

import chess.engine

# PyAutoGUI inserts a 100 ms pause after every action by default.  Keep a
# small pause for reliable browser input while avoiding ~300 ms of overhead
# for each drag-based move.
pyautogui.PAUSE = 0.02

# --- Hardware-level mouse input via Win32 API ---
# These constants and helpers produce real hardware mouse events that
# are indistinguishable from a physical mouse to the OS and to websites.
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_ABSOLUTE = 0x8000


def _move_cursor_to(x, y):
    """Move the physical mouse cursor to absolute screen coordinates."""
    ctypes.windll.user32.SetCursorPos(int(x), int(y))


def _mouse_down():
    """Simulate a physical left mouse button press."""
    ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)


def _mouse_up():
    """Simulate a physical left mouse button release."""
    ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def _bezier_move(start_x, start_y, end_x, end_y, steps=None):
    """
    Move the mouse along a curved bezier path with random jitter
    to simulate human hand movement.
    """
    dist = math.hypot(end_x - start_x, end_y - start_y)
    if steps is None:
        steps = max(10, min(40, int(dist / 8)))
    # Two random control points for a quadratic bezier curve
    offset_x = (end_x - start_x) * 0.3
    offset_y = (end_y - start_y) * 0.3
    ctrl1_x = start_x + offset_x + random.uniform(-30, 30)
    ctrl1_y = start_y + offset_y + random.uniform(-30, 30)
    ctrl2_x = end_x - offset_x + random.uniform(-20, 20)
    ctrl2_y = end_y - offset_y + random.uniform(-20, 20)

    for i in range(steps + 1):
        t = i / steps
        # Cubic bezier interpolation
        u = 1 - t
        x = (u**3 * start_x + 3 * u**2 * t * ctrl1_x +
             3 * u * t**2 * ctrl2_x + t**3 * end_x)
        y = (u**3 * start_y + 3 * u**2 * t * ctrl1_y +
             3 * u * t**2 * ctrl2_y + t**3 * end_y)
        # Add small random jitter
        x += random.uniform(-1.5, 1.5)
        y += random.uniform(-1.5, 1.5)
        _move_cursor_to(x, y)
        time.sleep(random.uniform(0.005, 0.015))


def _bezier_move_timed(start_x, start_y, end_x, end_y, target_duration):
    """
    Move the mouse along a curved bezier path, but stretch/compress
    the per-step delays so the whole motion takes approximately
    `target_duration` seconds.
    """
    base_steps = max(10, min(40, int(math.hypot(end_x - start_x, end_y - start_y) / 8)))
    # Randomize step count slightly for natural feel
    steps = max(8, base_steps + random.randint(-4, 4))
    offset_x = (end_x - start_x) * 0.3
    offset_y = (end_y - start_y) * 0.3
    ctrl1_x = start_x + offset_x + random.uniform(-30, 30)
    ctrl1_y = start_y + offset_y + random.uniform(-30, 30)
    ctrl2_x = end_x - offset_x + random.uniform(-20, 20)
    ctrl2_y = end_y - offset_y + random.uniform(-20, 20)

    # Base delay per step so total = target_duration, with small randomness
    base_delay = target_duration / steps
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        x = (u**3 * start_x + 3 * u**2 * t * ctrl1_x +
             3 * u * t**2 * ctrl2_x + t**3 * end_x)
        y = (u**3 * start_y + 3 * u**2 * t * ctrl1_y +
             3 * u * t**2 * ctrl2_y + t**3 * end_y)
        x += random.uniform(-1.5, 1.5)
        y += random.uniform(-1.5, 1.5)
        _move_cursor_to(x, y)
        # Vary delay slightly step-to-step
        time.sleep(max(0.001, base_delay + random.uniform(-base_delay * 0.3, base_delay * 0.3)))


class NewGameDetected(Exception):
    """Raised internally to restart analysis without stopping the bot."""

class StockfishBot(multiprocess.Process):
    # Selenium is remote-command based.  A tiny pause prevents the position
    # watcher from flooding Chrome while still noticing a move almost
    # immediately (normally within one polling interval).
    POSITION_POLL_INTERVAL = 0.03
    STATUS_CHECK_INTERVAL = 0.25
    # Leave enough of the two-second target for browser detection and drawing.
    # Stockfish receives both limits and stops at whichever arrives first.
    ENGINE_TIME_BUDGET = 1.20
    # Humanized jitter ranges for timing to avoid robotic patterns
    JITTER_POLL = 0.02      # ±20ms on position polls
    JITTER_STATUS = 0.1     # ±100ms on status checks
    JITTER_BG = 0.15        # ±150ms on background analysis cadence

    def _jitter(self, base, jitter_range):
        """Return base plus/minus random jitter, clamped non-negative."""
        return max(0.001, base + random.uniform(-jitter_range, jitter_range))

    def _get_move_duration(self):
        """Return a human-like move duration scaled by remaining clock time."""
        try:
            min_time = float(getattr(self, 'mouse_move_min_time', 1.0))
            max_time = float(getattr(self, 'mouse_move_max_time', 3.0))
        except Exception:
            min_time, max_time = 1.0, 3.0
        remaining = self._get_remaining_seconds()
        if remaining is None:
            return random.uniform(min_time, max_time)
        if remaining <= 5:
            divisor = 4.0      # 4x faster
        elif remaining <= 10:
            divisor = 3.0      # 3x faster
        elif remaining <= 30:
            divisor = 2.0      # 2x faster
        elif remaining <= 60:
            divisor = 1.5      # 1.5x faster
        else:
            divisor = 1.0      # normal speed
        return random.uniform(min_time / divisor, max_time / divisor)

    def _get_remaining_seconds(self):
        """Best-effort read of the player's remaining clock in seconds."""
        try:
            if self.website == "Chess.com":
                clocks = self.grabber.chrome.find_elements(
                    "css selector",".clock-time"
                )
                if not clocks:
                    return None
                text = clocks[self.is_white if self.is_white is not None else 0].text
                m, s = text.split(":")
                return int(m) * 60 + int(s)
            else:
                clocks = self.grabber.chrome.find_elements(
                    "css selector","[data-timetype]"
                )
                if not clocks:
                    return None
                idx = 0 if self.is_white is None else (0 if self.is_white else 1)
                text = clocks[idx].get_attribute("textContent").strip()
                parts = [p.strip() for p in text.split(":")]
                if len(parts) == 2:
                    return int(parts[0]) * 60 + int(float(parts[1]))
                return None
        except Exception:
            return None

    def __init__(self, chrome_url, chrome_session_id, website, pipe, overlay_queue, stockfish_path, 
                 enable_manual_mode, enable_mouseless_mode, enable_non_stop_puzzles, bongcloud, 
                 stockfish_depth, stockfish_parameters, timer_interval, move_to_play=1,
                 analysis_time_budget=None, limit_elo=False, elo_preset=2000, dynamic_difficulty=False,
                 mouse_move_min_time=1.0, mouse_move_max_time=3.0):
        multiprocess.Process.__init__(self)
        self.wait_for_first_turn = True
        self.chrome_url = chrome_url
        self.chrome_session_id = chrome_session_id
        self.website = website
        self.pipe = pipe
        self.overlay_queue = overlay_queue
        self.stockfish_path = stockfish_path
        self.enable_manual_mode = enable_manual_mode
        self.enable_mouseless_mode = enable_mouseless_mode
        self.enable_non_stop_puzzles = enable_non_stop_puzzles
        self.bongcloud = bongcloud
        self.stockfish_depth = stockfish_depth
        self.grabber = None
        self.is_white = None
        self.stockfish_parameters = stockfish_parameters
        self.analysis_time_budget = max(
            0.05,
            float(self.ENGINE_TIME_BUDGET if analysis_time_budget is None else analysis_time_budget),
        )
        self.timer_running = False
        self.play_depth = stockfish_depth
        # Keep the evaluation bar in step with the configured engine depth.
        # The previous hard-coded depth 15 made every update much slower than
        # the depth selected in the UI (and was particularly noticeable with
        # the default depth of 6).
        self.analysis_depth = stockfish_depth
        self.move_to_play = move_to_play
        self.mouse_move_min_time = mouse_move_min_time
        self.mouse_move_max_time = mouse_move_max_time
        if timer_interval != None:
            self.timer_min = timer_interval[0]
            self.timer_max = timer_interval[1]
        else:
            self.timer_min = None
            self.timer_max = None

        self.eval = 0
        
        # --- New features: ELo, dynamic difficulty, background analysis ---
        self.limit_elo = limit_elo
        self.elo_preset = elo_preset
        self.dynamic_difficulty = dynamic_difficulty
        
        # Position cache: Fen string -> (score, pv_moves_uci, timestamp)
        self.position_cache = {}
        self.max_cache_size = 50
        
        # Background analysis control
        self.bg_analysis_depth = min(stockfish_depth, 12)  # slightly shallower for bg
        self.bg_last_analysis_time = 0
        self.bg_analysis_interval = 0.5  # analyse every 0.5s on opponent's turn
        
        # Track consecutive wins/losses for dynamic difficulty
        self.consecutive_wins = 0
        self.consecutive_losses = 0
        self.last_game_result = None
        self.moves_played = 0

    def publish_board_rect(self):
        """Tell the overlay where the current board is on the desktop."""
        board = self.grabber.get_board()
        if board is None:
            return
        offset_x, offset_y = self.grabber.get_top_left_corner()
        self.overlay_queue.put({
            "type": "board",
            "rect": (int(offset_x + board.location["x"]), int(offset_y + board.location["y"]),
                     int(board.size["width"]), int(board.size["height"])),
            "player_is_white": self.is_white,
        })

    def publish_evaluation(self, score):
        """Update both the GUI and the left-of-board overlay evaluation bar."""
        white_score = score.white()
        if white_score.is_mate():
            self.eval = white_score.mate()
            self.pipe.send("evalm" + str(self.eval))
            score_cp = 100000 if self.eval > 0 else -100000
            label = "#" + str(self.eval)
        else:
            self.eval = white_score.score() or 0
            self.pipe.send("evalp" + str(self.eval))
            score_cp = self.eval
            label = f"{self.eval / 100:+.2f}"
        self.overlay_queue.put({"type": "evaluation", "score_cp": score_cp, "label": label})

    def publish_predictions(self, values):
        self.overlay_queue.put({"type": "predictions", "values": [f"{value / 100:+.2f}" for value in values]})

    def analyse(self, engine, board, depth, multipv=1):
        """Return the best available analysis before the UI update deadline."""
        return engine.analyse(
            board,
            chess.engine.Limit(depth=depth, time=self.analysis_time_budget),
            multipv=multipv,
        )
        
    def analyse_with_cache(self, engine, board, depth, multipv=1):
        """Analyse with position caching to avoid redundant searches."""
        fen = board.fen()
        cache_key = (fen, depth, multipv)
        
        # Return cached result if fresh enough (within 5 seconds)
        if cache_key in self.position_cache:
            cached = self.position_cache[cache_key]
            if time.time() - cached['timestamp'] < 5.0:
                return cached['result']
        
        result = self.analyse(engine, board, depth, multipv)
        
        # Store in cache, evict oldest if needed
        self.position_cache[cache_key] = {
            'result': result,
            'timestamp': time.time()
        }
        if len(self.position_cache) > self.max_cache_size:
            oldest_key = min(self.position_cache.keys(), 
                           key=lambda k: self.position_cache[k]['timestamp'])
            del self.position_cache[oldest_key]
        
        return result

    def get_dynamic_strength_params(self):
        """
        Adjust engine parameters based on game state for more human-like play.
        Returns modified stockfish_parameters dict.
        """
        if not self.dynamic_difficulty:
            return dict(self.stockfish_parameters)
        
        params = dict(self.stockfish_parameters)
        
        # Base elo from preset
        base_elo = self.elo_preset if self.limit_elo else 3200
        
        # Adjust based on game phase
        if self.moves_played < 10:
            # Opening: play closer to full strength (80-100% of elo)
            elo_adjust = int(base_elo * random.uniform(0.8, 1.0))
        elif self.moves_played < 30:
            # Middlegame: vary strength (70-100% of elo)
            elo_adjust = int(base_elo * random.uniform(0.7, 1.0))
        else:
            # Endgame: can vary more (60-100%)
            elo_adjust = int(base_elo * random.uniform(0.6, 1.0))
        
        # Adjust based on evaluation (being winning = play weaker, losing = play stronger)
        eval_abs = abs(self.eval)
        if eval_abs > 300 and self.eval > 0:
            # Bot is winning significantly - play a bit weaker
            elo_adjust = int(elo_adjust * random.uniform(0.6, 0.85))
        elif eval_abs > 300 and self.eval < 0:
            # Bot is losing - play stronger
            elo_adjust = int(elo_adjust * random.uniform(0.9, 1.0))
        elif eval_abs > 100 and self.eval < 0:
            # Slightly worse - play normal to strong
            elo_adjust = int(elo_adjust * random.uniform(0.85, 1.0))
        else:
            # Equal or slightly better - add some randomness
            elo_adjust = int(elo_adjust * random.uniform(0.7, 1.0))
        
        # Clamp to valid range (Stockfish UCI_Elo max is 3190)
        elo_adjust = max(700, min(3190, elo_adjust))
        
        if self.limit_elo:
            params["UCI_LimitStrength"] = True
            params["UCI_Elo"] = elo_adjust
        else:
            # Use skill level instead (1-20 mapping roughly to playing strength)
            skill = max(1, min(20, int((elo_adjust - 700) / 125) + 1))
            params["Skill Level"] = skill
        
        # Randomize move selection occasionally (blunder chance)
        # Higher when winning, lower when losing
        if abs(self.eval) > 200 and self.eval > 0:
            # Winning - occasionally play a suboptimal move
            if random.random() < 0.08:
                params.setdefault("Skill Level", 20)
                params["Skill Level"] = max(1, params.get("Skill Level", 20) - random.randint(3, 8))
        elif random.random() < 0.02:
            # Small chance of blunder anyway for human-like play
            params.setdefault("Skill Level", 20)
            params["Skill Level"] = max(1, params.get("Skill Level", 20) - random.randint(1, 4))
        
        return params

    @staticmethod
    def format_score(score):
        """Format a White-perspective engine score for an arrow label."""
        white_score = score.white()
        if white_score.is_mate():
            return "#" + str(white_score.mate())
        pawns = (white_score.score() or 0) / 100
        return f"{pawns:+.2f}".rstrip("0").rstrip(".")

    def game_has_changed(self, game_url, known_moves, current_moves=None):
        """Detect navigation or a replaced move list while the bot stays active."""
        if self.grabber.chrome.current_url != game_url:
            return True
        if current_moves is None:
            current_moves = self.grabber.get_move_list()
        return current_moves is not None and (
            len(current_moves) < len(known_moves) or current_moves[:len(known_moves)] != known_moves
        )

    def wait_for_new_game(self, old_url, old_moves):
        self.overlay_queue.put({"type": "clear"})
        while True:
            time.sleep(self.STATUS_CHECK_INTERVAL)
            self.grabber.update_board_elem()
            moves = self.grabber.get_move_list()
            if self.grabber.get_board() is None or moves is None or self.grabber.is_game_over():
                continue
            if self.grabber.chrome.current_url != old_url or len(moves) < len(old_moves) or moves[:len(old_moves)] != old_moves:
                raise NewGameDetected()

    # Converts a move to screen coordinates
    # Example: "a1" -> (x, y)
    def move_to_screen_pos(self, move):
        # Get the absolute top left corner of the website
        canvas_x_offset, canvas_y_offset = self.grabber.get_top_left_corner()

        # Get the absolute board position
        board_x = canvas_x_offset + self.grabber.get_board().location["x"]
        board_y = canvas_y_offset + self.grabber.get_board().location["y"]

        # Get the square size
        square_size = self.grabber.get_board().size['width'] / 8

        # Depending on the player color, the board is flipped, so the coordinates need to be adjusted
        if self.is_white:
            x = board_x + square_size * (char_to_num(move[0]) - 1) + square_size / 2
            y = board_y + square_size * (8 - int(move[1])) + square_size / 2
        else:
            x = board_x + square_size * (8 - char_to_num(move[0])) + square_size / 2
            y = board_y + square_size * (int(move[1]) - 1) + square_size / 2

        return x, y

    def get_move_pos(self, move):  # sourcery skip: remove-redundant-slice-index
        # Get the start and end position screen coordinates
        start_pos_x, start_pos_y = self.move_to_screen_pos(move[0:2])
        end_pos_x, end_pos_y = self.move_to_screen_pos(move[2:4])

        return (start_pos_x, start_pos_y), (end_pos_x, end_pos_y)


    def make_move(self, move):
        """
        Execute a move using hardware-level Win32 mouse events.
        The physical mouse cursor moves along a human-like bezier curve,
        presses down on the source square, drags to the target square,
        and releases.  No website APIs or JavaScript are involved.
        Move duration scales with remaining clock time so the bot
        speeds up automatically in time trouble.
        """
        while True:
            if self.timer_running == False:
                start_pos, end_pos = self.get_move_pos(move)
                target_duration = self._get_move_duration()

                # Small random delay before reaching for the piece (human reaction)
                time.sleep(random.uniform(0.05, 0.15))

                # Move cursor to the source square with a curved path
                _bezier_move(
                    pyautogui.position()[0], pyautogui.position()[1],
                    start_pos[0], start_pos[1]
                )
                time.sleep(random.uniform(0.02, 0.06))

                # Press mouse button down on the source square
                _mouse_down()
                time.sleep(random.uniform(0.03, 0.08))

                # Drag the piece to the target square along a curved path,
                # stretched or compressed to match the target duration.
                _bezier_move_timed(
                    start_pos[0], start_pos[1],
                    end_pos[0], end_pos[1],
                    target_duration
                )

                # Release mouse button on the target square
                _mouse_up()

                # Handle promotion: click on the promotion piece selector
                if len(move) == 5:
                    time.sleep(random.uniform(0.1, 0.2))
                    promo_x, promo_y = None, None
                    if move[4] == "n":
                        promo_x, promo_y = self.move_to_screen_pos(move[2] + str(int(move[3]) - 1))
                    elif move[4] == "r":
                        promo_x, promo_y = self.move_to_screen_pos(move[2] + str(int(move[3]) - 2))
                    elif move[4] == "b":
                        promo_x, promo_y = self.move_to_screen_pos(move[2] + str(int(move[3]) - 3))

                    if promo_x is not None:
                        promo_duration = random.uniform(
                            max(0.1, target_duration * 0.3),
                            max(0.2, target_duration * 0.6)
                        )
                        _bezier_move_timed(
                            end_pos[0], end_pos[1],
                            promo_x, promo_y,
                            promo_duration
                        )
                        time.sleep(random.uniform(0.03, 0.07))
                        _mouse_down()
                        time.sleep(random.uniform(0.02, 0.05))
                        _mouse_up()
                break

    #timer callback
    def set_timer_runing(self):
        self.timer_running = False
        
    def wait_for_gui_to_delete(self):
        while self.pipe.recv() != "DELETE":
            pass

    def run(self):
        
        # sourcery skip: extract-duplicate-method, switch, use-fstring-for-concatenation

        if self.website == "Chess.com":
            self.grabber = ChesscomGrabber(self.chrome_url, self.chrome_session_id)
        else:
            self.grabber = LichessGrabber(self.chrome_url, self.chrome_session_id)

        # Initialize Stockfish
        try:
            engine = chess.engine.SimpleEngine.popen_uci(self.stockfish_path)
            engine.configure(self.stockfish_parameters)
        except PermissionError:
            self.pipe.send("ERR_PERM")
            return
        except OSError:
            self.pipe.send("ERR_EXE")
            return
        
        while True:
            self.current_url = self.grabber.chrome.current_url
            if (self.website == "Chess.com" and ("live" in self.current_url or "computer" in self.current_url or bool(re.search(r'game/\d+', self.current_url)))) or self.website != "Chess.com":
                

                try:
                    # Return if the board element is not found
                    self.grabber.update_board_elem()
                    if self.grabber.get_board() is None:
                        self.pipe.send("ERR_BOARD")
                        return

                    # Find out what color the player has
                    self.is_white = self.grabber.is_white()
                    if self.is_white is None:
                        self.pipe.send("ERR_COLOR")
                        return
                    
                    elif self.is_white is True:
                        self.pipe.send("playeriswhite")
                        
                    elif self.is_white is False:
                        self.pipe.send("playerisblack")

                    game_url = self.current_url
                    self.publish_board_rect()

                    # Get the starting position
                    # Return if the starting position is not found
                    move_list = self.grabber.get_move_list()
                    if move_list is None:
                        self.pipe.send("ERR_MOVES")
                        return

                    # Check if the game is over
                    score_pattern = r"([0-9]+)\-([0-9]+)"
                    if len(move_list) > 0 and re.match(score_pattern, move_list[-1]):
                        self.pipe.send("ERR_GAMEOVER")
                        return

                    # Update the board with the starting position
                    board = chess.Board()
                    for move in move_list:
                        try:
                            board.push_san(move)

                        except chess.IllegalMoveError:
                            print(move_list)
                            print("curr:", move)
                    move_list_uci = [move.uci() for move in board.move_stack]

                    # Initial analysis with position cache
                    score = self.analyse_with_cache(engine, board, self.analysis_depth)[0]['score']
                    self.publish_evaluation(score)
                    
                    # Reset counters
                    self.moves_played = len(move_list)
                    self.position_cache.clear()

                    # Notify GUI that bot is ready
                    self.pipe.send("START")

                    # Send the first moves to the GUI (if there are any)
                    if len(move_list) > 0:
                        self.pipe.send("M_MOVE" + ",".join(move_list))

                    # Start the game loop
                    while True:
                        poll_interval = self._jitter(self.POSITION_POLL_INTERVAL, self.JITTER_POLL)
                        status_interval = self._jitter(self.STATUS_CHECK_INTERVAL, self.JITTER_STATUS)
                        bg_interval = self._jitter(self.bg_analysis_interval, self.JITTER_BG)
                        if self.game_has_changed(game_url, move_list):
                            raise NewGameDetected()
                       
                        # Act if it is the player's turn
                        if (self.is_white and board.turn == chess.WHITE) or (not self.is_white and board.turn == chess.BLACK):

                            self.wait_for_first_turn = False
                            #start Timer
                            if self.timer_min != None and self.timer_max != None:
                                self.timer_running = True
                                interval = random.randrange(self.timer_min, self.timer_max)
                                timer = Timer(interval, self.set_timer_runing)
                                timer.name = "Timer"
                                timer.start()

                        
                            # Apply dynamic strength before thinking
                            if self.dynamic_difficulty or self.limit_elo:
                                strength_params = self.get_dynamic_strength_params()
                                engine.configure(strength_params)
                        
                            # Think of a move
                            move = None
                            self_moved = False

                            move_count = len(board.move_stack)
                            if self.bongcloud and move_count <= 3:
                                if move_count == 0:
                                    move = "e2e3"
                                elif move_count == 1:
                                    move = "e7e6"
                                elif move_count == 2:
                                    move = "e1e2"
                                elif move_count == 3:
                                    move = "e8e7"

                                # Hardcoded bongcloud move is not legal,
                                # so find a legal move
                                if not board.is_legal(chess.Move.from_uci(move)):
                                    try:
                                        move = self.analyse_with_cache(engine, board, self.play_depth, self.move_to_play)[self.move_to_play - 1]["pv"][0].uci()
                                    except IndexError:
                                        move = self.analyse_with_cache(engine, board, self.play_depth, self.move_to_play)[-1]["pv"][0].uci()

                            else:
                                if not self.enable_manual_mode:
                                    try:
                                        move = self.analyse_with_cache(engine, board, self.play_depth, self.move_to_play)[self.move_to_play - 1]["pv"][0].uci()
                                    except IndexError:
                                        move = self.analyse_with_cache(engine, board, self.play_depth, self.move_to_play)[-1]["pv"][0].uci()

                            # Wait for keypress or player movement if in manual mode
                                else:
                                    moves = []
                                    # Single Stockfish call with multipv=3 gives us all 3 moves and their scores.
                                    top_3_moves = self.analyse_with_cache(engine, board, self.play_depth, multipv=3)

                                    # Extract centipawn scores directly from the root analysis (no extra analyses).
                                    current_scores = []
                                    for analysis in top_3_moves:
                                        sc = analysis["score"].white().score(mate_score=100000)
                                        current_scores.append(sc if sc is not None else 0)
                                    # Endgames can have fewer than three legal
                                    # moves; preserve the three UI slots.
                                    current_scores.extend([0] * (3 - len(current_scores)))

                                    eval_ = current_scores[0]
                                    eval1 = current_scores[1] if len(current_scores) > 1 else 0
                                    eval2 = current_scores[2] if len(current_scores) > 2 else 0

                                    for rank, value in enumerate((eval_, eval1, eval2), start=1):
                                        self.pipe.send("moveEval" + str(rank) + str(value))
                                    self.publish_predictions((eval_, eval1, eval2))
                                    self.publish_evaluation(top_3_moves[0]["score"])

                                    # Cache board geometry once to avoid 6× Selenium calls below.
                                    canvas_x_offset, canvas_y_offset = self.grabber.get_top_left_corner()
                                    board_elem = self.grabber.get_board()
                                    board_x_cache = canvas_x_offset + board_elem.location["x"]
                                    board_y_cache = canvas_y_offset + board_elem.location["y"]
                                    square_size_cache = board_elem.size['width'] / 8

                                    for i in range(len(top_3_moves)):
                                        cmove = top_3_moves[i]["pv"][0].uci()
                                        # Inline coordinate calculation using cache.
                                        if self.is_white:
                                            sx = board_x_cache + square_size_cache * (char_to_num(cmove[0]) - 1) + square_size_cache / 2
                                            sy = board_y_cache + square_size_cache * (8 - int(cmove[1])) + square_size_cache / 2
                                            ex = board_x_cache + square_size_cache * (char_to_num(cmove[2]) - 1) + square_size_cache / 2
                                            ey = board_y_cache + square_size_cache * (8 - int(cmove[3])) + square_size_cache / 2
                                        else:
                                            sx = board_x_cache + square_size_cache * (8 - char_to_num(cmove[0])) + square_size_cache / 2
                                            sy = board_y_cache + square_size_cache * (int(cmove[1]) - 1) + square_size_cache / 2
                                            ex = board_x_cache + square_size_cache * (8 - char_to_num(cmove[2])) + square_size_cache / 2
                                            ey = board_y_cache + square_size_cache * (int(cmove[3]) - 1) + square_size_cache / 2
                                        moves.append({
                                            'position': ((int(sx), int(sy)), (int(ex), int(ey))),
                                            'label': self.format_score(top_3_moves[i]["score"]),
                                        })
                                    self.overlay_queue.put({"type": "arrows", "arrows": moves})
                                    next_status_check = time.monotonic()
                                    while True:
                                        observed_moves = self.grabber.get_move_list()
                                        if observed_moves is None:
                                            time.sleep(poll_interval)
                                            continue
                                        if (len(observed_moves) < len(move_list)
                                                or observed_moves[:len(move_list)] != move_list):
                                            raise NewGameDetected()
                                        if len(move_list) != len(observed_moves):
                                            self_moved = True
                                            move_list = observed_moves
                                            move_san = move_list[-1]
                                            move = board.parse_san(move_san).uci()
                                            board.push_uci(move)
                                            break
                                        # URL checks are needed for navigation detection, but doing one
                                        # per poll adds a second Selenium round trip to the hot path.
                                        if time.monotonic() >= next_status_check:
                                            if self.grabber.chrome.current_url != game_url:
                                                raise NewGameDetected()
                                            next_status_check = time.monotonic() + status_interval
                                        time.sleep(poll_interval)

                            if not self_moved:
                                move_san = board.san(chess.Move(chess.parse_square(move[0:2]), chess.parse_square(move[2:4])))
                                board.push_uci(move)
                                move_list.append(move_san)
                                # Always use external hardware mouse cursor.
                                # No website APIs / JavaScript injection.
                                self.make_move(move)

                            self.overlay_queue.put({"type": "arrows", "arrows": []})
                            # Update eval with caching
                            score = self.analyse_with_cache(engine, board, self.analysis_depth)[0]['score']
                            self.publish_evaluation(score)
                            
                            self.moves_played += 1
                                
                            # Send the move to the GUI
                            self.pipe.send("S_MOVE" + move_san)

                            # Check if the game is over
                            if board.is_checkmate():
                                print()
                                # Track result for dynamic difficulty
                                self.consecutive_wins += 1
                                self.consecutive_losses = 0
                                # Send restart message to GUI
                                if self.enable_non_stop_puzzles and self.grabber.is_game_puzzles():
                                    self.grabber.click_puzzle_next()
                                    self.pipe.send("RESTART")
                                    self.wait_for_gui_to_delete()

                                elif self.grabber.is_game_over():
                                    self.wait_for_new_game(game_url, move_list)

                            # Give the site a moment to commit our move before
                            # polling for the opponent's reply.
                            time.sleep(poll_interval)

                        else:
                            # Opponent's turn - perform background analysis
                            if len(move_list) <= 0:
                                move_list = self.grabber.get_move_list()

                                for move in move_list:
                                    board.push_san(move)
                                continue
                            else:
                                # Background analysis: continuously analyse and update eval bar
                                # during opponent's turn
                                break
                        
                        # Wait for a response from the opponent
                        # by finding the differences between
                        # the previous and current position.
                        # While waiting, continuously update eval via background analysis.
                        previous_move_list = move_list.copy()
                        next_status_check = time.monotonic()
                        bg_next_analysis = time.monotonic()
                        while True:
                            now = time.monotonic()
                            
                            # Background analysis during opponent's turn
                            if now >= bg_next_analysis:
                                try:
                                    # Use cached analysis to avoid hammering the engine
                                    bg_score = self.analyse_with_cache(engine, board, self.bg_analysis_depth)[0]['score']
                                    self.publish_evaluation(bg_score)
                                except Exception:
                                    pass
                                bg_next_analysis = now + bg_interval
                            
                            if now >= next_status_check and self.grabber.is_game_over():
                                # Track loss for dynamic difficulty
                                self.consecutive_losses += 1
                                self.consecutive_wins = 0
                                # Send restart message to GUI
                                if self.enable_non_stop_puzzles and self.grabber.is_game_puzzles():
                                    self.grabber.click_puzzle_next()
                                    self.pipe.send("RESTART")
                                
                                elif self.grabber.is_game_over():
                                    self.wait_for_new_game(game_url, previous_move_list)
                            move_list = self.grabber.get_move_list()
                            if move_list is None:
                                time.sleep(poll_interval)
                                continue
                            if (len(move_list) < len(previous_move_list)
                                    or move_list[:len(previous_move_list)] != previous_move_list):
                                raise NewGameDetected()
                            if len(move_list) > len(previous_move_list):
                                # Opponent moved - do a final eval update
                                try:
                                    final_score = self.analyse_with_cache(engine, board, self.analysis_depth)[0]['score']
                                    self.publish_evaluation(final_score)
                                except Exception:
                                    pass
                                break
                            if now >= next_status_check:
                                if self.grabber.chrome.current_url != game_url:
                                    raise NewGameDetected()
                                next_status_check = now + status_interval
                            time.sleep(poll_interval)

                        # Get the move that the opponent made
                        move = move_list[-1]
                        board.push_san(move)
                        self.moves_played += 1
                        
                        if board.is_checkmate():
                            # Track loss for dynamic difficulty
                            self.consecutive_losses += 1
                            self.consecutive_wins = 0
                            # Send restart message to GUI
                            if self.enable_non_stop_puzzles and self.grabber.is_game_puzzles():
                                self.grabber.click_puzzle_next()
                                self.pipe.send("RESTART")

                            elif self.grabber.is_game_over():
                                self.wait_for_new_game(game_url, move_list)

                        # Manual mode performs a single MultiPV search at the
                        # start of the next turn.  It now publishes this same
                        # evaluation there, avoiding two searches of the same
                        # position while preserving the bar and all arrows.
                        if not self.enable_manual_mode:
                            score = self.analyse_with_cache(engine, board, self.analysis_depth)[0]['score']
                            self.publish_evaluation(score)

                except NewGameDetected:
                    self.wait_for_first_turn = True
                    self.position_cache.clear()
                    continue
                except NoSuchWindowException:
                    self.pipe.send("windowfail")
                    
                except Exception as e:
                    print(e)
                    exc_type, exc_obj, exc_tb = sys.exc_info()
                    fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
                    print(exc_type, fname, exc_tb.tb_lineno)
            else:
                continue

    def set_move_to_play(self, move_rank):
        self.move_to_play = move_rank