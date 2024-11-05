import pickle
import multiprocess
import threading
import time
import customtkinter as tk
from customtkinter import filedialog
from tkinter import ttk
from CTkMessagebox import ctkmessagebox as CTkMessagebox
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from overlay import run
from stockfish_bot import StockfishBot
from selenium.common import WebDriverException


class GUI:
    def __init__(self, master):
        self.master = master

        # Used for closing the threads
        self.exit = False

        # The Selenium Chrome driver
        self.chrome = None

        # # Used for storing the Stockfish Bot class Instance
        # self.stockfish_bot = None
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

        # Set the window properties
        self.master.title("Chess")
        #master.geometry("400x500")
        self.master.iconbitmap('src/assets/pawn_32x32.png')
        self.master.resizable(False, False)
        self.master.attributes("-topmost", True)
        self.master.protocol("WM_DELETE_WINDOW", self.on_close_listener)

        # Change the style
        style = ttk.Style()
        style.theme_use("clam")

        # Left frame
        left_frame = tk.CTkFrame(master)

        # Create the status text
        status_label = tk.CTkFrame(left_frame)
        tk.CTkLabel(status_label, text="Status:").pack(side=tk.LEFT)
        self.status_text = tk.CTkLabel(status_label, text="Inactive", fg_color="red")
        self.status_text.pack()
        status_label.pack(anchor=tk.NW)

        # Create the website chooser radio buttons
        self.website = tk.StringVar(value="chesscom")
        self.chesscom_radio_button = tk.CTkRadioButton(
            left_frame,
            text="Chess.com",
            variable=self.website,
            value="chesscom"
        )
        self.chesscom_radio_button.pack(anchor=tk.NW)
        self.lichess_radio_button = tk.CTkRadioButton(
            left_frame,
            text="Lichess.org",
            variable=self.website,
            value="lichess"
        )
        self.lichess_radio_button.pack(anchor=tk.NW)

        # Create the open browser button
        self.opening_browser = False
        self.opened_browser = False
        self.open_browser_button = tk.CTkButton(
            left_frame,
            text="Open Browser",
            command=self.on_open_browser_button_listener,
        )
        self.open_browser_button.pack(anchor=tk.NW)

        # Create the start button
        self.running = False
        self.start_button = tk.CTkButton(
            left_frame, text="Start", command=self.on_start_button_listener
        )
        self.start_button.configure(state = "disabled")
        self.start_button.pack(anchor=tk.NW, pady=5)

        # Create the manual mode checkbox
        self.enable_manual_mode = tk.BooleanVar(value=False)
        self.manual_mode_checkbox = tk.CTkCheckBox(
            left_frame,
            text="Manual Mode",
            variable=self.enable_manual_mode,
            command=self.on_manual_mode_checkbox_listener,
        )
        self.manual_mode_checkbox.pack(anchor=tk.NW)

        # Create the manual mode instructions
        self.manual_mode_frame = tk.CTkFrame(left_frame)
        self.manual_mode_label = tk.CTkLabel(
            self.manual_mode_frame, text="\u2022 Press 3 to make a move"
        )
        self.manual_mode_label.pack(anchor=tk.NW)

        # Create the mouseless mode checkbox
        self.enable_mouseless_mode = tk.BooleanVar(value=False)
        self.mouseless_mode_checkbox = tk.CTkCheckBox(
            left_frame,
            text="Mouseless Mode",
            variable=self.enable_mouseless_mode
        )
        self.mouseless_mode_checkbox.pack(anchor=tk.NW)

        # Create the non-stop puzzles check button
        self.enable_non_stop_puzzles = tk.IntVar(value=0)
        self.non_stop_puzzles_check_button = tk.CTkCheckBox(
            left_frame,
            text="Non-stop puzzles",
            variable=self.enable_non_stop_puzzles
        )
        self.non_stop_puzzles_check_button.pack(anchor=tk.NW)

        # Create the bongcloud check button
        self.enable_bongcloud = tk.IntVar()
        self.bongcloud_check_button = tk.CTkCheckBox(
            left_frame,
            text="Bongcloud",
            variable=self.enable_bongcloud
        )
        self.bongcloud_check_button.pack(anchor=tk.NW)
        
        
        #Timer
        self.enable_timer = tk.IntVar(value=1)
        self.timer_check_button = tk.CTkCheckBox(
            left_frame,
            text="Timer",
            variable=self.enable_timer,
            command = self.on_timer_chek
        )
        self.timer_check_button.pack(anchor=tk.NW)
        
        min_timer_frame = tk.CTkFrame(left_frame, fg_color = "transparent")
        self.min_timer_label = tk.CTkLabel(min_timer_frame, text="MIN")
        self.min_timer_label.pack(anchor=tk.N)
        self.timer_min = tk.IntVar(value=2)
        self.min_timer_scale = tk.CTkSlider(
            min_timer_frame,
            from_=0,
            to=20,
            orientation=tk.HORIZONTAL,
            variable=self.timer_min,
            command=self.on_min_timer_change,
            number_of_steps = 20
        )
        self.min_timer_counter = tk.CTkLabel(min_timer_frame, text=int(self.min_timer_scale.get()))
        self.min_timer_counter.pack(anchor=tk.N)
        self.min_timer_scale.pack(anchor=tk.N)
        min_timer_frame.pack(anchor=tk.N)

        max_timer_frame = tk.CTkFrame(left_frame, fg_color = "transparent")
        self.max_timer_label = tk.CTkLabel(max_timer_frame, text="MAX")
        self.max_timer_label.pack(anchor=tk.N)

        
        self.timer_max = tk.IntVar(value=15)
        self.max_timer_scale = tk.CTkSlider(
            max_timer_frame,
            from_=0,
            to=20,
            orientation=tk.HORIZONTAL,
            variable=self.timer_max,
            command=self.on_max_timer_change,
            number_of_steps = 20
        )
        self.max_timer_counter = tk.CTkLabel(max_timer_frame, text=int(self.max_timer_scale.get()))
        self.max_timer_counter.pack(anchor=tk.N)
        self.max_timer_scale.pack(anchor=tk.N)
        max_timer_frame.pack(anchor=tk.N)


        # Separator
        separator_frame = tk.CTkFrame(left_frame)
        separator = ttk.Separator(separator_frame, orient="horizontal")
        separator.grid(row=0, column=0, sticky="ew")
        label = tk.CTkLabel(separator_frame, text="Misc")
        label.grid(row=0, column=0, padx=82)
        separator_frame.pack(anchor=tk.NW, pady=10, expand=True, fill=tk.X)
        
        #cookies
        self.enable_cookie = tk.IntVar(value=1)
        self.cookies_checkbox = tk.CTkCheckBox(
            left_frame,
            text="Auto load cookies",
            variable=self.enable_cookie,
            onvalue=1,
            offvalue=0
        )
        self.cookies_checkbox.pack(anchor=tk.NW)

        self.save_cookies_button = tk.CTkButton(
            left_frame,
            text="Save cookies",
            command=self.on_save_cookies_button_listener,
        )
        self.save_cookies_button.pack(anchor=tk.NW)

        # Create the topmost check button
        self.enable_topmost = tk.IntVar(value=1)
        self.topmost_check_button = tk.CTkCheckBox(
            left_frame,
            text="Window stays on top",
            variable=self.enable_topmost,
            onvalue=1,
            offvalue=0,
            command=self.on_topmost_check_button_listener,
        )
        self.topmost_check_button.pack(anchor=tk.NW)


        left_frame.grid(row=0, column=0, padx=5, sticky=tk.NW)

        # Center frame
        center_frame = tk.CTkFrame(master)

        # Treeview frame
        treeview_frame = tk.CTkFrame(center_frame)

        # Create the moves Treeview
        self.tree = ttk.Treeview(
            treeview_frame,
            column=("#", "White", "Black"),
            show="headings",
            height=23,
            selectmode="browse",
        )
        self.tree.pack(anchor=tk.NW, side=tk.LEFT)

        # # Add the scrollbar to the Treeview
        self.vsb = ttk.Scrollbar(
            treeview_frame,
            orient="vertical",
            command=self.tree.yview
        )
        self.vsb.pack(fill=tk.Y, expand=True)
        self.tree.configure(yscrollcommand=self.vsb.set)

        # Create the columns
        self.tree.column("# 1", anchor=tk.CENTER, width=35)
        self.tree.heading("# 1", text="#")
        self.tree.column("# 2", anchor=tk.CENTER, width=60)
        self.tree.heading("# 2", text="White")
        self.tree.column("# 3", anchor=tk.CENTER, width=60)
        self.tree.heading("# 3", text="Black")

        treeview_frame.pack(anchor=tk.NW)
        

        # Create the export PGN button
        self.export_pgn_button = tk.CTkButton(
            center_frame, text="Export PGN", command=self.on_export_pgn_button_listener
        )
        self.export_pgn_button.pack(anchor=tk.NW, fill=tk.X)

        center_frame.grid(row=0, column=1, sticky=tk.NW)

#custom

        eval_frame = tk.CTkFrame(master)
        eval_frame.grid(row=0, column=2, padx=2, sticky=tk.NW)
        right_frame = tk.CTkFrame(master, fg_color="transparent")
        right_frame.grid(row=0, column=3, padx=5, sticky=tk.NW)
        
        self.eval_bar = tk.CTkProgressBar(
            eval_frame,
            orientation=tk.VERTICAL,
            #command=self.on_skill_change,
            height= 450,
            width= 20,
            #button_color = "grey",
            progress_color = "black",
            fg_color = "white"
        )
        self.eval_bar.pack()
        
        self.eval_label = tk.CTkLabel(eval_frame, text = '0')
        self.eval_label.pack()
        
        # Separator
        separator_frame = tk.CTkFrame(right_frame)
        separator = ttk.Separator(separator_frame, orient="horizontal")
        separator.grid(row=0, column=0, sticky="ew")
        
        label = tk.CTkLabel(separator_frame, text="Stockfish parameters")
        label.grid(row=0, column=0, padx=40)
        separator_frame.pack(anchor=tk.NW, pady=5, expand=True, fill=tk.X)

        # Create the Slow mover entry field
        slow_mover_frame = tk.CTkFrame(right_frame)
        self.slow_mover_label = tk.CTkLabel(slow_mover_frame, text="Slow Mover")
        self.slow_mover_label.pack(side=tk.LEFT)
        self.slow_mover = tk.IntVar(value=100)
        self.slow_mover_entry = tk.CTkEntry(
            slow_mover_frame, textvariable=self.slow_mover, justify="center", width=50,
        )
        self.slow_mover_entry.pack()
        slow_mover_frame.pack(anchor=tk.N)

        # Create the skill level scale
        skill_level_frame = tk.CTkFrame(right_frame, fg_color = "transparent")
        tk.CTkLabel(skill_level_frame, text="Skill Level").pack(anchor=tk.N)
        
        self.skill_level = tk.IntVar(value=20)
        self.skill_level_scale = tk.CTkSlider(
            skill_level_frame,
            from_=1,
            to=20,
            orientation=tk.HORIZONTAL,
            variable=self.skill_level,
            command=self.on_skill_change,
            number_of_steps = 20
        )
        self.skill_level_counter = tk.CTkLabel(skill_level_frame, text=int(self.skill_level_scale.get()))
        self.skill_level_counter.pack(anchor=tk.N)
        self.skill_level_scale.pack(anchor=tk.N)
        skill_level_frame.pack(anchor=tk.N)

        # Create the Stockfish depth scale
        stockfish_depth_frame = tk.CTkFrame(right_frame, fg_color = "transparent")
        tk.CTkLabel(stockfish_depth_frame, text="Depth").pack(anchor=tk.N, pady=(5, 0))
        self.stockfish_depth = tk.IntVar(value=15)
        self.stockfish_depth_scale = tk.CTkSlider(
            stockfish_depth_frame,
            from_=1,
            to=20,
            orientation=tk.HORIZONTAL,
            variable=self.stockfish_depth,
            command=self.on_depth_change
        )
        
        self.depth_counter = tk.CTkLabel(stockfish_depth_frame, text=int(self.stockfish_depth.get()))
        self.depth_counter.pack(anchor=tk.N)
        self.stockfish_depth_scale.pack(anchor=tk.N)
        stockfish_depth_frame.pack(anchor=tk.N)
        
       

        # Create the memory entry field
        memory_frame = tk.CTkFrame(right_frame, fg_color="transparent")
        tk.CTkLabel(memory_frame, text="Memory", padx=10).pack(side=tk.LEFT)
        self.memory = tk.IntVar(value=8)
        self.memory_entry = tk.CTkEntry(
            memory_frame, textvariable=self.memory, justify="center", width=50)
        self.memory_entry.pack(side=tk.LEFT)
        tk.CTkLabel(memory_frame, text="MB", padx=10).pack()
        memory_frame.pack(anchor=tk.NW, pady=(0, 15))

        # Create the CPU threads entry field
        cpu_threads_frame = tk.CTkFrame(right_frame, fg_color="transparent")
        tk.CTkLabel(cpu_threads_frame, text="CPU Threads", padx=10).pack(side=tk.LEFT)
        self.cpu_threads = tk.IntVar(value=1)
        self.cpu_threads_entry = tk.CTkEntry(
            cpu_threads_frame, textvariable=self.cpu_threads, justify="center", width=30
        )
        self.cpu_threads_entry.pack()
        cpu_threads_frame.pack(anchor=tk.NW)
        
        #min split depth entry
        min_split_depth_frame = tk.CTkFrame(right_frame, fg_color="transparent")
        tk.CTkLabel(min_split_depth_frame, text="Min Split Depth", padx=10).pack(side=tk.LEFT)
        self.min_split_depth = tk.IntVar(value=4)
        self.min_split_depth_entry = tk.CTkEntry(
            min_split_depth_frame, textvariable=self.min_split_depth, justify="center", width=50)
        self.min_split_depth_entry.pack()
        min_split_depth_frame.pack(anchor=tk.NW)
              
        #Contempt entry
        contempt_frame = tk.CTkFrame(right_frame, fg_color="transparent")
        tk.CTkLabel(contempt_frame, text="Contempt", padx=10).pack(side=tk.LEFT)
        self.contempt = tk.IntVar(value=30)
        self.contempt_entry = tk.CTkEntry(
            contempt_frame, textvariable=self.contempt, justify="center", width=50)
        self.contempt_entry.pack()
        contempt_frame.pack(anchor=tk.NW)
        
        #Move Overhead entry
        move_overhead_frame = tk.CTkFrame(right_frame, fg_color="transparent")
        tk.CTkLabel(move_overhead_frame, text="Move Overhead", padx=10).pack(side=tk.LEFT)
        self.move_overhead = tk.IntVar(value=15)
        self.overhead_entry = tk.CTkEntry(
            move_overhead_frame, textvariable=self.move_overhead, justify="center", width=50)
        self.overhead_entry.pack()
        move_overhead_frame.pack(anchor=tk.NW)
        
        #Min Think TIme Entry
        min_think_time_frame = tk.CTkFrame(right_frame, fg_color="transparent")
        tk.CTkLabel(min_think_time_frame, text="Min Think Time", padx=10).pack(side=tk.LEFT)
        self.min_think_time = tk.IntVar(value=10)
        self.min_think_time_entry = tk.CTkEntry(
            min_think_time_frame, textvariable=self.min_think_time, justify="center", width=50)
        self.min_think_time_entry.pack()
        min_think_time_frame.pack(anchor=tk.NW)
        
        #multipv entry
        multiPV_frame = tk.CTkFrame(right_frame, fg_color="transparent")
        tk.CTkLabel(multiPV_frame, text="MultiPV", padx=10).pack(side=tk.LEFT)
        self.multiPV = tk.IntVar(value=1)
        self.multiPV_entry = tk.CTkEntry(
            multiPV_frame, textvariable=self.multiPV, justify="center", width=50)
        self.multiPV_entry.pack()
        multiPV_frame.pack(anchor=tk.NW)
        
         #elo entry
        elo_frame = tk.CTkFrame(right_frame, fg_color="transparent")
        tk.CTkLabel(elo_frame, text="Elo", padx=10).pack(side=tk.LEFT)
        self.elo = tk.IntVar(value=4000)
        self.elo_entry = tk.CTkEntry(
            elo_frame, textvariable=self.elo, justify="center", width=50)
        self.elo_entry.pack()
        elo_frame.pack(anchor=tk.NW)
        
        # Separator
        separator_frame = tk.CTkFrame(right_frame)
        separator = ttk.Separator(separator_frame, orient="horizontal")
        separator.pack(anchor=tk.N)
        separator_frame.pack(anchor=tk.NW, pady=10, expand=True, fill=tk.X)
        
        
        # Create the select stockfish button
        self.stockfish_path = ""
        self.select_stockfish_button = tk.CTkButton(
            right_frame,
            text="Select Stockfish",
            command=self.on_select_stockfish_button_listener,
        )
        self.select_stockfish_button.pack(anchor=tk.N)
        
         # Create the stockfish path text
        self.stockfish_path_text = tk.CTkLabel(right_frame, text="", wraplength=180)
        self.stockfish_path_text.pack(anchor=tk.N)
        
        

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

        # Start the keyboard listener thread
        keyboard_listener_thread = threading.Thread(
            target=self.keypress_listener_thread
        )
        keyboard_listener_thread.start()

    # Detects if the user pressed the close button
    def on_close_listener(self):
        # Set self.exit to True so that the threads will stop
        self.exit = True
        self.master.destroy()

    # Detects if the Stockfish Bot process is running
    def process_checker_thread(self):
        while not self.exit:
            if (
                self.running
                and self.stockfish_bot_process is not None
                and not self.stockfish_bot_process.is_alive()
            ):
                self.on_stop_button_listener()

                # Restart the process if restart_after_stopping is True
                if self.restart_after_stopping:
                    self.restart_after_stopping = False
                    self.on_start_button_listener()
            time.sleep(0.1)

    # Detects if Selenium Chromedriver is running
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

                    # Set Opening Browser button state to closed
                    self.open_browser_button["text"] = "Open Browser"
                    self.open_browser_button["state"] = "normal"
                    self.open_browser_button.update()

                    self.on_stop_button_listener()
                    self.chrome = None
            except IndexError:
                pass
            time.sleep(0.1)

    # Responsible for communicating with the Stockfish Bot process
    # The pipe can receive the following commands:
    # - "START": Resets and starts the Stockfish Bot
    # - "S_MOVE": Sends the Stockfish Bot a single move to make
    #   Ex. "S_MOVEe4
    # - "M_MOVE": Sends the Stockfish Bot multiple moves to make
    #   Ex. "S_MOVEe4,c5,Nf3
    # - "ERR_EXE": Notifies the GUI that the Stockfish Bot can't initialize Stockfish
    # - "ERR_PERM": Notifies the GUI that the Stockfish Bot can't execute the Stockfish executable
    # - "ERR_BOARD": Notifies the GUI that the Stockfish Bot can't find the board
    # - "ERR_COLOR": Notifies the GUI that the Stockfish Bot can't find the player color
    # - "ERR_MOVES": Notifies the GUI that the Stockfish Bot can't find the moves list
    # - "ERR_GAMEOVER": Notifies the GUI that the current game is already over
    def process_communicator_thread(self):
        while not self.exit:
            try:
                if (
                    self.stockfish_bot_pipe is not None
                    and self.stockfish_bot_pipe.poll()
                ):
                    data = self.stockfish_bot_pipe.recv()
                    if data == "START":
                        self.clear_tree()
                        self.match_moves = []
                        self.eval_bar.set(0.5)
                        # Update the status text
                        self.status_text.configure(text = "Running")
                        self.status_text.configure(fg_color = "green")

                        # Update the run button
                        self.start_button.configure(text = "Stop")
                        self.start_button.configure(state = "normal")
                        self.start_button.configure(command = self.on_stop_button_listener)
                    
                    elif data == "playeriswhite":
                        self.is_white = True
                        self.eval_bar.configure(fg_color = "black")
                        self.eval_bar.configure(progress_color = "white")
                    
                    elif data == "playerisblack":
                        self.is_white = False

                        self.eval_bar.configure(fg_color = "white")
                        self.eval_bar.configure(progress_color = "black")
                    

                        
                    elif data[:4] == "eval":
                        
                        if data[:5] == "evalm":
                            eval = 'M in\n' + data[5:]
                            self.eval_label.configure(text = eval)


                        elif data[:5] == "evalp":
                            eval = data[5:]
                            eval_float = float(eval)/10
                            
                            if self.is_white == True:
                                
                                self.eval_bar.set(0.5 + eval_float/2)
                            else:
                                
                                self.eval_bar.set(0.5 + eval_float/-2)
                                    
                            self.eval_label.configure(text = eval)
                            
                    elif data[:7] == "RESTART":
                        self.restart_after_stopping = True
                        self.stockfish_bot_pipe.send("DELETE")
                    elif data[:6] == "S_MOVE":
                        move = data[6:]
                        self.match_moves.append(move)
                        self.insert_move(move)
                        self.tree.yview_moveto(1)
                    elif data[:6] == "M_MOVE":
                        moves = data[6:].split(",")
                        self.match_moves += moves
                        self.set_moves(moves)
                        self.tree.yview_moveto(1)
                    elif data[:7] == "ERR_EXE":
                        CTkMessagebox.CTkMessagebox(
                            title="Error",
                            message="Stockfish path provided is not valid!"
                        )
                    elif data[:8] == "ERR_PERM":
                        CTkMessagebox.CTkMessagebox(
                            title="Error",
                            message="Stockfish path provided is not executable!"
                        )
                    elif data[:9] == "ERR_BOARD":
                        CTkMessagebox.CTkMessagebox(
                            title= "Error",
                            message="Cant find board!"
                        )
                    elif data[:9] == "ERR_COLOR":
                        CTkMessagebox.CTkMessagebox(
                            title="Error",
                            message="Cant find player color!"
                        )
                    elif data[:9] == "ERR_MOVES":
                        CTkMessagebox.CTkMessagebox(
                            title="Error",
                            message="Cant find moves list!"
                        )
                    elif data[:12] == "ERR_GAMEOVER":
                        CTkMessagebox.CTkMessagebox(
                            title="Error",
                            message="Game has already finished!"
                        )
            except (BrokenPipeError, OSError):
                self.stockfish_bot_pipe = None

            time.sleep(0.1)

    def keypress_listener_thread(self):
        while not self.exit:
            time.sleep(0.1)
            if not self.opened_browser:
                continue

    def on_open_browser_button_listener(self):
        # Set Opening Browser button state to opening
        self.opening_browser = True
        self.open_browser_button.configure(text = "Opening Browser...")
        self.open_browser_button.configure(state = "disabled")
        
        # Open Webdriver
        options = webdriver.ChromeOptions()
        options.add_experimental_option("excludeSwitches", ["enable-logging", "enable-automation"])
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option('useAutomationExtension', False)
        try:
            self.chrome = webdriver.Chrome(
                service=Service(executable_path="./bin/chromedriver.exe"),
                options=options
            )
        except WebDriverException:
            # No chrome installed
            self.opening_browser = False
            self.open_browser_button.configure(text = "Open Browser")
            self.open_browser_button.configure(state = "enabled")
            CTkMessagebox.CTkMessagebox(
                title = "Error",
                message = "Cant find Chrome. You need to have Chrome installed for this to work.",
            )
            return

        # Open chess.com
        if self.website.get() == "chesscom":
            self.chrome.get("https://www.chess.com")
        else:
            self.chrome.get("https://www.lichess.org")
            
        if self.enable_cookie.get() == 1:
            try:
                cookies = pickle.load(open("cookies.pkl", "rb"))
                for cookie in cookies:
                    self.chrome.add_cookie(cookie)
                self.chrome.refresh()
            except FileNotFoundError:
                CTkMessagebox.CTkMessagebox(
                title="Error",
                message = "Cookies not save. sign in and Save cookies before loading"
            )

        # Build Stockfish Bot
        self.chrome_url = self.chrome.service.service_url
        self.chrome_session_id = self.chrome.session_id

        # Set Opening Browser button state to opened
        self.opening_browser = False
        self.opened_browser = True
        self.open_browser_button.configure(text = "Browser is opened")
        self.open_browser_button.configure(state = "enabled")

        # Enable run button
        self.start_button.configure(state = "normal")
         

    def on_start_button_listener(self):
        # Check if Slow mover value is valid
        slow_mover = self.slow_mover.get()
        if slow_mover < 10 or slow_mover > 1000:
            CTkMessagebox.CTkMessagebox(
                title="Error",
                message = "Slow Mover must be between 10 and 1000"
            )
            return

        # Check if stockfish path is not emptpip install CTkMessageboxy
        if self.stockfish_path == "":
            CTkMessagebox.CTkMessagebox(
                title="Error",
                message="Stockfish path is empty"
            )
            return

        # Check if mouseless mode is enabled when on chess.com
        if self.enable_mouseless_mode.get() == 1 and self.website.get() == "chesscom":
            CTkMessagebox.CTkMessagebox(
                "Error", "Mouseless mode is only supported on lichess.org"
            )
            return

        # Create the pipes used for the communication
        # between the GUI and the Stockfish Bot process
        parent_conn, child_conn = multiprocess.Pipe()
        self.stockfish_bot_pipe = parent_conn

        # Create the message queue that is used for the communication
        # between the Stockfish and the Overlay processes
        st_ov_queue = multiprocess.Queue()
        
        params = {
                #"Contempt": self.contempt_entry.get(),
                #"Min Split Depth": self.min_split_depth_entry.get(),
                "Threads": self.cpu_threads_entry.get(),
                #Ponder": "true
                "Hash": self.memory_entry.get(),
                #"MultiPV": self.multiPV_entry.get(),
                "Skill Level": self.skill_level.get(),
                "Move Overhead": self.overhead_entry.get(),
                #"Minimum Thinking Time": self.min_think_time_entry.get(),
                #"Slow Mover": self.slow_mover.get(),
                "UCI_LimitStrength": "false",
                #"UCI_Elo": self.elo_entry.get()
            }
        if self.enable_timer.get() == 1:
            timer = (self.timer_min.get(), self.timer_max.get())
        else:
            timer = None
        # Create the Stockfish Bot process
        self.stockfish_bot_process = StockfishBot(
            self.chrome_url,
            self.chrome_session_id,
            self.website.get(),
            child_conn,
            st_ov_queue,
            self.stockfish_path,
            self.enable_manual_mode.get() == 1,
            self.enable_mouseless_mode.get() == 1,
            self.enable_non_stop_puzzles.get() == 1,
            self.enable_bongcloud.get() == 1,
            self.stockfish_depth.get(),
            params,
            timer
        )
        self.stockfish_bot_process.start()

        # Create the overlay
        self.overlay_screen_process = multiprocess.Process(
            target=run, args=(st_ov_queue,)
        )
        self.overlay_screen_process.start()

        # Update the run button
        self.running = True
        self.start_button.configure(text = "Starting...")
        self.start_button.configure(state = "disabled")

    def on_stop_button_listener(self):
        # Stop the Stockfish Bot process
        if self.stockfish_bot_process is not None:
            self.stockfish_bot_process.kill()
            self.stockfish_bot_process = None

        # Close the Stockfish Bot pipe
        if self.stockfish_bot_pipe is not None:
            self.stockfish_bot_pipe.close()
            self.stockfish_bot_pipe = None

        # Stop the overlay
        if self.overlay_screen_process is not None:
            self.overlay_screen_process.kill()
            self.overlay_screen_process = None

        # Close the overlay pipe
        if self.overlay_screen_pipe is not None:
            self.overlay_screen_pipe.close()
            self.overlay_screen_pipe = None

        # Update the status text
        self.running = False
        self.status_text.configure(text = "Inactive")
        self.status_text.configure(fg_color = "red")

        # Update the run button
        self.start_button.configure(text = "Start")
        self.start_button.configure(state = "normal")
        self.start_button.configure(command = self.on_start_button_listener)

    def on_topmost_check_button_listener(self):
        if self.enable_topmost.get() == 1:
            self.master.attributes("-topmost", True)
        else:
            self.master.attributes("-topmost", False)

    def on_export_pgn_button_listener(self):
        # Create the file dialog
        f = filedialog.asksaveasfile(
            initialfile="match.pgn",
            defaultextension=".pgn",
            filetypes=[("Portable Game Notation", "*.pgn"), ("All Files", "*.*")],
        )
        if f is None:
            return

        # Write the PGN to the file
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
        # Create the file dialog
        f = filedialog.askopenfilename()
        if f is None:
            return

        # Set the Stockfish path
        self.stockfish_path = f
        self.stockfish_path_text.configure(text = self.stockfish_path)
        self.stockfish_path_text.update()

    # Clears the Treeview
    def clear_tree(self):
        self.tree.delete(*self.tree.get_children())
        self.tree.update()

    # Inserts a move into the Treeview
    def insert_move(self, move):
        cells_num = sum(
            [len(self.tree.item(i)["values"]) - 1 for i in self.tree.get_children()]
        )
        if (cells_num % 2) == 0:
            rows_num = len(self.tree.get_children())
            self.tree.insert("", "end", text="1", values=(rows_num + 1, move))
        else:
            self.tree.set(self.tree.get_children()[-1], column=2, value=move)
        self.tree.update()

    # Overwrites the Treeview with the given list of moves
    def set_moves(self, moves):
        self.clear_tree()

        # Insert in pairs
        pairs = list(zip(*[iter(moves)] * 2))
        for i, pair in enumerate(pairs):
            self.tree.insert("", "end", text="1", values=(str(i + 1), pair[0], pair[1]))

        # Insert the remaining one if it exists
        if len(moves) % 2 == 1:
            self.tree.insert("", "end", text="1", values=(len(pairs) + 1, moves[-1]))

        self.tree.update()

    def on_manual_mode_checkbox_listener(self):
        if self.enable_manual_mode.get() == 1:
            self.manual_mode_frame.pack(after=self.manual_mode_checkbox)
            self.manual_mode_frame.update()
        else:
            self.manual_mode_frame.pack_forget()
            self.manual_mode_checkbox.update()
    
    #Custom methods
    
    def on_save_cookies_button_listener(self):
        pickle.dump(self.chrome.get_cookies(), open("cookies.pkl", "wb"))

    def on_skill_change(self, value):
        self.skill_level_counter.configure(text=int(value))
    
    def on_depth_change(self, value):
        self.depth_counter.configure(text=int(value))
    
    def on_min_timer_change(self, value):
        self.min_timer_counter.configure(text=int(value))
      
    def on_max_timer_change(self, value):
        self.max_timer_counter.configure(text=int(value))
        
    def on_timer_chek(self):
        if self.enable_timer.get() == 1:
            self.min_timer_label.pack()
            self.min_timer_counter.pack()
            self.min_timer_scale.pack()
            
            self.max_timer_label.pack()
            self.max_timer_counter.pack()
            self.max_timer_scale.pack()
            


        else:
            self.min_timer_counter.pack_forget()
            self.min_timer_scale.pack_forget()
            self.max_timer_scale.pack_forget()
            self.min_timer_counter.pack_forget()
            self.max_timer_counter.pack_forget()
            self.max_timer_label.pack_forget()
            self.min_timer_label.pack_forget()

            



if __name__ == "__main__":
    window = tk.CTk()
    my_gui = GUI(window)
    window.mainloop()
