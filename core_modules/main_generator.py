# core_modules/main_generator.py

import argparse
import json
import logging
import pathlib
import sys
import asyncio

# Relative imports for modules within the same package (core_modules)
from downloader import download_filter_lists
from parser_validator import parse_and_validate_rules
from rephraser import rephrase_rules
from unifier_optimizer import unify_and_optimize_rules
from generator import generate_brave_power_list

# --- Global Project Root Path ---
# Assumes main_generator.py is in core_modules, so project_root is its parent.
PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent

def setup_logging(log_level_str: str = "INFO", log_format_str: str = None):
    if not log_format_str:
        log_format_str = "%(asctime)s - %(levelname)s - %(name)s - %(funcName)s - %(message)s"
    try:
        log_level = getattr(logging, log_level_str.upper())
    except AttributeError:
        log_level = logging.INFO
        logging.warning(f"Invalid log level '{log_level_str}'. Defaulting to INFO.")
    logging.basicConfig(
        level=log_level, format=log_format_str, datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    logging.getLogger('parfive').setLevel(logging.WARNING)
    logging.getLogger('asyncio').setLevel(logging.INFO)

def load_configuration(config_path_str: str) -> dict | None:
    logger_cfg = logging.getLogger(__name__)
    # argparse provides path relative to CWD. If running from project root, this is fine.
    config_path = pathlib.Path(config_path_str) 

    if not config_path.is_file(): # Check path as given first
        # If not found, try resolving relative to project root (in case CWD is different)
        config_path_alt = PROJECT_ROOT / config_path_str
        if config_path_alt.is_file():
            config_path = config_path_alt
        else:
            logger_cfg.error(f"Configuration file not found at '{config_path_str}' (CWD) or '{config_path_alt}' (project root).")
            return None

    logger_cfg.info(f"Loading configuration from: {config_path.resolve()}")
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        logger_cfg.info("Configuration loaded successfully.")
        return config
    except json.JSONDecodeError as e:
        logger_cfg.error(f"Error decoding JSON from config file {config_path.resolve()}: {e}")
        raise
    except Exception as e:
        logger_cfg.error(f"Error loading config file {config_path.resolve()}: {e}")
        raise


def load_brave_scriptlet_metadata(config: dict) -> dict:
    logger_meta = logging.getLogger(__name__)
    metadata_filepath_str = config.get("brave_metadata_filepath")
    if not metadata_filepath_str:
        logger_meta.warning("Path to Brave scriptlet metadata ('brave_metadata_filepath') not in config. Scriptlet rephrasing may be limited.")
        return {}

    metadata_path = PROJECT_ROOT / metadata_filepath_str # Path relative to project root
    if not metadata_path.is_file():
        logger_meta.error(f"Brave scriptlet metadata file not found: {metadata_path.resolve()}")
        return {}
    
    logger_meta.info(f"Loading Brave scriptlet metadata from: {metadata_path.resolve()}")
    try:
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata_content = json.load(f)
        if "scriptlets" in metadata_content and isinstance(metadata_content["scriptlets"], list):
            scriptlet_map = {}
            for scriptlet_def in metadata_content["scriptlets"]:
                if "name" in scriptlet_def:
                    scriptlet_map[scriptlet_def["name"]] = scriptlet_def
                    if "aliases" in scriptlet_def and isinstance(scriptlet_def["aliases"], list):
                        for alias in scriptlet_def["aliases"]:
                            scriptlet_map[alias] = scriptlet_def
            logger_meta.info(f"Loaded and mapped {len(scriptlet_map)} scriptlets (including aliases).")
            return scriptlet_map
        else:
            logger_meta.warning("Brave scriptlet metadata is not in expected format (missing 'scriptlets' list).")
            return {}
    except Exception as e:
        logger_meta.error(f"Error loading/parsing Brave scriptlet metadata {metadata_path.resolve()}: {e}")
        return {}

async def main_workflow(config: dict):
    main_logger = logging.getLogger("MainWorkflow")
    main_logger.info("Starting Brave Power List Generation Workflow...")

    brave_scriptlets_data = {}
    if config.get("rephraser_options", {}).get("load_brave_metadata", True):
        brave_scriptlets_data = load_brave_scriptlet_metadata(config)

    try:
        main_logger.info("--- 1. Downloader Module ---")
        raw_lists_data = await download_filter_lists(
            config.get("filter_list_urls", []),
            config.get("downloader_options", {})
        )
        if not raw_lists_data: main_logger.warning("Downloader returned no data. Workflow might produce empty list."); # Allow continuing

        main_logger.info("--- 2. Parser & Validator Module ---")
        parsed_rules = parse_and_validate_rules(
            raw_lists_data,
            config.get("parser_validator_options", {})
        )
        if not parsed_rules: main_logger.warning("Parser & Validator returned no rules.");

        main_logger.info("--- 3. Rephraser Module ---")
        rephrased_rules = rephrase_rules(
            parsed_rules,
            brave_scriptlets_data,
            config.get("rephraser_options", {})
        )

        main_logger.info("--- 4. Unifier & Optimizer Module ---")
        unified_optimized_rules = unify_and_optimize_rules(
            rephrased_rules,
            config.get("unifier_optimizer_options", {})
        )
        if not unified_optimized_rules: 
            main_logger.warning("Unifier & Optimizer returned no rules for final list. Output will be minimal (header only).")
            # unified_optimized_rules = [] # Ensure it's an empty list for the generator
            
        main_logger.info("--- 5. Generator Module ---")
        generation_successful = generate_brave_power_list(
            unified_optimized_rules,
            config
        )

        if generation_successful:
            main_logger.info("Brave Power List Generation Workflow COMPLETED successfully.")
        else:
            main_logger.error("Generator Module FAILED. Final list may not have been created or is incomplete.")
            main_logger.info("Brave Power List Generation Workflow FAILED.")
    except Exception as e:
        main_logger.critical(f"Critical error during generation workflow: {e}", exc_info=True)
        main_logger.info("Brave Power List Generation Workflow FAILED due to an unhandled exception.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Brave Power List Generator Orchestrator. Run from the project root directory."
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config.json",
        help="Path to the JSON configuration file (default: config.json in CWD, assumed project root)"
    )
    args = parser.parse_args()

    script_logger = logging.getLogger("core_modules.main_generator") # Explicit name
    setup_logging() 

    try:
        configuration = load_configuration(args.config)
        if configuration is None:
            script_logger.error(f"Exiting: Could not load configuration from '{args.config}'.")
            sys.exit(1)
            
        log_level_from_config = configuration.get("log_level", "INFO")
        log_format_from_config = configuration.get("log_format")
        setup_logging(log_level_from_config, log_format_from_config) # Re-init with config settings
        
        script_logger.info(f"Using configuration file: {pathlib.Path(args.config).resolve()}")
        script_logger.debug(f"Loaded configuration: {json.dumps(configuration, indent=2)}")

        asyncio.run(main_workflow(configuration))

    except json.JSONDecodeError: # Already handled in load_configuration if it raises
        script_logger.error(f"Exiting: Could not decode JSON from '{args.config}'. Ensure it's valid JSON.")
        sys.exit(1)
    except Exception as e:
        script_logger.critical(f"An unexpected error occurred at the top level: {e}", exc_info=True)
        sys.exit(1)
