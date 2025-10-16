import pendulum
import time
import statsapi
from datetime import datetime
from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics
from PIL import Image, ImageDraw


class schedule:
    def get_sched():
        # datetime.today().strftime('%m/%d/%Y')
        current_date = pendulum.now().format('MM/DD/YYYY')
        sched = statsapi.schedule(start_date=current_date, team=112)
        if not sched:
            next_game = statsapi.next_game(teamId=112)
            sched = statsapi.schedule(game_id=next_game)
            print("Inside if statement!")
        print(sched)
        return sched


def startup(canvas):
    double_header, a = 0, 0
    canvas.Clear()
    sched = schedule.get_sched()
    print(sched)
    gameid = sched['game_id']
    lineup = schedule.get_lineup(gameid)
    opp_image, cubs_image, batting_image = get_images(sched, a)


def error_correction(canvas):
    startup(canvas)


startup(canvas)
