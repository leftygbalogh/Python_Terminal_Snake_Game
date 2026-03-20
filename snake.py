#!/usr/bin/env python3
import csv
import curses
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from shutil import get_terminal_size

MIN_WIDTH = 11
MIN_HEIGHT = 11
SNAKE_ART = ".oOOO(:)="
APPLE_CHAR = "*"
START_MESSAGE = "Press any key to start."
RESIZE_MESSAGE = "Window is too small for the game. Please resize it before you can play."
LEADERBOARD_FILE = Path("leaderboard.csv")
LOG_FILE = Path("snake.log")
TICK_SECONDS = 0.12

UP = (0, -1)
DOWN = (0, 1)
LEFT = (-1, 0)
RIGHT = (1, 0)
DIRECTIONS = [UP, DOWN, LEFT, RIGHT]

KEY_TO_DIR = {
    curses.KEY_UP: UP,
    curses.KEY_DOWN: DOWN,
    curses.KEY_LEFT: LEFT,
    curses.KEY_RIGHT: RIGHT,
}


@dataclass
class EndState:
    score: int
    won: bool


class SizeError(Exception):
    def __init__(self, width: int, height: int, reason: str):
        super().__init__(reason)
        self.width = width
        self.height = height
        self.reason = reason


def log_size_crash(width: int, height: int, reason: str) -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with LOG_FILE.open("a", encoding="ascii") as fh:
        fh.write(f"{timestamp},width={width},height={height},reason={reason}\n")


def startup_size_check() -> tuple[int, int]:
    size = get_terminal_size()
    width = size.columns
    height = size.lines
    if width < MIN_WIDTH or height < MIN_HEIGHT:
        reason = f"startup terminal too small (min {MIN_WIDTH}x{MIN_HEIGHT})"
        print(RESIZE_MESSAGE)
        log_size_crash(width, height, reason)
        raise SystemExit(1)
    return width, height


def in_bounds(x: int, y: int, width: int, height: int) -> bool:
    return 0 <= x < width and 0 <= y < height


def initial_snake(center_x: int, center_y: int) -> list[tuple[int, int]]:
    # Head-first contiguous path of length 9 that keeps the head at center.
    offsets = [
        (0, 0),
        (-1, 0),
        (-2, 0),
        (-3, 0),
        (-3, -1),
        (-3, -2),
        (-2, -2),
        (-1, -2),
        (0, -2),
    ]
    return [(center_x + dx, center_y + dy) for dx, dy in offsets]


def random_start_direction(snake: list[tuple[int, int]], width: int, height: int) -> tuple[int, int]:
    head_x, head_y = snake[0]
    occupied = set(snake[1:])
    valid = []
    for dx, dy in DIRECTIONS:
        nx, ny = head_x + dx, head_y + dy
        if in_bounds(nx, ny, width, height) and (nx, ny) not in occupied:
            valid.append((dx, dy))
    return random.choice(valid)


def place_apple(snake: list[tuple[int, int]], width: int, height: int) -> tuple[int, int] | None:
    occupied = set(snake)
    empties = [
        (x, y)
        for y in range(height)
        for x in range(width)
        if (x, y) not in occupied
    ]
    if not empties:
        return None
    return random.choice(empties)


_NECK = ["=", ")", "("]  # chars anchored right behind the head (index 1, 2, 3)
_TAIL = ["o", "."]       # chars anchored at the tail tip (index total-1, total-2)


def segment_char(index: int, total: int) -> str:
    if index == 0:
        return ":"
    tail_pos = total - 1 - index   # 0 = tail tip
    if tail_pos < len(_TAIL):
        return _TAIL[tail_pos]
    neck_pos = index - 1           # 0 = right behind head
    if neck_pos < len(_NECK):
        return _NECK[neck_pos]
    return "O"


def draw(stdscr: curses.window, snake: list[tuple[int, int]], apple: tuple[int, int]) -> None:
    stdscr.erase()
    ax, ay = apple
    try:
        stdscr.addch(ay, ax, APPLE_CHAR)
    except curses.error:
        pass
    total = len(snake)
    for i, (x, y) in enumerate(snake):
        try:
            stdscr.addch(y, x, segment_char(i, total))
        except curses.error:
            pass
    stdscr.refresh()


def load_leaderboard() -> list[tuple[str, int]]:
    if not LEADERBOARD_FILE.exists():
        return []
    entries: list[tuple[str, int]] = []
    with LEADERBOARD_FILE.open("r", encoding="ascii", newline="") as fh:
        reader = csv.reader(fh)
        for row in reader:
            if len(row) != 2:
                continue
            name = row[0][:5]
            try:
                score = int(row[1])
            except ValueError:
                continue
            entries.append((name, score))
    return entries[:10]


def save_leaderboard(entries: list[tuple[str, int]]) -> None:
    with LEADERBOARD_FILE.open("w", encoding="ascii", newline="") as fh:
        writer = csv.writer(fh)
        for name, score in entries[:10]:
            writer.writerow([name[:5], score])


def run_game(stdscr: curses.window, fixed_width: int, fixed_height: int) -> EndState:
    curses.curs_set(0)
    stdscr.keypad(True)

    center_x = fixed_width // 2
    center_y = fixed_height // 2
    snake = initial_snake(center_x, center_y)
    direction = random_start_direction(snake, fixed_width, fixed_height)
    apple = place_apple(snake, fixed_width, fixed_height)
    if apple is None:
        return EndState(score=0, won=True)

    # Pre-start: show board and wait for any key
    stdscr.nodelay(False)
    while True:
        h, w = stdscr.getmaxyx()
        if w < fixed_width or h < fixed_height:
            raise SizeError(w, h, "runtime resize too small for fixed board")
        draw(stdscr, snake, apple)
        msg_x = max(0, (fixed_width - len(START_MESSAGE)) // 2)
        msg_y = fixed_height // 2
        try:
            stdscr.addstr(msg_y, msg_x, START_MESSAGE)
        except curses.error:
            pass
        stdscr.refresh()
        key = stdscr.getch()
        if key == curses.KEY_RESIZE:
            h, w = stdscr.getmaxyx()
            if w < fixed_width or h < fixed_height:
                raise SizeError(w, h, "runtime resize too small for fixed board")
            continue
        break

    stdscr.nodelay(True)
    score = 0

    while True:
        h, w = stdscr.getmaxyx()
        if w < fixed_width or h < fixed_height:
            raise SizeError(w, h, "runtime resize too small for fixed board")

        key = stdscr.getch()
        if key in KEY_TO_DIR:
            direction = KEY_TO_DIR[key]
        elif key == curses.KEY_RESIZE:
            h, w = stdscr.getmaxyx()
            if w < fixed_width or h < fixed_height:
                raise SizeError(w, h, "runtime resize too small for fixed board")

        head_x, head_y = snake[0]
        dx, dy = direction
        new_head = (head_x + dx, head_y + dy)

        if not in_bounds(new_head[0], new_head[1], fixed_width, fixed_height):
            return EndState(score=score, won=False)
        if new_head in set(snake):
            return EndState(score=score, won=False)

        if new_head == apple:
            score += 1
            snake = [new_head, snake[0]] + snake[1:]
            if len(snake) == fixed_width * fixed_height:
                return EndState(score=score, won=True)
            apple = place_apple(snake, fixed_width, fixed_height)
            if apple is None:
                return EndState(score=score, won=True)
        else:
            snake = [new_head] + snake[:-1]

        draw(stdscr, snake, apple)
        time.sleep(TICK_SECONDS)


def main() -> None:
    fixed_width, fixed_height = startup_size_check()

    try:
        end_state = curses.wrapper(run_game, fixed_width, fixed_height)
    except SizeError as err:
        print(RESIZE_MESSAGE)
        log_size_crash(err.width, err.height, err.reason)
        raise SystemExit(1)

    text = "Congratulations!"
    border = "+" + "-" * (len(text) + 2) + "+"
    print(border)
    print(f"| {text} |")
    print(border)

    leaderboard = load_leaderboard()
    previous_high = leaderboard[0][1] if leaderboard else 0
    if end_state.score > previous_high:
        name = input("Enter your name (max 5 chars): ")[:5]
        leaderboard = [(name, end_state.score)] + leaderboard
        leaderboard = leaderboard[:10]
        save_leaderboard(leaderboard)
        print("Leaderboard")
        for idx, (n, s) in enumerate(leaderboard, 1):
            print(f"{idx}. {n},{s}")


if __name__ == "__main__":
    main()
