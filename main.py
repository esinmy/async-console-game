import asyncio
import curses
import itertools
import os
import random
import time
from curses_tools import draw_frame, read_controls, get_frame_size
from physics import update_speed
from obstacles import Obstacle
from explosion import explode
from game_scenario import PHRASES, get_garbage_delay_tics

TIC_TIMEOUT = 0.1
YEAR_CHANGE_SEC = 1.5
DIM_SEC = 2
BOLD_SEC = 1
STD_SEC = 0.3

YEAR_GUN_ON = 2020

BORDER = 1
STAR_SYM = '+*.:'
FRAME_FOLDERS = {"rocket": r"./frames/rocket/",
                 "garbage": r"./frames/garbage/",
                 }
GAMEOVER_FRAME = r"./frames/misc/game_over.txt"

coroutines = []
obstacles = []
obstacles_in_last_collisions = []
spaceship_frame = None
year = 1957


def read_text_file(path):
    with open(path, "r") as my_file:
        content = my_file.read()
    return content


def get_frames():
    frames = {}
    for frame_type, folder in FRAME_FOLDERS.items():
        files = os.listdir(folder)
        frames[frame_type] = [read_text_file(os.path.join(folder, frame)) for frame in files]
    return frames


def get_canvas_max_coords(canvas):
    """Get row's and column's maximum of the canvas.

    Curses getmaxyx() function returns height and width of the canvas.
    Subtract 1 to get row's and column's maximum.

    """

    row_max, col_max = canvas.getmaxyx()
    row_max = row_max - 1
    col_max = col_max - 1
    return row_max, col_max


def get_sub_canvases(canvas):
    rows, cols = canvas.getmaxyx()

    info_hight = 3
    info_canvas = canvas.derwin(info_hight, cols, rows - info_hight, 0)
    game_canvas = canvas.derwin(rows - info_hight, cols, 0, 0)

    return info_canvas, game_canvas


def get_star_coroutines(canvas, row_max, col_max, star_num=50):
    for _ in range(star_num):
        row = random.randint(BORDER, row_max - BORDER)
        col = random.randint(BORDER, col_max - BORDER)
        mode = random.randint(1, 4)
        symbol = random.choice(STAR_SYM)
        coroutines.append(blink(canvas, row, col, mode, symbol))
    return coroutines


async def blink(canvas, row, column, mode, symbol='*'):
    dim_tics = int(DIM_SEC // TIC_TIMEOUT)
    bold_tics = int(BOLD_SEC // TIC_TIMEOUT)
    std_ticks = int(STD_SEC // TIC_TIMEOUT)
    while True:
        if mode == 1:
            canvas.addstr(row, column, symbol, curses.A_DIM)
            await sleep(dim_tics)
            mode += 1

        if mode == 2:
            canvas.addstr(row, column, symbol)
            await sleep(std_ticks)
            mode += 1

        if mode == 3:
            canvas.addstr(row, column, symbol, curses.A_BOLD)
            await sleep(bold_tics)
            mode += 1

        if mode == 4:
            canvas.addstr(row, column, symbol)
            await sleep(std_ticks)
            mode = 1


async def fill_orbit_with_garbage(canvas, col_max, frames):
    while True:
        delay = get_garbage_delay_tics(year)
        if delay is None:
            await sleep()
            continue
        frame = random.choice(frames)
        row_max_f, col_max_f = get_frame_size(frame)
        col = random.randint(BORDER, col_max - col_max_f)
        garbage = fly_garbage(canvas, col, frame)
        coroutines.append(garbage)
        await sleep(delay)


async def fly_garbage(canvas, column, garbage_frame, speed=0.5):
    """Animate garbage, flying from top to bottom. Сolumn position will stay same, as specified on start."""
    rows_number, columns_number = canvas.getmaxyx()
    row_max_f, col_max_f = get_frame_size(garbage_frame)

    column = max(column, 0)
    column = min(column, columns_number - 1)

    row = 0
    obstacle = Obstacle(0, column, row_max_f, col_max_f)
    obstacles.append(obstacle)
    try:
        while row < rows_number:
            draw_frame(canvas, row, column, garbage_frame)
            await sleep()
            draw_frame(canvas, row, column, garbage_frame, negative=True)
            row += speed
            obstacle.row = row
            if obstacle in obstacles_in_last_collisions:
                await explode(canvas, row + row_max_f // 2, column + col_max_f // 2)
                obstacles_in_last_collisions.remove(obstacle)
                break
    finally:
        obstacles.remove(obstacle)


async def animate_spaceship(frames):
    global spaceship_frame
    for frame in itertools.cycle(frames):
        spaceship_frame = frame
        await sleep()


async def run_spaceship(canvas, frames):
    row_max_f, col_max_f = get_frame_size(frames[0])
    row_max, col_max = get_canvas_max_coords(canvas)
    row = row_max - row_max_f // 2
    col = col_max // 2 - col_max_f // 2
    row_speed = col_speed = 0
    cur_frame = None

    while True:
        for obstacle in obstacles:
            if obstacle.has_collision(row, col):
                draw_frame(canvas, row, col, cur_frame, negative=True)
                await show_gameover(canvas)

        row_change, col_change, shot_made = read_controls(canvas)

        if shot_made and year >= YEAR_GUN_ON:
            fire = animate_fire(canvas, row, col + col_max_f // 2)
            coroutines.append(fire)

        row_speed, col_speed = update_speed(row_speed, col_speed, row_change, col_change)

        row += row_speed
        col += col_speed
        row = min(row, row_max - row_max_f)
        col = min(col, col_max - col_max_f)
        row = max(row, BORDER)
        col = max(col, BORDER)

        draw_frame(canvas, row, col, spaceship_frame)
        cur_frame = spaceship_frame
        await sleep()
        draw_frame(canvas, row, col, cur_frame, negative=True)


async def animate_fire(canvas, start_row, start_column, rows_speed=-0.3, columns_speed=0):
    """Display animation of gun shot. Direction and speed can be specified."""

    row, column = start_row, start_column

    canvas.addstr(round(row), round(column), '*')
    await sleep()

    canvas.addstr(round(row), round(column), 'O')
    await sleep()
    canvas.addstr(round(row), round(column), ' ')

    row += rows_speed
    column += columns_speed

    symbol = '-' if columns_speed else '|'

    rows, columns = canvas.getmaxyx()
    max_row, max_column = rows - 1, columns - 1

    curses.beep()

    while 1 < row < max_row and 0 < column < max_column:
        for obstacle in obstacles:
            if obstacle.has_collision(row, column):
                obstacles_in_last_collisions.append(obstacle)
                return
        canvas.addstr(round(row), round(column), symbol)
        await sleep()
        canvas.addstr(round(row), round(column), ' ')
        row += rows_speed
        column += columns_speed


async def show_gameover(canvas):
    frame = read_text_file(GAMEOVER_FRAME)
    row_max_f, col_max_f = get_frame_size(frame)
    row_max, col_max = get_canvas_max_coords(canvas)
    row = row_max // 2 - row_max_f // 2
    col = col_max // 2 - col_max_f // 2
    while True:
        draw_frame(canvas, row, col, frame)
        await sleep()


async def show_year(canvas):
    global year
    year_ticks = int(YEAR_CHANGE_SEC // TIC_TIMEOUT)
    while True:
        frame = f"{year} {PHRASES.get(year, '')}"
        row_max_f, col_max_f = get_frame_size(frame)
        row_max, col_max = get_canvas_max_coords(canvas)
        row = row_max - row_max_f
        col = col_max // 2 - col_max_f // 2
        draw_frame(canvas, row, col, frame)
        await sleep(year_ticks)
        draw_frame(canvas, row, col, frame, negative=True)
        year += 1


async def sleep(ticks=1):
    [await asyncio.sleep(0) for _ in range(ticks)]


def draw(canvas):
    frames = get_frames()
    curses.curs_set(False)
    canvas.nodelay(True)

    info_canvas, game_canvas = get_sub_canvases(canvas)
    row_max, col_max = get_canvas_max_coords(game_canvas)

    coroutines = get_star_coroutines(game_canvas, row_max, col_max)
    rocket = animate_spaceship(frames['rocket'])
    rocket_move = run_spaceship(game_canvas, frames['rocket'])
    garbage = fill_orbit_with_garbage(game_canvas, col_max, frames['garbage'])
    year = show_year(info_canvas)

    coroutines.extend([rocket, rocket_move, garbage, year])
    run_event_loop(coroutines, info_canvas, game_canvas)


def run_event_loop(coroutines, *canvases):
    while True:
        for coroutine in coroutines.copy():
            try:
                coroutine.send(None)
            except StopIteration:
                coroutines.remove(coroutine)
        for canvas in canvases:
            canvas.border()
            canvas.refresh()
        time.sleep(TIC_TIMEOUT)


if __name__ == '__main__':
    curses.update_lines_cols()
    curses.wrapper(draw)
