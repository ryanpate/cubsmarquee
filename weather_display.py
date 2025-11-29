"""Weather display handler using OpenWeatherMap API"""

import time
import json
import os
import requests
import pendulum
from PIL import Image
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

        # Track when background was last drawn
        self._last_hour = None
        self._last_condition = None
        self._last_mode = None  # Track which display mode we're in
        self._last_time_period = None  # NEW: Track time period for animation resets

        # Cache the current background for efficient redraws
        self._background_cache = None

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
            condition = self.weather_data['weather'][0]['main']
            description = self.weather_data['weather'][0]['description']
            print(
                f"Weather updated: {self.weather_data['name']}, {self.weather_data['main']['temp']}°F, Condition: {condition} ({description})")
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
        print(f"Starting weather display for {duration} seconds")

        # Fetch weather if needed
        if self._should_update_weather():
            if not self._fetch_weather():
                print("Failed to fetch weather, exiting")
                return  # Failed to fetch

        if not self.weather_data:
            print("No weather data available, exiting")
            return

        # Initialize animations once at start
        if not self.rain_drops and not self.snow_flakes:
            self._initialize_animations()

        start_time = time.time()
        display_mode = 0  # 0 = current, 1 = forecast
        mode_switch_time = time.time()
        mode_duration = 15  # Switch every 15 seconds
        frame_count = 0

        while time.time() - start_time < duration:
            frame_count += 1

            # Switch between current and forecast
            if time.time() - mode_switch_time > mode_duration:
                display_mode = (display_mode + 1) % 2
                mode_switch_time = time.time()
                # Force background redraw on mode switch
                if display_mode == 0:  # Switching to current weather
                    self._last_mode = None
                    self._background_cache = None
                print(
                    f"Switching to {'forecast' if display_mode == 1 else 'current weather'}")

            # Check if we need to update weather
            if self._should_update_weather():
                self._fetch_weather()

            if display_mode == 0:
                self._draw_current_weather_animated()
            else:
                self._draw_forecast()

            self.manager.swap_canvas()
            time.sleep(0.3)

        print(f"Weather display completed after {frame_count} frames")

    def _get_time_period(self, hour):
        """Determine the time period (dawn/day/dusk/night) for current conditions"""
        # Get sunrise and sunset times from weather data
        sunrise_timestamp = self.weather_data.get('sys', {}).get('sunrise', 0)
        sunset_timestamp = self.weather_data.get('sys', {}).get('sunset', 0)

        # Convert to local hour with minutes as decimal for accurate comparison
        current_time = pendulum.now()
        current_hour_decimal = current_time.hour + (current_time.minute / 60.0)

        # Determine time period based on actual sun position
        if sunrise_timestamp and sunset_timestamp:
            # Convert UTC timestamps to local timezone
            local_tz = 'America/Chicago'  # Rochester, IL is in Central Time
            sunrise_time = pendulum.from_timestamp(
                sunrise_timestamp, tz=local_tz)
            sunset_time = pendulum.from_timestamp(
                sunset_timestamp, tz=local_tz)

            sunrise_hour_decimal = sunrise_time.hour + \
                (sunrise_time.minute / 60.0)
            sunset_hour_decimal = sunset_time.hour + \
                (sunset_time.minute / 60.0)

            # Dawn: 1 hour before sunrise to 30 minutes after sunrise
            dawn_start = sunrise_hour_decimal - 1
            dawn_end = sunrise_hour_decimal + 0.5

            # Dusk: 30 minutes before sunset to 1 hour after sunset
            dusk_start = sunset_hour_decimal - 0.5
            dusk_end = sunset_hour_decimal + 1

            # Determine time period based on actual sun position
            if dawn_start <= current_hour_decimal < dawn_end:
                return 'dawn'
            elif dawn_end <= current_hour_decimal < dusk_start:
                return 'day'
            elif dusk_start <= current_hour_decimal < dusk_end:
                return 'dusk'
            else:
                return 'night'
        else:
            # Fallback to fixed times if sunrise/sunset not available
            if 6 <= hour < 8:
                return 'dawn'
            elif 8 <= hour < 17:
                return 'day'
            elif 17 <= hour < 20:
                return 'dusk'
            else:
                return 'night'

    def _draw_current_weather_animated(self):
        """Draw current weather with animations (called each frame)"""
        current_hour = pendulum.now().hour
        condition = self.weather_data['weather'][0]['main']
        time_period = self._get_time_period(current_hour)

        # Check if we need to regenerate the background
        needs_background_redraw = (
            self._last_mode != 'current' or
            self._last_hour != current_hour or
            self._last_condition != condition or
            self._background_cache is None
        )

        # NEW: Check if time period changed (for animation resets)
        time_period_changed = (self._last_time_period != time_period)

        if needs_background_redraw:
            # Generate and cache the background
            self._background_cache = self._generate_background_cache(
                current_hour, condition, time_period)
            self._last_hour = current_hour
            self._last_condition = condition
            self._last_mode = 'current'

        # NEW: Reset animations when time period changes
        if time_period_changed:
            print(
                f"Time period changed to {time_period}, reinitializing animations")
            self._initialize_animations_for_condition(condition, time_period)
            self._last_time_period = time_period

        # STEP 1: Draw the cached background (full screen)
        self._draw_cached_background()

        # STEP 2: Draw animations on top of background
        self._draw_animated_weather(condition, current_hour, time_period)
        self.animation_frame += 1

        # STEP 3: Draw all text on top of animations
        self._draw_weather_text()

    def _generate_background_cache(self, hour, condition, time_period):
        """Generate and cache the background gradient as a pixel array"""
        top_color, bottom_color = self._get_gradient_colors(
            hour, condition, time_period)
        r1, g1, b1 = top_color
        r2, g2, b2 = bottom_color

        # Create a 2D array to store the background
        background = []
        for y in range(48):
            row = []
            ratio = y / 48
            r = int(r1 + (r2 - r1) * ratio)
            g = int(g1 + (g2 - g1) * ratio)
            b = int(b1 + (b2 - b1) * ratio)
            for x in range(96):
                row.append((r, g, b))
            background.append(row)

        return background

    def _draw_cached_background(self):
        """Draw the cached background to canvas"""
        if self._background_cache:
            for y in range(48):
                for x in range(96):
                    r, g, b = self._background_cache[y][x]
                    self.manager.draw_pixel(x, y, r, g, b)

    def _draw_weather_text(self):
        """Draw all weather text elements"""
        # Get weather data
        temp = int(self.weather_data['main']['temp'])
        feels_like = int(self.weather_data['main']['feels_like'])
        condition_text = self.weather_data['weather'][0]['main']
        humidity = self.weather_data['main']['humidity']
        city = self.weather_data['name']

        # Draw title
        self.manager.draw_text(
            'tiny_bold', 10, 8, Colors.WHITE, 'CURRENT WEATHER')

        # Draw city name
        city_x = max(2, (96 - len(city) * 4) // 2)
        self.manager.draw_text('tiny', city_x, 16, Colors.YELLOW, city)

        # Draw temperature (large)
        temp_str = f"{temp}"
        temp_x = 28 if temp >= 100 else (38 if temp >= 10 else 46)
        self.manager.draw_text('large_bold', temp_x, 32,
                               Colors.WHITE, temp_str)

        # Draw degree symbol and F
        degree_x = temp_x + (len(temp_str) * 10) - 2
        self.manager.draw_text('tiny', degree_x, 22, Colors.WHITE, 'o')
        self.manager.draw_text('small', degree_x + 4, 26, Colors.WHITE, 'F')

        # Draw condition
        cond_x = max(2, (96 - len(condition_text) * 4) // 2)
        self.manager.draw_text(
            'tiny', cond_x, 40, Colors.BRIGHT_YELLOW, condition_text)

        # Draw feels like and humidity
        self.manager.draw_text(
            'micro', 4, 47, Colors.WHITE, f'FEELS:{feels_like}')
        self.manager.draw_text(
            'micro', 64, 47, Colors.WHITE, f'HUM:{humidity}%')

    def _get_gradient_colors(self, hour, condition, time_period):
        """Get the gradient colors for current time and condition"""
        # Return tuple of (top_color, bottom_color)
        if condition == 'Clear':
            if time_period == 'dawn':
                return ((255, 180, 120), (255, 220, 180))
            elif time_period == 'day':
                return ((100, 180, 255), (150, 220, 255))
            elif time_period == 'dusk':
                return ((255, 120, 80), (120, 80, 150))
            else:
                return ((20, 30, 80), (10, 15, 40))
        elif condition == 'Clouds':
            if time_period == 'dawn':
                return ((180, 170, 160), (200, 190, 180))
            elif time_period == 'day':
                return ((150, 160, 170), (180, 190, 200))
            elif time_period == 'dusk':
                return ((120, 100, 120), (90, 80, 100))
            else:
                return ((50, 55, 60), (30, 35, 40))
        elif condition in ['Rain', 'Drizzle']:
            if time_period == 'dawn':
                return ((90, 100, 110), (110, 120, 130))
            elif time_period == 'day':
                return ((80, 90, 105), (100, 110, 125))
            elif time_period == 'dusk':
                return ((70, 70, 90), (50, 50, 70))
            else:
                return ((40, 45, 55), (25, 30, 40))
        elif condition == 'Thunderstorm':
            if time_period == 'dawn':
                return ((60, 60, 80), (50, 50, 70))
            elif time_period == 'day':
                return ((50, 55, 70), (60, 65, 80))
            elif time_period == 'dusk':
                return ((45, 40, 60), (35, 30, 50))
            else:
                return ((30, 30, 45), (15, 15, 30))
        elif condition == 'Snow':
            # Darker backgrounds so white text and snowflakes are visible
            if time_period == 'dawn':
                return ((80, 90, 110), (100, 110, 130))
            elif time_period == 'day':
                return ((60, 80, 120), (80, 100, 140))
            elif time_period == 'dusk':
                return ((50, 55, 80), (70, 75, 100))
            else:
                return ((25, 30, 50), (40, 45, 65))
        elif condition in ['Mist', 'Fog', 'Haze', 'Smoke']:
            if time_period == 'dawn':
                return ((190, 190, 190), (210, 210, 210))
            elif time_period == 'day':
                return ((200, 200, 200), (220, 220, 220))
            elif time_period == 'dusk':
                return ((130, 135, 140), (150, 155, 160))
            else:
                return ((60, 65, 70), (45, 50, 55))
        else:
            # Fallback to Clear
            if time_period == 'dawn':
                return ((255, 180, 120), (255, 220, 180))
            elif time_period == 'day':
                return ((100, 180, 255), (150, 220, 255))
            elif time_period == 'dusk':
                return ((255, 120, 80), (120, 80, 150))
            else:
                return ((20, 30, 80), (10, 15, 40))

    def _get_weather_icon_filename(self, condition):
        """Get the filename for weather icon PNG"""
        # Map condition to PNG filename
        icon_map = {
            'Clear': 'clear.png',
            'Clouds': 'clouds.png',
            'Rain': 'rain.png',
            'Drizzle': 'drizzle.png',
            'Snow': 'snow.png',
            'Thunderstorm': 'thunderstorm.png',
            'Mist': 'mist.png',
            'Fog': 'fog.png',
            'Haze': 'haze.png',
            'Smoke': 'smoke.png'
        }
        return icon_map.get(condition, 'default.png')

    def _load_weather_icon(self, condition):
        """Load and return weather icon PNG, or None if not found"""
        icon_filename = self._get_weather_icon_filename(condition)
        icon_path = f'/home/pi/{icon_filename}'

        try:
            if os.path.exists(icon_path):
                icon = Image.open(icon_path)
                # Keep RGBA mode to preserve transparency
                if icon.mode not in ['RGB', 'RGBA']:
                    icon = icon.convert('RGBA')
                return icon
            else:
                print(f"Weather icon not found: {icon_path}")
                return None
        except Exception as e:
            print(f"Error loading weather icon {icon_path}: {e}")
            return None

    def _draw_forecast(self):
        """Draw professional forecast information"""
        import traceback

        # Clear canvas
        self.manager.clear_canvas()

        # Create gradient background (darker blue at top, lighter at bottom)
        for y in range(48):
            ratio = y / 48
            r = int(10 + (30 * ratio))
            g = int(40 + (80 * ratio))
            b = int(80 + (120 * ratio))
            for x in range(96):
                self.manager.draw_pixel(x, y, r, g, b)

        # Mark that we're in forecast mode
        self._last_mode = 'forecast'
        self._background_cache = None

        # Draw title (moved down to avoid cutoff)
        self.manager.draw_text(
            'tiny_bold', 14, 6, Colors.WHITE, '3-DAY FORECAST')

        # Draw title underline
        for x in range(0, 96):
            self.manager.draw_pixel(x, 7, 80, 130, 180)

        if not self.forecast_data:
            return

        try:
            # Get current date to exclude today
            today = pendulum.now().format('YYYY-MM-DD')

            # Get forecast for next 3 days - collect all temps per day
            daily_data = {}

            for item in self.forecast_data['list']:
                dt = pendulum.parse(item['dt_txt'])
                day_key = dt.format('YYYY-MM-DD')

                # Skip today's data
                if day_key == today:
                    continue

                # Initialize day if not seen
                if day_key not in daily_data:
                    daily_data[day_key] = {
                        'day': dt.format('ddd').upper(),
                        'temps': [],
                        'conditions': []
                    }

                # Collect all temps and conditions for the day
                daily_data[day_key]['temps'].append(item['main']['temp'])
                daily_data[day_key]['conditions'].append(
                    item['weather'][0]['main'])

            # Process into forecast list with actual high/low
            forecasts = []
            # Get first 3 days after today
            for day_key in sorted(daily_data.keys())[:3]:
                day_info = daily_data[day_key]

                # Get actual high and low from all readings that day
                temp_high = int(max(day_info['temps']))
                temp_low = int(min(day_info['temps']))

                # Use most common condition for the day
                condition = max(
                    set(day_info['conditions']), key=day_info['conditions'].count)

                forecasts.append({
                    'day': day_info['day'],
                    'temp_high': temp_high,
                    'temp_low': temp_low,
                    'condition': condition
                })

                if len(forecasts) >= 3:
                    break

            # Draw column headers
            self.manager.draw_text('micro', 4, 15, Colors.BRIGHT_YELLOW, 'DAY')
            self.manager.draw_text(
                'micro', 28, 15, Colors.BRIGHT_YELLOW, 'HIGH')
            self.manager.draw_text(
                'micro', 52, 15, Colors.BRIGHT_YELLOW, 'LOW')
            self.manager.draw_text(
                'micro', 72, 15, Colors.BRIGHT_YELLOW, 'COND')

            # Draw divider line under headers
            for x in range(0, 96):
                self.manager.draw_pixel(x, 16, 100, 150, 200)

            # Draw forecasts with alternating subtle backgrounds
            y_pos = 25
            for i, forecast in enumerate(forecasts):
                # Subtle alternating row background
                row_start_y = y_pos - 7
                row_end_y = y_pos + 1

                if i % 2 == 0:
                    for y in range(row_start_y, row_end_y):
                        # Calculate background color based on gradient position
                        ratio = y / 48
                        r = int(10 + (30 * ratio) + 15)  # Slightly lighter
                        g = int(40 + (80 * ratio) + 15)
                        b = int(80 + (120 * ratio) + 15)
                        for x in range(2, 94):
                            self.manager.draw_pixel(x, y, r, g, b)

                # Day name (bold white)
                self.manager.draw_text(
                    'tiny_bold', 4, y_pos, Colors.WHITE, forecast['day'])

                # Weather icon PNG (if available)
                weather_icon = self._load_weather_icon(forecast['condition'])
                if weather_icon:
                    # Position the icon (adjust size if needed - assuming 10x10 or smaller)
                    icon_x = 19
                    icon_y = y_pos - 7

                    # Adjust rain icon position up by 1 pixel for better centering
                    if forecast['condition'] == 'Rain' or forecast['condition'] == 'Clear':
                        icon_y -= 1

                    # Adjust clouds icon position up by 1 pixel for better centering
                    if forecast['condition'] == 'Clouds':
                        icon_y += 2

                    # Adjust snow icon position up by 1 pixel for better centering
                    if forecast['condition'] == 'Snow':
                        icon_x += 1
                        icon_y -= 1

                    # Resize icon if it's too large (max 10x10 for the forecast display)
                    icon_width, icon_height = weather_icon.size
                    max_size = 10
                    if icon_width > max_size or icon_height > max_size:
                        weather_icon = weather_icon.resize(
                            (max_size, max_size), Image.LANCZOS)

                    # Draw the icon pixel by pixel with transparency support
                    try:
                        # Get the background color at this position
                        ratio = icon_y / 48
                        bg_r = int(10 + (30 * ratio))
                        bg_g = int(40 + (80 * ratio))
                        bg_b = int(80 + (120 * ratio))
                        if i % 2 == 0:
                            bg_r += 15
                            bg_g += 15
                            bg_b += 15

                        # Draw icon pixel by pixel
                        for py in range(weather_icon.height):
                            for px in range(weather_icon.width):
                                pixel = weather_icon.getpixel((px, py))

                                # Handle different image modes
                                if weather_icon.mode == 'RGBA':
                                    r, g, b, a = pixel
                                    if a > 0:  # Only draw non-transparent pixels
                                        # Blend with background based on alpha
                                        if a < 255:
                                            alpha = a / 255.0
                                            r = int(
                                                r * alpha + bg_r * (1 - alpha))
                                            g = int(
                                                g * alpha + bg_g * (1 - alpha))
                                            b = int(
                                                b * alpha + bg_b * (1 - alpha))
                                        self.manager.draw_pixel(
                                            icon_x + px, icon_y + py, r, g, b)
                                else:  # RGB mode
                                    r, g, b = pixel[:3]
                                    self.manager.draw_pixel(
                                        icon_x + px, icon_y + py, r, g, b)

                    except Exception as e:
                        print(f"Error drawing weather icon: {e}")
                        traceback.print_exc()
                        # Fallback to text if image fails
                        icon_color = self._get_icon_color(
                            forecast['condition'])
                        icon_char = self._get_weather_icon(
                            forecast['condition'])
                        self.manager.draw_text(
                            'small', icon_x, icon_y, icon_color, icon_char)
                else:
                    # Fallback to ASCII character if PNG not found
                    icon_color = self._get_icon_color(forecast['condition'])
                    icon_char = self._get_weather_icon(forecast['condition'])
                    self.manager.draw_text(
                        'small', 19, y_pos - 1, icon_color, icon_char)

                # High temp (orange/red)
                temp_high_color = (
                    255, 140, 0) if forecast['temp_high'] >= 80 else (255, 180, 60)
                self.manager.draw_text('tiny_bold', 30, y_pos, temp_high_color,
                                       f"{forecast['temp_high']}")
                # Degree symbol positioned at top right
                self.manager.draw_text(
                    'micro', 42, y_pos - 2, temp_high_color, 'o')

                # Low temp (light blue)
                temp_low_color = (
                    120, 180, 255) if forecast['temp_low'] <= 50 else (180, 200, 220)
                self.manager.draw_text('tiny', 54, y_pos, temp_low_color,
                                       f"{forecast['temp_low']}")
                # Degree symbol positioned at top right
                self.manager.draw_text(
                    'micro', 66, y_pos - 2, temp_low_color, 'o')

                # Condition text (abbreviated)
                cond_text = self._get_condition_abbrev(forecast['condition'])
                self.manager.draw_text(
                    'micro', 72, y_pos, Colors.WHITE, cond_text)

                y_pos += 10

            # Draw bottom accent line
            for x in range(2, 94):
                self.manager.draw_pixel(x, 47, 80, 130, 180)

        except Exception as e:
            print(f"Error drawing forecast: {e}")
            traceback.print_exc()

    def _get_weather_icon(self, condition):
        """Get weather icon character - using standard ASCII characters (FALLBACK)"""
        icons = {
            'Clear': 'O',      # Sun
            'Clouds': '~',     # Cloud
            'Rain': '|',       # Rain drops
            'Drizzle': ':',    # Light rain
            'Snow': '*',       # Snowflake
            'Thunderstorm': 'Z',  # Lightning
            'Mist': '=',       # Mist
            'Fog': '=',        # Fog
            'Haze': '=',       # Haze
            'Smoke': '='       # Smoke
        }
        return icons.get(condition, '?')

    def _get_icon_color(self, condition):
        """Get color for weather icon"""
        colors = {
            'Clear': (255, 220, 0),
            'Clouds': (200, 200, 200),
            'Rain': (100, 150, 255),
            'Drizzle': (120, 170, 255),
            'Snow': (240, 240, 255),
            'Thunderstorm': (255, 200, 0),
            'Mist': (180, 180, 180),
            'Fog': (160, 160, 160),
            'Haze': (200, 180, 160),
            'Smoke': (140, 140, 140)
        }
        return colors.get(condition, (200, 200, 200))

    def _get_condition_abbrev(self, condition):
        """Get abbreviated condition text"""
        abbrev = {
            'Clear': 'CLEAR',
            'Clouds': 'CLOUD',
            'Rain': 'RAIN',
            'Drizzle': 'DRZL',
            'Snow': 'SNOW',
            'Thunderstorm': 'STRM',
            'Mist': 'MIST',
            'Fog': 'FOG',
            'Haze': 'HAZE',
            'Smoke': 'SMOKE'
        }
        return abbrev.get(condition, condition[:5].upper())

    def _initialize_animations(self):
        """Initialize all animation objects at startup"""
        import random

        # Initialize all animation types
        self.rain_drops = []
        for i in range(12):
            self.rain_drops.append({
                'x': random.randint(0, 95),
                'y': random.randint(-10, 30),
                'speed': random.uniform(1.5, 2.5)
            })

        self.snow_flakes = []
        for i in range(15):
            self.snow_flakes.append({
                'x': random.randint(0, 95),
                'y': random.randint(-10, 30),
                'speed': random.uniform(0.3, 0.8),
                'drift': random.uniform(-0.2, 0.2)
            })

        self.cloud_positions = []
        for i in range(3):
            self.cloud_positions.append({
                'x': random.randint(-20, 96),
                'y': random.randint(2, 42),
                'speed': random.uniform(0.5, 1.0),
                'width': random.randint(8, 14)
            })

        self.star_twinkle = []
        for i in range(12):
            self.star_twinkle.append({
                'x': random.randint(0, 95),
                'y': random.randint(0, 35),
                'brightness': random.randint(150, 255),
                'direction': random.choice([-1, 1]),
                'speed': random.uniform(2, 5)
            })

        self.animation_frame = 0
        self.lightning_flash = 0

    def _initialize_animations_for_condition(self, condition, time_period):
        """Reinitialize animations when condition or time period changes"""
        import random

        print(
            f"Reinitializing animations for {condition} during {time_period}")

        # Reset animation frame counter for fresh start
        self.animation_frame = 0

        # Only reinitialize the relevant animation type
        if condition in ['Rain', 'Drizzle', 'Thunderstorm']:
            self.rain_drops = []
            for i in range(12):
                self.rain_drops.append({
                    'x': random.randint(0, 95),
                    'y': random.randint(-10, 30),
                    'speed': random.uniform(1.5, 2.5)
                })
            if condition == 'Thunderstorm':
                self.lightning_flash = 0

        elif condition == 'Snow':
            self.snow_flakes = []
            for i in range(15):
                self.snow_flakes.append({
                    'x': random.randint(0, 95),
                    'y': random.randint(-10, 30),
                    'speed': random.uniform(0.3, 0.8),
                    'drift': random.uniform(-0.2, 0.2)
                })

        elif condition == 'Clouds':
            self.cloud_positions = []
            for i in range(3):
                self.cloud_positions.append({
                    'x': random.randint(-20, 96),
                    'y': random.randint(2, 42),
                    'speed': random.uniform(0.5, 1.0),
                    'width': random.randint(8, 14)
                })

        elif condition == 'Clear':
            if time_period == 'night':
                # Fresh stars for night time!
                self.star_twinkle = []
                for i in range(12):
                    self.star_twinkle.append({
                        'x': random.randint(0, 95),
                        'y': random.randint(0, 35),
                        'brightness': random.randint(100, 255),
                        'direction': random.choice([-1, 1]),
                        'speed': random.uniform(8, 15)
                    })

    def _draw_animated_weather(self, condition, hour, time_period):
        """Draw animated weather effects"""
        if condition in ['Rain', 'Drizzle']:
            self._animate_rain()
        elif condition == 'Thunderstorm':
            self._animate_thunderstorm()
        elif condition == 'Snow':
            self._animate_snow()
        elif condition == 'Clouds':
            self._animate_clouds()
        elif condition == 'Clear':
            if time_period in ['day', 'dawn', 'dusk']:
                self._animate_sun()
            else:  # night
                self._animate_stars()

    def _animate_rain(self):
        """Animate falling rain"""
        import random
        for drop in self.rain_drops:
            y = int(drop['y'])
            if 0 <= y < 47:
                self.manager.draw_pixel(drop['x'], y, 180, 200, 220)
            if 0 <= y + 1 < 48:
                self.manager.draw_pixel(drop['x'], y + 1, 160, 180, 200)
            drop['y'] += drop['speed']
            if drop['y'] > 48:
                drop['y'] = -2
                drop['x'] = random.randint(0, 95)
                drop['speed'] = random.uniform(2.5, 3.5)

    def _animate_snow(self):
        """Animate falling snow"""
        import random
        for flake in self.snow_flakes:
            x = int(flake['x'])
            y = int(flake['y'])
            if 0 <= y < 48 and 0 <= x < 96:
                self.manager.draw_pixel(x, y, 255, 255, 255)
                if x > 0:
                    self.manager.draw_pixel(x - 1, y, 240, 240, 245)
                if x < 95:
                    self.manager.draw_pixel(x + 1, y, 240, 240, 245)
                if y > 0:
                    self.manager.draw_pixel(x, y - 1, 240, 240, 245)
            flake['y'] += flake['speed']
            flake['x'] += flake['drift']
            if flake['x'] < 0:
                flake['x'] = 95
            elif flake['x'] > 95:
                flake['x'] = 0
            if flake['y'] > 48:
                flake['y'] = -2
                flake['x'] = random.randint(0, 95)

    def _animate_clouds(self):
        """Animate drifting clouds with rounded edges"""
        import random
        for cloud in self.cloud_positions:
            x_start = int(cloud['x'])
            y = cloud['y']
            width = cloud['width']
            # Bright white clouds for visibility
            cloud_color = (255, 255, 255)

            # Draw cloud with rounded, puffy shape
            for x_offset in range(width):
                x = x_start + x_offset
                if 0 <= x < 96:
                    # Determine if we're at the edges
                    at_left_edge = x_offset < 2
                    at_right_edge = x_offset >= width - 2
                    at_edge = at_left_edge or at_right_edge

                    # Top layer - only draw in middle, skip edges for rounding
                    if not at_edge and y > 1 and 0 <= y - 2 < 48:
                        self.manager.draw_pixel(x, y - 2, 200, 200, 210)

                    # Upper shadow layer - softer at edges
                    if y > 0 and 0 <= y - 1 < 48:
                        if at_edge:
                            self.manager.draw_pixel(x, y - 1, 200, 200, 210)
                        else:
                            self.manager.draw_pixel(x, y - 1, 230, 230, 240)

                    # Main cloud body (bright white core - 2 rows)
                    if 0 <= y < 48:
                        self.manager.draw_pixel(x, y, *cloud_color)
                    if y < 47 and 0 <= y + 1 < 48:
                        self.manager.draw_pixel(x, y + 1, *cloud_color)

                    # Lower shadow layer - softer at edges
                    if y < 46 and 0 <= y + 2 < 48:
                        if at_edge:
                            self.manager.draw_pixel(x, y + 2, 200, 200, 210)
                        else:
                            self.manager.draw_pixel(x, y + 2, 230, 230, 240)

                    # Bottom layer - only draw in middle, skip edges for rounding
                    if not at_edge and y < 45 and 0 <= y + 3 < 48:
                        self.manager.draw_pixel(x, y + 3, 200, 200, 210)

            # Add rounded puffs on edges for organic look
            # Left rounded edge
            if x_start >= 0 and x_start < 96:
                if 0 <= y < 48:
                    self.manager.draw_pixel(x_start, y, 230, 230, 240)
                if y < 47 and 0 <= y + 1 < 48:
                    self.manager.draw_pixel(x_start, y + 1, 230, 230, 240)

            # Right rounded edge
            right_edge = x_start + width - 1
            if right_edge >= 0 and right_edge < 96:
                if 0 <= y < 48:
                    self.manager.draw_pixel(right_edge, y, 230, 230, 240)
                if y < 47 and 0 <= y + 1 < 48:
                    self.manager.draw_pixel(right_edge, y + 1, 230, 230, 240)

            # Move cloud
            cloud['x'] += cloud['speed']
            if cloud['x'] > 96:
                cloud['x'] = -cloud['width']
                cloud['y'] = random.randint(2, 10)

    def _animate_thunderstorm(self):
        """Animate thunderstorm with rain and lightning"""
        import random
        self._animate_rain()
        if self.animation_frame % 100 == 0 and random.random() > 0.7:
            self.lightning_flash = 3
        if self.lightning_flash > 0:
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
        sun_x, sun_y = 88, 5
        pulse = int(abs(math.sin(self.animation_frame * 0.1) * 20))
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                if dx * dx + dy * dy <= 4:
                    brightness = min(255, 235 + pulse)
                    self.manager.draw_pixel(
                        sun_x + dx, sun_y + dy, brightness, brightness, 100)
        for angle in [0, 45, 90, 135, 180, 225, 270, 315]:
            ray_length = 4 + int(pulse / 10)
            ray_x = sun_x + int(ray_length * math.cos(math.radians(angle)))
            ray_y = sun_y + int(ray_length * math.sin(math.radians(angle)))
            if 0 <= ray_x < 96 and 0 <= ray_y < 48:
                self.manager.draw_pixel(ray_x, ray_y, 255, 255, 150)

    def _animate_stars(self):
        """Animate twinkling stars"""
        for star in self.star_twinkle:
            brightness = int(star['brightness'])
            # Clamp brightness to valid range (0-255)
            brightness = max(0, min(255, brightness))
            # Clamp the blue component to prevent overflow
            blue_brightness = min(255, brightness + 20)

            if 0 <= star['x'] < 96 and 0 <= star['y'] < 48:
                # Draw the star with current brightness
                self.manager.draw_pixel(
                    star['x'], star['y'], brightness, brightness, blue_brightness)

                # Add a subtle glow effect for brighter stars
                if brightness > 200:
                    glow_brightness = int(brightness * 0.4)
                    # Draw glow pixels around the star
                    if star['x'] > 0:
                        self.manager.draw_pixel(
                            star['x'] - 1, star['y'], glow_brightness, glow_brightness, min(255, glow_brightness + 10))
                    if star['x'] < 95:
                        self.manager.draw_pixel(
                            star['x'] + 1, star['y'], glow_brightness, glow_brightness, min(255, glow_brightness + 10))
                    if star['y'] > 0:
                        self.manager.draw_pixel(
                            star['x'], star['y'] - 1, glow_brightness, glow_brightness, min(255, glow_brightness + 10))
                    if star['y'] < 47:
                        self.manager.draw_pixel(
                            star['x'], star['y'] + 1, glow_brightness, glow_brightness, min(255, glow_brightness + 10))

            # Update brightness for twinkling
            star['brightness'] += star['direction'] * star['speed']

            # Reverse direction at brightness limits with wider range
            if star['brightness'] >= 255:
                star['brightness'] = 255
                star['direction'] = -1
            elif star['brightness'] <= 80:
                star['brightness'] = 80
                star['direction'] = 1
