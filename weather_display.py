"""Weather display handler using OpenWeatherMap API"""

import time
import json
import os
import requests
import pendulum
from scoreboard_config import Colors, GameConfig


class WeatherDisplay:
    """Handles weather data fetching and display"""

    def __init__(self, scoreboard_manager):
        """Initialize weather display"""
        self.manager = scoreboard_manager
        self.weather_data = None
        self.forecast_data = None
        self.last_update = None
        self.update_interval = 1800  # 30 minutes in seconds

    def _load_config(self):
        """Load configuration"""
        config_path = '/home/pi/config.json'
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except:
            return {}

    def _fetch_weather(self):
        """Fetch weather data from OpenWeatherMap API"""
        config = self._load_config()
        zip_code = config.get('zip_code')
        api_key = config.get('weather_api_key')

        if not zip_code or not api_key:
            print("Weather not configured")
            return False

        try:
            # Current weather
            current_url = f"https://api.openweathermap.org/data/2.5/weather?zip={zip_code},US&appid={api_key}&units=imperial"
            current_response = requests.get(current_url, timeout=10)
            current_response.raise_for_status()
            self.weather_data = current_response.json()

            # 5-day forecast (3-hour intervals)
            forecast_url = f"https://api.openweathermap.org/data/2.5/forecast?zip={zip_code},US&appid={api_key}&units=imperial"
            forecast_response = requests.get(forecast_url, timeout=10)
            forecast_response.raise_for_status()
            self.forecast_data = forecast_response.json()

            self.last_update = time.time()
            print(
                f"Weather updated: {self.weather_data['name']}, {self.weather_data['main']['temp']}°F")
            return True

        except Exception as e:
            print(f"Error fetching weather: {e}")
            return False

    def _should_update_weather(self):
        """Check if weather data needs updating"""
        if not self.weather_data or not self.last_update:
            return True
        return (time.time() - self.last_update) > self.update_interval

    def display_weather_screen(self, duration=300):
        """Display weather for specified duration"""
        # Fetch weather if needed
        if self._should_update_weather():
            if not self._fetch_weather():
                return  # Failed to fetch

        if not self.weather_data:
            return

        start_time = time.time()
        display_mode = 0  # 0 = current, 1 = forecast
        mode_switch_time = time.time()
        mode_duration = 15  # Switch every 15 seconds

        while time.time() - start_time < duration:
            # Switch between current and forecast
            if time.time() - mode_switch_time > mode_duration:
                display_mode = (display_mode + 1) % 2
                mode_switch_time = time.time()

            # Check if we need to update weather
            if self._should_update_weather():
                self._fetch_weather()

            if display_mode == 0:
                self._draw_current_weather()
            else:
                self._draw_forecast()

            self.manager.swap_canvas()
            time.sleep(0.5)

    def _draw_current_weather(self):
        """Draw current weather conditions"""
        self.manager.clear_canvas()

        # Background gradient (blue sky)
        for y in range(48):
            blue_val = int(200 - (y * 2))
            for x in range(96):
                self.manager.draw_pixel(x, y, 100, 150, blue_val)

        # Get weather data
        temp = int(self.weather_data['main']['temp'])
        feels_like = int(self.weather_data['main']['feels_like'])
        condition = self.weather_data['weather'][0]['main']
        description = self.weather_data['weather'][0]['description'].title()
        humidity = self.weather_data['main']['humidity']
        city = self.weather_data['name']

        # Draw title
        self.manager.draw_text(
            'tiny_bold', 2, 8, Colors.WHITE, 'CURRENT WEATHER')

        # Draw city name
        city_x = max(2, (96 - len(city) * 5) // 2)
        self.manager.draw_text('tiny', city_x, 16, Colors.YELLOW, city)

        # Draw temperature (large)
        temp_str = f"{temp}"
        temp_x = 20 if temp >= 100 else (30 if temp >= 10 else 38)
        self.manager.draw_text('large_bold', temp_x, 32,
                               Colors.WHITE, temp_str)

        # Draw degree symbol and F
        degree_x = temp_x + (len(temp_str) * 10) - 2
        self.manager.draw_text('tiny', degree_x, 22, Colors.WHITE, 'o')
        self.manager.draw_text('small', degree_x + 4, 26, Colors.WHITE, 'F')

        # Draw condition
        cond_x = max(2, (96 - len(condition) * 5) // 2)
        self.manager.draw_text(
            'tiny', cond_x, 40, Colors.BRIGHT_YELLOW, condition)

        # Draw feels like and humidity
        self.manager.draw_text(
            'micro', 2, 47, Colors.WHITE, f'FEELS:{feels_like}')
        self.manager.draw_text(
            'micro', 60, 47, Colors.WHITE, f'HUM:{humidity}%')

    def _draw_forecast(self):
        """Draw forecast information"""
        self.manager.clear_canvas()

        # Background
        self.manager.fill_canvas(*Colors.CUBS_BLUE)

        # Draw title
        self.manager.draw_text(
            'tiny_bold', 12, 8, Colors.BRIGHT_YELLOW, '3-DAY FORECAST')

        if not self.forecast_data:
            return

        try:
            # Get forecast for next 3 days at noon
            forecasts = []
            seen_days = set()

            for item in self.forecast_data['list']:
                dt = pendulum.parse(item['dt_txt'])
                day_key = dt.format('YYYY-MM-DD')

                # Get forecast around noon (12:00)
                if dt.hour == 12 and day_key not in seen_days:
                    forecasts.append({
                        'day': dt.format('ddd'),
                        'temp_high': int(item['main']['temp_max']),
                        'temp_low': int(item['main']['temp_min']),
                        'condition': item['weather'][0]['main'][:4].upper()
                    })
                    seen_days.add(day_key)

                if len(forecasts) >= 3:
                    break

            # Draw forecasts
            y_pos = 18
            for forecast in forecasts:
                # Day name
                self.manager.draw_text(
                    'tiny', 3, y_pos, Colors.WHITE, forecast['day'])

                # High temp
                self.manager.draw_text('tiny', 25, y_pos, Colors.YELLOW,
                                       f"{forecast['temp_high']}")

                # Low temp
                self.manager.draw_text('tiny', 45, y_pos, Colors.WHITE,
                                       f"{forecast['temp_low']}")

                # Condition
                self.manager.draw_text('micro', 65, y_pos - 1, Colors.WHITE,
                                       forecast['condition'])

                y_pos += 10

        except Exception as e:
            print(f"Error drawing forecast: {e}")

    def _get_weather_icon(self, condition):
        """Get simple ASCII representation of weather condition"""
        icons = {
            'Clear': 'O',
            'Clouds': '~',
            'Rain': '|',
            'Snow': '*',
            'Thunderstorm': 'Z'
        }
        return icons.get(condition, '?')
