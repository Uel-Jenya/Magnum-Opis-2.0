import random
import threading
import multiprocess
import pyautogui
import time
import sys
import os
import chess
import re
from grabbers.chesscom_grabber import ChesscomGrabber
from grabbers.lichess_grabber import LichessGrabber
from utilities import char_to_num
from threading import Timer
from selenium.common.exceptions import NoSuchWindowException

import chess.engine

class StockfishBot(multiprocess.Process):
    def __init__(self, chrome_url, chrome_session_id, website, pipe, overlay_queue, stockfish_path, 
                 enable_manual_mode, enable_mouseless_mode, enable_non_stop_puzzles, bongcloud, 
                 stockfish_depth, stockfish_parameters,  timer_interval, move_to_play = 1):
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
        self.timer_running = False
        self.analysis_depth = 15
        self.play_depth = stockfish_depth
        self.move_to_play = move_to_play
        if timer_interval != None:
            self.timer_min = timer_interval[0]
            self.timer_max = timer_interval[1]
        else:
            self.timer_min = None
            self.timer_max = None

        
      

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


    def make_move(self, move):  # sourcery skip: extract-method
        while True:
            if self.timer_running == False:
                
                # Get the start and end position screen coordinates
                start_pos, end_pos = self.get_move_pos(move)

                # Drag the piece from the start to the end position
                pyautogui.moveTo(start_pos[0], start_pos[1])
                pyautogui.dragTo(end_pos[0], end_pos[1])

                # Check for promotion. If there is a promotion,
                # promote to the corresponding piece type
                if len(move) == 5:
                    time.sleep(0.1)
                    end_pos_x = None
                    end_pos_y = None
                    if move[4] == "n":
                        end_pos_x, end_pos_y = self.move_to_screen_pos(move[2] + str(int(move[3]) - 1))
                    elif move[4] == "r":
                        end_pos_x, end_pos_y = self.move_to_screen_pos(move[2] + str(int(move[3]) - 2))
                    elif move[4] == "b":
                        end_pos_x, end_pos_y = self.move_to_screen_pos(move[2] + str(int(move[3]) - 3))

                    pyautogui.moveTo(x=end_pos_x, y=end_pos_y)
                    pyautogui.click(button='left')
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
            print(self.current_url)


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

                    # Update Stockfish with the starting position
                    #stockfish.set_position(move_list_uci)
                    
                    score = engine.analyse(board, chess.engine.Limit(depth=self.analysis_depth), multipv=1)[0]['score']
                    if score.is_mate():
                        eval = score.white().mate()
                        self.pipe.send("evalm" + str(eval))

                    else:
                        eval = score.white().score()
                        self.pipe.send("evalp" + str(eval))

                    # Notify GUI that bot is ready                    self.pipe.send("START")

                    # Send the first moves to the GUI (if there are any)
                    if len(move_list) > 0:
                        self.pipe.send("M_MOVE" + ",".join(move_list))

                    # Start the game loop
                    while True:

                       
                        print(self.move_to_play)
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
                                        move = engine.analyse(board,chess.engine.Limit(depth=self.play_depth), multipv=self.move_to_play)[self.move_to_play - 1]["pv"][0].uci()
                                    except IndexError:
                                        move = engine.analyse(board,chess.engine.Limit(depth=self.play_depth), multipv=self.move_to_play)[-1]["pv"][0].uci()

                            else:
                                if not self.enable_manual_mode:
                                    try:
                                        move = engine.analyse(board,chess.engine.Limit(depth=self.play_depth), multipv=self.move_to_play)[self.move_to_play - 1]["pv"][0].uci()
                                    except IndexError:
                                        move = engine.analyse(board,chess.engine.Limit(depth=self.play_depth), multipv=self.move_to_play)[-1]["pv"][0].uci()

                            # Wait for keypress or player movement if in manual mode
                                else:
                                    moves = []
                                    top_3_moves = engine.analyse(board,chess.engine.Limit(depth=self.play_depth), multipv=3)
                                    
                                    for i in range(len(top_3_moves)):
                                        
                                        cmove =top_3_moves[i]["pv"][0].uci()
                                        move_start_pos, move_end_pos = self.get_move_pos(cmove)
                                        
                                        '''try:
                                            if mate != None:
                                                rank = 1
                                            else:
                                                if self.is_white == True:
                                                    if i == 2:
                                                        if centipawn >= top_3_moves[i - 1]['Centipawn'] and centipawn >= top_3_moves[i - 2]['Centipawn']:
                                                            rank = 1
                                                        
                                                        elif (centipawn <= top_3_moves[i - 1]['Centipawn'] and centipawn >= top_3_moves[i - 2]['Centipawn']) or (centipawn >= top_3_moves[i - 2]['Centipawn'] and centipawn <= top_3_moves[i -2]['Centipawn']):                          
                                                            rank = 2
                                                            
                                                        elif centipawn <= top_3_moves[i - 1]['Centipawn'] and centipawn <= top_3_moves[i - 2]['Centipawn']:
                                                            rank = 3
                                                            
                                                        moves.append({
                                                            #'Centipawn': float(centipawn),
                                                            #'Mate': mate,
                                                            'position': ((int(move_start_pos[0]), int(move_start_pos[1])), (int(move_end_pos[0]), int(move_end_pos[1]))),
                                                            'rank': rank
                                                        })
                                                        
                                                        break
                                                    
                                                    if centipawn >= top_3_moves[i - 1]['Centipawn'] and centipawn >= top_3_moves[i + 1]['Centipawn']:
                                                        rank = 1
                                                        
                                                    elif (centipawn <= top_3_moves[i - 1]['Centipawn'] and centipawn >= top_3_moves[i + 1]['Centipawn']) or (centipawn >= top_3_moves[i - 1]['Centipawn'] and centipawn <= top_3_moves[i + 1]['Centipawn']):                          
                                                        rank = 2
                                                        
                                                    elif centipawn <= top_3_moves[i - 1]['Centipawn'] and centipawn <= top_3_moves[i + 1]['Centipawn']:
                                                        rank = 3
                                                    
                                                else:
                                                    if i == 2:
                                                        if centipawn >= top_3_moves[i - 1]['Centipawn'] and centipawn >= top_3_moves[i - 2]['Centipawn']:
                                                            rank = 3
                                                        
                                                        elif (centipawn <= top_3_moves[i - 1]['Centipawn'] and centipawn >= top_3_moves[i - 2]['Centipawn']) or (centipawn >= top_3_moves[i - 2]['Centipawn'] and centipawn <= top_3_moves[i -2]['Centipawn']):                          
                                                            rank = 2
                                                            
                                                        elif centipawn <= top_3_moves[i - 1]['Centipawn'] and centipawn <= top_3_moves[i - 2]['Centipawn']:
                                                            rank = 1
                                                            
                                                        moves.append({
                                                            #'Centipawn': float(centipawn),
                                                            #'Mate': mate,
                                                            'position': ((int(move_start_pos[0]), int(move_start_pos[1])), (int(move_end_pos[0]), int(move_end_pos[1]))),
                                                            'rank': rank
                                                        })
                                                        
                                                        break
                                                    
                                                    if centipawn >= top_3_moves[i - 1]['Centipawn'] and centipawn >= top_3_moves[i + 1]['Centipawn']:
                                                        rank = 3
                                                        
                                                    elif (centipawn <= top_3_moves[i - 1]['Centipawn'] and centipawn >= top_3_moves[i + 1]['Centipawn']) or (centipawn >= top_3_moves[i - 1]['Centipawn'] and centipawn <= top_3_moves[i + 1]['Centipawn']):                          
                                                        rank = 2
                                                        
                                                    elif centipawn <= top_3_moves[i - 1]['Centipawn'] and centipawn <= top_3_moves[i + 1]['Centipawn']:
                                                        rank = 1
                                                '''
                                        moves.append({
                                            #'Centipawn': float(centipawn),
                                            #'Mate': mate,
                                            'position': ((int(move_start_pos[0]), int(move_start_pos[1])), (int(move_end_pos[0]), int(move_end_pos[1]))),
                                            #'rank': rank
                                        })
                                        '''except TypeError as e:
                                            print(e)
                                            print(mate)
                                            print(centipawn)
                                            '''
                                    self.overlay_queue.put(moves)
                                    while True:
                                        
                                        if len(move_list) != len(self.grabber.get_move_list()):
                                            self_moved = True
                                            move_list = self.grabber.get_move_list()
                                            move_san = move_list[-1]
                                            move = board.parse_san(move_san).uci()
                                            board.push_uci(move)
                                            #stockfish.make_moves_from_current_position([move])
                                            break

                            if not self_moved:
                                move_san = board.san(chess.Move(chess.parse_square(move[0:2]), chess.parse_square(move[2:4])))
                                board.push_uci(move)
                                #stockfish.make_moves_from_current_position([move])
                                move_list.append(move_san)
                                if self.enable_mouseless_mode and not self.grabber.is_game_puzzles():
                                    self.grabber.make_mouseless_move(move, move_count + 1)
                                    
                                else:
                                    self.make_move(move)

                            self.overlay_queue.put([])
                            #get eval
                            score = engine.analyse(board, chess.engine.Limit(depth=self.analysis_depth), multipv=1)[0]['score']
                            if score.is_mate():
                                eval = score.white().mate()
                                self.pipe.send("evalm" + str(eval))

                            else:
                                eval = score.white().score()
                                self.pipe.send("evalp" + str(eval))
                                
                            # Send the move to the GUI
                            self.pipe.send("S_MOVE" + move_san)

                            # Check if the game is over
                            if board.is_checkmate():
                                print()
                                # Send restart message to GUI
                                if self.enable_non_stop_puzzles and self.grabber.is_game_puzzles():
                                    self.grabber.click_puzzle_next()
                                    self.pipe.send("RESTART")
                                    self.wait_for_gui_to_delete()

                                elif self.grabber.is_game_over():
                                    # Send stop message to GUI
                                    self.pipe.send("STOP")
                                #self.wait_for_gui_to_delete()
                            
                                return

                            time.sleep(0.1)

                        else:
                            if len(move_list) <= 0:
                                move_list = self.grabber.get_move_list()

                                for move in move_list:
                                    board.push_san(move)
                                continue
                            else:
                                break
                        # Wait for a response from the opponent
                        # by finding the differences between
                        # the previous and current position
                        previous_move_list = move_list.copy()
                        while True:
                            if self.grabber.is_game_over():
                                # Send restart message to GUI
                                if self.enable_non_stop_puzzles and self.grabber.is_game_puzzles():
                                    self.grabber.click_puzzle_next()
                                    self.pipe.send("RESTART")
                                    #self.wait_for_gui_to_delete()
                                
                                elif self.grabber.is_game_over():
                                    # Send stop message to GUI
                                    self.pipe.send("STOP")
                                return
                            move_list = self.grabber.get_move_list()
                            if move_list is None:
                                return
                            if len(move_list) > len(previous_move_list):
                                
                                break

                        # Get the move that the opponent made
                        move = move_list[-1]
                        #self.pipe.send("S_MOVE" + move)
                        board.push_san(move)
                        #stockfish.make_moves_from_current_position([str(board.peek())])
                        if board.is_checkmate():
                            # Send restart message to GUI
                            if self.enable_non_stop_puzzles and self.grabber.is_game_puzzles():
                                self.grabber.click_puzzle_next()
                                self.pipe.send("RESTART")
                                #self.wait_for_gui_to_delete()

                            elif self.grabber.is_game_over():
                                    # Send stop message to GUI
                                    self.pipe.send("STOP")

                            return

                        score = engine.analyse(board, chess.engine.Limit(depth=self.analysis_depth), multipv=1)[0]['score']
                        if score.is_mate():
                            eval = score.white().mate()
                            self.pipe.send("evalm" + str(eval))

                        else:
                            eval = score.white().score()
                            self.pipe.send("evalp" + str(eval))

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