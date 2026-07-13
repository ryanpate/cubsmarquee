"""Flight tracking display - Shows aircraft flying overhead using local ADS-B receiver with OpenSky fallback"""

from __future__ import annotations

import time
import requests
import json
import os
import math
from PIL import Image
from typing import TYPE_CHECKING, Any

from scoreboard_config import Colors, GameConfig, DisplayConfig, RGBColor, get_scroll_delay, load_user_config
from adsb_lol_source import fetch_aircraft as adsb_lol_fetch_aircraft
from adsb_lol_source import enrich_routes as adsb_lol_enrich_routes
from route_cache import RouteCache

if TYPE_CHECKING:
    from scoreboard_manager import ScoreboardManager


class FlightDisplay:
    """Handles flight tracking information display"""

    # Minimum altitude in feet to display (filters out ground traffic)
    MIN_ALTITUDE_FT: int = 1000

    # Time to display each flight in seconds
    FLIGHT_DISPLAY_TIME: int = 10

    # Summary view duration in seconds
    SUMMARY_DISPLAY_TIME: int = 5

    # Cache file for destination lookups
    DESTINATION_CACHE_FILE: str = '/var/tmp/flight_destination_cache.json'
    DESTINATION_CACHE_FILE_ALT: str = './flight_destination_cache.json'

    # Cache expiry time (7 days in seconds) - flight routes don't change often
    CACHE_EXPIRY: int = 7 * 24 * 60 * 60

    # Cardinal direction labels
    CARDINAL_DIRECTIONS: list[str] = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']

    # ICAO callsign prefix -> airline display name
    AIRLINE_NAMES: dict[str, str] = {
        'UAL': 'UNITED', 'AAL': 'AMERICAN', 'DAL': 'DELTA', 'SWA': 'SOUTHWEST',
        'JBU': 'JETBLUE', 'ASA': 'ALASKA', 'NKS': 'SPIRIT', 'FFT': 'FRONTIER',
        'SKW': 'SKYWEST', 'RPA': 'REPUBLIC', 'ENY': 'ENVOY', 'PDT': 'PIEDMONT',
        'EJA': 'NETJETS', 'FDX': 'FEDEX', 'UPS': 'UPS', 'BAW': 'BRITISH',
        'AFR': 'AIR FRANCE', 'DLH': 'LUFTHANSA', 'ACA': 'AIR CANADA',
        'ETD': 'ETIHAD', 'UAE': 'EMIRATES', 'QTR': 'QATAR', 'CPA': 'CATHAY',
        'ANA': 'ANA', 'JAL': 'JAPAN AIR', 'KAL': 'KOREAN', 'SIA': 'SINGAPORE',
    }

    def __init__(self, scoreboard_manager: ScoreboardManager) -> None:
        """Initialize flight display"""
        self.manager = scoreboard_manager
        self.flight_data: list[dict[str, Any]] = []
        self.last_fetch_time: float = 0

        # Load location configuration
        self.latitude: float | None = None
        self.longitude: float | None = None
        self.airlabs_api_key: str | None = None
        self.flight_source: str = ''
        self.adsb_receiver_url: str = GameConfig.ADSB_RECEIVER_URL
        self.flight_max_range_nm: int = GameConfig.FLIGHT_MAX_RANGE_NM
        self.enable_flight_radar: bool = True
        self.route_cache: RouteCache = RouteCache(
            db_path=GameConfig.ROUTE_CACHE_DB_PATH,
            ttl_hours=GameConfig.ROUTE_CACHE_TTL_HOURS,
        )
        self._load_config()
        # Prefer the explicit `flight_source` admin setting; fall back to the
        # legacy behavior (empty adsb_receiver_url means use adsb.lol).
        if self.flight_source in ('adsb_lol', 'local'):
            self.use_adsb_lol: bool = (self.flight_source == 'adsb_lol')
        else:
            self.use_adsb_lol = not (self.adsb_receiver_url or "").strip()
        print(
            f"Flight data source: "
            f"{'adsb.lol' if self.use_adsb_lol else f'local ({self.adsb_receiver_url})'}"
        )

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

        # Pre-generate cached background image for performance
        self._flight_header_bg: Image.Image = self._create_flight_header_background()

    def _create_flight_header_background(self) -> Image.Image:
        """Pre-generate flight header background image for performance"""
        img = Image.new("RGB", (DisplayConfig.MATRIX_COLS, DisplayConfig.MATRIX_ROWS))
        pixels = img.load()
        # Header area - sky gradient fading down into the night
        for y in range(14):
            t = y / 13.0
            color = (int(55 - 43 * t), int(110 - 82 * t), int(180 - 124 * t))
            for x in range(DisplayConfig.MATRIX_COLS):
                pixels[x, y] = color
        # Content area - deep navy for text contrast
        for y in range(14, DisplayConfig.MATRIX_ROWS):
            for x in range(DisplayConfig.MATRIX_COLS):
                pixels[x, y] = (10, 24, 48)
        print("Flight header background cached")
        return img

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
                    self.flight_source = config.get('flight_source', '')
                    self.adsb_receiver_url = config.get(
                        'adsb_receiver_url', GameConfig.ADSB_RECEIVER_URL)
                    self.flight_max_range_nm = config.get(
                        'flight_max_range_nm', GameConfig.FLIGHT_MAX_RANGE_NM)
                    self.enable_flight_radar = config.get('enable_flight_radar', True)

                    if self.latitude and self.longitude:
                        print(f"Flight tracking location loaded: {self.latitude}, {self.longitude}")
                    else:
                        print("Flight tracking location not configured")

                    if self.airlabs_api_key:
                        print("AirLabs API key configured for destination lookups")
        except Exception as e:
            print(f"Error loading flight tracking config: {e}")

    def _load_scroll_config(self) -> dict:
        """Load scroll speed settings from config file"""
        return load_user_config()

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

    def _lookup_destination_airplaneslive(self, hex_code: str) -> str | None:
        """
        Look up flight destination using airplanes.live API (free, no key needed).
        Returns airport IATA code or None if not found.
        """
        if not hex_code:
            return None

        # Check cache first using hex code
        cache_key = f"hex_{hex_code}"
        if cache_key in self.destination_cache:
            cached = self.destination_cache[cache_key]
            if time.time() - cached.get('timestamp', 0) < self.CACHE_EXPIRY:
                return cached.get('destination')

        try:
            url = f"https://api.airplanes.live/v2/hex/{hex_code}"
            response = requests.get(url, timeout=5)

            if response.status_code == 200:
                data = response.json()
                aircraft_list = data.get('ac', [])
                if aircraft_list:
                    ac = aircraft_list[0]
                    # Try to get arrival airport
                    arr_iata = ac.get('dst', '')
                    dep_iata = ac.get('org', '')

                    if arr_iata:
                        self.destination_cache[cache_key] = {
                            'destination': arr_iata,
                            'departure': dep_iata,
                            'timestamp': time.time()
                        }
                        print(f"airplanes.live: {hex_code} -> {dep_iata} to {arr_iata}")
                        return arr_iata

        except requests.exceptions.Timeout:
            print(f"airplanes.live timeout for {hex_code}")
        except Exception as e:
            print(f"airplanes.live error for {hex_code}: {e}")

        # Cache negative result
        self.destination_cache[cache_key] = {
            'destination': None,
            'timestamp': time.time()
        }
        return None

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
            url = f"https://airlabs.co/api/v9/flight?flight_icao={callsign}&api_key={self.airlabs_api_key}"
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
                        return arr_iata

            # Try IATA format
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
                            return arr_iata

        except requests.exceptions.Timeout:
            print(f"AirLabs timeout for {callsign}")
        except Exception as e:
            print(f"AirLabs error for {callsign}: {e}")

        # Cache negative result
        self.destination_cache[callsign] = {
            'destination': None,
            'timestamp': time.time()
        }
        return None

    # Airport IATA code to city name mapping
    AIRPORT_CITIES: dict[str, str] = {
        # Major US Hubs
        'ATL': 'ATLANTA',
        'DFW': 'DALLAS',
        'DEN': 'DENVER',
        'ORD': 'CHICAGO',
        'MDW': 'CHICAGO',
        'LAX': 'LOS ANGELES',
        'CLT': 'CHARLOTTE',
        'LAS': 'LAS VEGAS',
        'PHX': 'PHOENIX',
        'MCO': 'ORLANDO',
        'SEA': 'SEATTLE',
        'MIA': 'MIAMI',
        'JFK': 'NEW YORK',
        'EWR': 'NEWARK',
        'LGA': 'NEW YORK',
        'SFO': 'SAN FRAN',
        'IAH': 'HOUSTON',
        'BOS': 'BOSTON',
        'FLL': 'FT LAUD',
        'MSP': 'MINNEAPOLIS',
        'DTW': 'DETROIT',
        'PHL': 'PHILLY',
        'SLC': 'SALT LAKE',
        'DCA': 'WASHINGTON',
        'IAD': 'WASHINGTON',
        'BWI': 'BALTIMORE',
        'SAN': 'SAN DIEGO',
        'TPA': 'TAMPA',
        'PDX': 'PORTLAND',
        'STL': 'ST LOUIS',
        'BNA': 'NASHVILLE',
        'AUS': 'AUSTIN',
        'HNL': 'HONOLULU',
        'OAK': 'OAKLAND',
        'SJC': 'SAN JOSE',
        'RDU': 'RALEIGH',
        'MCI': 'KANSAS CITY',
        'SMF': 'SACRAMENTO',
        'SNA': 'ORANGE CO',
        'CLE': 'CLEVELAND',
        'IND': 'INDIANAPOLIS',
        'PIT': 'PITTSBURGH',
        'CMH': 'COLUMBUS',
        'SAT': 'SAN ANTONIO',
        'MKE': 'MILWAUKEE',
        'JAX': 'JACKSONVILLE',
        'OMA': 'OMAHA',
        'ABQ': 'ALBUQUERQUE',
        'BUF': 'BUFFALO',
        'ONT': 'ONTARIO CA',
        'BUR': 'BURBANK',
        'RSW': 'FT MYERS',
        'PBI': 'PALM BEACH',
        'MSY': 'NEW ORLEANS',
        'RNO': 'RENO',
        'BOI': 'BOISE',
        'OKC': 'OKLAHOMA CITY',
        'TUS': 'TUCSON',
        'ELP': 'EL PASO',
        'SDF': 'LOUISVILLE',
        'CVG': 'CINCINNATI',
        'DSM': 'DES MOINES',
        'GRR': 'GRAND RAPIDS',
        'MSN': 'MADISON',
        'ORF': 'NORFOLK',
        'RIC': 'RICHMOND',
        'ALB': 'ALBANY',
        'SYR': 'SYRACUSE',
        'ROC': 'ROCHESTER',
        'PWM': 'PORTLAND ME',
        'BTV': 'BURLINGTON',
        'MHT': 'MANCHESTER',
        'PVD': 'PROVIDENCE',
        'HPN': 'WESTCHESTER',
        # International
        'YYZ': 'TORONTO',
        'YVR': 'VANCOUVER',
        'YUL': 'MONTREAL',
        'YYC': 'CALGARY',
        'MEX': 'MEXICO CITY',
        'CUN': 'CANCUN',
        'GDL': 'GUADALAJARA',
        'LHR': 'LONDON',
        'LGW': 'LONDON',
        'CDG': 'PARIS',
        'FRA': 'FRANKFURT',
        'AMS': 'AMSTERDAM',
        'MAD': 'MADRID',
        'BCN': 'BARCELONA',
        'FCO': 'ROME',
        'MUC': 'MUNICH',
        'ZRH': 'ZURICH',
        'DUB': 'DUBLIN',
        'NRT': 'TOKYO',
        'HND': 'TOKYO',
        'ICN': 'SEOUL',
        'PEK': 'BEIJING',
        'PVG': 'SHANGHAI',
        'HKG': 'HONG KONG',
        'SIN': 'SINGAPORE',
        'BKK': 'BANGKOK',
        'SYD': 'SYDNEY',
        'DXB': 'DUBAI',
        'DOH': 'DOHA',
    }

    def _get_airport_city(self, airport_code: str) -> str:
        """Convert airport IATA or ICAO code to city name.
        Handles ICAO codes like KORD -> ORD, KJFK -> JFK for US airports."""
        if not airport_code or airport_code == 'UNKNOWN':
            return 'UNKNOWN'
        code = airport_code.upper().strip()
        # Try direct IATA lookup first
        if code in self.AIRPORT_CITIES:
            return self.AIRPORT_CITIES[code]
        # Try stripping leading K for US ICAO codes (KORD -> ORD)
        if len(code) == 4 and code.startswith('K'):
            iata = code[1:]
            if iata in self.AIRPORT_CITIES:
                return self.AIRPORT_CITIES[iata]
        # Try stripping leading C for Canadian ICAO codes (CYYZ -> YYZ)
        if len(code) == 4 and code.startswith('C'):
            iata = code[1:]
            if iata in self.AIRPORT_CITIES:
                return self.AIRPORT_CITIES[iata]
        # Return the code itself as fallback
        return code

    def _icao_to_iata_callsign(self, icao_callsign: str) -> str | None:
        """Convert ICAO callsign to IATA format."""
        icao_to_iata = {
            'UAL': 'UA', 'AAL': 'AA', 'DAL': 'DL', 'SWA': 'WN',
            'JBU': 'B6', 'ASA': 'AS', 'NKS': 'NK', 'FFT': 'F9',
            'SKW': 'OO', 'RPA': 'YX', 'ENY': 'MQ', 'PDT': 'PT',
            'EJA': 'EJ', 'FDX': 'FX', 'UPS': '5X', 'BAW': 'BA',
            'AFR': 'AF', 'DLH': 'LH', 'ACA': 'AC', 'ETD': 'EY',
            'UAE': 'EK', 'QTR': 'QR', 'CPA': 'CX', 'ANA': 'NH',
            'JAL': 'JL', 'KAL': 'KE', 'SIA': 'SQ',
        }

        if len(icao_callsign) >= 4:
            icao_code = icao_callsign[:3].upper()
            flight_num = icao_callsign[3:]
            if icao_code in icao_to_iata:
                return f"{icao_to_iata[icao_code]}{flight_num}"
        return None

    def _calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two points using Haversine formula. Returns distance in miles."""
        R = 3959  # Earth's radius in miles
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)

        a = (math.sin(delta_lat / 2) ** 2 +
             math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

    def _degrees_to_cardinal(self, degrees: float) -> str:
        """Convert heading degrees to cardinal direction."""
        index = round(degrees / 45) % 8
        return self.CARDINAL_DIRECTIONS[index]

    def _airline_name(self, callsign: str) -> str | None:
        """Airline display name from an ICAO callsign prefix, or None"""
        if not callsign or len(callsign) < 4:
            return None
        return self.AIRLINE_NAMES.get(callsign[:3].upper())

    @staticmethod
    def _aircraft_category(type_code: str | None) -> str:
        """Bucket an ICAO type code into jet/regional/prop/heli for icons"""
        if not type_code:
            return ''
        code = type_code.upper()
        if code.startswith(('E1', 'E2', 'E7', 'CRJ', 'AT4', 'AT7', 'DH8')):
            return 'regional'
        if code.startswith(('R22', 'R44', 'R66', 'EC', 'H6', 'B06', 'AS3', 'S76')):
            return 'heli'
        if code.startswith(('C1', 'C2', 'P28', 'PA', 'SR2', 'BE', 'DA2', 'DA4', 'M20')):
            return 'prop'
        if code.startswith(('B', 'A', 'MD')):
            return 'jet'
        return ''

    @staticmethod
    def _heading_vector(heading: float, length: int) -> tuple[int, int]:
        """Pixel offset (dx, dy) for a heading, screen-north up"""
        rad = math.radians(heading)
        return (round(length * math.sin(rad)), round(-length * math.cos(rad)))

    @staticmethod
    def _sweep_angle(elapsed: float) -> int:
        """Radar sweep bearing in degrees; one revolution every 4 seconds"""
        return int((elapsed % 4.0) * 90) % 360

    @staticmethod
    def _dot_bearing(cx: int, cy: int, px: int, py: int) -> float:
        """Bearing in degrees from radar center to a dot, screen-north up"""
        return math.degrees(math.atan2(px - cx, cy - py)) % 360

    @staticmethod
    def _sweep_flare(sweep_deg: float, bearing_deg: float) -> float:
        """How brightly a dot flares after the sweep passes it: 1.0 right
        at the beam, fading to 0.0 over the 45 degrees behind it"""
        behind = (sweep_deg - bearing_deg) % 360
        if behind >= 45:
            return 0.0
        return 1.0 - behind / 45

    def _get_vertical_rate_indicator(
        self, vertical_rate: int | None
    ) -> tuple[str, RGBColor, str]:
        """Vertical rate as (text, color, direction) where direction is
        'up', 'down', or 'level' - the caller draws the matching triangle."""
        if vertical_rate is None:
            return ('', (150, 150, 150), 'level')

        if vertical_rate > 200:
            return (str(abs(vertical_rate)), (100, 255, 100), 'up')
        elif vertical_rate < -200:
            return (str(abs(vertical_rate)), (255, 130, 50), 'down')
        else:
            return ('LVL', (150, 150, 150), 'level')

    def _fetch_from_adsb_lol(self) -> bool:
        """Fetch flight data from adsb.lol. Returns True on success."""
        if not self.latitude or not self.longitude:
            return False

        flights = adsb_lol_fetch_aircraft(
            base_url=GameConfig.ADSB_LOL_BASE_URL,
            home_lat=self.latitude,
            home_lon=self.longitude,
            range_nm=self.flight_max_range_nm,
            min_altitude_ft=self.MIN_ALTITUDE_FT,
        )

        if not flights:
            return False

        try:
            adsb_lol_enrich_routes(
                base_url=GameConfig.ADSB_LOL_BASE_URL,
                flights=flights,
                cache=self.route_cache,
            )
        except Exception as e:
            # Route info is nice-to-have; never lose the flights over it
            print(f"Route enrichment failed: {e}")

        self.flight_data = flights
        print(f"adsb.lol: {len(self.flight_data)} flights found")
        return True

    def _fetch_from_adsb_receiver(self) -> bool:
        """
        Fetch flight data from local ADS-B receiver.
        Returns True if successful, False to trigger fallback.
        """
        if not self.latitude or not self.longitude:
            return False

        try:
            response = requests.get(self.adsb_receiver_url, timeout=3)

            if response.status_code == 200:
                data = response.json()
                aircraft_list = data.get('aircraft', [])

                flights = []
                max_range_mi = self.flight_max_range_nm * 1.15078  # NM to miles

                for ac in aircraft_list:
                    lat = ac.get('lat')
                    lon = ac.get('lon')
                    alt_baro = ac.get('alt_baro')

                    # Skip aircraft without position or on ground
                    if lat is None or lon is None:
                        continue
                    if alt_baro == 'ground' or alt_baro is None:
                        continue
                    if isinstance(alt_baro, str):
                        continue

                    # Filter below minimum altitude
                    altitude_ft = int(alt_baro)
                    if altitude_ft < self.MIN_ALTITUDE_FT:
                        continue

                    # Filter by freshness (skip stale contacts)
                    seen = ac.get('seen', 999)
                    if seen > 60:
                        continue

                    # Calculate distance
                    distance = self._calculate_distance(
                        self.latitude, self.longitude, lat, lon)

                    # Filter by max range
                    if distance > max_range_mi:
                        continue

                    # Get callsign, strip whitespace
                    callsign = (ac.get('flight') or '').strip()

                    # Convert ground speed from knots to MPH
                    gs_knots = ac.get('gs')
                    velocity_mph = int(gs_knots * 1.15078) if gs_knots else 0

                    flights.append({
                        'callsign': callsign or ac.get('r', '') or ac.get('hex', '').upper(),
                        'altitude_ft': altitude_ft,
                        'velocity_mph': velocity_mph,
                        'distance': distance,
                        'latitude': lat,
                        'longitude': lon,
                        'aircraft_type': ac.get('t', ''),
                        'registration': ac.get('r', ''),
                        'vertical_rate': ac.get('baro_rate'),
                        'heading': ac.get('track'),
                        'icao_hex': ac.get('hex', ''),
                        'destination': 'UNKNOWN',
                    })

                # Sort by distance (closest first)
                flights.sort(key=lambda x: x['distance'])
                self.flight_data = flights[:15]

                print(f"ADS-B receiver: {len(self.flight_data)} flights found (of {len(aircraft_list)} total)")

                # Look up destinations for flights with hex codes
                self._lookup_destinations()

                return True

        except requests.exceptions.ConnectionError:
            print("ADS-B receiver unreachable, falling back to OpenSky")
            return False
        except requests.exceptions.Timeout:
            print("ADS-B receiver timeout, falling back to OpenSky")
            return False
        except Exception as e:
            print(f"ADS-B receiver error: {e}, falling back to OpenSky")
            return False

    def _lookup_destinations(self) -> None:
        """Look up destinations for flights using airplanes.live (free) then AirLabs (paid)."""
        cache_before = dict(self.destination_cache)

        for flight in self.flight_data:
            callsign = flight['callsign']
            hex_code = flight.get('icao_hex', '')

            # Check callsign cache first
            if callsign and callsign in self.destination_cache:
                cached = self.destination_cache[callsign]
                if time.time() - cached.get('timestamp', 0) < self.CACHE_EXPIRY:
                    dest = cached.get('destination')
                    if dest:
                        flight['destination'] = dest
                    continue

            # Check hex cache
            cache_key = f"hex_{hex_code}"
            if hex_code and cache_key in self.destination_cache:
                cached = self.destination_cache[cache_key]
                if time.time() - cached.get('timestamp', 0) < self.CACHE_EXPIRY:
                    dest = cached.get('destination')
                    if dest:
                        flight['destination'] = dest
                    continue

            # Try airplanes.live first (free, no key needed)
            if hex_code:
                dest = self._lookup_destination_airplaneslive(hex_code)
                if dest:
                    flight['destination'] = dest
                    # Also cache under callsign for faster future lookups
                    if callsign:
                        self.destination_cache[callsign] = {
                            'destination': dest,
                            'timestamp': time.time()
                        }
                    continue

            # Fall back to AirLabs if configured
            if callsign and self.airlabs_api_key:
                dest = self._lookup_destination_airlabs(callsign)
                if dest:
                    flight['destination'] = dest

            # Small delay to avoid rate limiting
            time.sleep(0.2)

        # Persist once per cycle instead of once per lookup (SD-card wear)
        if self.destination_cache != cache_before:
            self._save_destination_cache()

    def _fetch_from_opensky(self) -> bool:
        """Fetch flight data from OpenSky Network API (fallback)."""
        if not self.latitude or not self.longitude:
            return False

        try:
            box_size = GameConfig.FLIGHT_BOUNDING_BOX_SIZE
            lamin = self.latitude - box_size
            lamax = self.latitude + box_size
            lomin = self.longitude - box_size
            lomax = self.longitude + box_size

            url = f"https://opensky-network.org/api/states/all?lamin={lamin}&lamax={lamax}&lomin={lomin}&lomax={lomax}"
            print("Fetching flights from OpenSky (fallback)...")

            response = requests.get(
                url, timeout=15,
                headers={'User-Agent': 'CubsMarquee/1.0'}
            )

            if response.status_code == 200:
                data = response.json()
                states = data.get('states', [])

                flights = []
                for state in states:
                    if len(state) >= 14:
                        callsign = (state[1] or '').strip()
                        if not callsign:
                            continue

                        flight_lat = state[6]
                        flight_lon = state[5]
                        altitude_m = state[7] or state[13]
                        velocity_ms = state[9]

                        if flight_lat is None or flight_lon is None:
                            continue

                        altitude_ft = int(altitude_m * 3.28084) if altitude_m else 0
                        if altitude_ft < self.MIN_ALTITUDE_FT:
                            continue

                        velocity_mph = int(velocity_ms * 2.237) if velocity_ms else 0

                        distance = self._calculate_distance(
                            self.latitude, self.longitude,
                            flight_lat, flight_lon
                        )

                        flights.append({
                            'callsign': callsign,
                            'altitude_ft': altitude_ft,
                            'velocity_mph': velocity_mph,
                            'distance': distance,
                            'latitude': flight_lat,
                            'longitude': flight_lon,
                            'aircraft_type': '',
                            'registration': '',
                            'vertical_rate': None,
                            'heading': None,
                            'icao_hex': '',
                            'destination': 'UNKNOWN',
                        })

                flights.sort(key=lambda x: x['distance'])
                self.flight_data = flights[:15]
                print(f"OpenSky: {len(self.flight_data)} flights found")

                self._lookup_destinations()
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
            print(f"Error fetching from OpenSky: {e}")
            return False

    def _fetch_flight_data(self) -> bool:
        """Fetch flight data - tries local ADS-B receiver first, falls back to OpenSky."""
        if not self.latitude or not self.longitude:
            print("Flight tracking: Location not configured")
            return False

        # Try configured source first
        fetch_ok = (
            self._fetch_from_adsb_lol()
            if self.use_adsb_lol
            else self._fetch_from_adsb_receiver()
        )
        if fetch_ok:
            self.last_fetch_time = time.time()
            # Enrich with route info via adsb.lol /api/0/routeset (free, no key).
            # The adsb.lol path already calls this internally, but the local
            # readsb path does not, so we call it here for the local case.
            if not self.use_adsb_lol and self.flight_data:
                try:
                    adsb_lol_enrich_routes(
                        base_url=GameConfig.ADSB_LOL_BASE_URL,
                        flights=self.flight_data,
                        cache=self.route_cache,
                    )
                except Exception as e:
                    print(f"Route enrichment failed (non-fatal): {e}")
            return True

        # Fall back to OpenSky
        if self._fetch_from_opensky():
            self.last_fetch_time = time.time()
            return True

        return False

    def _get_altitude_color(self, altitude_ft: int) -> RGBColor:
        """Get color based on altitude"""
        if altitude_ft >= 30000:
            return self.ALTITUDE_HIGH  # Gold for high altitude
        elif altitude_ft >= 15000:
            return self.ALTITUDE_MED   # Orange for medium altitude
        else:
            return self.ALTITUDE_LOW   # Green for low altitude

    def _draw_flight_header(
        self, header_text: str = 'OVERHEAD FLIGHT', tick: float | None = None
    ) -> None:
        """Draw sky gradient header for flight display using cached background"""
        if tick is None:
            tick = time.time()
        self.manager.set_image(self._flight_header_bg, 0, 0)

        # Thin separator line below header
        for x in range(DisplayConfig.MATRIX_COLS):
            self.manager.draw_pixel(x, 13, 70, 95, 130)

        # Top-view airplane silhouette flying right
        cx, cy = 9, 7
        for i in range(-4, 6):  # fuselage
            self.manager.draw_pixel(cx + i, cy, *self.FLIGHT_WHITE)
        self.manager.draw_pixel(cx + 6, cy, 200, 220, 255)  # nose
        for d in (1, 2, 3):  # swept wings
            self.manager.draw_pixel(cx + 1 - d, cy - d, *self.FLIGHT_WHITE)
            self.manager.draw_pixel(cx + 1 - d, cy + d, *self.FLIGHT_WHITE)
        for d in (1, 2):  # tail
            self.manager.draw_pixel(cx - 4 - d + 1, cy - d, *self.FLIGHT_WHITE)
            self.manager.draw_pixel(cx - 4 - d + 1, cy + d, *self.FLIGHT_WHITE)
        # Blinking red beacon on the tail
        if int(tick * 2) % 2:
            self.manager.draw_pixel(cx - 5, cy, 255, 60, 60)

        # Header text, centered between the top edge and the separator
        self.manager.draw_text('tiny_bold', 19, 9, self.FLIGHT_WHITE, header_text)

    def _display_no_location(self, duration: int) -> None:
        """Display message when location is not configured"""
        start_time = time.time()
        scroll_position = DisplayConfig.MATRIX_COLS
        message = "CONFIGURE LOCATION IN ADMIN PANEL"

        while time.time() - start_time < duration:
            self.manager.clear_canvas()
            self._draw_flight_header()

            scroll_position -= 1
            text_length = len(message) * 5

            if scroll_position + text_length < 0:
                scroll_position = DisplayConfig.MATRIX_COLS

            self.manager.draw_text('tiny_bold', int(scroll_position), 32,
                                   self.FLIGHT_WHITE, message)

            self.manager.swap_canvas()
            config = self._load_scroll_config()
            scroll_delay = get_scroll_delay(config.get('scroll_speed_flights', 5))
            time.sleep(scroll_delay)

    def _display_no_flights(self, duration: int) -> None:
        """Display message when no flights are detected"""
        start_time = time.time()

        while time.time() - start_time < duration:
            self.manager.clear_canvas()
            self._draw_flight_header()

            message = "NO FLIGHTS"
            msg_x = (DisplayConfig.MATRIX_COLS - len(message) * 5) // 2
            self.manager.draw_text('tiny_bold', msg_x, 28, self.FLIGHT_WHITE, message)

            message2 = "OVERHEAD"
            msg2_x = (DisplayConfig.MATRIX_COLS - len(message2) * 5) // 2
            self.manager.draw_text('tiny_bold', msg2_x, 38, self.FLIGHT_WHITE, message2)

            self.manager.swap_canvas()
            time.sleep(0.5)

    def _display_summary_view(self, duration: int) -> None:
        """Display summary of all flights overhead.
        Layout (96x48):
          Row 0-13:  Header with airplane icon + "FLIGHTS NEARBY"
          Row 22:    Aircraft count (e.g., "12 AIRCRAFT")
          Row 30:    Closest distance
          Row 38:    Highest altitude
          Row 46:    Lowest altitude
        """
        start_time = time.time()

        total = len(self.flight_data)
        if total == 0:
            return

        closest = min(self.flight_data, key=lambda f: f['distance'])
        highest = max(self.flight_data, key=lambda f: f['altitude_ft'])
        lowest = min(self.flight_data, key=lambda f: f['altitude_ft'])

        count_str = f"{total} AIRCRAFT"
        close_str = f"CLOSEST: {closest['distance']:.1f} MI"
        high_str = f"HIGH: {highest['altitude_ft']:,} FT"
        low_str = f"LOW:  {lowest['altitude_ft']:,} FT"

        while time.time() - start_time < duration:
            self.manager.clear_canvas()
            self._draw_flight_header('FLIGHTS NEARBY')

            # Aircraft count - centered, yellow
            count_x = (DisplayConfig.MATRIX_COLS - len(count_str) * 5) // 2
            self.manager.draw_text('tiny_bold', count_x, 22, self.ALTITUDE_HIGH, count_str)

            # Closest distance
            self.manager.draw_text('tiny', 4, 30, (150, 150, 150), close_str)

            # Highest altitude
            self.manager.draw_text('tiny', 4, 38, self.ALTITUDE_HIGH, high_str)

            # Lowest altitude
            self.manager.draw_text('tiny', 4, 46, self.ALTITUDE_LOW, low_str)

            self.manager.swap_canvas()
            time.sleep(0.1)

    def _display_radar_view(self, highlighted_index: int, display_time: int) -> None:
        """Full-screen radar scope view (96x48). All aircraft plotted as dots,
        the highlighted flight gets a bright dot + callsign label.
        Center crosshair = user location, range ring shows boundary."""
        if not self.flight_data or not self.latitude or not self.longitude:
            return

        start_time = time.time()

        # Radar scope uses full 96x48
        # Reserve bottom 8 rows for info bar about highlighted flight
        radar_w = DisplayConfig.MATRIX_COLS   # 96
        radar_h = DisplayConfig.MATRIX_ROWS - 8  # 40 pixels for radar
        info_y = 41  # y position for info text

        # Center of radar area
        cx = radar_w // 2   # 48
        cy = radar_h // 2   # 20

        # Determine max range from data to scale the plot
        max_range_mi = self.flight_max_range_nm * 1.15078
        if self.flight_data:
            farthest = max(f['distance'] for f in self.flight_data)
            # Use whichever is larger so all dots fit, with 10% padding
            plot_range = max(farthest * 1.1, 5.0)
            # Cap at configured max range
            plot_range = min(plot_range, max_range_mi)
        else:
            plot_range = max_range_mi

        # Scale factor: pixels per mile (use smaller dimension to keep circle)
        # Leave 4px margin on each side
        usable_radius = min(cx - 4, cy - 4)
        scale = usable_radius / plot_range if plot_range > 0 else 1.0

        highlighted = self.flight_data[highlighted_index]

        # Blink timer for highlighted dot
        blink_on = True
        last_blink = time.time()

        while time.time() - start_time < display_time:
            self.manager.clear_canvas()

            # Dark background
            bg = Image.new("RGB", (radar_w, DisplayConfig.MATRIX_ROWS), (5, 15, 30))
            self.manager.set_image(bg, 0, 0)

            # Draw range ring (circle at usable_radius)
            ring_color = (45, 85, 125)
            for angle_deg in range(360):
                rad = math.radians(angle_deg)
                rx = int(cx + usable_radius * math.cos(rad))
                ry = int(cy + usable_radius * math.sin(rad))
                if 0 <= rx < radar_w and 0 <= ry < radar_h:
                    self.manager.draw_pixel(rx, ry, *ring_color)

            # Draw half-range ring
            half_r = usable_radius // 2
            for angle_deg in range(0, 360, 2):
                rad = math.radians(angle_deg)
                rx = int(cx + half_r * math.cos(rad))
                ry = int(cy + half_r * math.sin(rad))
                if 0 <= rx < radar_w and 0 <= ry < radar_h:
                    self.manager.draw_pixel(rx, ry, *ring_color)

            # Rotating radar sweep: a single line, kept subtle and
            # contained within the range ring
            sweep_base = self._sweep_angle(time.time() - start_time)
            sweep_reach = usable_radius
            angle = math.radians(sweep_base)
            level = 55
            for r in range(3, sweep_reach):
                rx = int(cx + r * math.sin(angle))
                ry = int(cy - r * math.cos(angle))
                if 0 <= rx < radar_w and 0 <= ry < radar_h:
                    self.manager.draw_pixel(
                        rx, ry, 0, level, int(level * 0.45))

            # Draw crosshair at center (your location)
            crosshair_color = (90, 180, 95)
            for i in range(-2, 3):
                if 0 <= cx + i < radar_w:
                    self.manager.draw_pixel(cx + i, cy, *crosshair_color)
                if 0 <= cy + i < radar_h:
                    self.manager.draw_pixel(cx, cy + i, *crosshair_color)

            # Cardinal direction labels + range readout
            self.manager.draw_text('micro', cx - 2, 5, (70, 105, 140), 'N')
            self.manager.draw_text('micro', cx - 2, radar_h - 1, (70, 105, 140), 'S')
            self.manager.draw_text('micro', 1, cy + 3, (70, 105, 140), 'W')
            self.manager.draw_text('micro', radar_w - 5, cy + 3, (70, 105, 140), 'E')
            self.manager.draw_text(
                'micro', 1, 5, (70, 105, 140), f"{int(round(plot_range))}MI")

            # Blink toggle every 0.4s
            now = time.time()
            if now - last_blink >= 0.4:
                blink_on = not blink_on
                last_blink = now

            # Plot all aircraft
            for i, flight in enumerate(self.flight_data):
                if flight['latitude'] is None or flight['longitude'] is None:
                    continue

                # Convert lat/lon offset to pixel position
                # lon difference -> x (east is right)
                # lat difference -> y (north is up, so invert)
                dlat = flight['latitude'] - self.latitude
                dlon = flight['longitude'] - self.longitude

                # Approximate miles from degree offsets at this latitude
                lat_mi = dlat * 69.0
                lon_mi = dlon * 69.0 * math.cos(math.radians(self.latitude))

                px = int(cx + lon_mi * scale)
                py = int(cy - lat_mi * scale)  # Invert Y: north is up

                # Clamp to radar area
                px = max(1, min(radar_w - 2, px))
                py = max(1, min(radar_h - 2, py))

                is_highlighted = (i == highlighted_index)
                alt_color = self._get_altitude_color(flight['altitude_ft'])

                if is_highlighted:
                    if blink_on:
                        # Bright 3x3 dot for highlighted aircraft
                        for dy in range(-1, 2):
                            for dx in range(-1, 2):
                                nx, ny = px + dx, py + dy
                                if 0 <= nx < radar_w and 0 <= ny < radar_h:
                                    self.manager.draw_pixel(nx, ny, 255, 255, 255)
                    else:
                        # Dimmer dot on blink-off
                        self.manager.draw_pixel(px, py, *alt_color)

                    # Draw callsign label near the highlighted dot
                    cs = flight['callsign'][:7]  # Truncate for space
                    label_x = px + 3
                    # If label would go off-screen right, put it left of the dot
                    if label_x + len(cs) * 4 > radar_w:
                        label_x = px - len(cs) * 4 - 1
                    label_y = py + 3
                    if label_y > radar_h - 1:
                        label_y = py - 2
                    if label_y < 1:
                        label_y = py + 3
                    self.manager.draw_text('micro', label_x, label_y,
                                           (200, 200, 200), cs)
                else:
                    # Dim 1-pixel dot that blips bright as the sweep
                    # passes over it, then fades back down
                    dim_color = (alt_color[0] // 2, alt_color[1] // 2, alt_color[2] // 2)
                    flare = self._sweep_flare(
                        sweep_base, self._dot_bearing(cx, cy, px, py))
                    dot_color = tuple(
                        int(d + (255 - d) * flare) for d in dim_color)
                    self.manager.draw_pixel(px, py, *dot_color)

            # Info bar at bottom - highlighted flight details
            # Separator line
            for x in range(radar_w):
                self.manager.draw_pixel(x, radar_h + 1, 40, 60, 80)

            cs = highlighted['callsign']
            alt = highlighted['altitude_ft']
            dist = highlighted['distance']
            # Airport code, not a truncated city name ("LAX", never "LOS ANGE")
            dest_code = (highlighted.get('dest_iata')
                         or highlighted.get('destination', 'UNKNOWN'))
            if dest_code and dest_code != 'UNKNOWN':
                dest_str = f">{dest_code[:4]}"
            else:
                dest_str = f"{dist:.1f}MI"

            info_left = f"{cs} {alt // 1000}K"
            self.manager.draw_text('micro', 1, info_y, self.ALTITUDE_HIGH, info_left)
            # Right-align destination/distance
            info_right = dest_str
            rx = radar_w - len(info_right) * 4 - 1
            self.manager.draw_text('micro', rx, info_y, (150, 150, 150), info_right)

            # Flight count in bottom-right corner
            count_str = f"{highlighted_index + 1}/{len(self.flight_data)}"
            cx2 = radar_w - len(count_str) * 4 - 1
            self.manager.draw_text('micro', cx2, 47, (80, 80, 80), count_str)

            self.manager.swap_canvas()
            time.sleep(0.08)

    def _draw_aircraft_icon(
        self, category: str, x: int, y: int, color: RGBColor
    ) -> None:
        """Small side-view aircraft silhouette; (x, y) is the top-left of a
        roughly 11x7 box. Category comes from _aircraft_category()."""
        draw = self.manager.draw_pixel
        cy = y + 4
        if category == 'heli':
            for i in range(8):  # rotor
                draw(x + 1 + i, y + 1, *color)
            draw(x + 4, y + 2, *color)  # mast
            for i in range(5):  # cabin
                draw(x + 2 + i, y + 3, *color)
                draw(x + 2 + i, y + 4, *color)
            for i in range(3):  # tail boom
                draw(x + 7 + i, y + 3, *color)
            draw(x + 9, y + 2, *color)  # tail rotor
            return

        # Fixed wing: fuselage with nose to the right
        body = 9 if category == 'jet' else 7
        for i in range(body):
            draw(x + i, cy, *color)
        draw(x + body, cy, *color)
        if category in ('jet', 'regional'):
            sweep = 3 if category == 'jet' else 2
            mid = x + body // 2 + 1
            for d in range(1, sweep + 1):  # swept wings
                draw(mid - d, cy - d, *color)
                draw(mid - d, cy + d, *color)
            draw(x, cy - 1, *color)  # tail fin
            draw(x - 1 + 1, cy - 2, *color)
        else:  # prop: straight wings + propeller disc
            mid = x + 4
            for d in (1, 2):
                draw(mid, cy - d, *color)
                draw(mid, cy + d, *color)
            draw(x, cy - 1, *color)
            draw(x + body + 1, cy, 160, 160, 160)  # prop

    def _draw_rate_triangle(
        self, x: int, y: int, direction: str, color: RGBColor
    ) -> None:
        """5x3 climb/descend triangle; (x, y) is the top-left"""
        draw = self.manager.draw_pixel
        rows = ((2, 2), (1, 3), (0, 4)) if direction == 'up' else \
               ((0, 4), (1, 3), (2, 2))
        for row, (start, end) in enumerate(rows):
            for dx in range(start, end + 1):
                draw(x + dx, y + row, *color)

    def _draw_compass_arrow(
        self, cx: int, cy: int, heading: float, color: RGBColor
    ) -> None:
        """7x7 arrow rotated to the nearest of 8 headings, centered on (cx, cy)"""
        draw = self.manager.draw_pixel
        vx, vy = self._heading_vector(heading, 3)
        for t in range(-3, 4):  # full shaft, tail through tip
            draw(cx + round(vx * t / 3), cy + round(vy * t / 3), *color)
        # Arrowhead: perpendicular pixels one step back from the tip
        bx, by = cx + round(vx * 2 / 3), cy + round(vy * 2 / 3)
        px, py = (round(vy / 3), -round(vx / 3))
        draw(bx + px, by + py, *color)
        draw(bx - px, by - py, *color)

    def _draw_route_arrow(self, x: int, y: int, color: RGBColor) -> None:
        """Small 5px right-arrow between origin and destination codes"""
        draw = self.manager.draw_pixel
        for i in range(5):
            draw(x + i, y, *color)
        draw(x + 3, y - 1, *color)
        draw(x + 3, y + 1, *color)

    def _detail_footer(
        self, flight: dict[str, Any], dest_display: str, tick: float
    ) -> str:
        """Bottom line of the detail screen; alternates destination and
        airline name every 4 seconds when both are known."""
        airline = self._airline_name(flight.get('callsign', ''))
        if airline and dest_display and int(tick / 4) % 2:
            return airline
        return dest_display

    def _draw_detail_frame(
        self, flight: dict[str, Any], header_text: str, tick: float
    ) -> None:
        """One frame of the single-flight detail screen.
        Layout (96x48):
          Row 0-13:  Header with airplane silhouette + "N OF M"
          Row 22:    Aircraft icon + callsign (left), route or type (right)
          Row 30:    Altitude (left) + climb/descend triangle + rate (right)
          Row 38:    Speed (left) + compass arrow + cardinal (right)
          Row 46:    Destination city / airline name / registration
        """
        callsign = flight['callsign']
        altitude_ft = flight['altitude_ft']
        alt_color = self._get_altitude_color(altitude_ft)
        heading = flight.get('heading')
        vertical_rate = flight.get('vertical_rate')

        self.manager.clear_canvas()
        self._draw_flight_header(header_text, tick)

        # Row 1 (y=22): category icon + callsign left, route or type right
        category = self._aircraft_category(flight.get('aircraft_type'))
        if category:
            self._draw_aircraft_icon(category, 2, 15, (170, 200, 230))
        self.manager.draw_text('tiny_bold', 15, 22, (140, 210, 255), callsign)
        origin, dest = flight.get('origin_iata'), flight.get('dest_iata')
        if origin and dest:
            route_x = DisplayConfig.MATRIX_COLS - (len(origin) + len(dest)) * 5 - 8
            self.manager.draw_text('tiny', route_x, 22, (150, 150, 150), origin)
            self._draw_route_arrow(route_x + len(origin) * 5 + 1, 19, (150, 150, 150))
            self.manager.draw_text(
                'tiny', route_x + len(origin) * 5 + 7, 22, (150, 150, 150), dest)
        else:
            aircraft_type = flight.get('aircraft_type', '') or ''
            if aircraft_type:
                type_x = DisplayConfig.MATRIX_COLS - len(aircraft_type) * 5 - 2
                self.manager.draw_text(
                    'tiny_bold', type_x, 22, (150, 150, 150), aircraft_type)

        # Row 2 (y=30): altitude left, vertical rate with triangle right
        self.manager.draw_text('tiny', 2, 30, alt_color, f"{altitude_ft:,} FT")
        vr_str, vr_color, vr_dir = self._get_vertical_rate_indicator(
            int(vertical_rate) if vertical_rate is not None else None)
        if vr_str:
            vr_x = DisplayConfig.MATRIX_COLS - len(vr_str) * 5 - 2
            self.manager.draw_text('tiny', vr_x, 30, vr_color, vr_str)
            if vr_dir in ('up', 'down'):
                self._draw_rate_triangle(vr_x - 7, 25, vr_dir, vr_color)

        # Row 3 (y=38): speed left, compass arrow + cardinal right
        self.manager.draw_text(
            'tiny', 2, 38, self.FLIGHT_WHITE, f"{flight['velocity_mph']} MPH")
        if heading is not None:
            cardinal = self._degrees_to_cardinal(heading)
            hdg_x = DisplayConfig.MATRIX_COLS - len(cardinal) * 5 - 2
            self.manager.draw_text('tiny', hdg_x, 38, (150, 150, 150), cardinal)
            self._draw_compass_arrow(hdg_x - 7, 35, heading, (150, 150, 150))

        # Row 4 (y=46): destination, airline, or registration
        dest_code = flight.get('dest_iata') or flight.get('destination', 'UNKNOWN')
        destination = self._get_airport_city(dest_code)
        registration = flight.get('registration', '')
        if destination and destination != 'UNKNOWN':
            dest_display = f"TO: {destination}"[:18]
        elif registration:
            dest_display = f"REG: {registration}"
        else:
            dest_display = ''
        footer = self._detail_footer(flight, dest_display, tick)
        if footer:
            self.manager.draw_text('tiny', 2, 46, self.FLIGHT_WHITE, footer)

        self.manager.swap_canvas()

    def _display_single_flight(self, flight: dict[str, Any], flight_num: int,
                                total_flights: int, display_time: int) -> None:
        """Display a single flight's information for the specified duration"""
        start_time = time.time()
        header_text = f"{flight_num} OF {total_flights}"

        while time.time() - start_time < display_time:
            self._draw_detail_frame(flight, header_text, time.time())
            time.sleep(0.1)

    def display_flight_info(self, duration: int = 120) -> None:
        """Main display method for flight tracking.
        Shows summary view first, then cycles through individual flights.
        Re-fetches data every FLIGHT_REFRESH_INTERVAL seconds."""
        # Reload config in case settings changed
        self._load_config()

        # Check if location is configured
        if not self.latitude or not self.longitude:
            self._display_no_location(duration)
            return

        # Initial data fetch
        self._fetch_flight_data()

        # Check if we have any flights
        if not self.flight_data:
            self._display_no_flights(duration)
            return

        # Cycle through flights, showing summary at the start of each full rotation
        start_time = time.time()
        flight_index = 0
        show_summary = True  # Show summary before the first flight

        while time.time() - start_time < duration:
            # Re-fetch data if refresh interval has elapsed
            if time.time() - self.last_fetch_time >= GameConfig.FLIGHT_REFRESH_INTERVAL:
                self._fetch_flight_data()
                if not self.flight_data:
                    self._display_no_flights(duration - (time.time() - start_time))
                    return
                # Reset index if it's out of bounds after refresh
                if flight_index >= len(self.flight_data):
                    flight_index = 0

            # Show summary at the start of each rotation through the list
            if show_summary:
                self._display_summary_view(self.SUMMARY_DISPLAY_TIME)
                show_summary = False

            # Display current flight: radar view then detail view
            if self.enable_flight_radar:
                self._display_radar_view(flight_index, self.FLIGHT_DISPLAY_TIME)

            flight = self.flight_data[flight_index]
            self._display_single_flight(
                flight,
                flight_index + 1,
                len(self.flight_data),
                self.FLIGHT_DISPLAY_TIME
            )

            # Move to next flight; trigger summary again when wrapping around
            flight_index += 1
            if flight_index >= len(self.flight_data):
                flight_index = 0
                show_summary = True

    def get_quick_flight_summary(self) -> dict[str, Any] | None:
        """Get a quick summary of current flights for between-innings display.
        Returns dict with count, closest_callsign, closest_distance or None."""
        if not self.latitude or not self.longitude:
            return None

        # Use cached data if recent enough, otherwise quick fetch
        if time.time() - self.last_fetch_time > 60:
            self._fetch_flight_data()

        if not self.flight_data:
            return None

        closest = min(self.flight_data, key=lambda f: f['distance'])
        return {
            'count': len(self.flight_data),
            'closest_callsign': closest['callsign'],
            'closest_distance': closest['distance'],
        }
