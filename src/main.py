import os
import dearpygui.dearpygui as dpg
import pickle
import multiprocess
import threading
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from overlay import run
from stockfish_bot import StockfishBot
from selenium.common import WebDriverException
from selenium.common.exceptions import InvalidCookieDomainException, UnableToSetCookieException
import tkinter as tk
from tkinter import filedialog

class ChessApp:

    def __init__(self):
        self.stockfish_path = "C:\\Users\\TJ\\Documents\\stockfish\\stockfish-windows-x86-64.exe"
        #Bot properties
        self.website = "Chess.com"
        self.move_to_play = 1
        #self.stockfish_path = None
        self.running = False
        self.opened_browser = False
        self.move_colors = {
            '1': (0, 255, 0, 122),
            '2': (255, 102, 0, 122),
            '3': (255, 0, 0, 122)
        }
        #UI properties
        self.errors = {
            1: "critical",
            2: "mild",
            3: "information"
        }


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


        dpg.create_context()
        self.min_width = 400
        self.min_height = 550
        self.max_width = 750
        self.max_height = 550
        self.stockfish_settings_toggled = False
        
        
        with dpg.font_registry():
            # first argument ids the path to the .ttf or .otf file
            default_font = dpg.add_font(".\\bin\\Kanit-Regular.ttf", 20)
        # Set up window
        # Ensure the table is set up with the correct structure
        with dpg.window(label="Chess", no_close=True, tag="Primary Window", no_scrollbar=True):
            
            # Create the table with proper columns for layout
            
            # Create a single table row with three child windows in different columns
            with dpg.group(horizontal=True):

                # Left Frame - Status and Controls
                with dpg.child_window(tag=1,border=False, no_scrollbar=True,  pos=(10,10)):
                    
                    with dpg.group(horizontal=True):
                        
                        with dpg.child_window(border=False, no_scrollbar=True, width=300):
                            
                            with dpg.child_window(width = 400, height=150, border = False):
                                with dpg.group(horizontal=True):
                                        dpg.add_text("Status:")
                                        self.status_text = dpg.add_text("Inactive", tag="status", color=[255, 0, 0])
                            
                                with dpg.group(horizontal=True, horizontal_spacing= 10):
                                    with dpg.child_window(width = 150, border = False):
                                        dpg.add_radio_button(("Chess.com", "Lichess.org"), callback=self.on_website_choice, default_value="Chess.com")
                                        dpg.add_button(tag = "open browser", label="Open Browser", callback=self.on_open_browser_button_listener)
                                        dpg.add_button(tag = "start",label="Start", callback=self.on_start_button_listener, enabled=False)

                                    with dpg.child_window(width = 150, border = False):
                                        dpg.add_checkbox(tag = "manual mode", label="Manual Mode")
                                        dpg.add_checkbox(tag = "mouseless mode", label="Mouseless Mode")
                                        dpg.add_checkbox(tag = "puzzles", label="Non-stop puzzles")
                                        dpg.add_checkbox(tag = "bongcloud", label="Bongcloud")
                            with dpg.group(height=500):
                                dpg.add_separator()
                                with dpg.tree_node(label="Arrows"):
                                    dpg.add_separator(label="Arrow 1")
                                    dpg.add_checkbox(tag="Arrow 1", label = "show")
                                    dpg.add_color_edit(tag = "edit 1", default_value=(0,255,0,122), no_alpha=True, no_label=True, callback=self.on_color_edit)

                                    dpg.add_separator(label="Arrow 2")
                                    dpg.add_checkbox(tag="Arrow 2", label = "show")
                                    dpg.add_color_edit(tag = "edit 2", default_value=(255,163,0,122), no_alpha=True, no_label=True, callback=self.on_color_edit)

                                    dpg.add_separator(label="Arrow 3")
                                    dpg.add_checkbox(tag="Arrow 3", label = "show")
                                    dpg.add_color_edit(tag = "edit 3", default_value=(255,0,0,122), no_alpha=True, no_label=True, callback=self.on_color_edit)
                                    
                                with dpg.tree_node(label="Settings"):

                                    with dpg.group(horizontal=True):
                                        dpg.add_text(default_value="PLay")
                                        dpg.add_combo(["Best Move", "2nd Best Move", "3rd Best Move"], tag = "move select", callback = self.on_move_selected)

                                    dpg.add_separator(label="Timer")
                                    dpg.add_checkbox(tag = "timer", label="Timer", )
                                    self.timer_min_slider = dpg.add_slider_int(tag = "min timer",label="MIN", clamped=True,min_value=0, max_value=20, default_value=2)
                                    self.timer_max_slider = dpg.add_slider_int(tag = "max timer",label="MAX", min_value=0, max_value=20, default_value=15)

                            dpg.add_separator()
                            dpg.add_checkbox(tag = "load cookies",label="Load cookies")
                            dpg.add_button(label="Save cookies", callback=self.on_save_cookies_button_listener)
                            dpg.add_separator(label ="Eval")
                            dpg.add_progress_bar(tag="eval", default_value= 0.5, width= 200)
                            dpg.add_text(tag = "eval text", default_value="0")

                            #dpg.add_checkbox(label="Window stays on top", default_value=True, callback=self.on_topmost_checkbox_listener)

                        with dpg.child_window(no_scrollbar=True, border=False, width=50):  # Increase width here
                            dpg.add_button(tag="toggle next", height=100, width=50, pos=(0, 225), arrow=True, direction=1, callback=self.togle_fish)  # Button inside larger child_window
            
                # Right Frame - Stockfish Settings
                with dpg.child_window(tag=2, width=200, height=500, show=False, pos=(400, 0), border=False):
                    dpg.add_text("Stockfish Parameters")
                    dpg.add_slider_int(tag = "skill level", label="Skill Level", min_value=1, max_value=20, default_value=20, width=90)
                    dpg.add_input_int(tag = "hash", label="Hash (MB)", default_value=8, width=90)
                    dpg.add_slider_int(tag = "depth", label="depth", min_value=1, max_value=20, default_value=6, width=90)

                    dpg.add_input_int(tag = "threads", label="Threads", default_value=1, width=90)
                    dpg.add_input_int(tag = "move overhead", label="Move Overhead", default_value=15, width=90)
                    dpg.add_button(tag = "select stockfish", label="Select Stockfish", callback= self.on_select_stockfish_button_listener)\
                    
                    with dpg.window(label="Select Fish", modal=True, show=False, tag="modal", no_title_bar=True, width=250):
                        dpg.add_text("", tag= "modal text")
                        dpg.add_separator()
                        dpg.add_button(label="OK", width=75, callback=lambda: dpg.configure_item("modal", show=False), pos=(90, 70))

                    

                    #dpg.add_bar_group_series(values= [0,5, 0.5], label_ids= ["black", "white"], group_size=2)
                    # Create a plot
                    # create x axis
                    '''                    with dpg.plot(label="Bar Group Series", height=400, width=50):
                        dpg.add_plot_legend()

                        ilabels = ["black","white"]
                        glabels = (("eval", 0))
                        groups_c = 2

                        

                        dpg.add_plot_axis(dpg.mvXAxis, label="Student", tag="xaxis_bar_group", no_gridlines=True, auto_fit=True)
                        dpg.set_axis_limits(dpg.last_item(), 5, 10)
                        #dpg.set_axis_ticks(dpg.last_item(), glabels)

                        # create y axis
                        with dpg.plot_axis(dpg.mvYAxis, label="Score", tag="yaxis_bar_group", auto_fit=True):
                            dpg.set_axis_limits(dpg.last_item(), 0, 110)
                            dpg.add_bar_group_series(values=[0.5, 0.5], label_ids=ilabels, 
                                group_size=groups_c, tag="bar_group_series", label="Final Exam")
                    
                        '''



        dpg.bind_font(default_font)

        #Themes
        with dpg.theme() as global_theme:
            #All components
            with dpg.theme_component(dpg.mvAll):
                #set colors
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, (0, 0, 0, 0), category=dpg.mvThemeCat_Core)
                dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (0, 0, 0, 0), category=dpg.mvThemeCat_Core)
                dpg.add_theme_color(dpg.mvThemeCol_Border, (115, 6, 37), category=dpg.mvThemeCat_Core)
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, (0, 0, 0, 0), category=dpg.mvThemeCat_Core)
                dpg.add_theme_color(dpg.mvThemeCol_CheckMark, (115, 6, 37), category=dpg.mvThemeCat_Core)
                
                #set style
                dpg.add_theme_style(dpg.mvStyleVar_FrameBorderSize, 1, category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 5, category=dpg.mvThemeCat_Core)

            with dpg.theme_component(dpg.mvChildWindow):
                #dpg.add_theme_color(dpg.mvThemeCol_Border, (40, 1, 56), category=dpg.mvThemeCat_Core)
                pass
            #Buttons
            with dpg.theme_component(dpg.mvButton):
                #color
                dpg.add_theme_color(dpg.mvThemeCol_Button, (92, 9, 33), category=dpg.mvThemeCat_Core)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (92, 9, 33), category=dpg.mvThemeCat_Core)

                #style
                dpg.add_theme_style(dpg.mvStyleVar_FrameBorderSize, 0, category=dpg.mvThemeCat_Core)
            

            

            with dpg.theme_component(dpg.mvSliderInt):
                
                dpg.add_theme_color(dpg.mvThemeCol_SliderGrab, (92, 9, 33), category=dpg.mvThemeCat_Core)
                dpg.add_theme_color(dpg.mvThemeCol_SliderGrabActive, (0,0,0,0), category=dpg.mvThemeCat_Core)
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 12)  # Rounded slider edges

                dpg.add_theme_style(dpg.mvStyleVar_GrabRounding, 12)  # Rounding for the thumb
                dpg.add_theme_style(dpg.mvStyleVar_GrabMinSize, 20)   # Size adjustment for a larger, rounded thumb

        dpg.bind_theme(global_theme)

        #dpg.show_style_editor()
        #dpg.show_font_manager()

        dpg.create_viewport(title="Chess", width=self.min_width, height=self.min_height)
        dpg.setup_dearpygui()
        dpg.set_primary_window("Primary Window", True)
        dpg.set_exit_callback(self.on_close_listener)
        dpg.show_viewport()
        dpg.start_dearpygui()
        dpg.destroy_context()

       

#Methods

    def togle_fish(self):
        #disable the stockfish settings view
        if self.stockfish_settings_toggled is True:
            dpg.configure_item(2, show=False)
            dpg.set_viewport_width(self.min_width)
            self.stockfish_settings_toggled = False
            dpg.configure_item("toggle next", direction = 1)
            

        else:
            #togle the stockfish settings view
            dpg.configure_item(2, show=True)
            dpg.set_viewport_width(self.max_width)
            self.stockfish_settings_toggled = True
            dpg.configure_item("toggle next", direction = 0)

    def on_close_listener(self):
        # Set self.exit to True so that the threads will stop
        self.exit = True
    

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
                    dpg.configure_item("start", label = "open Browser", enabled = True)

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
                        if data == "START":
                        # Update the run button
                            dpg.configure_item("start", label = "Stop", callback = self.on_stop_button_listener, enabled = True)

                    elif data == "STOP":
                        self.on_stop_button_listener()

                    elif data == "playeriswhite":
                        self.is_white = True
                        #self.eval_bar.configure(fg_color = "black")
                        #self.eval_bar.configure(progress_color = "white")
                    
                    elif data == "playerisblack":
                        self.is_white = False

                        #self.eval_bar.configure(fg_color = "white")
                        #self.eval_bar.configure(progress_color = "black")
                    
                    
                        
                    elif data[:4] == "eval":
                        
                        if data[:5] == "evalm":
                            eval = 'M in\n' + data[5:]
                            dpg.set_value("eval text", str(eval))


                        elif data[:5] == "evalp":
                            eval = data[5:]
                            eval_float = float(eval)/1000
                                
                            dpg.set_value("eval", 0.5 + eval_float/2)
                                    
                            dpg.set_value("eval text", str(eval_float))
                        
                            
                    elif data[:7] == "RESTART":
                        self.restart_after_stopping = True
                        self.stockfish_bot_pipe.send("DELETE")
                        
                        '''
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
                            '''
    
                    elif data[:7] == "ERR_EXE":
                        message = "Stockfish path provided is not valid!"
                        self.popup(message, self.errors[1])
                        
                    elif data[:8] == "ERR_PERM":
                            message="Stockfish path provided is not executable!"
                            self.popup(message, self.errors[1])
                    elif data[:9] == "ERR_BOARD":
                        message="Cant find board!"
                        self.popup(message, self.errors[1])
                    elif data[:9] == "ERR_COLOR":
                        message="Cant find player color!"
                        self.popup(message, self.errors[1])
                    elif data[:9] == "ERR_MOVES":
                        message="Cant find moves list!"
                        self.popup(message, self.errors[1])
                    elif data[:12] == "ERR_GAMEOVER":
                        message="Game has already finished!"
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
        # Set Opening Browser button state to opening
        self.opening_browser = True
        dpg.configure_item("open browser", enabled = False, label = "Opening")
        
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
            #self.opening_browser = False
            #self.open_browser_button.configure(text = "Open Browser")
            #self.open_browser_button.configure(state = "enabled")
            '''
            CTkMessagebox.CTkMessagebox(
                title = "Error",
                message = "Cant find Chrome. You need to have Chrome installed for this to work.",
            )
            '''
            self.opening_browser = False
            dpg.configure_item("open browser", label = "open browser", enabled = True)
            #popup
            message = "chrome no found"
            self.popup(message, self.errors[3])
            return

        # Open chess.com
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
                #Cookies not saved error
                message = "Cookies not saved error"
                self.popup(message, self.errors[3])

            except InvalidCookieDomainException:
                message = "Unnable to load cookies"
                self.popup(message, self.errors[3])

            except UnableToSetCookieException:
                message = "Unnable to load cookies"
                self.popup(message, self.errors[3])
            

        # Build Stockfish Bot
        self.chrome_url = self.chrome.service.service_url
        self.chrome_session_id = self.chrome.session_id

        # Set Opening Browser button state to opened
        self.opening_browser = False
        self.opened_browser = True
        dpg.configure_item("open browser", label = "Browser is opened", enabled = True)

        # Enable run button
        dpg.configure_item("start", enabled = True)
         

    def on_start_button_listener(self):

        dpg.configure_item("start", label = "Starting...", enabled = False, )

        # Check if stockfish path is  empty
        if self.stockfish_path == "":
            #CTkMessagebox.CTkMessagebox(
            #    title="Error",
             #   message="Stockfish path is empty"
            #)
            return
        '''
        # Check if mouseless mode is enabled when on chess.com
        if self.enable_mouseless_mode.get() == 1 and self.website.get() == "chesscom":
            CTkMessagebox.CTkMessagebox(
                "Error", "Mouseless mode is only supported on lichess.org"
            )
            return
        '''

        # Create the pipes used for the communication
        # between the GUI and the Stockfish Bot process
        parent_conn, child_conn = multiprocess.Pipe()
        self.stockfish_bot_pipe = parent_conn

        # Create the message queue that is used for the communication
        # between the Stockfish and the Overlay processes
        st_ov_queue = multiprocess.Queue()
        
        params = {
                "Threads": dpg.get_value("threads"),
                "Hash": dpg.get_value("hash"),
                "Skill Level": dpg.get_value("skill level"),
                "Move Overhead": dpg.get_value("move overhead"),
                "UCI_LimitStrength": "false",
            }
        if  dpg.get_value("timer") == True:
            timer = (dpg.get_value("min timer"), dpg.get_value("max timer"))
        else:
            timer = None
        # Create the Stockfish Bot process
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
            self.move_to_play
        )
        self.stockfish_bot_process.start()

        # Create the overlay
        self.overlay_screen_process = multiprocess.Process(
            target=run, args=(st_ov_queue, self.move_colors)
        )
        self.overlay_screen_process.start()

        # Update the run button
        self.running = True
        dpg.configure_item("start", label = "Stop", enabled = True, callback = self.on_stop_button_listener)
        dpg.configure_item("status",  default_value = "Active", color = (0,255,0))

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
        # Update the run button
        dpg.configure_item("start", label = "Start", enabled = True, callback = self.on_start_button_listener)
        dpg.configure_item("status",  default_value = "Inactive", color = (255,0,0))

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

    #Custom methods
    
    def on_save_cookies_button_listener(self):
        pickle.dump(self.chrome.get_cookies(), open("cookies.pkl", "wb"))

    def on_website_choice(self, sender, app_data, user_data):
        self.website = app_data
        print("gggggg", app_data, "ggggggggggg")

    def on_color_edit(self, sender, app_data, user_data):

        alpha = 122

        color = [int(i) for i in dpg.get_value(sender)[:3]]
        color.append(alpha)

        self.move_colors[sender.split(" ")[1]] = color
        print(self.move_colors)

    def on_move_selected(self, sender, app_data, user_data):
        if app_data == "Best Move":
            rank = "1"
        elif app_data == "2nd Best Move":
            rank = "2"                           
        elif app_data == "3rd Best Move":
            rank = "3"

        self.move_to_play = int(rank)

    def popup(self, message, level):
        dpg.configure_item("modal", show = True)
        dpg.configure_item("modal text", default_value = message)
        if level == self.errors[1]:
            dpg.configure_item("open browser", enabled = True, label = "Open Browser")
            dpg.configure_item("start", label = "start", callback = self.on_start_button_listener, enabled = True)
        
    
if __name__ == "__main__":
    ChessApp()
