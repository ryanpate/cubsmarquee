from PIL import Image, ImageDraw
from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics
import statsapi, time, random
from datetime import datetime

# Configuration
matrix_options = RGBMatrixOptions()
matrix_options.rows = 48
matrix_options.cols = 96
matrix_options.chain_length = 1
matrix_options.parallel = 1
matrix_options.hardware_mapping = 'regular'  # Check your specific mapping

# Initialize matrix
matrix = RGBMatrix(options=matrix_options)
canvas = matrix.CreateFrameCanvas()

def get_sched():
    current_date = datetime.today().strftime('%m/%d/%Y')
    sched = statsapi.schedule(start_date=current_date, team=112)
    if sched == []:
        next_game = statsapi.next_game(teamId=112)
        sched = statsapi.schedule(game_id=next_game)
    return sched

def game_over(canvas, sched, opp_image, cubs_image):
    cubs_home = 0
    home_team = sched[0]['home_id']
    if home_team == 112:
        cubs_home = 1
    else:
        cubs_run = sched[0]['away_score']            
#    while True:
    canvas.Clear()
    sched = get_sched()
    output_image = Image.new("RGB", (matrix_options.cols, matrix_options.rows))
    cubs_image_pos = (1, 0)
    opp_image_pos = (66, 0)
    opp_image_newsize = (opp_image.size[0], 28)
    opp_image = opp_image.resize(opp_image_newsize)
    output_image.paste(cubs_image, cubs_image_pos)
    output_image.paste(opp_image, opp_image_pos)
    canvas.SetImage(output_image.convert("RGB"), 0, 0)
    cubs_score_font = graphics.Font()
    cubs_score_font.LoadFont('./fonts/10x20.bdf')
    shadow_color = graphics.Color(0, 0, 255)
    run_color = graphics.Color(255, 255, 255)
    final_color = graphics.Color(255, 233, 0)
    inning_font = graphics.Font()
    inning_font.LoadFont('./fonts/7x14B.bdf')
    graphics.DrawText(canvas, inning_font, 34, 12, final_color, 'GAME')
    graphics.DrawText(canvas, inning_font, 34, 23, final_color, 'OVER')
    if home_team == 112:
        if sched[0]['home_score'] >= 10:
            graphics.DrawText(canvas, cubs_score_font, 5, 44, shadow_color, str(sched[0]['home_score']))
            graphics.DrawText(canvas, cubs_score_font, 6, 45, run_color, str(sched[0]['home_score']))
        else:
            graphics.DrawText(canvas, cubs_score_font, 9, 44, shadow_color, str(sched[0]['home_score']))
            graphics.DrawText(canvas, cubs_score_font, 10, 45, run_color, str(sched[0]['home_score']))
        if sched[0]['away_score'] >= 10:
            graphics.DrawText(canvas, cubs_score_font, 72, 44, shadow_color, str(sched[0]['away_score']))
            graphics.DrawText(canvas, cubs_score_font, 73, 45, run_color, str(sched[0]['away_score']))
        else:
            graphics.DrawText(canvas, cubs_score_font, 75, 44, shadow_color, str(sched[0]['away_score']))
            graphics.DrawText(canvas, cubs_score_font, 76, 45, run_color, str(sched[0]['away_score']))
    else:
        if sched[0]['home_score'] >= 10:
            graphics.DrawText(canvas, cubs_score_font, 5, 44, shadow_color, str(sched[0]['away_score']))
            graphics.DrawText(canvas, cubs_score_font, 6, 45, run_color, str(sched[0]['away_score']))
        else:
            graphics.DrawText(canvas, cubs_score_font, 9, 44, shadow_color, str(sched[0]['away_score']))
            graphics.DrawText(canvas, cubs_score_font, 10, 45, run_color, str(sched[0]['away_score']))
        if sched[0]['away_score'] >= 10:
            graphics.DrawText(canvas, cubs_score_font, 72, 44, shadow_color, str(sched[0]['home_score']))
            graphics.DrawText(canvas, cubs_score_font, 73, 45, run_color, str(sched[0]['home_score']))
        else:
            graphics.DrawText(canvas, cubs_score_font, 75, 44, shadow_color, str(sched[0]['home_score']))
            graphics.DrawText(canvas, cubs_score_font, 76, 45, run_color, str(sched[0]['home_score']))

sched = get_sched()
gameid = sched[0]['game_id']

for x in statsapi.get('game', {'gamePk':gameid})['gameData']['teams']:
    if statsapi.get('game', {'gamePk':gameid})['gameData']['teams'][x]['abbreviation'] != 'CHC':
        opp_abv = statsapi.get('game', {'gamePk':gameid})['gameData']['teams'][x]['abbreviation']

opp_image_path = './logos/' + opp_abv + '.png'
opp_image = Image.open(opp_image_path)
cubs_image_path = './logos/cubs.png'
cubs_image = Image.open(cubs_image_path)

game_over(canvas, sched, opp_image, cubs_image)

canvas = matrix.SwapOnVSync(canvas)

input('Press Enter to EXIT...')