import statsapi
from datetime import datetime

def get_sched():
    current_date = datetime.today().strftime('%m/%d/%Y')
    sched = statsapi.schedule(start_date=current_date, team=112)
    if sched == []:
        next_game = statsapi.next_game(teamId=112)
        sched = statsapi.schedule(game_id=next_game)
    return sched

def get_pitchers():
    sched = get_sched()
    if sched[0]['home_id'] == 112:
        pitchers = ('Cubs Pitcher: ' + sched[0]['home_probable_pitcher'] + '    ' + 'Opponent Pitcher: ' + sched[0]['away_probable_pitcher'])
    else:
        pitchers = ('Cubs Pitcher: ' + sched[0]['away_probable_pitcher'] + '    ' + 'Opponent Pitcher: ' + sched[0]['home_probable_pitcher'])
    return pitchers

def get_lineup():
    sched = get_sched()
    gameid = sched[0]['game_id']
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
