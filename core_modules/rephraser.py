# core_modules/rephraser.py

import re
import logging
import json # For json.dumps when creating scriptlet args, and loading metadata

# Assuming RuleType and BraveValidityStatus enums are defined in parser_validator
# and will be available in the execution context.
# For standalone testing, you might need to define them or import them.
from .parser_validator import RuleType, BraveValidityStatus

logger = logging.getLogger(__name__)

# --- Mock python-adblock re-validator (as defined previously) ---
class MockPythonAdblockRevalidator:
    def is_rule_valid_for_brave(self, rule_string: str) -> tuple[bool, str, dict]:
        if not rule_string or rule_string.isspace():
            return False, "Rule string is empty.", {}
        if "INVALID_PATTERN_AFTER_REPHRASE" in rule_string: # More specific for rephrase failure
            return False, "Mock re-validation: Rephrased rule contains invalid pattern.", {}
        
        parsed_components = {} # Simulate parsing of rephrased rule
        if "##+js" in rule_string:
            match = re.match(r"^(.*?)##\+js\((.*?)\)$", rule_string)
            if match:
                domain = match.group(1).strip() if match.group(1) else ""
                scriptlet_call = match.group(2).split(',', 1)
                scriptlet_name = scriptlet_call[0].strip()
                args_str = scriptlet_call[1].strip() if len(scriptlet_call) > 1 else ""
                parsed_components = {"domain": domain, "scriptlet_name": scriptlet_name, "arguments_string": args_str, "type": "scriptlet"}
        elif "##" in rule_string:
             parts = rule_string.split("##", 1)
             parsed_components = {"domain": parts[0].strip() if parts[0] else "", "selector": parts[1].strip(), "type": "cosmetic"}
        elif rule_string.startswith("||") or rule_string.startswith("|") or "/" in rule_string :
            pattern = rule_string
            options_part = ""
            if "$" in pattern:
                pattern, options_part = rule_string.split("$", 1)
            parsed_components = {"pattern": pattern, "options_string": options_part, "type": "network"}
        
        logger.debug(f"Mock re-validation for '{rule_string[:70]}...': PASSED. Parsed: {parsed_components if parsed_components else 'basic'}")
        return True, "Mock re-validation: Syntax appears valid.", parsed_components

mock_revalidator = MockPythonAdblockRevalidator()

# This would be passed in, but for structure:
DEFAULT_MOCK_BRAVE_SCRIPTLET_METADATA = {
    "noop.js": {"name": "noop.js"}, "log.js": {"name": "log.js"},
    "json-prune.js": {"name": "json-prune.js"},
    "ubo-annoyance-fixer.js": {"name": "ubo-annoyance-fixer.js"}
    # ... more from your metadata file
}
DEFAULT_MOCK_ADGUARD_TO_UBO_SCRIPTLET_MAP = {
    "adguard-specific-anti-annoyance": "ubo-annoyance-fixer.js",
    "ag_json_prune": "json-prune.js"
}


def rephrase_rules(
    validated_rule_objects: list[dict],
    brave_scriptlet_metadata: dict, # Expected to be a map: name -> definition
    rephraser_config: dict = None
) -> list[dict]:
    rephrased_rules_list = []
    # Store details of custom scriptlets implied by rephrasing
    # This could be passed back or handled by a global collector if needed.
    implied_custom_scriptlets = [] 

    if rephraser_config is None: rephraser_config = {}
    
    # Use default mocks if None is passed (e.g. if metadata loading failed)
    active_brave_scriptlets = brave_scriptlet_metadata if brave_scriptlet_metadata else DEFAULT_MOCK_BRAVE_SCRIPTLET_METADATA
    active_ag_to_ubo_map = rephraser_config.get("adguard_to_ubo_map", DEFAULT_MOCK_ADGUARD_TO_UBO_SCRIPTLET_MAP)


    for rule_obj in validated_rule_objects:
        # Make a copy to modify, preserving the original from the parser
        current_rule_obj = rule_obj.copy()
        original_rule_str = current_rule_obj["original_rule_string"]
        current_status_enum = BraveValidityStatus[current_rule_obj["brave_validity_status"]]
        rule_type_enum = RuleType[current_rule_obj["rule_type"]]
        parsed_components = current_rule_obj.get("parsed_components", {})
        
        rephrased_rule_str = original_rule_str # Default to original
        new_status_enum = current_status_enum
        rephrase_strategy_applied = "" # Short description of what was done
        needs_revalidation = False

        if current_status_enum not in [
            BraveValidityStatus.UNSUPPORTED_BRAVE_FEATURE,
            BraveValidityStatus.POTENTIAL_ADGUARD_SPECIFIC,
            BraveValidityStatus.NEEDS_REPHRASING
        ]:
            rephrased_rules_list.append(current_rule_obj) # Pass through if no rephrasing needed
            continue

        logger.debug(f"Rephraser: Attempting rule ID {current_rule_obj['id']}: '{original_rule_str[:80]}' (Status: {current_status_enum.name})")

        # --- Rephrasing Strategies ---
        if "$popup" in original_rule_str or "$popunder" in original_rule_str:
            temp_rephrased = re.sub(r",?\$popup(?:=[^,]+)?", "", original_rule_str)
            temp_rephrased = re.sub(r",?\$popunder(?:=[^,]+)?", "", temp_rephrased)
            temp_rephrased = re.sub(r",[,\s]*$", "", temp_rephrased).rstrip("$")
            if not "$" in temp_rephrased and temp_rephrased.startswith("||") and not temp_rephrased.endswith("^"):
                 temp_rephrased += "^"
            if temp_rephrased != original_rule_str:
                rephrased_rule_str = temp_rephrased
                rephrase_strategy_applied = "Removed $popup/$popunder."
                needs_revalidation = True
        
        elif rule_type_enum == RuleType.COSMETIC and parsed_components.get("abp_extended_syntax") and \
             current_status_enum == BraveValidityStatus.NEEDS_REPHRASING:
            domain = parsed_components.get("domain", "")
            selector = parsed_components.get("selector", "")
            if ":-abp-has(" in selector:
                new_selector = selector.replace(":-abp-has(", ":has(")
                rephrased_rule_str = f"{domain}##{new_selector}" if domain else f"##{new_selector}"
                rephrase_strategy_applied = "Converted ABP :-abp-has() to :has()."
                needs_revalidation = True
            elif ":-abp-contains(" in selector:
                match = re.search(r":-abp-contains\((['\"])(.*?)\1\)", selector)
                if match:
                    text = json.dumps(match.group(2))
                    base_sel = selector[:match.start()] + selector[match.end():] or 'div'
                    scriptlet_name = "user-hideIfTextContains"
                    rephrased_rule_str = f"{domain}##+js({scriptlet_name}, {base_sel}, {text})"
                    rephrase_strategy_applied = f"ABP :-abp-contains() to ##+js({scriptlet_name})."
                    implied_custom_scriptlets.append({"name": scriptlet_name, "type": "cosmetic_helper"})
                    needs_revalidation = True
                else: new_status_enum = BraveValidityStatus.CANNOT_REPHRASE
            elif ":-abp-properties(" in selector: # Simplified
                scriptlet_name = "user-hideIfStyleMatches"
                rephrased_rule_str = f"{domain}##+js({scriptlet_name}, div, width, 300px)" # Example
                rephrase_strategy_applied = f"ABP :-abp-properties() to ##+js({scriptlet_name}) (simplified)."
                implied_custom_scriptlets.append({"name": scriptlet_name, "type": "cosmetic_helper"})
                needs_revalidation = True
            else: # General #?#
                rephrased_rule_str = original_rule_str.replace("#?#", "##", 1)
                rephrase_strategy_applied = "Changed ABP #?# to ##."
                needs_revalidation = True
        
        elif rule_type_enum == RuleType.SCRIPTLET and "#$#" in original_rule_str: # ABP Snippet
            domain_part, snippet_call = original_rule_str.split("#$#", 1)
            domain = domain_part.strip()
            match = re.match(r"^([\w-]+)\s*\((.*)\)$", snippet_call.strip())
            if match:
                name, args_str = match.group(1), match.group(2)
                if name == "log":
                    scriptlet_name = "user-log" # Or map to brave's 'log.js' if args compatible
                    rephrased_rule_str = f"{domain}##+js({scriptlet_name}, {args_str})"
                    rephrase_strategy_applied = f"ABP '{name}' snippet to ##+js({scriptlet_name})."
                    implied_custom_scriptlets.append({"name": scriptlet_name, "type": "utility"})
                    needs_revalidation = True
                # Add more ABP snippet conversions here
                else: new_status_enum = BraveValidityStatus.CANNOT_REPHRASE
            else: new_status_enum = BraveValidityStatus.CANNOT_REPHRASE

        elif rule_type_enum == RuleType.SCRIPTLET and current_status_enum == BraveValidityStatus.POTENTIAL_ADGUARD_SPECIFIC and \
             ("#%#//scriptlet" in original_rule_str or "#@%#//scriptlet" in original_rule_str):
            domain_part, ag_call = re.split(r"#%#//scriptlet|#@%#//scriptlet", original_rule_str, 1)
            domain = domain_part.strip()
            match = re.match(r"^\((?:['\"])([\w.-]+)(?:['\"]),?(.*)\)$", ag_call.strip())
            if match:
                ag_name, ag_args = match.group(1), match.group(2).strip()
                ubo_equiv = active_ag_to_ubo_map.get(ag_name)
                if ubo_equiv and ubo_equiv in active_brave_scriptlets:
                    scriptlet_name_for_brave = ubo_equiv.replace(".js", "")
                    rephrased_rule_str = f"{domain}##+js({scriptlet_name_for_brave}{f', {ag_args}' if ag_args else ''})"
                    rephrase_strategy_applied = f"AdGuard '{ag_name}' to Brave ##+js({scriptlet_name_for_brave})."
                    needs_revalidation = True
                else: new_status_enum = BraveValidityStatus.CANNOT_REPHRASE
            else: new_status_enum = BraveValidityStatus.CANNOT_REPHRASE
        
        elif rule_type_enum == RuleType.NETWORK and current_status_enum == BraveValidityStatus.POTENTIAL_ADGUARD_SPECIFIC:
            if "$app=" in original_rule_str:
                rephrased_rule_str = re.sub(r",?\$app=[^,]+", "", original_rule_str).rstrip(",$")
                if not rephrased_rule_str or "$" not in rephrased_rule_str and not re.match(r"(\|\||\||\/)", rephrased_rule_str):
                     new_status_enum = BraveValidityStatus.CANNOT_REPHRASE
                else:
                    rephrase_strategy_applied = "Removed AdGuard $app."
                    needs_revalidation = True
            elif "$jsonprune=" in original_rule_str:
                match = re.match(r"^(.*?)\$jsonprune=(.*)$", original_rule_str)
                if match and "json-prune.js" in active_brave_scriptlets: # Check by .js name
                    base_pattern, args = match.group(1), match.group(2)
                    domain_for_scriptlet = base_pattern.replace("||","").split("/")[0].replace("^","").split("$")[0]
                    rephrased_rule_str = f"{domain_for_scriptlet}##+js(json-prune, {args})"
                    rephrase_strategy_applied = "AdGuard $jsonprune to ##+js(json-prune)."
                    needs_revalidation = True
                else: new_status_enum = BraveValidityStatus.CANNOT_REPHRASE
        
        elif rule_type_enum == RuleType.COSMETIC and current_status_enum == BraveValidityStatus.UNSUPPORTED_BRAVE_FEATURE:
            selector = parsed_components.get("selector", "")
            domain = parsed_components.get("domain", "")
            if ":xpath(" in selector: # Simplified conversion
                match = re.search(r":xpath\((//(\w+)(?:\[@id=['\"]([^'\"]+)['\"]\])?(?:\[@class=['\"]([^'\"]+)['\"]\])?)\)", selector)
                if match:
                    tag, id_val, class_val = match.group(2), match.group(4), match.group(6)
                    css = f"{tag}{f'#{id_val}' if id_val else ''}{f'.{class_val.replace(" ", ".")}' if class_val else ''}"
                    base_sel = selector[:match.start()]
                    rephrased_rule_str = f"{domain}##{base_sel}{css}" if domain else f"##{base_sel}{css}"
                    rephrase_strategy_applied = "Simple :xpath() to CSS."
                    needs_revalidation = True
                else: new_status_enum = BraveValidityStatus.CANNOT_REPHRASE
            elif ":has-text(" in selector:
                match = re.search(r"(:has-text\((['\"])(.*?)\2\))", selector)
                if match:
                    text = json.dumps(match.group(3))
                    base_sel = selector.replace(match.group(1), "").strip() or 'div'
                    scriptlet_name = "user-hideIfTextContains"
                    rephrased_rule_str = f"{domain}##+js({scriptlet_name}, {base_sel}, {text})"
                    rephrase_strategy_applied = f":has-text() to ##+js({scriptlet_name})."
                    implied_custom_scriptlets.append({"name": scriptlet_name, "type": "cosmetic_helper"})
                    needs_revalidation = True
                else: new_status_enum = BraveValidityStatus.CANNOT_REPHRASE
            elif ":style(" in selector and current_rule_obj.get("validation_reason","").startswith("Uses direct CSS style injection"):
                 new_status_enum = BraveValidityStatus.CANNOT_REPHRASE # No auto-rephrase for this yet

        # --- Finalizing status after rephrasing attempt ---
        if needs_revalidation and original_rule_str != rephrased_rule_str:
            is_valid_after, reval_reason, new_components = mock_revalidator.is_rule_valid_for_brave(rephrased_rule_str)
            if is_valid_after:
                current_rule_obj["brave_validity_status"] = BraveValidityStatus.REPHRASED_AND_VALID.name
                current_rule_obj["rephrased_rule_string"] = rephrased_rule_str
                current_rule_obj["parsed_components"] = new_components # Update with components of rephrased rule
                current_rule_obj["rephrasing_applied_reason"] = rephrase_strategy_applied
                logger.info(f"Rule ID {current_rule_obj['id']} REPHRASED & VALID: '{original_rule_str[:60]}' -> '{rephrased_rule_str[:60]}'. Strategy: {rephrase_strategy_applied}")
            else:
                current_rule_obj["brave_validity_status"] = BraveValidityStatus.REPHRASE_FAILED_VALIDATION.name
                current_rule_obj["rephrased_rule_string"] = rephrased_rule_str # Keep attempt
                current_rule_obj["validation_reason"] = f"Re-validation failed: {reval_reason}"
                current_rule_obj["rephrasing_applied_reason"] = rephrase_strategy_applied
                logger.warning(f"Rule ID {current_rule_obj['id']} REPHRASE FAILED VALIDATION: '{rephrased_rule_str[:60]}'. Original: '{original_rule_str[:60]}'. Reason: {reval_reason}")
        elif new_status_enum != current_status_enum: # Status changed without re-validation (e.g. to CANNOT_REPHRASE)
            current_rule_obj["brave_validity_status"] = new_status_enum.name
            if rephrase_strategy_applied: current_rule_obj["rephrasing_applied_reason"] = rephrase_strategy_applied
            # If rule string changed but didn't need revalidation (e.g. minor cleanup only)
            if original_rule_str != rephrased_rule_str and not needs_revalidation :
                 current_rule_obj["rephrased_rule_string"] = rephrased_rule_str
            logger.info(f"Rule ID {current_rule_obj['id']} status changed to {new_status_enum.name}: '{original_rule_str[:60]}'. Reason: {current_rule_obj.get('validation_reason','')}")
        elif original_rule_str == rephrased_rule_str and \
             current_status_enum in [BraveValidityStatus.UNSUPPORTED_BRAVE_FEATURE, BraveValidityStatus.NEEDS_REPHRASING, BraveValidityStatus.POTENTIAL_ADGUARD_SPECIFIC]:
            # No change in rule string, and it was a candidate for rephrasing -> means no strategy applied
            current_rule_obj["brave_validity_status"] = BraveValidityStatus.CANNOT_REPHRASE.name
            current_rule_obj["validation_reason"] = current_rule_obj.get("validation_reason", "") + " (No applicable rephrasing strategy found)."
            logger.debug(f"Rule ID {current_rule_obj['id']} CANNOT_REPHRASE (no strategy): '{original_rule_str[:60]}'.")

        rephrased_rules_list.append(current_rule_obj)

    if implied_custom_scriptlets:
        logger.info(f"Rephraser: Implied the need for {len(implied_custom_scriptlets)} types of custom user-scriptlets.")
        # In a real app, this list might be returned or stored for the generator.
        current_rule_obj["implied_custom_scriptlets"] = implied_custom_scriptlets # Example of attaching to last rule, better to return separately

    logger.info(f"Rephraser: Finished processing {len(validated_rule_objects)} rules.")
    return rephrased_rules_list
