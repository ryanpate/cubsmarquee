"""Flight tracking display - Shows aircraft flying overhead using OpenSky Network API"""

from __future__ import annotations

import time
import requests
import json
import os
import math
from typing import TYPE_CHECKING, Any

from scoreboard_config import Colors, GameConfig, DisplayConfig, RGBColor

if TYPE_CHECKING:
    from scoreboard_manager import ScoreboardManager


class FlightDisplay:
    """Handles flight tracking information display"""

    # Minimum altitude in feet to display (filters out ground traffic)
    MIN_ALTITUDE_FT: int = 1000

    # Time to display each flight in seconds
    FLIGHT_DISPLAY_TIME: int = 10

    # Cache file for destination lookups
    DESTINATION_CACHE_FILE: str = '/home/pi/flight_destination_cache.json'
    DESTINATION_CACHE_FILE_ALT: str = './flight_destination_cache.json'

    # Cache expiry time (7 days in seconds) - flight routes don't change often
    CACHE_EXPIRY: int = 7 * 24 * 60 * 60

    def __init__(self, scoreboard_manager: ScoreboardManager) -> None:
        """Initialize flight display"""
        self.manager = scoreboard_manager
        self.flight_data: list[dict[str, Any]] = []

        # Load location configuration
        self.latitude: float | None = None
        self.longitude: float | None = None
        self.airlabs_api_key: str | None = None
        self._load_config()

        # Load destination cache
        self.destination_cache: dict[str, dict[str, Any]] = {}
        self._load_destination_cache()

        # Flight display colors (using centralized config)
        self.FLIGHT_BLUE: RGBColor = Colors.FLIGHT_BLUE
        self.FLIGHT_DARK_BLUE: RGBColor = Colors.FLIGHT_DARK_BLUE
        self.FLIGHT_WHITE: RGBColor = Colors.WHITE
        self.ALTITUDE_HIGH: RGBColor = Colors.FLIGHT_ALTITUDE_HIGH
        self.ALTITUDE_MED: RGBColor = Colors.FLIGHT_ALTITUDE_MED
        self.ALTITUDE_LOW: RGBColor = Colors.FLIGHT_ALTITUDE_LOW

    def _load_config(self) -> None:
        """Load configuration from config file"""
        config_path = '/home/pi/config.json'
        alt_config_path = './config.json'

        config_file = config_path if os.path.exists(config_path) else alt_config_path

        try:
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    config = json.load(f)
                    self.latitude = config.get('flight_tracking_latitude')
                    self.longitude = config.get('flight_tracking_longitude')
                    self.airlabs_api_key = config.get('airlabs_api_key', '')

                    if self.latitude and self.longitude:
                        print(f"Flight tracking location loaded: {self.latitude}, {self.longitude}")
                    else:
                        print("Flight tracking location not configured")

                    if self.airlabs_api_key:
                        print("AirLabs API key configured for destination lookups")
                    else:
                        print("AirLabs API key not configured - destinations will show as UNKNOWN")
        except Exception as e:
            print(f"Error loading flight tracking config: {e}")

    def _load_destination_cache(self) -> None:
        """Load cached destination data from file"""
        cache_file = self.DESTINATION_CACHE_FILE if os.path.exists(self.DESTINATION_CACHE_FILE) else self.DESTINATION_CACHE_FILE_ALT

        try:
            if os.path.exists(cache_file):
                with open(cache_file, 'r') as f:
                    self.destination_cache = json.load(f)
                    # Clean expired entries
                    current_time = time.time()
                    expired_keys = [
                        k for k, v in self.destination_cache.items()
                        if current_time - v.get('timestamp', 0) > self.CACHE_EXPIRY
                    ]
                    for key in expired_keys:
                        del self.destination_cache[key]
                    print(f"Loaded {len(self.destination_cache)} cached flight destinations")
        except Exception as e:
            print(f"Error loading destination cache: {e}")
            self.destination_cache = {}

    def _save_destination_cache(self) -> None:
        """Save destination cache to file"""
        cache_file = self.DESTINATION_CACHE_FILE if os.path.exists(os.path.dirname(self.DESTINATION_CACHE_FILE) or '/home/pi') else self.DESTINATION_CACHE_FILE_ALT

        try:
            with open(cache_file, 'w') as f:
                json.dump(self.destination_cache, f)
        except Exception as e:
            print(f"Error saving destination cache: {e}")

    def _lookup_destination_airlabs(self, callsign: str) -> str | None:
        """
        Look up flight destination using AirLabs API.
        Returns airport IATA code or None if not found.
        """
        if not self.airlabs_api_key:
            return None

        # Check cache first
        if callsign in self.destination_cache:
            cached = self.destination_cache[callsign]
            if time.time() - cached.get('timestamp', 0) < self.CACHE_EXPIRY:
                return cached.get('destination')

        try:
            # AirLabs flight API - can search by flight_icao (callsign)
            url = f"https://airlabs.co/api/v9/flight?flight_icao={callsign}&api_key={self.airlabs_api_key}"

            response = requests.get(url, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if data.get('response'):
                    flight_info = data['response']
                    arr_iata = flight_info.get('arr_iata')
                    dep_iata = flight_info.get('dep_iata')

                    if arr_iata:
                        # Cache the result
                        self.destination_cache[callsign] = {
                            'destination': arr_iata,
                            'departure': dep_iata,
                            'timestamp': time.time()
                        }
                        self._save_destination_cache()
                        print(f"AirLabs: {callsign} -> {dep_iata} to {arr_iata}")
                        return arr_iata

            # Also try with flight_iata format (some callsigns need this)
            # Convert ICAO callsign to potential IATA format
            # e.g., UAL123 -> UA123, AAL456 -> AA456
            iata_callsign = self._icao_to_iata_callsign(callsign)
            if iata_callsign and iata_callsign != callsign:
                url = f"https://airlabs.co/api/v9/flight?flight_iata={iata_callsign}&api_key={self.airlabs_api_key}"
                response = requests.get(url, timeout=10)

                if response.status_code == 200:
                    data = response.json()
                    if data.get('response'):
                        flight_info = data['response']
                        arr_iata = flight_info.get('arr_iata')
                        dep_iata = flight_info.get('dep_iata')

                        if arr_iata:
                            self.destination_cache[callsign] = {
                                'destination': arr_iata,
                                'departure': dep_iata,
                                'timestamp': time.time()
                            }
                            self._save_destination_cache()
                            print(f"AirLabs: {callsign} ({iata_callsign}) -> {dep_iata} to {arr_iata}")
                            return arr_iata

        except requests.exceptions.Timeout:
            print(f"AirLabs timeout for {callsign}")
        except Exception as e:
            print(f"AirLabs error for {callsign}: {e}")

        # Cache negative result to avoid repeated lookups
        self.destination_cache[callsign] = {
            'destination': None,
            'timestamp': time.time()
        }
        self._save_destination_cache()
        return None

    def _icao_to_iata_callsign(self, icao_callsign: str) -> str | None:
        """
        Convert ICAO callsign to IATA format.
        Common conversions: UAL -> UA, AAL -> AA, DAL -> DL, SWA -> WN, etc.
        """
        # Common ICAO to IATA airline code mappings
        icao_to_iata = {
            'UAL': 'UA',   # United
            'AAL': 'AA',   # American
            'DAL': 'DL',   # Delta
            'SWA': 'WN',   # Southwest
            'JBU': 'B6',   # JetBlue
            'ASA': 'AS',   # Alaska
            'NKS': 'NK',   # Spirit
            'FFT': 'F9',   # Frontier
            'SKW': 'OO',   # SkyWest
            'RPA': 'YX',   # Republic
            'ENY': 'MQ',   # Envoy (American Eagle)
            'PDT': 'PT',   # Piedmont
            'EJA': 'EJ',   # NetJets
            'FDX': 'FX',   # FedEx
            'UPS': '5X',   # UPS
            'BAW': 'BA',   # British Airways
            'AFR': 'AF',   # Air France
            'DLH': 'LH',   # Lufthansa
            'ACA': 'AC',   # Air Canada
            'ETD': 'EY',   # Etihad
            'UAE': 'EK',   # Emirates
            'QTR': 'QR',   # Qatar
            'CPA': 'CX',   # Cathay Pacific
            'ANA': 'NH',   # All Nippon
            'JAL': 'JL',   # Japan Airlines
            'KAL': 'KE',   # Korean Air
            'SIA': 'SQ',   # Singapore Airlines
        }

        # Extract airline code (first 3 letters) and flight number
        if len(icao_callsign) >= 4:
            icao_code = icao_callsign[:3].upper()
            flight_num = icao_callsign[3:]

            if icao_code in icao_to_iata:
                return f"{icao_to_iata[icao_code]}{flight_num}"

        return None

    def _calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculate distance between two points using Haversine formula.
        Returns distance in miles.
        """
        R = 3959  # Earth's radius in miles

        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)

        a = (math.sin(delta_lat / 2) ** 2 +
             math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c

    def _fetch_flight_data(self) -> bool:
        """
        Fetch flight data from OpenSky Network API.
        Uses bounding box query around configured location.
        """
        if not self.latitude or not self.longitude:
            print("Flight tracking: Location not configured")
            return False

        try:
            # Calculate bounding box
            box_size = GameConfig.FLIGHT_BOUNDING_BOX_SIZE
            lamin = self.latitude - box_size
            lamax = self.latitude + box_size
            lomin = self.longitude - box_size
            lomax = self.longitude + box_size

            # OpenSky Network API endpoint
            url = f"https://opensky-network.org/api/states/all?lamin={lamin}&lamax={lamax}&lomin={lomin}&lomax={lomax}"

            print(f"Fetching flights from OpenSky...")

            response = requests.get(
                url,
                timeout=15,
                headers={'User-Agent': 'CubsMarquee/1.0'}
            )

            if response.status_code == 200:
                data = response.json()
                states = data.get('states', [])

                # Parse flight data
                flights = []
                for state in states:
                    if len(state) >= 14:
                        callsign = (state[1] or '').strip()
                        if not callsign:
                            continue

                        flight_lat = state[6]
                        flight_lon = state[5]
                        altitude_m = state[7] or state[13]  # baro_altitude or geo_altitude
                        velocity_ms = state[9]
                        origin_country = state[2]

                        # Skip if missing critical data
                        if flight_lat is None or flight_lon is None:
                            continue

                        # Convert altitude from meters to feet
                        altitude_ft = int(altitude_m * 3.28084) if altitude_m else 0

                        # Filter out flights below minimum altitude
                        if altitude_ft < self.MIN_ALTITUDE_FT:
                            continue

                        # Convert velocity from m/s to mph
                        velocity_mph = int(velocity_ms * 2.237) if velocity_ms else 0

                        # Calculate distance from center point
                        distance = self._calculate_distance(
                            self.latitude, self.longitude,
                            flight_lat, flight_lon
                        )

                        flights.append({
                            'callsign': callsign,
                            'altitude_ft': altitude_ft,
                            'velocity_mph': velocity_mph,
                            'distance': distance,
                            'origin_country': origin_country,
                            'latitude': flight_lat,
                            'longitude': flight_lon,
                            'destination': 'UNKNOWN'  # Will be filled in by AirLabs
                        })

                # Sort by distance (closest first)
                flights.sort(key=lambda x: x['distance'])

                self.flight_data = flights[:15]  # Keep top 15 closest flights

                print(f"OpenSky: {len(self.flight_data)} flights found (above {self.MIN_ALTITUDE_FT} ft)")

                # Now look up destinations for each flight via AirLabs
                if self.airlabs_api_key and self.flight_data:
                    print("Looking up destinations via AirLabs...")
                    for flight in self.flight_data:
                        callsign = flight['callsign']

                        # Check cache first
                        if callsign in self.destination_cache:
                            cached = self.destination_cache[callsign]
                            if time.time() - cached.get('timestamp', 0) < self.CACHE_EXPIRY:
                                dest = cached.get('destination')
                                if dest:
                                    flight['destination'] = dest
                                continue

                        # Look up via API
                        dest = self._lookup_destination_airlabs(callsign)
                        if dest:
                            flight['destination'] = dest

                        # Small delay to avoid rate limiting
                        time.sleep(0.2)

                return True

            elif response.status_code == 429:
                print("OpenSky API rate limit reached")
                return False
            else:
                print(f"OpenSky API error: {response.status_code}")
                return False

        except requests.exceptions.Timeout:
            print("OpenSky API timeout")
            return False
        except Exception as e:
            print(f"Error fetching flight data: {e}")
            return False

    def _get_altitude_color(self, altitude_ft: int) -> RGBColor:
        """Get color based on altitude"""
        if altitude_ft >= 30000:
            return self.ALTITUDE_HIGH  # Gold for high altitude
        elif altitude_ft >= 15000:
            return self.ALTITUDE_MED   # Orange for medium altitude
        else:
            return self.ALTITUDE_LOW   # Green for low altitude

    def _draw_flight_header(self) -> None:
        """Draw sky gradient header for flight display"""
        # Sky gradient background - lighter blue at top, darker at bottom
        for y in range(DisplayConfig.MATRIX_ROWS):
            if y < 14:
                # Header area - dark blue
                for x in range(DisplayConfig.MATRIX_COLS):
                    self.manager.draw_pixel(x, y, *self.FLIGHT_DARK_BLUE)
            else:
                # Content area - slightly lighter blue
                for x in range(DisplayConfig.MATRIX_COLS):
                    self.manager.draw_pixel(x, y, 20, 50, 100)

        # Light blue bar at top (y=0-2) - sky highlight
        for y in range(3):
            for x in range(DisplayConfig.MATRIX_COLS):
                self.manager.draw_pixel(x, y, 100, 180, 255)

        # Draw thin white separator line below header
        for x in range(DisplayConfig.MATRIX_COLS):
            self.manager.draw_pixel(x, 13, 150, 150, 150)

        # Draw simple airplane icon at left
        plane_y = 8
        plane_x = 3
        # Fuselage
        for i in range(5):
            self.manager.draw_pixel(plane_x + i, plane_y, *self.FLIGHT_WHITE)
        # Wings
        self.manager.draw_pixel(plane_x + 2, plane_y - 1, *self.FLIGHT_WHITE)
        self.manager.draw_pixel(plane_x + 2, plane_y + 1, *self.FLIGHT_WHITE)
        self.manager.draw_pixel(plane_x + 2, plane_y - 2, *self.FLIGHT_WHITE)
        self.manager.draw_pixel(plane_x + 2, plane_y + 2, *self.FLIGHT_WHITE)
        # Tail
        self.manager.draw_pixel(plane_x, plane_y - 1, *self.FLIGHT_WHITE)

        # "OVERHEAD FLIGHT" text
        self.manager.draw_text('tiny_bold', 14, 11, self.FLIGHT_WHITE, 'OVERHEAD FLIGHT')

    def _display_no_location(self, duration: int) -> None:
        """Display message when location is not configured"""
        start_time = time.time()
        scroll_position = DisplayConfig.MATRIX_COLS
        message = "CONFIGURE LOCATION IN ADMIN PANEL"

        while time.time() - start_time < duration:
            self.manager.clear_canvas()
            self._draw_flight_header()

            # Scroll the message
            scroll_increment = getattr(GameConfig, 'SCROLL_PIXELS', 1)
            scroll_position -= scroll_increment
            text_length = len(message) * 5

            if scroll_position + text_length < 0:
                scroll_position = DisplayConfig.MATRIX_COLS

            self.manager.draw_text('tiny_bold', int(scroll_position), 32,
                                   self.FLIGHT_WHITE, message)

            self.manager.swap_canvas()
            time.sleep(GameConfig.SCROLL_SPEED)

    def _display_no_flights(self, duration: int) -> None:
        """Display message when no flights are detected"""
        start_time = time.time()

        while time.time() - start_time < duration:
            self.manager.clear_canvas()
            self._draw_flight_header()

            # Static centered message
            message = "NO FLIGHTS"
            msg_x = (DisplayConfig.MATRIX_COLS - len(message) * 5) // 2
            self.manager.draw_text('tiny_bold', msg_x, 28, self.FLIGHT_WHITE, message)

            message2 = "OVERHEAD"
            msg2_x = (DisplayConfig.MATRIX_COLS - len(message2) * 5) // 2
            self.manager.draw_text('tiny_bold', msg2_x, 38, self.FLIGHT_WHITE, message2)

            self.manager.swap_canvas()
            time.sleep(0.5)

    def _display_single_flight(self, flight: dict[str, Any], display_time: int) -> None:
        """Display a single flight's information for the specified duration"""
        start_time = time.time()

        callsign = flight['callsign']
        altitude_ft = flight['altitude_ft']
        velocity_mph = flight['velocity_mph']
        destination = flight.get('destination', 'UNKNOWN')

        # Get altitude color
        alt_color = self._get_altitude_color(altitude_ft)

        # Format altitude with commas
        if altitude_ft >= 1000:
            alt_str = f"{altitude_ft:,} FT"
        else:
            alt_str = f"{altitude_ft} FT"

        while time.time() - start_time < display_time:
            self.manager.clear_canvas()
            self._draw_flight_header()

            # Flight callsign - large and centered (y=22)
            callsign_width = len(callsign) * 6  # small_bold font width
            callsign_x = (DisplayConfig.MATRIX_COLS - callsign_width) // 2
            self.manager.draw_text('small_bold', callsign_x, 22, self.ALTITUDE_HIGH, callsign)

            # Altitude line (y=31)
            alt_label = "ALT:"
            self.manager.draw_text('tiny', 4, 31, (150, 150, 150), alt_label)
            self.manager.draw_text('tiny', 28, 31, alt_color, alt_str)

            # Speed line (y=39)
            spd_label = "SPD:"
            spd_str = f"{velocity_mph} MPH"
            self.manager.draw_text('tiny', 4, 39, (150, 150, 150), spd_label)
            self.manager.draw_text('tiny', 28, 39, self.FLIGHT_WHITE, spd_str)

            # Destination line (y=47)
            dest_label = "TO:"
            self.manager.draw_text('tiny', 4, 47, (150, 150, 150), dest_label)
            # Truncate destination if too long
            dest_display = destination[:12] if len(destination) > 12 else destination
            self.manager.draw_text('tiny', 24, 47, self.FLIGHT_WHITE, dest_display)

            self.manager.swap_canvas()
            time.sleep(0.1)

    def display_flight_info(self, duration: int = 120) -> None:
        """Main display method for flight tracking - cycles through flights one at a time"""
        # Reload config in case API key was added
        self._load_config()

        # Check if location is configured
        if not self.latitude or not self.longitude:
            self._display_no_location(duration)
            return

        # Fetch flight data ONCE at the start of display cycle
        self._fetch_flight_data()

        # Check if we have any flights
        if not self.flight_data:
            self._display_no_flights(duration)
            return

        # Cycle through flights one at a time
        start_time = time.time()
        flight_index = 0

        while time.time() - start_time < duration:
            # Get current flight
            flight = self.flight_data[flight_index]

            # Display this flight for FLIGHT_DISPLAY_TIME seconds
            self._display_single_flight(flight, self.FLIGHT_DISPLAY_TIME)

            # Move to next flight
            flight_index = (flight_index + 1) % len(self.flight_data)
