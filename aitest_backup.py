from PIL import Image, ImageDraw
from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics
from datetime import datetime
import statsapi, time, os

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

# Load BDF font
font = graphics.Font()
font.LoadFont("./fonts/7x13B.bdf")

# Load image
image_path = "./marquee.png"
image = Image.open(image_path)

def draw_bases(canvas):
    base_xy = {}
    second_base_x = 43
    second_base_y = 15
    first_base_x = second_base_x + 7
    first_base_y = second_base_y + 7
    third_base_x = second_base_x - 7
    third_base_y = second_base_y + 7
    base_xy['first_base_x'] = first_base_x
    base_xy['first_base_y'] = first_base_y
    base_xy['second_base_x'] = second_base_x
    base_xy['second_base_y'] = second_base_y
    base_xy['third_base_x'] = third_base_x
    base_xy['third_base_y'] = third_base_y
    for base in range(3):
        if base == 0:
            bag_x = first_base_x
            bag_y = first_base_y
        if base == 1:
            bag_x = second_base_x
            bag_y = second_base_y
        if base == 2:
            bag_x = third_base_x
            bag_y = third_base_y
        for a in range(0, 5):
            canvas.SetPixel(bag_x + a, bag_y, 255, 233, 0)
            bag_y -= 1
            if a == 4:
                for b in range(5, 10):
                    canvas.SetPixel(bag_x + b, bag_y, 255, 233, 0)
                    bag_y +=1
                    if b == 9:
                        for c in range(10, 5, -1):
                            canvas.SetPixel(bag_x + c, bag_y, 255, 233, 0)
                            bag_y += 1
                            if c == 6:
                                for d in range(5, 0, -1):
                                    canvas.SetPixel(bag_x + d, bag_y, 255, 233, 0)
                                    bag_y -= 1
    return base_xy

def draw_outs(canvas):
    outs_xy = {}
    out_one_x = 36
    out_one_y = 32
    out_two_x = out_one_x + 9
    out_two_y = out_one_y
    out_three_x = out_two_x + 9
    out_three_y = out_two_y
    outs_xy['out_one_x'] = out_one_x
    outs_xy['out_one_y'] = out_one_y
    outs_xy['out_two_x'] = out_two_x
    outs_xy['out_two_y'] = out_two_y
    outs_xy['out_three_x'] = out_three_x
    outs_xy['out_three_y'] = out_three_y
    for out in range(3):
        if out == 0:
            out_x = out_one_x
            out_y = out_one_y
        if out == 1:
            out_x = out_two_x
            out_y = out_two_y
        if out == 2:
            out_x = out_three_x
            out_y = out_three_y
        for a in range(6):
            canvas.SetPixel(out_x + a, out_y, 255, 233, 0)
            canvas.SetPixel(out_x + a, out_y + 2, 255, 233, 0)
            if a == 5:
                for b in range(0, 3):
                    canvas.SetPixel(out_x, out_y + b, 255, 233, 0)
                    canvas.SetPixel(out_x + 6, out_y + b, 255, 233, 0)
    return outs_xy

def on_base(hit_x, hit_y, filled, canvas):
    next_y = 0
    if filled == 1:
        for fill in range(1, 6):
            for i in range(5):
                canvas.SetPixel(hit_x + i + fill, hit_y + i - next_y, 255, 233, 0)
            next_y += 1
    else:
        for fill in range(1, 6):
            for i in range(5):
                canvas.SetPixel(hit_x + i + fill, hit_y + i - next_y, 0, 0, 0)
            next_y += 1

def outs(out_x, out_y, filled, canvas):
    if filled == 1:
        for fill in range(5):
            canvas.SetPixel(out_x + fill + 1, out_y + 1, 255, 233, 0)
    else:
        for fill in range(5):
            canvas.SetPixel(out_x + fill + 1, out_y + 1, 0, 0, 0)
            canvas.SetPixel(out_x + 9 + fill + 1, out_y + 1, 0, 0, 0)
            canvas.SetPixel(out_x + 18 + fill + 1, out_y + 1, 0, 0, 0)

def get_sched():
    current_date = datetime.today().strftime('%m/%d/%Y')
    sched = statsapi.schedule(start_date=current_date, team=112)
    if sched == []:
        next_game = statsapi.next_game(teamId=112)
        sched = statsapi.schedule(game_id=next_game)
    return sched

def get_pitchers(a):
    sched = get_sched()
    if sched[a]['home_id'] == 112:
        pitchers = ('Cubs Pitcher: ' + sched[a]['home_probable_pitcher'] + '    ' + 'Opponent Pitcher: ' + sched[a]['away_probable_pitcher'])
    else:
        pitchers = ('Cubs Pitcher: ' + sched[a]['away_probable_pitcher'] + '    ' + 'Opponent Pitcher: ' + sched[a]['home_probable_pitcher'])
    return pitchers

def get_lineup(gameid):
    count = 1
    home_data = statsapi.get('game', {'gamePk':gameid})['liveData']['boxscore']['teams']['home']['batters']
    home_team = statsapi.get('game', {'gamePk':gameid})['liveData']['boxscore']['teams']['home']['team']['name']
    away_team = statsapi.get('game', {'gamePk':gameid})['liveData']['boxscore']['teams']['away']['team']['name']
    lineup = home_team + ' - '
    for x in home_data:
        home_player = statsapi.get('people', {'personIds':x})['people'][0]['lastName']
        home_player_pos = statsapi.get('people', {'personIds':x})['people'][0]['primaryPosition']['abbreviation']
        lineup = lineup + home_player_pos + ':' + home_player + ' '
        count += 1
    away_data = statsapi.get('game', {'gamePk':gameid})['liveData']['boxscore']['teams']['away']['batters']
    count = 1
    lineup = lineup + '  ' + away_team + ' - '
    for y in away_data:
        away_player = statsapi.get('people', {'personIds':y})['people'][0]['lastName']
        away_player_pos = statsapi.get('people', {'personIds':y})['people'][0]['primaryPosition']['abbreviation']
        lineup = lineup + away_player_pos + ':' + away_player + ' '
        count += 1
    return lineup

def get_away_team(gameid):
    if statsapi.get('game', {'gamePk':gameid})['gameData']['teams']['home']['id'] == 112:
        away_team = statsapi.get('game', {'gamePk':gameid})['gameData']['teams']['away']['abbreviation']        
    else:
        away_team = statsapi.get('game', {'gamePk':gameid})['gameData']['teams']['home']['abbreviation']        
    return away_team

def game_time(a):
    sched = get_sched()
    game_time = sched[a]['game_datetime'][-9:19]
    if game_time[:2] == '00':
        game_time = '24:' + game_time[3:]
    if int(game_time[:2]) - 5 < 0:
        game_time = str(int(game_time[:2]) + 7) + game_time[2:]
    else:
        game_time = str(int(game_time[:2]) - 5) + game_time[2:]
    try:
        if int(game_time[:2]) > 12:
            game_time = str(int(game_time[:2]) - 12) + game_time[2:]
    except:
        a = 0  
    return game_time

def play_ball(a, gameid):
    sched = get_sched()
    start_time = game_time()
    if statsapi.get('game', {'gamePk':gameid})['gameData']['teams']['home']['abbreviation'] == 'CHC':
        away = 'away'
    else:
        away = 'home'
    sched_text = ('NEXT GAME ' + sched[a]['game_date'][6:10] + ' at ' + start_time[:4] + ' vs '  + statsapi.get('game', {'gamePk':gameid})['gameData']['teams'][away]['name'] + '     ' + (get_pitchers(a)))
    return sched_text

def warmup(a, canvas, image, lineup, gameid, opp_image, cubs_image, batting_image):
#    try:
    sched = get_sched()
    hour_length = 4
    game_time = sched[a]['game_datetime'][-9:19]
    time_compare = game_time[:5]
    if game_time[:2] == '00':
        game_time = '24:' + game_time[3:]
    if int(game_time[:2]) - 5 < 0:
        game_time = str(int(game_time[:2]) + 7) + game_time[2:]
    else:
        game_time = str(int(game_time[:2]) - 5) + game_time[2:]
    try:
        if int(game_time[:2]) > 12:
            game_time = str(int(game_time[:2]) - 12) + game_time[2:]
        try:
            if int(game_time[:2]) >= 10:
                hour_length = 5
        except:
            hour_length = 4
    except:
        hour_length = 4
    current_time = datetime.now().strftime('%H:%M')
    pos = canvas.width
    time_font = graphics.Font()
    time_font.LoadFont('./fonts/6x9.bdf')
    warmup_font = graphics.Font()
    warmup_font.LoadFont('./fonts/9x18B.bdf')
    batter_font = graphics.Font()
    batter_font.LoadFont('./fonts/4x6.bdf')
    lineup_font = graphics.Font()
    lineup_font.LoadFont('./fonts/7x14B.bdf')
    textColor = graphics.Color(255, 255, 255)
    start_time = game_time[:hour_length]
    while current_time != time_compare or sched[a]['status'] != 'In Progress' or sched[a]['status'][:7] != 'Delayed':
        canvas.Fill(70, 128, 83)
        for x in range(96):
            canvas.SetPixel(x, 14, 255, 255, 255)
        graphics.DrawText(canvas, warmup_font, 17, 12, textColor, 'WARM UP')
        graphics.DrawText(canvas, time_font, 17, 24, textColor, 'START TIME')
        graphics.DrawText(canvas, time_font, 36, 32, textColor, start_time)
        pos -= 1  
        len = graphics.DrawText(canvas, lineup_font, pos, 45, textColor, lineup)
        if (pos + len < 0):
            pos = canvas.width
            sched = get_sched()
            lineup = get_lineup(gameid)
        graphics.DrawText(canvas, lineup_font, pos, 45, textColor, lineup)
        if sched[a]['status'] == 'In Progress':
            break
        if sched[a]['status'][:7] == 'Delayed':
            delayed(a, canvas, image, lineup, gameid, opp_image, cubs_image, batting_image)
        current_time = datetime.now().strftime('%H:%M')
        canvas = matrix.SwapOnVSync(canvas)
        time.sleep(.02)

    game_on(a, canvas, image, lineup, gameid, opp_image, cubs_image, batting_image)
#    except:
#        print('encountered an error warm_up...')
#        time.sleep(10)
#        error_correction(canvas)


def delayed(a, canvas, image, lineup, gameid, opp_image, cubs_image, batting_image):
    try:
        sched = get_sched()
        hour_length = 4
        game_time = sched[a]['game_datetime'][-9:19]
        time_compare = game_time[:5]
        if game_time[:2] == '00':
            game_time = '24:' + game_time[3:]
        if int(game_time[:2]) - 5 < 0:
            game_time = str(int(game_time[:2]) + 7) + game_time[2:]
        else:
            game_time = str(int(game_time[:2]) - 5) + game_time[2:]
        try:
            if int(game_time[:2]) > 12:
                game_time = str(int(game_time[:2]) - 12) + game_time[2:]
            try:
                if int(game_time[:2]) >= 10:
                    hour_length = 5
            except:
                hour_length = 4
        except:
            hour_length = 4
        current_time = datetime.now().strftime('%H:%M')
        pos = canvas.width
        time_font = graphics.Font()
        time_font.LoadFont('./fonts/6x9.bdf')
        warmup_font = graphics.Font()
        warmup_font.LoadFont('./fonts/9x18B.bdf')
        batter_font = graphics.Font()
        batter_font.LoadFont('./fonts/4x6.bdf')
        lineup_font = graphics.Font()
        lineup_font.LoadFont('./fonts/7x14B.bdf')
        textColor = graphics.Color(255, 255, 255)
        start_time = game_time[:hour_length]
        while current_time != time_compare or sched[a]['status'] != 'In Progress':
            canvas.Fill(255, 210, 0)
            for x in range(96):
                canvas.SetPixel(x, 14, 255, 255, 255)
            graphics.DrawText(canvas, warmup_font, 17, 12, textColor, 'DELAYED')
            graphics.DrawText(canvas, time_font, 17, 24, textColor, 'START TIME')
            graphics.DrawText(canvas, time_font, 36, 32, textColor, start_time)
            pos -= 1
            len = graphics.DrawText(canvas, lineup_font, pos, 45, textColor, lineup)
            if (pos + len < 0):
                pos = canvas.width
                sched = get_sched()
                lineup = get_lineup(gameid)
            graphics.DrawText(canvas, lineup_font, pos, 45, textColor, lineup)
            canvas = matrix.SwapOnVSync(canvas)
            time.sleep(.02)
            if sched[a]['status'] == 'In Progress':
                break
            current_time = datetime.now().strftime('%H:%M')
        game_on(canvas, image, lineup, gameid, opp_image, cubs_image, batting_image)
    except:
        print('encountered an error warm_up...')
        time.sleep(10)
        error_correction(canvas)

def no_game(a, canvas, image, lineup, gameid, opp_image, cubs_image, batting_image):
    try:
        canvas.Clear()
        sched = get_sched()
        gameid = sched[a]['game_id']
        game_date = sched[a]['game_date']
        game_time = sched[a]['game_datetime'][-9:19]
        game_time = datetime.strptime(game_time, '%H:%M:%S')
        game_time = game_time.strftime('%H:%M')
        font = graphics.Font()
        font.LoadFont("./fonts/7x13B.bdf")
        if game_time[:2] == '00':
            game_time = '24:' + game_time[3:]
        if int(game_time[:2]) - 5 < 0:
            game_time = str(int(game_time[:2]) + 7) + game_time[2:]
        else:
            game_time = str(int(game_time[:2]) - 5) + game_time[2:]
        try:
            if int(game_time[:2]) > 12:
                game_time = str(int(game_time[:2]) - 12) + game_time[2:]
        except:
            if int(game_time[:1]) > 12:
                game_time = str(int(game_time[:1]) - 12) + game_time[1:]
        if statsapi.get('game', {'gamePk':gameid})['gameData']['teams']['home']['abbreviation'] == 'CHC':
            away = 'away'
        else:
            away = 'home'
        text = ('NEXT GAME ' + game_date[5:] + ' at ' + game_time + ' vs '  + statsapi.get('game', {'gamePk':gameid})['gameData']['teams'][away]['name'] + '     ' + (get_pitchers(a)))
        output_image = Image.new("RGB", (matrix_options.cols, matrix_options.rows))
        pos = canvas.width
        image_position = (0, 0)
        while True:
            canvas.Clear()
            output_image.paste(image, image_position)
            canvas.SetImage(output_image.convert("RGB"), 0, 0)
            pos -= 1  
            textColor = graphics.Color(255, 223, 0)
            len = graphics.DrawText(canvas, font, pos, 46, textColor, text)
            if (pos + len < 0):
                pos = canvas.width
                canvas.Clear()
                standings = statsapi.get('standings', {'leagueId':104})['records'][1]['teamRecords']
                title_font = graphics.Font()
                title_font.LoadFont('./fonts/5x8.bdf')
                title_color = graphics.Color(255, 255, 0)
                standings_font = graphics.Font()
                standings_font.LoadFont('./fonts/4x6.bdf')
                standings_color = graphics.Color(255, 255, 255)
                canvas.Fill(70, 128, 83)
                graphics.DrawText(canvas, title_font, 3, 8, title_color, 'DIVISION STANDINGS')
                count = 0
                standings_y = 15
                for x in standings:
                    sched = get_sched()
                    team_id = statsapi.get('team', {'teamId':standings[count]['team']['id']})['teams'][0]['id']
                    team_abv = statsapi.get('team', {'teamId':standings[count]['team']['id']})['teams'][0]['abbreviation']
                    games_back = standings[count]['gamesBack']
                    wild_games_back = standings[count]['wildCardGamesBack']
                    if games_back == '-':
                        games_back = ''
                    if wild_games_back == '-':
                        wild_games_back = ''
                    record = str(standings[count]['leagueRecord']['wins']) + '-' + str(standings[count]['leagueRecord']['losses']) + ' ' + str(standings[count]['leagueRecord']['pct'])
                    if standings[count]['team']['id'] == team_id:
                        graphics.DrawText(canvas, standings_font, 5, standings_y, standings_color, team_abv)
                        graphics.DrawText(canvas, standings_font, 26, standings_y, standings_color, record)
                        graphics.DrawText(canvas, standings_font, 75, standings_y, standings_color, games_back)
                        standings_y += 8
                    count += 1
                canvas = matrix.SwapOnVSync(canvas)
                time.sleep(15)
                if sched[a]['summary'][-8:] == '(Warmup)' or sched[a]['summary'][-10:] == '(Pre-Game)':
                    warmup(canvas, image, lineup, gameid, opp_image, cubs_image, batting_image)
                if sched[a]['summary'][-10] == '(In Progress)':
                    game_on(canvas, image, lineup, gameid, opp_image, cubs_image, batting_image)
            canvas = matrix.SwapOnVSync(canvas)
            game_date = sched[a]['game_date']
            game_time = sched[a]['game_datetime'][-9:19]
            if game_time[:2] == '00':
                game_time = '24:' + game_time[3:]
            game_time = str(int(game_time[:2])) + game_time[2:]
            time.sleep(.02)
    except:
        print('encountered an error in no_game...')
        time.sleep(10)
        error_correction(canvas)

def game_on(a, canvas, image, lineup, gameid, opp_image, cubs_image, batting_image):
    try:
        sched = get_sched()
        cubs_home = 0
        home_team = sched[a]['home_id']
        pos = canvas.width
        if home_team == 112:
            cubs_run = sched[a]['home_score']
            opp_run = sched[a]['away_score']
            cubs_home = 1
        else:
            cubs_run = sched[a]['away_score']
            opp_run = sched[a]['home_score']           
        while True:
            canvas.Clear()
            sched = get_sched()
            batter = statsapi.get('game_playByPlay', {'gamePk': gameid})['currentPlay']['matchup']['batter']['fullName']
            batter_text = 'AT BAT: ' + batter
            if sched[a]['status'] == 'Game Over' or sched[a]['status'] == 'Final':
                print(sched[a]['status'])
                game_over(a, canvas, gameid, image, lineup, batting_image, sched, opp_image, cubs_image)
            output_image = Image.new("RGB", (matrix_options.cols, matrix_options.rows))
            cubs_image_pos = (1, 0)
            opp_image_pos = (66, 0)
            batting_home_pos = (28, 31)
            batting_away_pos = (64, 31)
            opp_image_newsize = (opp_image.size[0], 28)
            opp_image = opp_image.resize(opp_image_newsize)
            output_image.paste(cubs_image, cubs_image_pos)
            output_image.paste(opp_image, opp_image_pos)
            if str(statsapi.get('game', {'gamePk':gameid})['liveData']['linescore']['inningState'])[:3] == 'Top' and cubs_home == 0:
                output_image.paste(batting_image, batting_home_pos)
            if str(statsapi.get('game', {'gamePk':gameid})['liveData']['linescore']['inningState'])[:3] == 'End' and cubs_home == 0:
                output_image.paste(batting_image, batting_home_pos)
            if str(statsapi.get('game', {'gamePk':gameid})['liveData']['linescore']['inningState'])[:3] == 'Bot' and cubs_home == 0:
                output_image.paste(batting_image, batting_away_pos)
            if str(statsapi.get('game', {'gamePk':gameid})['liveData']['linescore']['inningState'])[:3] == 'Mid' and cubs_home == 0:
                output_image.paste(batting_image, batting_away_pos)
            if str(statsapi.get('game', {'gamePk':gameid})['liveData']['linescore']['inningState'])[:3] == 'Top' and cubs_home == 1:
                output_image.paste(batting_image, batting_away_pos)
            if str(statsapi.get('game', {'gamePk':gameid})['liveData']['linescore']['inningState'])[:3] == 'End' and cubs_home == 1:
                output_image.paste(batting_image, batting_away_pos)
            if str(statsapi.get('game', {'gamePk':gameid})['liveData']['linescore']['inningState'])[:3] == 'Bot' and cubs_home == 1:
                output_image.paste(batting_image, batting_home_pos)
            if str(statsapi.get('game', {'gamePk':gameid})['liveData']['linescore']['inningState'])[:3] == 'Mid' and cubs_home == 1:
                output_image.paste(batting_image, batting_home_pos)
            canvas.SetImage(output_image.convert("RGB"), 0, 0)
            base = draw_bases(canvas)
            out = draw_outs(canvas)
            cubs_score_font = graphics.Font()
            cubs_score_font.LoadFont('./fonts/10x20.bdf')
            count_font = graphics.Font()
            count_font.LoadFont('./fonts/4x6.bdf')
            count_color = graphics.Color(255, 233, 0)
            shadow_color = graphics.Color(0, 0, 255)
            run_color = graphics.Color(255, 255, 255)
            inning_font = graphics.Font()
            inning_font.LoadFont('./fonts/4x6.bdf')
            inning_text = str(statsapi.get('game', {'gamePk':gameid})['liveData']['linescore']['inningState'])[:3] + ' ' + str(statsapi.get('game', {'gamePk':gameid})['liveData']['linescore']['currentInningOrdinal'])
            count_text = 'B:' + str(statsapi.get('game_playByPlay', {'gamePk':gameid})['currentPlay']['count']['balls']) + ' S:' + str(statsapi.get('game_playByPlay', {'gamePk':gameid})['currentPlay']['count']['strikes'])
            graphics.DrawText(canvas, count_font, 35, 45, count_color, count_text)
            graphics.DrawText(canvas, inning_font, 35, 8, count_color, inning_text)
            current_out = statsapi.get('game', {'gamePk':gameid})['liveData']['linescore']['outs']
            is_on_base = statsapi.get('game', {'gamePk':gameid})['liveData']['linescore']['offense']
            try:
                if is_on_base['first']:
                    on_base(base['first_base_x'], base['first_base_y'], 1, canvas)
            except:
                    on_base(base['first_base_x'], base['first_base_y'], 0, canvas)
            try:
                if is_on_base['second']:
                    on_base(base['second_base_x'], base['second_base_y'], 1, canvas)
            except:
                    on_base(base['second_base_x'], base['second_base_y'], 0, canvas)
            try:
                if is_on_base['third']:
                    on_base(base['third_base_x'], base['third_base_y'], 1, canvas)
            except:
                    on_base(base['third_base_x'], base['third_base_y'], 0, canvas)
            if current_out == 0:
                outs(out['out_one_x'], out['out_one_y'], 0, canvas)
            if current_out >= 1:
                outs(out['out_one_x'], out['out_one_y'], 1, canvas)
            if current_out >= 2:
                outs(out['out_two_x'], out['out_two_y'], 1, canvas)
            if current_out == 3:
                outs(out['out_three_x'], out['out_three_y'], 1, canvas)
            if home_team == 112:
                if sched[a]['home_score'] >= 10:
                    graphics.DrawText(canvas, cubs_score_font, 5, 44, shadow_color, str(sched[a]['home_score']))
                    graphics.DrawText(canvas, cubs_score_font, 6, 45, run_color, str(sched[a]['home_score']))
                else:
                    graphics.DrawText(canvas, cubs_score_font, 9, 44, shadow_color, str(sched[a]['home_score']))
                    graphics.DrawText(canvas, cubs_score_font, 10, 45, run_color, str(sched[a]['home_score']))
                if sched[a]['away_score'] >= 10:
                    graphics.DrawText(canvas, cubs_score_font, 72, 44, shadow_color, str(sched[a]['away_score']))
                    graphics.DrawText(canvas, cubs_score_font, 73, 45, run_color, str(sched[a]['away_score']))
                else:
                    graphics.DrawText(canvas, cubs_score_font, 75, 44, shadow_color, str(sched[a]['away_score']))
                    graphics.DrawText(canvas, cubs_score_font, 76, 45, run_color, str(sched[a]['away_score']))
                cubs_score = sched[a]['home_score']
                opp_score = sched[a]['away_score']
            else:
                if sched[a]['home_score'] >= 10:
                    graphics.DrawText(canvas, cubs_score_font, 5, 44, shadow_color, str(sched[a]['away_score']))
                    graphics.DrawText(canvas, cubs_score_font, 6, 45, run_color, str(sched[a]['away_score']))
                else:
                    graphics.DrawText(canvas, cubs_score_font, 9, 44, shadow_color, str(sched[a]['away_score']))
                    graphics.DrawText(canvas, cubs_score_font, 10, 45, run_color, str(sched[a]['away_score']))
                if sched[a]['away_score'] >= 10:
                    graphics.DrawText(canvas, cubs_score_font, 72, 44, shadow_color, str(sched[a]['home_score']))
                    graphics.DrawText(canvas, cubs_score_font, 73, 45, run_color, str(sched[a]['home_score']))
                else:
                    graphics.DrawText(canvas, cubs_score_font, 75, 44, shadow_color, str(sched[a]['home_score']))
                    graphics.DrawText(canvas, cubs_score_font, 76, 45, run_color, str(sched[a]['home_score']))
                cubs_score = sched[a]['away_score']
                opp_score = sched[a]['home_score']
            if cubs_score > cubs_run:
                run_scored(canvas)
                cubs_run = cubs_score
            if opp_score > opp_run:
                opp_scored(canvas, opp_image)
                opp_run = opp_score
            canvas = matrix.SwapOnVSync(canvas)
            time.sleep(5)
    except:
        print('encountered an error in game_on...')
        time.sleep(10)
        error_correction(canvas)

def run_scored(canvas):
    y = 0
    run_image_path = './logos/run_scored.png'
    baseball_image_path = './logos/baseball.png'
    baseball_image = Image.open(baseball_image_path)
    run_image = Image.open(run_image_path)
    run_image_flipped = run_image.transpose(Image.FLIP_LEFT_RIGHT)
    run_image_position = (0, 12)
    run_y = 15
    next_x = 25
    for x in range(25, 97):
        canvas.Clear()
        if x > next_x + 5:
            next_x += 5
            run_y -= 1
        output_image = Image.new("RGB", (matrix_options.cols, matrix_options.rows))
        baseball_image_position = (x, run_y)
        output_image.paste(run_image_flipped, run_image_position)
        output_image.paste(baseball_image, baseball_image_position)
        canvas.SetImage(output_image.convert("RGB"), 0, 0)
        canvas = matrix.SwapOnVSync(canvas)
    while (y <= 2):
        canvas.Clear()
        scored_font = graphics.Font()
        scored_font.LoadFont('./fonts/9x18B.bdf')
        scored_color = graphics.Color(255, 233, 0)
        scored_shadow_color = graphics.Color(255, 255, 255)
        graphics.DrawText(canvas, scored_font, 35, 19, scored_shadow_color, 'RUN')
        graphics.DrawText(canvas, scored_font, 21, 35, scored_shadow_color, 'SCORED')
        graphics.DrawText(canvas, scored_font, 36, 20, scored_color, 'RUN')
        graphics.DrawText(canvas, scored_font, 22, 36, scored_color, 'SCORED')
        canvas = matrix.SwapOnVSync(canvas)
        time.sleep(.5)
        canvas.Clear()
        canvas = matrix.SwapOnVSync(canvas)
        time.sleep(.5)
        y += 1

def opp_scored(canvas, opp_image):
    opp_image_left = opp_image
    for x in range(-24, 220, 2):
        canvas.Clear()
        opp_image_pos = (x, 12)
        opp_image_newsize = (opp_image.size[0], 28)
        opp_image = opp_image.resize(opp_image_newsize)
        output_image = Image.new("RGB", (matrix_options.cols, matrix_options.rows))
        output_image.paste(opp_image, opp_image_pos)
        opp_image_pos_left = (x-119, 12)
        opp_image_newsize_left = (opp_image_left.size[0], 28)
        opp_image_left = opp_image_left.resize(opp_image_newsize_left)
        output_image.paste(opp_image_left, opp_image_pos_left)
        canvas.SetImage(output_image.convert("RGB"), 0, 0)
        scored_font = graphics.Font()
        scored_font.LoadFont('./fonts/9x18B.bdf')
        scored_color = graphics.Color(255, 0, 0)
        scored_shadow_color = graphics.Color(255, 255, 255)
        graphics.DrawText(canvas, scored_font, x-90, 30,scored_shadow_color, 'RUN SCORED')
        graphics.DrawText(canvas, scored_font, x-91, 29,scored_color, 'RUN SCORED')
        canvas = matrix.SwapOnVSync(canvas)

def game_over(a, canvas, gameid, image, lineup, batting_image, sched, opp_image, cubs_image):
    try:
        home_team = sched[a]['home_id']
        current_date = datetime.today().strftime('%Y-%m-%d')
        current_time = datetime.now().strftime("%H:%M")
        canvas.Clear()
        over_date = datetime.today().strftime('%Y-%m-%d')
        output_image = Image.new("RGB", (matrix_options.cols, matrix_options.rows))
        innings = statsapi.get('game', {'gamePk':gameid})['liveData']['linescore']['currentInning']
        if home_team == 112:
            runs = statsapi.get('game', {'gamePk':gameid})['liveData']['boxscore']['teams']['home']['teamStats']['batting']['runs']
            hits = statsapi.get('game', {'gamePk':gameid})['liveData']['boxscore']['teams']['home']['teamStats']['batting']['hits']
            errors = statsapi.get('game', {'gamePk':gameid})['liveData']['boxscore']['teams']['home']['teamStats']['fielding']['errors']
        else:
            runs = statsapi.get('game', {'gamePk':gameid})['liveData']['boxscore']['teams']['away']['teamStats']['batting']['runs']
            hits = statsapi.get('game', {'gamePk':gameid})['liveData']['boxscore']['teams']['away']['teamStats']['batting']['hits']
            errors = statsapi.get('game', {'gamePk':gameid})['liveData']['boxscore']['teams']['away']['teamStats']['fielding']['errors']
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
        inning_font.LoadFont('./fonts/6x13B.bdf')
        final_font = graphics.Font()
        final_font.LoadFont('./fonts/4x6.bdf')
        graphics.DrawText(canvas, inning_font, 36, 11, final_color, 'GAME')
        graphics.DrawText(canvas, inning_font, 36, 21, final_color, 'OVER')
        graphics.DrawText(canvas, final_font, 29, 29, final_color, 'INNINGS:' + str(innings))
        graphics.DrawText(canvas, final_font, 29, 35, final_color, 'HITS:   ' + str(hits))
        graphics.DrawText(canvas, final_font, 29, 41, final_color, 'RUNS:   ' + str(runs))
        graphics.DrawText(canvas, final_font, 29, 47, final_color, 'ERRORS: ' + str(errors))
        if home_team == 112:
            if sched[a]['home_score'] >= 10:
                graphics.DrawText(canvas, cubs_score_font, 5, 44, shadow_color, str(sched[a]['home_score']))
                graphics.DrawText(canvas, cubs_score_font, 6, 45, run_color, str(sched[a]['home_score']))
            else:
                graphics.DrawText(canvas, cubs_score_font, 9, 44, shadow_color, str(sched[a]['home_score']))
                graphics.DrawText(canvas, cubs_score_font, 10, 45, run_color, str(sched[a]['home_score']))
            if sched[a]['away_score'] >= 10:
                graphics.DrawText(canvas, cubs_score_font, 70, 44, shadow_color, str(sched[a]['away_score']))
                graphics.DrawText(canvas, cubs_score_font, 71, 45, run_color, str(sched[a]['away_score']))
            else:
                graphics.DrawText(canvas, cubs_score_font, 75, 44, shadow_color, str(sched[a]['away_score']))
                graphics.DrawText(canvas, cubs_score_font, 76, 45, run_color, str(sched[a]['away_score']))
            canvas = matrix.SwapOnVSync(canvas)
        else:
            if sched[a]['away_score'] >= 10:
                graphics.DrawText(canvas, cubs_score_font, 5, 44, shadow_color, str(sched[a]['away_score']))
                graphics.DrawText(canvas, cubs_score_font, 6, 45, run_color, str(sched[a]['away_score']))
            else:
                graphics.DrawText(canvas, cubs_score_font, 9, 44, shadow_color, str(sched[a]['away_score']))
                graphics.DrawText(canvas, cubs_score_font, 10, 45, run_color, str(sched[a]['away_score']))
            if sched[a]['home_score'] >= 10:
                graphics.DrawText(canvas, cubs_score_font, 70, 44, shadow_color, str(sched[a]['home_score']))
                graphics.DrawText(canvas, cubs_score_font, 71, 45, run_color, str(sched[a]['home_score']))
            else:
                graphics.DrawText(canvas, cubs_score_font, 75, 44, shadow_color, str(sched[a]['home_score']))
                graphics.DrawText(canvas, cubs_score_font, 76, 45, run_color, str(sched[a]['home_score']))
            canvas = matrix.SwapOnVSync(canvas)
        while over_date == current_date and current_time != '04:00':
            current_date = datetime.today().strftime('%Y-%m-%d')
            current_time = datetime.now().strftime("%H:%M")
            if sched[a]['doubleheader'] == 'S':
                time.sleep(360)
                startup(canvas)
        print('going to no_game')
        no_game(a, canvas, image, lineup, gameid, opp_image, cubs_image, batting_image)
    except:
        print('encountered an error in game_over...')
        time.sleep(10)
        error_correction(canvas)

def startup(canvas):
    double_header = 0
    a = 0
    canvas.Clear()
    sched = get_sched()
    try:
        print(sched[1])
        double_header = 1
        if double_header == 1 and sched[a]['status'] == 'Final':
            a = 1
    except:
        a = 0
    print(sched[a])
    gameid = sched[a]['game_id']
    lineup = get_lineup(gameid)
    for x in statsapi.get('game', {'gamePk':gameid})['gameData']['teams']:
        if statsapi.get('game', {'gamePk':gameid})['gameData']['teams'][x]['abbreviation'] != 'CHC':
            opp_abv = statsapi.get('game', {'gamePk':gameid})['gameData']['teams'][x]['abbreviation']
    opp_image_path = './logos/' + opp_abv + '.png'
    opp_image = Image.open(opp_image_path)
    cubs_image_path = './logos/cubs.png'
    cubs_image = Image.open(cubs_image_path)
    batting_image_path = './baseball.png'
    batting_image = Image.open(batting_image_path)
    while True:
        if sched[a]['status'] == 'Scheduled':
            no_game(a, canvas, image, lineup, gameid, opp_image, cubs_image, batting_image)
        if sched[a]['status'] == 'Warmup' or sched[a]['status'] == 'Pre-Game':
            warmup(a, canvas, image, lineup, gameid, opp_image, cubs_image, batting_image)
        if sched[a]['status'][:7] == 'Delayed':
            delayed(a, canvas, image, lineup, gameid, opp_image, cubs_image, batting_image)
        if sched[a]['status'] == 'In Progress':
            game_on(a, canvas, image, lineup, gameid, opp_image, cubs_image, batting_image)
        if sched[a]['status'] == 'Final' or sched[a]['status'] == 'Game Over':
            game_over(a, canvas, gameid, image, lineup, batting_image, sched, opp_image, cubs_image)

def error_correction(canvas):
    startup(canvas)

startup(canvas)
