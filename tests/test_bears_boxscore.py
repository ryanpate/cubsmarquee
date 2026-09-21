"""Quarter-by-quarter linescore parsing for the NFL final-score screen"""

from __future__ import annotations


def _competitor(*period_values):
    """An ESPN competitor in the shape the scoreboard payload returns."""
    return {'linescores': [{'value': float(v)} for v in period_values]}


def test_returns_one_string_per_quarter():
    import bears_display as bd

    assert bd.extract_linescores(_competitor(0, 3, 0, 0)) == ['0', '3', '0', '0']


def test_collapses_overtime_periods_into_a_single_column():
    import bears_display as bd

    # Two OT periods sum into one trailing column so the grid stays 5 wide
    assert bd.extract_linescores(
        _competitor(7, 0, 10, 3, 3, 6)) == ['7', '0', '10', '3', '9']


def test_returns_empty_when_linescores_are_absent():
    import bears_display as bd

    assert bd.extract_linescores({}) == []


def test_prefers_display_value_when_present():
    import bears_display as bd

    competitor = {'linescores': [{'value': 7.0, 'displayValue': '7'},
                                 {'value': 0.0, 'displayValue': '0'}]}
    assert bd.extract_linescores(competitor) == ['7', '0']


def test_score_pair_parses_display_strings_to_ints():
    import bears_display as bd

    assert bd._score_pair('3', '9') == (3, 9)


def test_score_pair_returns_none_pair_for_unparseable_scores():
    import bears_display as bd

    assert bd._score_pair('', '9') == (None, None)


# Advance width per font, for turning a draw_text call into an x-extent
_ADVANCE = {'ultra_micro': 4, 'micro': 4, 'tiny': 5, 'tiny_bold': 5,
            'small_bold': 6, 'standard_bold': 7}


def _final_draws(linescore_len):
    """Every draw_text call the final screen makes, as (font, x, y, text)."""
    from unittest.mock import MagicMock
    import teams
    import bears_display
    teams.load_user_config = lambda: {}
    d = bears_display.BearsDisplay(MagicMock())
    d.manager = MagicMock()
    # Two-digit quarters are the crowding case that must stay legible
    values = ['14', '7', '10', '3', '7'][:linescore_len]
    d._draw_final_content(
        {'bears_score': '41', 'opp_score': '24', 'opponent_abbr': 'MIN',
         'team_linescores': values, 'opp_linescores': values},
        frame_count=0)
    return [(c.args[0], c.args[1], c.args[2], c.args[4])
            for c in d.manager.draw_text.call_args_list]


def _extent(font, x, text):
    return x, x + len(text) * _ADVANCE[font]


def test_box_score_stays_on_panel_and_clear_of_the_badge():
    for length in (4, 5):
        for font, x, y, text in _final_draws(length):
            left, right = _extent(font, x, text)
            assert left >= 0, (text, left)
            assert right <= 96, (f'{text} overflows the panel', right, length)


def test_box_score_cells_never_touch_on_a_row():
    """A 2-digit quarter beside another must keep a readable ink gap."""
    for length in (4, 5):
        rows = {}
        for font, x, y, text in _final_draws(length):
            rows.setdefault(y, []).append(_extent(font, x, text))
        for y, spans in rows.items():
            spans.sort()
            for (_, prev_right), (next_left, _) in zip(spans, spans[1:]):
                assert next_left - prev_right >= 2, (
                    f'row y={y} columns collide at {prev_right}->{next_left} '
                    f'with {length} columns')


def test_centred_x_centres_on_ink_not_advance():
    """The last glyph's cell carries a blank trailing column, so centring
    on len*char_width lands text up to a pixel left of true centre."""
    import bears_display as bd

    # FINAL in tiny: 5 chars x 5px advance = 25, but only 24px of ink.
    # Centred on ink it spans 36..59, whose midpoint is the panel's 47.5.
    x = bd._centred_x('FINAL', 5)
    assert x == 36
    assert (x + (x + 24 - 1)) / 2 == 47.5


def test_centred_x_offsets_into_a_sub_region():
    import bears_display as bd

    # A 22px badge starting at x=72 centres 'LOSS' (19px of ink) at 73
    assert bd._centred_x('LOSS', 5, span=22, origin=72) == 73


def _competitor_full(abbrev, score, linescores=None):
    c = {'team': {'abbreviation': abbrev, 'displayName': abbrev},
         'score': {'displayValue': score}}
    if linescores is not None:
        c['linescores'] = [{'value': float(v)} for v in linescores]
    return c


def _final_game(with_linescores):
    """A schedule event for a finished game. The real schedule endpoint
    omits linescores entirely; only the scoreboard endpoint carries them."""
    home = _competitor_full('CHI', '3', ['0', '3', '0', '0'] if with_linescores else None)
    away = _competitor_full('MIN', '9', ['3', '0', '3', '3'] if with_linescores else None)
    return {'id': '401', 'date': '2026-09-20T17:00Z', 'competitions': [{
        'competitors': [home, away],
        'status': {'type': {'name': 'STATUS_FINAL', 'state': 'post',
                            'shortDetail': 'Final'}}}]}


def test_final_game_refetches_the_scoreboard_for_missing_linescores(monkeypatch):
    """The schedule payload has scores but no linescores, so without a
    refetch the box score silently degrades to the plain card."""
    from unittest.mock import MagicMock
    import teams
    import bears_display
    monkeypatch.setattr(teams, 'load_user_config', lambda: {})
    d = bears_display.BearsDisplay(MagicMock())

    schedule_game = _final_game(with_linescores=False)
    calls = []

    def fake_fetch(game_id):
        calls.append(game_id)
        return _final_game(with_linescores=True)

    monkeypatch.setattr(d, '_fetch_live_scores', fake_fetch)
    result = d._get_current_scores(schedule_game, '401')

    assert calls == ['401'], 'expected one scoreboard refetch'
    assert result['team_linescores'] == ['0', '3', '0', '0']
    assert result['opp_linescores'] == ['3', '0', '3', '3']


def test_final_game_with_linescores_already_present_does_not_refetch(monkeypatch):
    from unittest.mock import MagicMock
    import teams
    import bears_display
    monkeypatch.setattr(teams, 'load_user_config', lambda: {})
    d = bears_display.BearsDisplay(MagicMock())

    calls = []
    monkeypatch.setattr(d, '_fetch_live_scores',
                        lambda gid: calls.append(gid) or None)
    result = d._get_current_scores(_final_game(with_linescores=True), '401')

    assert calls == [], 'a complete payload must not trigger a request'
    assert result['team_linescores'] == ['0', '3', '0', '0']
