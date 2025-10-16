from PIL import Image, ImageDraw
from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics
from datetime import datetime
import statsapi, time, pendulum
import threading

class schedule:
    _cached_date = None
    _cached_sched = None
    
    @staticmethod
    def get_sched():
        current_date = pendulum.now()
        formatted_date = current_date.format('MM/DD/YYYY')
        # If the schedule has already been cached for today, return it
        if schedule._cached_date == formatted_date and schedule._cached_sched is not None:
            return schedule._cached_sched
        next_day = 1
        sched = statsapi.schedule(start_date=formatted_date, team=112)
        while sched == []:
            next_game = current_date.add(days=next_day)
            formatted_date = next_game.format('MM/DD/YYYY')
            sched = statsapi.schedule(start_date=formatted_date, team=112)
            next_day += 1
        # Cache the schedule for today's date
        schedule._cached_date = current_date.format('MM/DD/YYYY')
        schedule._cached_sched = sched
        return sched
    
    @staticmethod
    def get_pitchers(a, gameid):
        sched = schedule.get_sched()
        home_pitcher, away_pitcher = sched[a]['home_probable_pitcher'], sched[a]['away_probable_pitcher']
        if home_pitcher == '':
            home_pitcher = 'TBD'
        if away_pitcher == '':
            away_pitcher = 'TBD'
        if sched[a]['home_id'] == 112:
            pitchers = ('Cubs Pitcher: ' + home_pitcher + '    ' + str(statsapi.get('game',{'gamePk': gameid})['gameData']['teams']['away']['teamName']) + ' Pitcher: ' + away_pitcher)
        else:
            pitchers = ('Cubs Pitcher: ' + away_pitcher + '    ' + str(statsapi.get('game',{'gamePk': gameid})['gameData']['teams']['away']['teamName']) + ' Pitcher: ' + home_pitcher)
        return pitchers

    @staticmethod
    def get_lineup(gameid):
        count = 1
        home_data, home_team, away_team = statsapi.get('game', {'gamePk': gameid})['liveData']['boxscore']['teams']['home']['batters'], statsapi.get('game', {'gamePk': gameid})['liveData']['boxscore']['teams']['home']['team']['name'], statsapi.get('game', {'gamePk': gameid})['liveData']['boxscore']['teams']['away']['team']['name']
        lineup = home_team + ' - '
        for x in home_data:
            home_player = statsapi.get('people', {'personIds': x})[
                'people'][0]['lastName']
            home_player_pos = statsapi.get('people', {'personIds': x})[
                'people'][0]['primaryPosition']['abbreviation']
            lineup = lineup + home_player_pos + ':' + home_player + ' '
            count += 1
        away_data = statsapi.get('game', {'gamePk': gameid})[
            'liveData']['boxscore']['teams']['away']['batters']
        count = 1
        lineup = lineup + '  ' + away_team + ' - '
        for y in away_data:
            away_player = statsapi.get('people', {'personIds': y})[
                'people'][0]['lastName']
            away_player_pos = statsapi.get('people', {'personIds': y})[
                'people'][0]['primaryPosition']['abbreviation']
            lineup = lineup + away_player_pos + ':' + away_player + ' '
            count += 1
        return lineup
    @staticmethod
    def get_away_team(gameid):
        if statsapi.get('game', {'gamePk': gameid})['gameData']['teams']['home']['id'] == 112:
            away_team = statsapi.get('game', {'gamePk': gameid})[
                'gameData']['teams']['away']['abbreviation']
        else:
            away_team = statsapi.get('game', {'gamePk': gameid})[
                'gameData']['teams']['home']['abbreviation']
        return away_team

    @staticmethod
    def game_time(a):
        sched = schedule.get_sched()
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

class playball:
    @staticmethod
    def play_ball(a, gameid):
        sched = schedule.get_sched()
        start_time = schedule.game_time()
        if statsapi.get('game', {'gamePk': gameid})['gameData']['teams']['home']['abbreviation'] == 'CHC':
            away = 'away'
        else:
            away = 'home'
        sched_text = ('NEXT GAME ' + sched[a]['game_date'][6:10] + ' at ' + start_time[:4] + ' vs ' + statsapi.get(
            'game', {'gamePk': gameid})['gameData']['teams'][away]['name'] + '     ' + (schedule.get_pitchers(a, gameid)))
        return sched_text

class drawbases:
    @staticmethod
    def draw_bases(canvas):
        base_xy = {}
        second_base_x, second_base_y = 46, 8
        first_base_x, first_base_y = second_base_x + 7, second_base_y + 7
        third_base_x, third_base_y = second_base_x - 7, second_base_y + 7
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
                canvas.SetPixel(bag_x + a, bag_y, 255, 255, 255)
                bag_y -= 1
                if a == 4:
                    for b in range(5, 10):
                        canvas.SetPixel(bag_x + b, bag_y, 255, 255, 255)
                        bag_y += 1
                        if b == 9:
                            for c in range(10, 5, -1):
                                canvas.SetPixel(bag_x + c, bag_y, 255, 255, 255)
                                bag_y += 1
                                if c == 6:
                                    for d in range(5, 0, -1):
                                        canvas.SetPixel(
                                            bag_x + d, bag_y, 255, 255, 255)
                                        bag_y -= 1
        return base_xy

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


def load_fonts():
    """Load and return a dictionary of fonts to reuse throughout."""
    fonts = {}
    fonts['bdf_7x13'] = graphics.Font()
    fonts['bdf_7x13'].LoadFont("./fonts/7x13B.bdf")
    fonts['time'] = graphics.Font()
    fonts['time'].LoadFont('./fonts/6x9.bdf')
    fonts['warmup'] = graphics.Font()
    fonts['warmup'].LoadFont('./fonts/9x18B.bdf')
    fonts['batter'] = graphics.Font()
    fonts['batter'].LoadFont('./fonts/4x6.bdf')
    fonts['lineup'] = graphics.Font()
    fonts['lineup'].LoadFont('./fonts/7x14B.bdf')
    fonts['title'] = graphics.Font()
    fonts['title'].LoadFont('./fonts/5x8.bdf')
    fonts['standings'] = graphics.Font()
    fonts['standings'].LoadFont('./fonts/4x6.bdf')
    fonts['score'] = graphics.Font()
    fonts['score'].LoadFont('./fonts/9x18B.bdf')
    fonts['inning'] = graphics.Font()
    fonts['inning'].LoadFont('./fonts/6x13B.bdf')
    fonts['final'] = graphics.Font()
    fonts['final'].LoadFont('./fonts/4x6.bdf')
    fonts['tom_thumb'] = graphics.Font()
    fonts['tom_thumb'].LoadFont('./fonts/tom-thumb.bdf')
    fonts['final_score'] = graphics.Font()
    fonts['final_score'].LoadFont('./fonts/10x20.bdf')


    return fonts

# Load image
image_path = "./marquee.png"
image = Image.open(image_path)

def on_base(hit_x, hit_y, filled, canvas):
    next_y = 0
    if filled == 1:
        for fill in range(1, 6):
            for i in range(5):
                canvas.SetPixel(hit_x + i + fill, hit_y + i - next_y, 255, 255, 255)
            next_y += 1
    else:
        for fill in range(1, 6):
            for i in range(5):
                canvas.SetPixel(hit_x + i + fill, hit_y + i - next_y, 0, 51, 102)
            next_y += 1

def outs(out_x, out_y, filled, canvas):
    if filled == 1:
        for fill in range(5):
            canvas.SetPixel(out_x + fill + 1, out_y + 1, 255, 255, 255)
    else:
        for fill in range(5):
            canvas.SetPixel(out_x + fill + 1, out_y + 1, 0, 51, 102)
            canvas.SetPixel(out_x + 9 + fill + 1, out_y + 1, 0, 51, 102)
            canvas.SetPixel(out_x + 18 + fill + 1, out_y + 1, 0, 51, 102)

def warmup(a, canvas, image, lineup, gameid, opp_image, cubs_image, batting_image):
#    try:
    sched = schedule.get_sched()
    hour_length = 4
    game_time = sched[a]['game_datetime'][-9:19]
    pos = canvas.width
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
    # Compute game start time using pendulum for transition logic
    game_datetime = pendulum.parse(sched[a]['game_datetime'])
    textColor = graphics.Color(255, 255, 255)
    while True:
        current_datetime = pendulum.now()
        time_until_game = game_datetime - current_datetime

        # If the game is delayed, transition to the delayed function and exit warmup
        if sched[a]['status'][:7] == 'Delayed':
            delayed(a, canvas, image, lineup, gameid, opp_image, cubs_image, batting_image)
            return

        # If the game has started (i.e. time_until_game is zero or negative), break out to start game_on
        if time_until_game <= pendulum.duration(seconds=0):
            break

        # Warmup display
        canvas.Fill(70, 128, 83)
        for x in range(96):
            canvas.SetPixel(x, 14, 255, 255, 255)
        graphics.DrawText(canvas, fonts['warmup'], 17, 12, textColor, 'WARM UP')
        graphics.DrawText(canvas, fonts['time'], 17, 24, textColor, 'START TIME')
        graphics.DrawText(canvas, fonts['time'], 36, 32, textColor, game_time[:hour_length])
        pos -= 1  
        len_text = graphics.DrawText(canvas, fonts['lineup'], pos, 45, textColor, lineup)
        if (pos + len_text < 0):
            pos = canvas.width
            sched = schedule.get_sched()
            lineup = schedule.get_lineup(gameid)
        graphics.DrawText(canvas, fonts['lineup'], pos, 45, textColor, lineup)
        canvas = matrix.SwapOnVSync(canvas)
        time.sleep(0.02)

    game_on(a, canvas, image, lineup, gameid, opp_image, cubs_image, batting_image)
#    except:
#        print('encountered an error warm_up...')
#        time.sleep(10)
#        error_correction(canvas)

def delayed(a, canvas, image, lineup, gameid, opp_image, cubs_image, batting_image):
    try:
        sched = schedule.get_sched()
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
        current_time = pendulum.now().format('HH:MM')
        pos = canvas.width
        textColor = graphics.Color(255, 255, 255)
        start_time = game_time[:hour_length]
        while current_time != time_compare or sched[a]['status'] != 'In Progress':
            canvas.Clear()
            canvas.Fill(255, 210, 0)
            for x in range(96):
                canvas.SetPixel(x, 14, 255, 255, 255)
            graphics.DrawText(canvas, fonts['warmup'], 17, 12, textColor, 'DELAYED')
            graphics.DrawText(canvas, fonts['time'], 17, 24, textColor, 'START TIME')
            graphics.DrawText(canvas, fonts['time'], 36, 32, textColor, start_time)
            pos -= 1
            len = graphics.DrawText(canvas, fonts['lineup'], pos, 45, textColor, lineup)
            if (pos + len < 0):
                canvas.Clear()
                pos = canvas.width
                sched = schedule.get_sched()
                lineup = schedule.get_lineup(gameid)
            graphics.DrawText(canvas, fonts['lineup'], pos, 45, textColor, lineup)
            canvas = matrix.SwapOnVSync(canvas)
            time.sleep(.02)
            if sched[a]['status'] == 'In Progress':
                break
            current_time = pendulum.now().format('HH:MM')
        game_on(canvas, image, lineup, gameid, opp_image, cubs_image, batting_image)
    except:
        print('encountered an error warm_up...')
        time.sleep(10)
        error_correction(canvas)

def no_game(a, canvas, image, lineup, gameid, opp_image, cubs_image, batting_image):
    #try:
    canvas.Clear()
    sched = schedule.get_sched()
    gameid, game_date, game_time = sched[a]['game_id'], sched[a]['game_date'], sched[a]['game_datetime'][-9:19]
    game_time = datetime.strptime(game_time, '%H:%M:%S')
    game_time = game_time.strftime('%H:%M')
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
    away_team = statsapi.get('game', {'gamePk': gameid})['gameData']['teams'][away]['name']
    output_image = Image.new("RGB", (matrix_options.cols, matrix_options.rows))
    pos = canvas.width
    image_position = (0, 0)
    text = ('NEXT GAME ' + game_date[5:] + ' at ' + game_time +' vs ' + away_team + '     ' + (schedule.get_pitchers(a, gameid)))
    while True:
        canvas.Clear()
        output_image.paste(image, image_position)
        canvas.SetImage(output_image.convert("RGB"), 0, 0)
        pos -= 1  
        textColor = graphics.Color(255, 223, 0)
        len = graphics.DrawText(
            canvas, fonts['bdf_7x13'], pos, 46, textColor, text)
        if (pos + len < 0):
            pos = canvas.width
            canvas.Clear()
            standings = statsapi.get('standings', {'leagueId':104})['records'][1]['teamRecords']
            title_color = graphics.Color(255, 255, 0)
            standings_color = graphics.Color(255, 255, 255)
            canvas.Fill(70, 128, 83)
            graphics.DrawText(canvas, fonts['title'], 3, 8, title_color, 'DIVISION STANDINGS')
            count, standings_y = 0, 15
            for x in standings:
                sched, team_id, team_abv = schedule.get_sched(), statsapi.get('team', {'teamId': standings[count]['team']['id']})['teams'][0]['id'], statsapi.get('team', {'teamId': standings[count]['team']['id']})['teams'][0]['abbreviation']
                games_back, wild_games_back = standings[count]['gamesBack'], standings[count]['wildCardGamesBack']
                if games_back == '-':
                    games_back = ''
                if wild_games_back == '-':
                    wild_games_back = ''
                record = str(standings[count]['leagueRecord']['wins']) + '-' + str(standings[count]['leagueRecord']['losses']) + ' ' + str(standings[count]['leagueRecord']['pct'])
                if standings[count]['team']['id'] == team_id:
                    graphics.DrawText(canvas, fonts['standings'], 5, standings_y, standings_color, team_abv)
                    graphics.DrawText(canvas, fonts['standings'], 26, standings_y, standings_color, record)
                    graphics.DrawText(canvas, fonts['standings'], 75, standings_y, standings_color, games_back)
                    standings_y += 8
                count += 1
            canvas = matrix.SwapOnVSync(canvas)
            time.sleep(15)
            # Determine game start time using pendulum
            game_datetime = pendulum.parse(sched[a]['game_datetime'])
            current_datetime = pendulum.now()
            time_until_game = game_datetime - current_datetime
            
            if time_until_game > pendulum.duration(hours=1):
                # More than one hour until game start; continue displaying the no_game screen
                pass
            elif time_until_game > pendulum.duration(seconds=0):
                # Within one hour before game start; initiate warmup
                warmup_thread = threading.Thread(target=warmup, args=(a, canvas, image, lineup, gameid, opp_image, cubs_image, batting_image))
                warmup_thread.start()
            else:
                # Game has started; initiate game_on
                game_on_thread = threading.Thread(target=game_on, args=(a, canvas, image, lineup, gameid, opp_image, cubs_image, batting_image))
                game_on_thread.start()
        canvas = matrix.SwapOnVSync(canvas)
        game_date, game_time = sched[a]['game_date'], sched[a]['game_datetime'][-9:19]
        if game_time[:2] == '00':
            game_time = '24:' + game_time[3:]
        game_time = str(int(game_time[:2])) + game_time[2:]
        time.sleep(.02)
    #except:
        #print('encountered an error in no_game...')
        #time.sleep(10)
        #error_correction(canvas)

def game_on(a, canvas, image, lineup, gameid, opp_image, cubs_image, batting_image):
    #try:
    sched = schedule.get_sched()
    cubs_home = 0
    home_team = sched[a]['home_id']
    if home_team == 112:
        cubs_run, opp_run = sched[a]['home_score'], sched[a]['away_score']
        cubs_home = 1
    else:
        cubs_run, opp_run = sched[a]['away_score'], sched[a]['home_score']
    while True:
        sched = schedule.get_sched()
        batter_text = 'BAT: ' + str(statsapi.get('game_playByPlay', {'gamePk': gameid})['currentPlay']['matchup']['batter']['fullName'])
        if sched[a]['status'] == 'Game Over' or sched[a]['status'] == 'Final':
            print(sched[a]['status'])
            game_over(a, canvas, gameid, image, lineup, batting_image, sched, opp_image, cubs_image)
        if cubs_home == 1:
            cubs_pitcher, opp_pitcher = statsapi.get('game', {'gamePk': gameid})['liveData']['boxscore']['teams']['home']['pitchers'], statsapi.get('game', {'gamePk': gameid})['liveData']['boxscore']['teams']['away']['pitchers']
            c_pitch, o_pitch = len(cubs_pitcher) - 1, len(opp_pitcher) - 1
            cubs_pitch_count, opp_pitch_count = statsapi.get('person_stats', {'personId': cubs_pitcher[c_pitch], 'gamePk': gameid})['stats'][0]['splits'][1]['stat']['numberOfPitches'], statsapi.get('person_stats', {'personId': opp_pitcher[o_pitch], 'gamePk': gameid})['stats'][0]['splits'][1]['stat']['numberOfPitches']
        else:
            opp_pitcher, cubs_pitcher = statsapi.get('game', {'gamePk': gameid})['liveData']['boxscore']['teams']['home']['pitchers'], statsapi.get('game', {'gamePk': gameid})['liveData']['boxscore']['teams']['away']['pitchers']
            c_pitch, o_pitch = len(cubs_pitcher) - 1, len(opp_pitcher) - 1
            cubs_pitch_count, opp_pitch_count = statsapi.get('person_stats', {'personId': cubs_pitcher[c_pitch], 'gamePk': gameid})['stats'][0]['splits'][1]['stat']['numberOfPitches'], statsapi.get('person_stats', {'personId': opp_pitcher[o_pitch], 'gamePk': gameid})['stats'][0]['splits'][1]['stat']['numberOfPitches']
        output_image = Image.new("RGB", (matrix_options.cols, matrix_options.rows))
        cubs_image_pos, opp_image_pos, batting_home_pos, batting_away_pos = (1, 0), (1, 17), (30, 6), (30, 22)
        output_image.paste(cubs_image, cubs_image_pos)
        output_image.paste(opp_image, opp_image_pos)
        canvas.SetImage(output_image.convert("RGB"), 0, 0)
        for box_h in range(17, 32):
            for box_v in range(1, 32):
                canvas.SetPixel(box_h, box_v, 255, 255, 255)
        for white_line in range(1, 32):
            if white_line <= 16:
                canvas.SetPixel(white_line, 16, 255, 255, 255)
            else:
                canvas.SetPixel(white_line, 16, 0, 0, 0)
        for out_fill in range(32, 96):
            for out_fill_v in range(1, 32):
                canvas.SetPixel(out_fill, out_fill_v, 0, 51, 102)
        for base_line in range(32, 96):
            canvas.SetPixel(base_line, 23, 255, 255, 255)
        for out_line in range(1, 32):
            canvas.SetPixel(70, out_line, 255, 255, 255)
        m = 0
        for pitcher_line in range(32, 40):
            for pitcher_line_v in range (1, 96):
                canvas.SetPixel(pitcher_line_v, pitcher_line, 255 + m, 255 + m, 255 + m)
            m -= 20
        m = 0
        for batter_line in range(40, 48):
            for batter_line_v in range(1, 96):
                canvas.SetPixel(batter_line_v, batter_line, 255 + m, 255 + m, 255 + m)
            m -= 20
        if str(statsapi.get('game', {'gamePk': gameid})['liveData']['linescore']['inningState'])[:3] == 'Top' and cubs_home == 0:
            output_image.paste(batting_image, batting_home_pos)
            for ht_h in range(7, 9):
                for ht_v in range(30, 34):
                    canvas.SetPixel(ht_v, ht_h, 255, 0, 0)
        if str(statsapi.get('game', {'gamePk': gameid})['liveData']['linescore']['inningState'])[:3] == 'End' and cubs_home == 0:
            output_image.paste(batting_image, batting_home_pos)
            for ht_h in range(7, 9):
                for ht_v in range(30, 34):
                    canvas.SetPixel(ht_v, ht_h, 255, 0, 0)
        if str(statsapi.get('game', {'gamePk': gameid})['liveData']['linescore']['inningState'])[:3] == 'Bot' and cubs_home == 0:
            output_image.paste(batting_image, batting_away_pos)
            for at_h in range(23, 25):
                for at_v in range(30, 34):
                    canvas.SetPixel(at_v, at_h, 255, 0, 0)
        if str(statsapi.get('game', {'gamePk': gameid})['liveData']['linescore']['inningState'])[:3] == 'Mid' and cubs_home == 0:
            output_image.paste(batting_image, batting_away_pos)
            for at_h in range(23, 25):
                for at_v in range(30, 34):
                    canvas.SetPixel(at_v, at_h, 255, 0, 0)
        if str(statsapi.get('game', {'gamePk': gameid})['liveData']['linescore']['inningState'])[:3] == 'Top' and cubs_home == 1:
            output_image.paste(batting_image, batting_away_pos)
            for at_h in range(23, 25):
                for at_v in range(30, 34):
                    canvas.SetPixel(at_v, at_h, 255, 0, 0)
        if str(statsapi.get('game', {'gamePk': gameid})['liveData']['linescore']['inningState'])[:3] == 'End' and cubs_home == 1:
            output_image.paste(batting_image, batting_away_pos)
            for at_h in range(23, 25):
                for at_v in range(30, 34):
                    canvas.SetPixel(at_v, at_h, 255, 0, 0)
        if str(statsapi.get('game', {'gamePk': gameid})['liveData']['linescore']['inningState'])[:3] == 'Bot' and cubs_home == 1:
            output_image.paste(batting_image, batting_home_pos)
            for ht_h in range(7, 9):
                for ht_v in range(30, 34):
                    canvas.SetPixel(ht_v, ht_h, 255, 0, 0)
        if str(statsapi.get('game', {'gamePk': gameid})['liveData']['linescore']['inningState'])[:3] == 'Mid' and cubs_home == 1:
            output_image.paste(batting_image, batting_home_pos)
            for ht_h in range(7, 9):
                for ht_v in range(30, 34):
                    canvas.SetPixel(ht_v, ht_h, 255, 0, 0)
        base = drawbases.draw_bases(canvas)
        count_color, run_color = graphics.Color(255, 255, 255), graphics.Color(0, 0, 0)
        inning_text_up = str(statsapi.get('game', {'gamePk':gameid})['liveData']['linescore']['inningState'])[:3]
        inning_text_down = str(statsapi.get('game', {'gamePk':gameid})['liveData']['linescore']['currentInningOrdinal'])
        count_text = str(statsapi.get('game_playByPlay', {'gamePk':gameid})['currentPlay']['count']['balls']) + ' - ' + str(statsapi.get('game_playByPlay', {'gamePk':gameid})['currentPlay']['count']['strikes'])
        out_text = str(statsapi.get('game', {'gamePk': gameid})['liveData']['linescore']['outs'])
        out_text_a = ' OUTS'
        pitching_text = str(statsapi.get('game_playByPlay', {'gamePk': gameid})['currentPlay']['matchup']['pitcher']['fullName'])
        graphics.DrawText(canvas, fonts['final'], 39, 31, count_color, count_text)
        graphics.DrawText(canvas, fonts['time'], 76, 9, count_color, inning_text_up)
        graphics.DrawText(canvas, fonts['time'], 76, 19, count_color, inning_text_down)
        graphics.DrawText(canvas, fonts['final'], 72, 31, count_color, out_text)
        graphics.DrawText(canvas, fonts['final'], 75, 30, count_color, out_text_a)
        graphics.DrawText(canvas, fonts['final'], 2, 46, run_color, batter_text)
        graphics.DrawText(canvas, fonts['final'], 2, 38, run_color, pitching_text)
        if cubs_home == 1 and str(statsapi.get('game', {'gamePk': gameid})['liveData']['linescore']['inningState'])[:3] == 'Bot':
            pitch_count_text = 'P:' + str(cubs_pitch_count)
        else:
            pitch_count_text = 'P:' + str(opp_pitch_count)
        if cubs_pitch_count > 100 or opp_pitch_count > 100:
            graphics.DrawText(canvas, fonts['final'], (96 - (len(pitch_count_text) + 14)), 38, run_color, pitch_count_text)
        else:
            graphics.DrawText(
            canvas, fonts['final'], (96 - (len(pitch_count_text) + 12)), 38, run_color, pitch_count_text)
        is_on_base = statsapi.get('game', {'gamePk': gameid})['liveData']['linescore']['offense']
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
        if home_team == 112:
            if sched[a]['home_score'] >= 10:
                graphics.DrawText(canvas, fonts['score'], 23, 13, run_color, str(sched[a]['home_score']))
            else:
                graphics.DrawText(canvas, fonts['score'], 20, 13, run_color, str(sched[a]['home_score']))
            if sched[a]['away_score'] >= 10:
                graphics.DrawText(canvas, fonts['score'], 23, 30, run_color, str(sched[a]['away_score']))
            else:
                graphics.DrawText(canvas, fonts['score'], 20, 30, run_color, str(sched[a]['away_score']))
            cubs_score = sched[a]['home_score']
            opp_score = sched[a]['away_score']
        else:
            if sched[a]['home_score'] >= 10:
                graphics.DrawText(canvas, fonts['score'], 23, 13, run_color, str(sched[a]['away_score']))
            else:
                graphics.DrawText(canvas, fonts['score'], 20, 13, run_color, str(sched[a]['away_score']))
            if sched[a]['away_score'] >= 10:
                graphics.DrawText(canvas, fonts['score'], 23, 30, run_color, str(sched[a]['home_score']))
            else:
                graphics.DrawText(canvas, fonts['score'], 20, 30, run_color, str(sched[a]['home_score']))
            cubs_score, opp_score = sched[a]['away_score'], sched[a]['home_score']
        if cubs_score > cubs_run:
            run_scored(canvas)
            cubs_run = cubs_score
        if opp_score > opp_run:
            opp_scored(canvas, opp_image)
            opp_run = opp_score
        canvas = matrix.SwapOnVSync(canvas)
        time.sleep(5)
    #except:
    #    print('encountered an error in game_on...')
    #    time.sleep(10)
    #    error_correction(canvas)

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
        scored_color = graphics.Color(255, 233, 0)
        scored_shadow_color = graphics.Color(255, 255, 255)
        graphics.DrawText(canvas, fonts['score'], 35, 19, scored_shadow_color, 'RUN')
        graphics.DrawText(canvas, fonts['score'], 21, 35, scored_shadow_color, 'SCORED')
        graphics.DrawText(canvas, fonts['score'], 36, 20, scored_color, 'RUN')
        graphics.DrawText(canvas, fonts['score'], 22, 36, scored_color, 'SCORED')
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
        output_image = Image.new("RGB", (matrix_options.cols, matrix_options.rows))
        output_image.paste(opp_image, opp_image_pos)
        opp_image_pos_left = (x-119, 12)
        output_image.paste(opp_image_left, opp_image_pos_left)
        canvas.SetImage(output_image.convert("RGB"), 0, 0)
        scored_color = graphics.Color(255, 0, 0)
        scored_shadow_color = graphics.Color(255, 255, 255)
        graphics.DrawText(canvas, fonts['score'], x-90, 30,scored_shadow_color, 'RUN SCORED')
        graphics.DrawText(canvas, fonts['score'], x-91, 29,scored_color, 'RUN SCORED')
        canvas = matrix.SwapOnVSync(canvas)

def game_over(a, canvas, gameid, image, lineup, batting_image, sched, opp_image, cubs_image):
    try:
        home_team = sched[a]['home_id']
        current_date = pendulum.now().format('YYYY-MM-DD') #datetime.today().strftime('%Y-%m-%d')
        current_time = pendulum.now().format('HH:mm')
        canvas.Clear()
        over_date = current_date
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
        cubs_image_pos = (1, 1)
        opp_image_pos = (68, 1)
        cubs_image = cubs_image.resize((26, 26))
        opp_image = opp_image.resize((26, 26))
        output_image.paste(cubs_image, cubs_image_pos)
        output_image.paste(opp_image, opp_image_pos)
        canvas.SetImage(output_image.convert("RGB"), 0, 0)
        shadow_color = graphics.Color(0, 0, 255)
        run_color = graphics.Color(255, 255, 255)
        final_color = graphics.Color(255, 233, 0)
        graphics.DrawText(canvas, fonts['inning'], 36, 11, final_color, 'GAME')
        graphics.DrawText(canvas, fonts['inning'], 36, 21, final_color, 'OVER')
        graphics.DrawText(canvas, fonts['final'], 29, 29, final_color, 'INNINGS:' + str(innings))
        graphics.DrawText(canvas, fonts['final'], 29, 35, final_color, 'HITS:   ' + str(hits))
        graphics.DrawText(canvas, fonts['final'], 29, 41, final_color, 'RUNS:   ' + str(runs))
        graphics.DrawText(canvas, fonts['final'], 29, 47, final_color, 'ERRORS: ' + str(errors))
        if home_team == 112:
            if sched[a]['home_score'] >= 10:
                graphics.DrawText(canvas, fonts['final_score'], 5, 44, shadow_color, str(sched[a]['home_score']))
                graphics.DrawText(canvas, fonts['final_score'], 6, 45, run_color, str(sched[a]['home_score']))
            else:
                graphics.DrawText(canvas, fonts['final_score'], 9, 44, shadow_color, str(sched[a]['home_score']))
                graphics.DrawText(canvas, fonts['final_score'], 10, 45, run_color, str(sched[a]['home_score']))
            if sched[a]['away_score'] >= 10:
                graphics.DrawText(canvas, fonts['final_score'], 70, 44, shadow_color, str(sched[a]['away_score']))
                graphics.DrawText(canvas, fonts['final_score'], 71, 45, run_color, str(sched[a]['away_score']))
            else:
                graphics.DrawText(canvas, fonts['final_score'], 75, 44, shadow_color, str(sched[a]['away_score']))
                graphics.DrawText(canvas, fonts['final_score'], 76, 45, run_color, str(sched[a]['away_score']))
            canvas = matrix.SwapOnVSync(canvas)
        else:
            if sched[a]['away_score'] >= 10:
                graphics.DrawText(canvas, fonts['final_score'], 5, 44, shadow_color, str(sched[a]['away_score']))
                graphics.DrawText(canvas, fonts['final_score'], 6, 45, run_color, str(sched[a]['away_score']))
            else:
                graphics.DrawText(canvas, fonts['final_score'], 9, 44, shadow_color, str(sched[a]['away_score']))
                graphics.DrawText(canvas, fonts['final_score'], 10, 45, run_color, str(sched[a]['away_score']))
            if sched[a]['home_score'] >= 10:
                graphics.DrawText(canvas, fonts['final_score'], 70, 44, shadow_color, str(sched[a]['home_score']))
                graphics.DrawText(canvas, fonts['final_score'], 71, 45, run_color, str(sched[a]['home_score']))
            else:
                graphics.DrawText(canvas, fonts['final_score'], 75, 44, shadow_color, str(sched[a]['home_score']))
                graphics.DrawText(canvas, fonts['final_score'], 76, 45, run_color, str(sched[a]['home_score']))
            canvas = matrix.SwapOnVSync(canvas)
        while over_date == current_date and current_time != '04:00':
            current_date = pendulum.now().format('YYYY-MM-DD')
            current_time = pendulum.now().format('HH:MM')
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
    double_header, a = 0, 0
    canvas.Clear()
    sched = schedule.get_sched()
    try:
        print(sched[1])
        double_header = 1
        if double_header == 1 and sched[a]['status'] == 'Final':
            a = 1
    except:
        a = 0
    print(sched[a])
    gameid = sched[a]['game_id']
    lineup = schedule.get_lineup(gameid)
    for x in statsapi.get('game', {'gamePk':gameid})['gameData']['teams']:
        if statsapi.get('game', {'gamePk':gameid})['gameData']['teams'][x]['abbreviation'] != 'CHC':
            opp_abv = statsapi.get('game', {'gamePk':gameid})['gameData']['teams'][x]['abbreviation']
    opp_image_path, cubs_image_path, batting_image_path = './logos/' + opp_abv + '.png', './logos/cubs.png', './baseball.png'
    opp_image, cubs_image, batting_image = Image.open(opp_image_path), Image.open(cubs_image_path), Image.open(batting_image_path)
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

fonts = load_fonts()

startup(canvas)
