# core_modules/generator.py

import logging
from datetime import datetime
import pathlib

logger = logging.getLogger(__name__)

def generate_brave_power_list(
    optimized_rule_strings: list[str],
    config: dict
) -> bool:
    """
    Generates the final Brave Power List file with a standard header.

    Args:
        optimized_rule_strings: The final, unified, and optimized list of
                                rule strings (active rules and preserved comments).
        config: Configuration dictionary, expected to contain:
                'output_filename' (str): Name of the output file.
                'generator_header' (dict): Containing 'title', 'description',
                                           'author' for the list header.

    Returns:
        True if the list was generated successfully, False otherwise.
    """
    output_filename_str = config.get("output_filename")
    if not output_filename_str:
        logger.error("Generator: 'output_filename' not found in configuration.")
        return False

    header_config = config.get("generator_header", {})
    if not header_config: # Should not happen if config is well-defined
        logger.warning("Generator: 'generator_header' not found in configuration. Using default header values.")

    title = header_config.get("title", "Brave Power List")
    description = header_config.get("description", "Brave browser unified and optimized filter list.")
    author = header_config.get("author", "Murtaza Salih") # Default to PRD specified author

    version_timestamp = datetime.now().strftime("%Y%m%d.%H%M%S")

    header_lines = [
        f"! Title: {title}",
        f"! Description: {description}",
        f"! Author: {author}",
        f"! Version: {version_timestamp}",
        "!" 
    ]

    # Output path is relative to where the main script is executed (project root)
    output_path = pathlib.Path(output_filename_str)

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Generator: Writing {len(optimized_rule_strings)} rules and "
                    f"{len(header_lines)} header lines to '{output_path.resolve()}'...")

        with open(output_path, 'w', encoding='utf-8') as f:
            for line in header_lines:
                f.write(line + "\n")
            for rule_string in optimized_rule_strings:
                f.write(rule_string + "\n")

        final_line_count = len(header_lines) + len(optimized_rule_strings)
        logger.info(f"Generator: Successfully generated '{output_path.resolve()}' with {final_line_count} total lines.")
        return True

    except IOError as e:
        logger.error(f"Generator: Failed to write final list to {output_path.resolve()}: {e}")
        return False
    except Exception as e:
        logger.error(f"Generator: An unexpected error occurred while writing to {output_path.resolve()}: {e}")
        return False
