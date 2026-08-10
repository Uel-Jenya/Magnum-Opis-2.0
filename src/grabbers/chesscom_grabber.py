import re

from selenium.common import NoSuchElementException
from selenium.webdriver.common.by import By

from grabbers.grabber import Grabber


class ChesscomGrabber(Grabber):
    def __init__(self, chrome_url, chrome_session_id):
        super().__init__(chrome_url, chrome_session_id)
        self.moves_list = {}

    def update_board_elem(self):
        try:
            self._board_elem = self.chrome.find_element(By.XPATH, "//*[@id='board-play-computer']")
        except NoSuchElementException:
            try:
                self._board_elem = self.chrome.find_element(By.XPATH, "//*[@id='board-single']")
            except NoSuchElementException:
                self._board_elem = None

    def is_white(self):
        # Find the square names list
        square_names = None
        try:
            coordinates = self.chrome.find_element(By.XPATH, "//*[@id='board-play-computer']//*[name()='svg']")
            square_names = coordinates.find_elements(By.XPATH, ".//*")
        except NoSuchElementException:
            try:
                coordinates = self.chrome.find_elements(By.XPATH, "//*[@id='board-single']//*[name()='svg']")
                coordinates = [x for x in coordinates if x.get_attribute("class") == "coordinates"][0]
                square_names = coordinates.find_elements(By.XPATH, ".//*")
            except NoSuchElementException:
                return None

        # Find the square with the smallest x and biggest y values (bottom left number)
        elem = None
        min_x = None
        max_y = None
        for i in range(len(square_names)):
            name_element = square_names[i]
            x = float(name_element.get_attribute("x"))
            y = float(name_element.get_attribute("y"))

            if i == 0 or (x <= min_x and y >= max_y):
                min_x = x
                max_y = y
                elem = name_element

        # Use this square to determine whether the player is white or black
        num = elem.text
        return num == "1"

    def is_game_over(self):
        try:
            # Find the game over window
            game_over_window = self.chrome.find_element(By.CLASS_NAME, "game-over-modal-container")
            return game_over_window is not None
        except NoSuchElementException:
            # Return False since the game over window is not found
            return False

    def get_move_list(self):
        # Fetch the entire list in one browser round trip.  The former version
        # made several Selenium calls for every ply (element lookup, class,
        # nested lookup, figurine and text), which is the dominant delay as a
        # game gets longer.
        moves = self.chrome.execute_script("""
            const list = document.querySelector(
                '.play-controller-scrollable, .chessboard-pkg-move-list-component');
            if (!list) return null;
            return [...list.querySelectorAll('.main-line-ply')]
                .filter(move => /(?:white|black)-move/.test(move.className))
                .map(move => ({
                    text: move.innerText,
                    figure: move.querySelector('[data-figurine]')?.getAttribute('data-figurine')
                }));
        """)
        if moves is None:
            return None

        current_moves = []
        for move in moves:
            # innerText includes display whitespace around Chess.com's piece
            # icons (for example, "N f6").  SAN cannot contain it.
            text = re.sub(r"\s+", "", move["text"] or "")
            figure = move["figure"]
            if figure is None:
                current_moves.append(text)
                continue

            # Some page variants include the figurine in innerText while
            # others expose it only through data-figurine.  Never add it
            # twice.
            formatted = text if text.startswith(figure) else figure + text
            if "+" in formatted:
                formatted = formatted.replace("+", "") + "+"
            current_moves.append(formatted)
        return current_moves

    def is_game_puzzles(self):
        return False

    def click_puzzle_next(self):
        pass

    def make_mouseless_move(self, move, move_count):
        pass
