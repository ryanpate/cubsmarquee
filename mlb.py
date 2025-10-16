import time, csv
from datetime import datetime
from luma.led_matrix.device import max7219
from luma.core.interface.serial import spi, noop
from luma.core.virtual import viewport, sevensegment
import statsapi

serial = spi(port=0, device=0, gpio=noop())
device = max7219(serial, cascaded=2)
seg = sevensegment(device)

playing = False
run_scored = 0

def get_sched():
    current_date = datetime.today().strftime('%m/%d/%Y')
    sched = statsapi.schedule(start_date=current_date, team=112)
    if sched == []:
        next_game = statsapi.next_game(teamId=112)
        sched = statsapi.schedule(game_id=next_game)
    return sched

def get_pitchers(sched):
    if sched[0]['home_id'] == 112:
        pitchers = ('Cubs pitcher: ' + sched[0]['home_probable_pitcher'] + '    ' + 'Opponent pither: ' + sched[0]['away_probable_pitcher'])
    else:
        pitchers = ('Cubs pitcher: ' + sched[0]['away_probable_pitcher'] + '    ' + 'Opponent pither: ' + sched[0]['home_probable_pitcher'])
    return pitchers

def get_away_team(gameid):
    if statsapi.get('game', {'gamePk':gameid})['gameData']['teams']['home']['id'] == 112:
        away_team = 'away'
        statsapi.get('game', {'gamePk':gameid})['gameData']['teams']['away']['abbreviation']
    else:
        away_team = 'home'
        statsapi.get('game', {'gamePk':gameid})['gameData']['teams']['home']['abbreviation']
    return away_team

def show_message_vp(msg, delay=0.15):
    padding = ' ' * 8
    msg = padding + msg + padding
    for i in range(len(msg) - 7):
        seg.text = msg[i:i + 8] + 'GO CUBS'
        time.sleep(delay)

def play_ball(gameid):
    current_date = datetime.today().strftime('%m/%d/%Y')
    sched = get_sched()
    game_time = sched[0]['game_datetime'][-9:19]
    game_day = sched[0]['game_date'][-2:]
    current_time = datetime.now().strftime('%H:%M:%S')
    current_hour = current_time[:2]
    if game_time[:2] == '00':
        game_time = '24:' + game_time[3:]
    game_time = str(int(game_time[:2]) - 5) + game_time[2:]
    if int(game_time[:2]) > 12:
        game_time = str(int(game_time[:2]) - 12) + game_time[2:]
    if game_time[:1] == '0':
        game_hour = game_time[:2]
    else:
        game_hour = game_time[:1]
    if game_day != current_date[3:5] or int(game_hour) > int(current_hour) - 12:
        if game_time[:1] == '0':
            show_message_vp('NEXT GAME ' + sched[0]['game_date'][6:10] + ' at ' + game_time[:4] + ' vs '  + statsapi.get('game', {'gamePk':gameid})['gameData']['teams'][get_away_team(gameid)]['name'] + '     ' + (get_pitchers(sched)))            
        else:
            show_message_vp('NEXT GAME ' + sched[0]['game_date'][6:10] + ' at ' + game_time[:4] + ' vs '  + statsapi.get('game', {'gamePk':gameid})['gameData']['teams'][get_away_team(gameid)]['name'] + '     ' + (get_pitchers(sched)))
        playing = False
    else:
        playing = True
    return playing

def game_over(sched, seg, current_date, game_day):
    while current_date[3:5] == game_day:
        current_date = datetime.today().strftime('%m/%d/%Y')
        score_data(sched, seg, run_scored, 1)
        time.sleep(3)
        seg.text = '  OVER    GAME  '
        time.sleep(3)

def score_data(sched, seg, run_scored, final):
    if sched[0]['home_id'] == 112:
        cubs_score = str(sched[0]['home_score'])
        opp_score = str(sched[0]['away_score'])
        if int(run_scored) < int(cubs_score) and final == 0:
            for x in range(3):
                show_message_vp('--- RUN SCORED ---')
        cubs_space = 8 - len('CUBS' + cubs_score)
        opp_space = 8 - len(statsapi.get('game', {'gamePk':gameid})['gameData']['teams'][get_away_team(gameid)]['abbreviation'] + opp_score)
        seg.text = (statsapi.get('game', {'gamePk':gameid})['gameData']['teams'][get_away_team(gameid)]['abbreviation'] + (' ' * opp_space + opp_score) + 'CUBS' + (' ' * cubs_space) + cubs_score)
        run_scored = cubs_score
    else:
        cubs_score = str(sched[0]['away_score'])
        opp_score = str(sched[0]['home_score'])
        if int(run_scored) < int(cubs_score) and final == 0:
            for x in range(3):
                show_message_vp('--- RUN SCORED ---')
        cubs_space = 8 - len('CUBS' + cubs_score)
        opp_space = 8 - len(statsapi.get('game', {'gamePk':gameid})['gameData']['teams'][get_away_team(gameid)]['abbreviation'] + opp_score)
        seg.text = (statsapi.get('game', {'gamePk':gameid})['gameData']['teams'][get_away_team(gameid)]['abbreviation'] + (' ' * opp_space + opp_score) + 'CUBS' + (' ' * cubs_space) + cubs_score)
        run_scored = cubs_score
    return run_scored

while True:
    sched = get_sched()
    gameid = sched[0]['game_id']
    game_day = sched[0]['game_date'][-2:]
    current_date = datetime.today().strftime('%m/%d/%Y')
    current_time = datetime.now().strftime('%H:%M:%S')
    if current_date[3:5] != game_day:
        playing == False
    if playing == False:
        while playing == False:
            playing = play_ball(gameid)
    sched = get_sched()
    gameid = sched[0]['game_id']
    game_day = sched[0]['game_date'][-2:]
    if sched[0]['summary'][-7:] == '(Final)' or sched[0]['summary'][-11:] == '(Game Over)' and current_date[3:5] == game_day:
        run_scored = 0
        game_over(sched, seg, current_date, game_day)
    run_scored = score_data(sched, seg, run_scored, 0)
    time.sleep(3)
    if sched[0]['status'] == 'Pre-Game' or sched[0]['status'] == 'Warmup':
        seg.text = '  GAME    PRE-  '
        time.sleep(3)
    if sched[0]['status'] == 'In Progress':
        if sched[0]['inning_state'] == 'Bottom':
            inning_state = 'B'
        elif sched[0]['inning_state'] == 'Top':
            inning_state = 'T'
        elif sched[0]['inning_state'] == 'End':
            inning_state = 'E'
        else:
            inning_state = 'M'
        if len(str(sched[0]['current_inning'])) > 1:
            space = 4
        else:
            space = 3
        seg.text = 'OUTS   ' + str(statsapi.get('game', {'gamePk':gameid})['liveData']['linescore']['outs']) + 'ING ' + inning_state + statsapi.get('game', {'gamePk':gameid})['liveData']['linescore']['currentInningOrdinal']
        current_date = datetime.today().strftime('%m/%d/%Y')
        time.sleep(2)
        seg.text = str(statsapi.get('game', {'gamePk':gameid})['liveData']['linescore']['strikes']) + ' STRIKE' + str(statsapi.get('game', {'gamePk':gameid})['liveData']['linescore']['balls']) + '  BALLS'
        time.sleep(1)