"""Configuration validation for Cubs LED Scoreboard"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import logging

logger = logging.getLogger("cubs_scoreboard.config_validator")


@dataclass
class ValidationResult:
    """Result of a configuration validation check"""
    is_valid: bool
    field: str
    message: str
    is_required: bool = True


class ConfigValidator:
    """Validates configuration files and environment for the scoreboard"""

    CONFIG_PATH = Path("/home/pi/config.json")

    # Required configuration fields
    REQUIRED_FIELDS: list[tuple[str, str]] = [
        # (field_name, description)
    ]

    # Optional but recommended fields
    OPTIONAL_FIELDS: list[tuple[str, str]] = [
        ("zip_code", "ZIP code for weather display"),
        ("weather_api_key", "OpenWeatherMap API key for weather display"),
    ]

    def __init__(self, config_path: Path | None = None) -> None:
        """Initialize the validator with optional custom config path"""
        self.config_path = config_path or self.CONFIG_PATH
        self.config: dict[str, Any] = {}
        self.validation_results: list[ValidationResult] = []

    def load_config(self) -> bool:
        """
        Load the configuration file.

        Returns:
            True if config was loaded successfully, False otherwise
        """
        try:
            if not self.config_path.exists():
                logger.warning(f"Config file not found at {self.config_path}")
                self.config = {}
                return True  # Not an error - optional config

            with open(self.config_path, 'r') as f:
                self.config = json.load(f)

            logger.info(f"Configuration loaded from {self.config_path}")
            return True

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config file: {e}")
            return False
        except Exception as e:
            logger.error(f"Error loading config file: {e}")
            return False

    def validate_required_fields(self) -> list[ValidationResult]:
        """Validate all required configuration fields"""
        results: list[ValidationResult] = []

        for field_name, description in self.REQUIRED_FIELDS:
            value = self.config.get(field_name)

            if value is None or value == "":
                results.append(ValidationResult(
                    is_valid=False,
                    field=field_name,
                    message=f"Missing required field: {description}",
                    is_required=True
                ))
            else:
                results.append(ValidationResult(
                    is_valid=True,
                    field=field_name,
                    message=f"Valid: {description}",
                    is_required=True
                ))

        return results

    def validate_optional_fields(self) -> list[ValidationResult]:
        """Validate optional configuration fields"""
        results: list[ValidationResult] = []

        for field_name, description in self.OPTIONAL_FIELDS:
            value = self.config.get(field_name)

            if value is None or value == "":
                results.append(ValidationResult(
                    is_valid=False,
                    field=field_name,
                    message=f"Not configured: {description} (optional)",
                    is_required=False
                ))
            else:
                results.append(ValidationResult(
                    is_valid=True,
                    field=field_name,
                    message=f"Configured: {description}",
                    is_required=False
                ))

        return results

    def validate_weather_config(self) -> ValidationResult:
        """Validate weather-specific configuration"""
        zip_code = self.config.get("zip_code")
        api_key = self.config.get("weather_api_key")

        if not zip_code or not api_key:
            return ValidationResult(
                is_valid=False,
                field="weather",
                message="Weather display disabled: missing zip_code or weather_api_key",
                is_required=False
            )

        # Validate ZIP code format (5 digits)
        if not isinstance(zip_code, str) or not zip_code.isdigit() or len(zip_code) != 5:
            return ValidationResult(
                is_valid=False,
                field="zip_code",
                message=f"Invalid ZIP code format: '{zip_code}' (expected 5 digits)",
                is_required=False
            )

        # Validate API key format (basic check)
        if not isinstance(api_key, str) or len(api_key) < 20:
            return ValidationResult(
                is_valid=False,
                field="weather_api_key",
                message="Invalid weather API key format",
                is_required=False
            )

        return ValidationResult(
            is_valid=True,
            field="weather",
            message="Weather configuration valid",
            is_required=False
        )

    def validate_file_paths(self) -> list[ValidationResult]:
        """Validate that required files exist"""
        results: list[ValidationResult] = []

        required_files = [
            ("./marquee.png", "Marquee background image"),
            ("./baseball.png", "Batting indicator image"),
            ("./logos/cubs.png", "Cubs logo"),
        ]

        for file_path, description in required_files:
            if Path(file_path).exists():
                results.append(ValidationResult(
                    is_valid=True,
                    field=file_path,
                    message=f"Found: {description}",
                    is_required=False
                ))
            else:
                results.append(ValidationResult(
                    is_valid=False,
                    field=file_path,
                    message=f"Missing: {description} at {file_path}",
                    is_required=False
                ))

        return results

    def validate_fonts(self) -> list[ValidationResult]:
        """Validate that font files exist"""
        results: list[ValidationResult] = []

        font_dir = Path("./fonts")
        if not font_dir.exists():
            results.append(ValidationResult(
                is_valid=False,
                field="fonts",
                message="Font directory not found at ./fonts",
                is_required=True
            ))
            return results

        # Check for at least some font files
        font_files = list(font_dir.glob("*.bdf"))
        if not font_files:
            results.append(ValidationResult(
                is_valid=False,
                field="fonts",
                message="No .bdf font files found in ./fonts",
                is_required=True
            ))
        else:
            results.append(ValidationResult(
                is_valid=True,
                field="fonts",
                message=f"Found {len(font_files)} font files",
                is_required=True
            ))

        return results

    def validate_all(self) -> tuple[bool, list[ValidationResult]]:
        """
        Run all validation checks.

        Returns:
            Tuple of (all_required_valid, list of all results)
        """
        self.validation_results = []

        # Load config first
        if not self.load_config():
            self.validation_results.append(ValidationResult(
                is_valid=False,
                field="config_file",
                message="Failed to load configuration file",
                is_required=True
            ))
            return False, self.validation_results

        # Run all validators
        self.validation_results.extend(self.validate_required_fields())
        self.validation_results.extend(self.validate_optional_fields())
        self.validation_results.append(self.validate_weather_config())
        self.validation_results.extend(self.validate_file_paths())
        self.validation_results.extend(self.validate_fonts())

        # Check if all required validations passed
        all_required_valid = all(
            r.is_valid for r in self.validation_results if r.is_required
        )

        return all_required_valid, self.validation_results

    def print_validation_report(self) -> None:
        """Print a formatted validation report"""
        print("\n" + "=" * 60)
        print("CUBS LED SCOREBOARD - CONFIGURATION VALIDATION")
        print("=" * 60)

        # Group by validation status
        valid_results = [r for r in self.validation_results if r.is_valid]
        invalid_required = [r for r in self.validation_results
                          if not r.is_valid and r.is_required]
        invalid_optional = [r for r in self.validation_results
                          if not r.is_valid and not r.is_required]

        if invalid_required:
            print("\n[ERRORS - Required Configuration]")
            for r in invalid_required:
                print(f"  ✗ {r.message}")

        if invalid_optional:
            print("\n[WARNINGS - Optional Configuration]")
            for r in invalid_optional:
                print(f"  ⚠ {r.message}")

        if valid_results:
            print("\n[OK - Valid Configuration]")
            for r in valid_results:
                print(f"  ✓ {r.message}")

        print("\n" + "=" * 60)

        if invalid_required:
            print("STATUS: CONFIGURATION ERRORS FOUND")
            print("Please fix the required configuration before starting.")
        elif invalid_optional:
            print("STATUS: READY (with warnings)")
            print("Some optional features are not configured.")
        else:
            print("STATUS: ALL CONFIGURATION VALID")

        print("=" * 60 + "\n")


def validate_config_on_startup() -> bool:
    """
    Convenience function to validate configuration on startup.

    Returns:
        True if all required configuration is valid, False otherwise
    """
    validator = ConfigValidator()
    all_valid, results = validator.validate_all()

    # Log results
    for result in results:
        if result.is_valid:
            logger.info(f"Config validation: {result.message}")
        elif result.is_required:
            logger.error(f"Config validation: {result.message}")
        else:
            logger.warning(f"Config validation: {result.message}")

    return all_valid


if __name__ == "__main__":
    # Run validation when executed directly
    logging.basicConfig(level=logging.INFO)
    validator = ConfigValidator()
    all_valid, _ = validator.validate_all()
    validator.print_validation_report()
    exit(0 if all_valid else 1)
