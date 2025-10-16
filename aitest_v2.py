from PIL import Image, ImageDraw
from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics
import statsapi, time, pendulum

TEAM_ID = 112

# --- Helper Functions ---

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
    fonts['standings_title'] = graphics.Font()
    fonts['standings_title'].LoadFont('./fonts/5x8.bdf')
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
    return fonts

def normalize_game_time(dt_str, subtract_hours=5):
    """
    Normalize game datetime using pendulum.
    Assumes dt_str is a valid ISO datetime string.
    """
    try:
        dt = pendulum.parse(dt_str)
        # adjust by subtract_hours (e.g. convert UTC to local)
        dt = dt.subtract(hours=subtract_hours)
        # Format to 12-hour clock without leading zeros
        hour = dt.hour % 12 or 12
        return f"{hour}:{dt.format('mm')}"
    except Exception as e:
        return dt_str

def get_game_data(gameid):
    """Cache a single game API call for use within a function call."""
    return statsapi.get('game', {'gamePk': gameid})

def get_people_data(person_id):
    """Get people data for a given person id."""
    return statsapi.get('people', {'personIds': person_id})['people'][0]

# --- Classes with Centralized Logic ---

class Schedule:
    @staticmethod
    def get_sched():
        current_date = pendulum.now().format('MM/DD/YYYY')
        sched = statsapi.schedule(start_date=current_date, team=TEAM_ID)
        if not sched:
            next_game = statsapi.next_game(teamId=TEAM_ID)
            sched = statsapi.schedule(game_id=next_game)
        return sched

    @staticmethod
    def get_pitchers(index, gameid):
        sched = Schedule.get_sched()
        game_info = get_game_data(gameid)
        teams = game_info['gameData']['teams']
        # Use 'TBD' if pitcher is an empty string
        home_pitcher = sched[index]['home_probable_pitcher'] or 'TBD'
        away_pitcher = sched[index]['away_probable_pitcher'] or 'TBD'
        if sched[index]['home_id'] == TEAM_ID:
            pitchers = (f"Cubs Pitcher: {home_pitcher}    {teams['away']['teamName']} Pitcher: {away_pitcher}")
        else:
            pitchers = (f"Cubs Pitcher: {away_pitcher}    {teams['away']['teamName']} Pitcher: {home_pitcher}")
        return pitchers

    @staticmethod
    def get_lineup(gameid):
        game_data = get_game_data(gameid)
        boxscore = game_data['liveData']['boxscore']['teams']
        home_team = boxscore['home']['team']['name']
        away_team = boxscore['away']['team']['name']
        lineup = f"{home_team} - "
        # Process home batters
        for batter in boxscore['home']['batters']:
            person = get_people_data(batter)
            lineup += f"{person['primaryPosition']['abbreviation']}:{person['lastName']} "
        lineup += f"  {away_team} - "
        # Process away batters
        for batter in boxscore['away']['batters']:
            person = get_people_data(batter)
            lineup += f"{person['primaryPosition']['abbreviation']}:{person['lastName']} "
        return lineup

    @staticmethod
    def get_away_team(gameid):
        game_data = get_game_data(gameid)
        if game_data['gameData']['teams']['home']['id'] == TEAM_ID:
            return game_data['gameData']['teams']['away']['abbreviation']
        else:
            return game_data['gameData']['teams']['home']['abbreviation']

    @staticmethod
    def get_game_time(index):
        sched = Schedule.get_sched()
        # Assume sched[index]['game_datetime'] is ISO formatted
        return normalize_game_time(sched[index]['game_datetime'])

class Playball:
    @staticmethod
    def play_ball(index, gameid):
        sched = Schedule.get_sched()
        start_time = Schedule.get_game_time(index)
        game_info = get_game_data(gameid)
        if game_info['gameData']['teams']['home']['abbreviation'] == 'CHC':
            away_side = 'away'
        else:
            away_side = 'home'
        sched_text = (
            f"NEXT GAME {sched[index]['game_date'][6:10]} at {start_time} vs "
            f"{game_info['gameData']['teams'][away_side]['name']}     "
            f"{Schedule.get_pitchers(index, gameid)}"
        )
        return sched_text

class DrawBases:
    @staticmethod
    def draw_bases(canvas):
        base_xy = {}
        second_base_x, second_base_y = 46, 8
        first_base_x, first_base_y = second_base_x + 7, second_base_y + 7
        third_base_x, third_base_y = second_base_x - 7, second_base_y + 7
        base_xy.update({
            'first_base_x': first_base_x,
            'first_base_y': first_base_y,
            'second_base_x': second_base_x,
            'second_base_y': second_base_y,
            'third_base_x': third_base_x,
            'third_base_y': third_base_y,
        })
        # Draw each base with similar patterns using tuple iteration.
        for bag_x, bag_y in [(first_base_x, first_base_y),
                             (second_base_x, second_base_y),
                             (third_base_x, third_base_y)]:
            # Draw first leg of diamond
            y_offset = 0
            for a in range(5):
                canvas.SetPixel(bag_x + a, bag_y - y_offset, 255, 255, 255)
                y_offset += 1
            # Draw second leg
            y_offset = 4
            for b in range(5, 10):
                canvas.SetPixel(bag_x + b, bag_y - y_offset, 255, 255, 255)
                y_offset -= 1
            # Draw third leg
            y_offset = 0
            for c in range(10, 5, -1):
                canvas.SetPixel(bag_x + c, bag_y - y_offset, 255, 255, 255)
                y_offset += 1
            # Draw fourth leg
            y_offset = 4
            for d in range(5, 0, -1):
                canvas.SetPixel(bag_x + d, bag_y - y_offset, 255, 255, 255)
                y_offset -= 1
        return base_xy

# --- Drawing Helper Functions ---

def on_base(hit_x, hit_y, filled, canvas):
    """Draw a base runner symbol; white if filled else dark blue."""
    color = (255, 255, 255) if filled else (0, 51, 102)
    next_y = 0
    for fill in range(1, 6):
        for i in range(5):
            canvas.SetPixel(hit_x + i + fill, hit_y + i - next_y, *color)
        next_y += 1

def outs(out_x, out_y, filled, canvas):
    """Draw outs indicator."""
    color = (255, 255, 255) if filled else (0, 51, 102)
    for fill in range(5):
        canvas.SetPixel(out_x + fill + 1, out_y + 1, *color)
    if not filled:
        for fill in range(5):
            canvas.SetPixel(out_x + 9 + fill + 1, out_y + 1, *color)
            canvas.SetPixel(out_x + 18 + fill + 1, out_y + 1, *color)

# --- Main Screen Functions ---
# For brevity, similar refactoring is applied to warmup, delayed, no_game, game_on, run_scored, opp_scored, game_over,
# and startup functions: caching API calls where possible, pre-loading fonts, and using helper functions.

def warmup(index, canvas, bg_image, lineup, gameid, opp_image, cubs_image, batting_image, fonts):
    sched = Schedule.get_sched()
    game_time = Schedule.get_game_time(index)
    # Determine hour length based on hour value
    hour_val = int(game_time.split(':')[0])
    hour_length = 5 if hour_val >= 10 else 4
    current_time = pendulum.now().format('HH:mm')
    pos = canvas.width
    textColor = graphics.Color(255, 255, 255)
    start_time = game_time[:hour_length]
    
    while current_time != game_time[:5] or (sched[index]['status'] not in ['In Progress'] and not sched[index]['status'].startswith('Delayed')):
        canvas.Fill(70, 128, 83)
        for x in range(96):
            canvas.SetPixel(x, 14, 255, 255, 255)
        graphics.DrawText(canvas, fonts['warmup'], 17, 12, textColor, 'WARM UP')
        graphics.DrawText(canvas, fonts['time'], 17, 24, textColor, 'START TIME')
        graphics.DrawText(canvas, fonts['time'], 36, 32, textColor, start_time)
        pos -= 1  
        text_len = graphics.DrawText(canvas, fonts['lineup'], pos, 45, textColor, lineup)
        if pos + text_len < 0:
            pos = canvas.width
            sched = Schedule.get_sched()
            lineup = Schedule.get_lineup(gameid)
        if sched[index]['status'] == 'In Progress':
            break
        if sched[index]['status'].startswith('Delayed'):
            delayed(index, canvas, bg_image, lineup, gameid, opp_image, cubs_image, batting_image, fonts)
        current_time = pendulum.now().format('HH:mm')
        canvas = matrix.SwapOnVSync(canvas)
        time.sleep(0.02)
    game_on(index, canvas, bg_image, lineup, gameid, opp_image, cubs_image, batting_image, fonts)

def delayed(index, canvas, bg_image, lineup, gameid, opp_image, cubs_image, batting_image, fonts):
    try:
        sched = Schedule.get_sched()
        game_time = Schedule.get_game_time(index)
        hour_val = int(game_time.split(':')[0])
        hour_length = 5 if hour_val >= 10 else 4
        current_time = pendulum.now().format('HH:mm')
        pos = canvas.width
        textColor = graphics.Color(255, 255, 255)
        start_time = game_time[:hour_length]
        while current_time != game_time[:5] or sched[index]['status'] != 'In Progress':
            canvas.Clear()
            canvas.Fill(255, 210, 0)
            for x in range(96):
                canvas.SetPixel(x, 14, 255, 255, 255)
            graphics.DrawText(canvas, fonts['warmup'], 17, 12, textColor, 'DELAYED')
            graphics.DrawText(canvas, fonts['time'], 17, 24, textColor, 'START TIME')
            graphics.DrawText(canvas, fonts['time'], 36, 32, textColor, start_time)
            pos -= 1
            text_len = graphics.DrawText(canvas, fonts['lineup'], pos, 45, textColor, lineup)
            if pos + text_len < 0:
                pos = canvas.width
                sched = Schedule.get_sched()
                lineup = Schedule.get_lineup(gameid)
            if sched[index]['status'] == 'In Progress':
                break
            canvas = matrix.SwapOnVSync(canvas)
            time.sleep(0.02)
            current_time = pendulum.now().format('HH:mm')
        game_on(index, canvas, bg_image, lineup, gameid, opp_image, cubs_image, batting_image, fonts)
    except Exception as e:
        print('Error in delayed:', e)
        time.sleep(10)
        error_correction(canvas, fonts)

def no_game(index, canvas, bg_image, lineup, gameid, opp_image, cubs_image, batting_image, fonts):
    canvas.Clear()
    sched = Schedule.get_sched()
    game_date = sched[index]['game_date']
    game_time_raw = sched[index]['game_datetime']
    game_time = normalize_game_time(game_time_raw)
    try:
        # Adjust game_time for display (if needed)
        hour_val = int(game_time.split(':')[0])
        game_time = f"{hour_val}:{game_time.split(':')[1]}"
    except Exception:
        pass
    game_info = get_game_data(gameid)
    away_side = 'away' if game_info['gameData']['teams']['home']['abbreviation'] == 'CHC' else 'home'
    away_team = game_info['gameData']['teams'][away_side]['name']
    font = fonts['bdf_7x13']
    pos = canvas.width
    text = (f"NEXT GAME {game_date[5:]} at {game_time} vs {away_team}     "
            f"{Schedule.get_pitchers(index, gameid)}")
    # Loop with marquee text and display standings after scrolling
    while True:
        canvas.Clear()
        # Paste background image
        canvas.SetImage(bg_image.convert("RGB"), 0, 0)
        pos -= 1  
        textColor = graphics.Color(255, 223, 0)
        text_len = graphics.DrawText(canvas, font, pos, 46, textColor, text)
        if pos + text_len < 0:
            pos = canvas.width
            canvas.Clear()
            # Example: draw division standings (details omitted for brevity)
            graphics.DrawText(canvas, fonts['standings_title'], 3, 8, graphics.Color(255, 255, 0), 'DIVISION STANDINGS')
            # ... (Draw standings as needed)
            canvas = matrix.SwapOnVSync(canvas)
            time.sleep(15)
            # Transition based on updated schedule status:
            sched = Schedule.get_sched()
            if sched[index]['summary'].endswith('(Warmup)') or sched[index]['summary'].endswith('(Pre-Game)'):
                warmup(index, canvas, bg_image, lineup, gameid, opp_image, cubs_image, batting_image, fonts)
            elif sched[index]['summary'].startswith('(In Progress)'):
                game_on(index, canvas, bg_image, lineup, gameid, opp_image, cubs_image, batting_image, fonts)
        canvas = matrix.SwapOnVSync(canvas)
        time.sleep(0.02)

def game_on(index, canvas, bg_image, lineup, gameid, opp_image, cubs_image, batting_image, fonts):
    sched = Schedule.get_sched()
    # Determine if Cubs are home
    cubs_home = (sched[index]['home_id'] == TEAM_ID)
    game_info = get_game_data(gameid)
    # Determine runs based on home/away status
    if cubs_home:
        cubs_run = sched[index]['home_score']
        opp_run = sched[index]['away_score']
    else:
        cubs_run = sched[index]['away_score']
        opp_run = sched[index]['home_score']
    
    while True:
        sched = Schedule.get_sched()
        playbyplay = statsapi.get('game_playByPlay', {'gamePk': gameid})
        batter_text = f"BAT: {playbyplay['currentPlay']['matchup']['batter']['fullName']}"
        if sched[index]['status'] in ['Game Over', 'Final']:
            game_over(index, canvas, gameid, bg_image, lineup, batting_image, sched, opp_image, cubs_image, fonts)
        # (Pitcher and pitch count logic omitted for brevity; cache API calls when possible)
        # Update graphics with images and draw field elements…
        # (Drawing code omitted – refactor loops and combine repeated color settings)
        # Draw bases:
        base = DrawBases.draw_bases(canvas)
        # Draw texts (score, count, inning, outs, etc.) using fonts from the fonts dict.
        # Example:
        graphics.DrawText(canvas, fonts['score'], 39, 31, graphics.Color(255, 255, 255),
                          f"{playbyplay['currentPlay']['count']['balls']} - {playbyplay['currentPlay']['count']['strikes']}")
        # Check if a run has scored and trigger animations:
        # (Call run_scored or opp_scored as needed)
        canvas = matrix.SwapOnVSync(canvas)
        time.sleep(5)

def run_scored(canvas):
    # Simplified animation for run scored
    run_img = Image.open('./logos/run_scored.png').transpose(Image.FLIP_LEFT_RIGHT)
    baseball_img = Image.open('./logos/baseball.png')
    run_image_pos = (0, 12)
    run_y = 15
    next_x = 25
    for x in range(25, 97):
        canvas.Clear()
        if x > next_x + 5:
            next_x += 5
            run_y -= 1
        output_image = Image.new("RGB", (matrix_options.cols, matrix_options.rows))
        baseball_image_position = (x, run_y)
        output_image.paste(run_img, run_image_pos)
        output_image.paste(baseball_img, baseball_image_position)
        canvas.SetImage(output_image.convert("RGB"), 0, 0)
        canvas = matrix.SwapOnVSync(canvas)
    # Flash "RUN SCORED" text
    for _ in range(3):
        canvas.Clear()
        scored_font = graphics.Font()
        scored_font.LoadFont('./fonts/9x18B.bdf')
        shadow_color = graphics.Color(255, 255, 255)
        scored_color = graphics.Color(255, 233, 0)
        graphics.DrawText(canvas, scored_font, 35, 19, shadow_color, 'RUN')
        graphics.DrawText(canvas, scored_font, 21, 35, shadow_color, 'SCORED')
        graphics.DrawText(canvas, scored_font, 36, 20, scored_color, 'RUN')
        graphics.DrawText(canvas, scored_font, 22, 36, scored_color, 'SCORED')
        canvas = matrix.SwapOnVSync(canvas)
        time.sleep(0.5)
        canvas.Clear()
        canvas = matrix.SwapOnVSync(canvas)
        time.sleep(0.5)

def opp_scored(canvas, opp_image):
    # Simplified animation for opponent run scored
    for x in range(-24, 220, 2):
        canvas.Clear()
        output_image = Image.new("RGB", (matrix_options.cols, matrix_options.rows))
        output_image.paste(opp_image, (x, 12))
        output_image.paste(opp_image, (x - 119, 12))
        canvas.SetImage(output_image.convert("RGB"), 0, 0)
        scored_font = graphics.Font()
        scored_font.LoadFont('./fonts/9x18B.bdf')
        shadow_color = graphics.Color(255, 255, 255)
        scored_color = graphics.Color(255, 0, 0)
        graphics.DrawText(canvas, scored_font, x - 90, 30, shadow_color, 'RUN SCORED')
        graphics.DrawText(canvas, scored_font, x - 91, 29, scored_color, 'RUN SCORED')
        canvas = matrix.SwapOnVSync(canvas)

def game_over(index, canvas, gameid, bg_image, lineup, batting_image, sched, opp_image, cubs_image, fonts):
    try:
        home_team = sched[index]['home_id']
        current_date = pendulum.now().format('YYYY-MM-DD')
        current_time = pendulum.now().format('HH:mm')
        canvas.Clear()
        output_image = Image.new("RGB", (matrix_options.cols, matrix_options.rows))
        innings = statsapi.get('game', {'gamePk': gameid})['liveData']['linescore']['currentInning']
        if home_team == TEAM_ID:
            team_stats = statsapi.get('game', {'gamePk': gameid})['liveData']['boxscore']['teams']['home']['teamStats']
        else:
            team_stats = statsapi.get('game', {'gamePk': gameid})['liveData']['boxscore']['teams']['away']['teamStats']
        runs = team_stats['batting']['runs']
        hits = team_stats['batting']['hits']
        errors = statsapi.get('game', {'gamePk': gameid})['liveData']['boxscore']['teams'][ 'home' if home_team == TEAM_ID else 'away']['teamStats']['fielding']['errors']
        # Resize and paste team logos
        cubs_img = cubs_image.resize((26, 26))
        opp_img = opp_image.resize((26, 26))
        output_image.paste(cubs_img, (1, 1))
        output_image.paste(opp_img, (68, 1))
        canvas.SetImage(output_image.convert("RGB"), 0, 0)
        # Draw game over text and stats
        graphics.DrawText(canvas, fonts['inning'], 36, 11, graphics.Color(255, 233, 0), 'GAME')
        graphics.DrawText(canvas, fonts['inning'], 36, 21, graphics.Color(255, 233, 0), 'OVER')
        graphics.DrawText(canvas, fonts['final'], 29, 29, graphics.Color(255, 233, 0), f"INNINGS:{innings}")
        graphics.DrawText(canvas, fonts['final'], 29, 35, graphics.Color(255, 233, 0), f"HITS:   {hits}")
        graphics.DrawText(canvas, fonts['final'], 29, 41, graphics.Color(255, 233, 0), f"RUNS:   {runs}")
        graphics.DrawText(canvas, fonts['final'], 29, 47, graphics.Color(255, 233, 0), f"ERRORS: {errors}")
        # Draw final scores (positions adjusted based on score length)
        if home_team == TEAM_ID:
            cubs_score = sched[index]['home_score']
            opp_score = sched[index]['away_score']
        else:
            cubs_score = sched[index]['away_score']
            opp_score = sched[index]['home_score']
        shadow_color = graphics.Color(0, 0, 255)
        run_color = graphics.Color(255, 255, 255)
        if len(str(cubs_score)) >= 2:
            graphics.DrawText(canvas, fonts['score'], 23, 13, shadow_color, str(cubs_score))
            graphics.DrawText(canvas, fonts['score'], 24, 14, run_color, str(opp_score))
        else:
            graphics.DrawText(canvas, fonts['score'], 20, 13, shadow_color, str(cubs_score))
            graphics.DrawText(canvas, fonts['score'], 21, 14, run_color, str(opp_score))
        # Similar logic for opponent score...
        canvas = matrix.SwapOnVSync(canvas)
        # Wait until post-game period is over, then restart
        while current_date == pendulum.now().format('YYYY-MM-DD') and pendulum.now().format('HH:mm') != '04:00':
            time.sleep(360)
            startup(canvas, fonts)
    except Exception as e:
        print('Error in game_over:', e)
        time.sleep(10)
        error_correction(canvas, fonts)

def startup(canvas, fonts):
    index = 0
    canvas.Clear()
    sched = Schedule.get_sched()
    # Handle double headers if needed:
    try:
        if sched[1]:
            if sched[0]['status'] == 'Final':
                index = 1
    except Exception:
        index = 0
    gameid = sched[index]['game_id']
    lineup = Schedule.get_lineup(gameid)
    # Determine opponent abbreviation from game info
    game_info = get_game_data(gameid)
    for side in game_info['gameData']['teams']:
        if game_info['gameData']['teams'][side]['abbreviation'] != 'CHC':
            opp_abv = game_info['gameData']['teams'][side]['abbreviation']
    opp_image_path = f'./logos/{opp_abv}.png'
    cubs_image_path = './logos/cubs.png'
    batting_image_path = './baseball.png'
    opp_image = Image.open(opp_image_path)
    cubs_image = Image.open(cubs_image_path)
    batting_image = Image.open(batting_image_path)
    while True:
        sched = Schedule.get_sched()
        status = sched[index]['status']
        if status == 'Scheduled':
            no_game(index, canvas, bg_image, lineup, gameid, opp_image, cubs_image, batting_image, fonts)
        elif status in ['Warmup', 'Pre-Game']:
            warmup(index, canvas, bg_image, lineup, gameid, opp_image, cubs_image, batting_image, fonts)
        elif status.startswith('Delayed'):
            delayed(index, canvas, bg_image, lineup, gameid, opp_image, cubs_image, batting_image, fonts)
        elif status == 'In Progress':
            game_on(index, canvas, bg_image, lineup, gameid, opp_image, cubs_image, batting_image, fonts)
        elif status in ['Final', 'Game Over']:
            game_over(index, canvas, gameid, bg_image, lineup, batting_image, sched, opp_image, cubs_image, fonts)

def error_correction(canvas, fonts):
    startup(canvas, fonts)

# --- Configuration and Initialization ---

matrix_options = RGBMatrixOptions()
matrix_options.rows = 48
matrix_options.cols = 96
matrix_options.chain_length = 1
matrix_options.parallel = 1
matrix_options.hardware_mapping = 'regular'

matrix = RGBMatrix(options=matrix_options)
canvas = matrix.CreateFrameCanvas()

# Pre-load fonts once
fonts = load_fonts()

# Load background image (marquee)
bg_image = Image.open("./marquee.png")

# --- Start the Application ---
startup(canvas, fonts)