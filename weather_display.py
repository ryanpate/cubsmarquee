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

        # Animation state variables
        self.animation_frame = 0
        self.rain_drops = []
        self.snow_flakes = []
        self.cloud_positions = []
        self.star_twinkle = []
        self.lightning_flash = 0

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

    def _draw_complete_background(self, hour, condition):
        """Draw complete background combining time of day and weather condition"""
        import random

        # Determine time period
        if 6 <= hour < 8:
            time_period = 'dawn'
        elif 8 <= hour < 17:
            time_period = 'day'
        elif 17 <= hour < 20:
            time_period = 'dusk'
        else:
            time_period = 'night'

        print(f"Weather background: {time_period.upper()} + {condition}")

        # CLEAR SKY BACKGROUNDS
        if condition == 'Clear':
            if time_period == 'dawn':
                # Dawn - Orange/pink sunrise
                self._gradient_background((255, 180, 120), (255, 220, 180))
            elif time_period == 'day':
                # Day - Bright blue sky
                self._gradient_background((100, 180, 255), (150, 220, 255))
            elif time_period == 'dusk':
                # Dusk - Orange/purple sunset
                self._gradient_background((255, 120, 80), (120, 80, 150))
            else:  # night
                # Night - Dark blue/purple
                self._gradient_background((20, 30, 80), (10, 15, 40))

        # CLOUDY BACKGROUNDS
        elif condition == 'Clouds':
            if time_period == 'dawn':
                # Cloudy dawn - Muted warm gray
                self._gradient_background((180, 170, 160), (200, 190, 180))
            elif time_period == 'day':
                # Cloudy day - Light gray
                self._gradient_background((150, 160, 170), (180, 190, 200))
            elif time_period == 'dusk':
                # Cloudy dusk - Purple gray
                self._gradient_background((120, 100, 120), (90, 80, 100))
            else:  # night
                # Cloudy night - Dark gray
                self._gradient_background((50, 55, 60), (30, 35, 40))

        # RAINY BACKGROUNDS
        elif condition in ['Rain', 'Drizzle']:
            if time_period == 'dawn':
                # Rainy dawn - Dark blue-gray
                self._gradient_background((90, 100, 110), (110, 120, 130))
            elif time_period == 'day':
                # Rainy day - Storm gray
                self._gradient_background((80, 90, 105), (100, 110, 125))
            elif time_period == 'dusk':
                # Rainy dusk - Deep gray-blue
                self._gradient_background((70, 70, 90), (50, 50, 70))
            else:  # night
                # Rainy night - Very dark gray
                self._gradient_background((40, 45, 55), (25, 30, 40))

        # THUNDERSTORM BACKGROUNDS
        elif condition == 'Thunderstorm':
            if time_period == 'dawn':
                # Stormy dawn - Dark purple-gray
                self._gradient_background((60, 60, 80), (50, 50, 70))
            elif time_period == 'day':
                # Stormy day - Dark storm colors
                self._gradient_background((50, 55, 70), (60, 65, 80))
            elif time_period == 'dusk':
                # Stormy dusk - Very dark purple
                self._gradient_background((45, 40, 60), (35, 30, 50))
            else:  # night
                # Stormy night - Almost black
                self._gradient_background((30, 30, 45), (15, 15, 30))

        # SNOWY BACKGROUNDS
        elif condition == 'Snow':
            if time_period == 'dawn':
                # Snowy dawn - Pale pink/blue
                self._gradient_background((220, 210, 220), (240, 230, 240))
            elif time_period == 'day':
                # Snowy day - Bright white/blue
                self._gradient_background((230, 235, 245), (245, 250, 255))
            elif time_period == 'dusk':
                # Snowy dusk - Cool gray/blue
                self._gradient_background((160, 165, 180), (180, 185, 200))
            else:  # night
                # Snowy night - Dark blue-gray
                self._gradient_background((70, 75, 90), (55, 60, 75))

        # FOGGY/MISTY BACKGROUNDS
        elif condition in ['Mist', 'Fog', 'Haze', 'Smoke']:
            if time_period == 'dawn':
                # Misty dawn - Light gray
                self._gradient_background((190, 190, 190), (210, 210, 210))
            elif time_period == 'day':
                # Misty day - Bright gray
                self._gradient_background((200, 200, 200), (220, 220, 220))
            elif time_period == 'dusk':
                # Misty dusk - Medium gray
                self._gradient_background((130, 135, 140), (150, 155, 160))
            else:  # night
                # Misty night - Dark gray
                self._gradient_background((60, 65, 70), (45, 50, 55))

        # FALLBACK - Use Clear sky if condition unknown
        else:
            print(f"Unknown condition '{condition}', using Clear fallback")
            if time_period == 'dawn':
                self._gradient_background((255, 180, 120), (255, 220, 180))
            elif time_period == 'day':
                self._gradient_background((100, 180, 255), (150, 220, 255))
            elif time_period == 'dusk':
                self._gradient_background((255, 120, 80), (120, 80, 150))
            else:
                self._gradient_background((20, 30, 80), (10, 15, 40))

    def _gradient_background(self, top_color, bottom_color):
        """Draw a gradient background from top to bottom"""
        r1, g1, b1 = top_color
        r2, g2, b2 = bottom_color

        for y in range(48):
            # Calculate gradient interpolation
            ratio = y / 48
            r = int(r1 + (r2 - r1) * ratio)
            g = int(g1 + (g2 - g1) * ratio)
            b = int(b1 + (b2 - b1) * ratio)

            for x in range(96):
                self.manager.draw_pixel(x, y, r, g, b)

    def _initialize_animations(self):
        """Initialize animation objects"""
        import random

        # Initialize rain drops (x, y, speed)
        self.rain_drops = []
        for i in range(12):
            self.rain_drops.append({
                'x': random.randint(0, 95),
                'y': random.randint(-10, 30),
                'speed': random.uniform(1.5, 2.5)
            })

        # Initialize snow flakes (x, y, speed, drift)
        self.snow_flakes = []
        for i in range(15):
            self.snow_flakes.append({
                'x': random.randint(0, 95),
                'y': random.randint(-10, 30),
                'speed': random.uniform(0.3, 0.8),
                'drift': random.uniform(-0.2, 0.2)
            })

        # Initialize clouds (x, y, speed, width)
        self.cloud_positions = []
        for i in range(3):
            self.cloud_positions.append({
                'x': random.randint(-20, 96),
                'y': random.randint(2, 10),
                'speed': random.uniform(0.1, 0.3),
                'width': random.randint(6, 10)
            })

        # Initialize stars (x, y, brightness, twinkle_speed)
        self.star_twinkle = []
        for i in range(12):
            self.star_twinkle.append({
                'x': random.randint(0, 95),
                'y': random.randint(0, 15),
                'brightness': random.randint(150, 255),
                'direction': random.choice([-1, 1]),
                'speed': random.uniform(2, 5)
            })

        self.animation_frame = 0
        self.lightning_flash = 0

    def _draw_animated_weather(self, condition, hour):
        """Draw animated weather effects"""
        import random

        if condition in ['Rain', 'Drizzle']:
            self._animate_rain()
        elif condition == 'Thunderstorm':
            self._animate_thunderstorm()
        elif condition == 'Snow':
            self._animate_snow()
        elif condition == 'Clouds':
            self._animate_clouds()
        elif condition == 'Clear':
            if 6 <= hour < 20:
                self._animate_sun()
            else:
                self._animate_stars()

    def _animate_rain(self):
        """Animate falling rain"""
        import random

        for drop in self.rain_drops:
            # Draw rain drop (2 pixels vertical)
            y = int(drop['y'])
            if 0 <= y < 47:
                self.manager.draw_pixel(drop['x'], y, 180, 200, 220)
            if 0 <= y + 1 < 48:
                self.manager.draw_pixel(drop['x'], y + 1, 160, 180, 200)

            # Update position
            drop['y'] += drop['speed']

            # Reset if off screen
            if drop['y'] > 48:
                drop['y'] = -2
                drop['x'] = random.randint(0, 95)
                drop['speed'] = random.uniform(1.5, 2.5)

    def _animate_snow(self):
        """Animate falling snow"""
        import random

        for flake in self.snow_flakes:
            # Draw snowflake (small cross pattern)
            x = int(flake['x'])
            y = int(flake['y'])

            if 0 <= y < 48 and 0 <= x < 96:
                self.manager.draw_pixel(x, y, 255, 255, 255)
                # Add cross pattern
                if x > 0:
                    self.manager.draw_pixel(x - 1, y, 240, 240, 245)
                if x < 95:
                    self.manager.draw_pixel(x + 1, y, 240, 240, 245)
                if y > 0:
                    self.manager.draw_pixel(x, y - 1, 240, 240, 245)

            # Update position with drift
            flake['y'] += flake['speed']
            flake['x'] += flake['drift']

            # Keep x in bounds
            if flake['x'] < 0:
                flake['x'] = 95
            elif flake['x'] > 95:
                flake['x'] = 0

            # Reset if off screen
            if flake['y'] > 48:
                flake['y'] = -2
                flake['x'] = random.randint(0, 95)

    def _animate_clouds(self):
        """Animate drifting clouds"""
        import random

        for cloud in self.cloud_positions:
            # Draw simple cloud shape
            x_start = int(cloud['x'])
            y = cloud['y']
            width = cloud['width']

            cloud_color = (220, 225, 235)

            # Draw cloud as horizontal line
            for x_offset in range(width):
                x = x_start + x_offset
                if 0 <= x < 96 and 0 <= y < 48:
                    self.manager.draw_pixel(x, y, *cloud_color)
                    # Add some height
                    if y > 0:
                        self.manager.draw_pixel(x, y - 1, 200, 205, 215)

            # Update position
            cloud['x'] += cloud['speed']

            # Wrap around
            if cloud['x'] > 96:
                cloud['x'] = -cloud['width']
                cloud['y'] = random.randint(2, 10)

    def _animate_thunderstorm(self):
        """Animate thunderstorm with rain and lightning"""
        import random

        # Animate rain
        self._animate_rain()

        # Lightning flash effect
        if self.animation_frame % 100 == 0 and random.random() > 0.7:
            self.lightning_flash = 3

        if self.lightning_flash > 0:
            # Draw lightning bolt
            x = random.randint(30, 65)
            y = 0
            for segment in range(3):
                for dy in range(5):
                    if y + dy < 20:
                        brightness = 255 if self.lightning_flash == 3 else 200
                        self.manager.draw_pixel(
                            x, y + dy, brightness, brightness, brightness - 50)
                y += 5
                x += random.choice([-2, -1, 0, 1, 2])
                x = max(0, min(95, x))

            self.lightning_flash -= 1

    def _animate_sun(self):
        """Animate pulsing sun"""
        import math

        # Sun position
        sun_x, sun_y = 88, 5

        # Pulsing effect
        pulse = int(abs(math.sin(self.animation_frame * 0.1) * 20))

        # Draw sun core
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                if dx * dx + dy * dy <= 4:
                    brightness = min(255, 235 + pulse)
                    self.manager.draw_pixel(
                        sun_x + dx, sun_y + dy, brightness, brightness, 100)

        # Draw rays
        for angle in [0, 45, 90, 135, 180, 225, 270, 315]:
            ray_length = 4 + int(pulse / 10)
            ray_x = sun_x + int(ray_length * math.cos(math.radians(angle)))
            ray_y = sun_y + int(ray_length * math.sin(math.radians(angle)))
            if 0 <= ray_x < 96 and 0 <= ray_y < 48:
                self.manager.draw_pixel(ray_x, ray_y, 255, 255, 150)

    def _animate_stars(self):
        """Animate twinkling stars"""
        for star in self.star_twinkle:
            # Draw star with current brightness
            brightness = int(star['brightness'])
            if 0 <= star['x'] < 96 and 0 <= star['y'] < 48:
                self.manager.draw_pixel(
                    star['x'], star['y'], brightness, brightness, brightness + 20)

            # Update brightness (twinkling effect)
            star['brightness'] += star['direction'] * star['speed']

            # Reverse direction at limits
            if star['brightness'] >= 255:
                star['brightness'] = 255
                star['direction'] = -1
            elif star['brightness'] <= 150:
                star['brightness'] = 150
                star['direction'] = 1
