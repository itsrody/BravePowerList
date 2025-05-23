# core_modules/parser_validator.py

import re
import logging
from enum import Enum, auto

logger = logging.getLogger(__name__)

class RuleType(Enum):
    NETWORK = auto()
    COSMETIC = auto()
    SCRIPTLET = auto()
    HOSTS_RULE = auto()
    COMMENT = auto()
    METADATA_HEADER = auto()
    UNKNOWN = auto()

class BraveValidityStatus(Enum):
    VALID = auto()
    INVALID_BRAVE_SYNTAX = auto()
    UNSUPPORTED_BRAVE_FEATURE = auto()
    POTENTIAL_ADGUARD_SPECIFIC = auto()
    NEEDS_REPHRASING = auto()
    # Statuses after rephrasing attempt (set by rephraser)
    CANNOT_REPHRASE = auto() # Added for clarity
    REPHRASED_AND_VALID = auto()
    REPHRASE_FAILED_VALIDATION = auto()


# --- Mock python-adblock (as defined previously) ---
class MockPythonAdblock:
    def __init__(self):
        self.reject_as_invalid_syntax = {
            "|||too_many_pipes.com^",
            "example.com##[attr=val", 
            "example.com##+js(noClosingParen"
        }
    def parse_rule(self, rule_string: str):
        if rule_string in self.reject_as_invalid_syntax:
            return {
                "valid_syntax": False,
                "error_message": "Mock: adblock-rust core syntax validation failed.",
                "parsed_components": {}
            }
        components = {}
        # Simplified parsing logic from previous implementation
        if "##+js" in rule_string or "#@#+js" in rule_string :
            match = re.match(r"^(.*?)##\+js\((.*?)\)$", rule_string) or \
                    re.match(r"^(.*?)#@#\+js\((.*?)\)$", rule_string)
            if match:
                domain = match.group(1).strip() if match.group(1) else ""
                scriptlet_call = match.group(2).split(',', 1)
                scriptlet_name = scriptlet_call[0].strip()
                args = scriptlet_call[1].strip() if len(scriptlet_call) > 1 else ""
                components = {"domain": domain, "scriptlet_name": scriptlet_name, "arguments_string": args, "type": "scriptlet"}
        elif "##" in rule_string or "#?#" in rule_string or ("#@#" in rule_string and not "#@#+js" in rule_string):
            separator = ""
            if "##" in rule_string: separator = "##"
            elif "#?#" in rule_string: separator = "#?#"
            elif "#@#" in rule_string: separator = "#@#"
            if separator:
                parts = rule_string.split(separator, 1)
                components = {"domain": parts[0].strip() if parts[0] else "", "selector": parts[1].strip(), "type": "cosmetic"}
                if "#?#" in rule_string: components["abp_extended_syntax"] = True
        elif re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\s+[\w.-]+", rule_string):
             parts = rule_string.split(None, 1)
             if len(parts) == 2:
                components = {"ip_address": parts[0], "hostname": parts[1], "type": "hosts"}
        elif rule_string.startswith("@@"):
            pattern = rule_string[2:]
            options_part = ""
            if "$" in pattern:
                pattern, options_part = pattern.split("$", 1)
            components = {"pattern": pattern, "options_string": options_part, "is_exception": True, "type": "network"}
        elif rule_string.startswith("||") or rule_string.startswith("|") or "/" in rule_string or re.match(r"^[\w.-]+\^?", rule_string) :
            pattern = rule_string
            options_part = ""
            if "$" in pattern:
                pattern, options_part = rule_string.split("$", 1)
            components = {"pattern": pattern, "options_string": options_part, "is_exception": False, "type": "network"}

        if components:
             return {"valid_syntax": True, "parsed_components": components, "error_message": None}
        else:
            return {"valid_syntax": True, "parsed_components": {"pattern": rule_string, "type":"network_generic"}, "error_message": None}

mock_adblock_parser = MockPythonAdblock()

UNSUPPORTED_NETWORK_OPTIONS = {
    "$popup", "$popunder", "$csp", "$generichide", "$elemhide", "$document",
    "$genericblock", "$ping", "$all", "$match-case",
}
UNSUPPORTED_NETWORK_OPTION_PATTERNS = {
    re.compile(r"\$removeparam=/.*?complex regex", re.IGNORECASE), # Placeholder
    re.compile(r"\$denyallow=.*?[*,]", re.IGNORECASE),
}
UNSUPPORTED_COSMETIC_SELECTORS_PATTERNS = {
    re.compile(r":xpath\(", re.IGNORECASE),
    re.compile(r":has-text\(", re.IGNORECASE),
    re.compile(r":upward\(", re.IGNORECASE),
    re.compile(r":matches-css\(", re.IGNORECASE),
    re.compile(r":-abp-properties\(", re.IGNORECASE),
    re.compile(r":-abp-contains\(", re.IGNORECASE),
    re.compile(r":style\((?!display\s*:\s*none\s*!important)", re.IGNORECASE),
}
ADGUARD_SPECIFIC_PATTERNS = {
    re.compile(r"#%#//"),
    re.compile(r"\$app="),
    re.compile(r"\$cookie", re.IGNORECASE),
    re.compile(r"\$jsonprune", re.IGNORECASE),
}
ABP_EXTENDED_CSS_SEPARATOR = "#?#"

def identify_rule_type(rule_string: str) -> tuple[RuleType, dict]:
    stripped_rule = rule_string.strip()
    if not stripped_rule: return RuleType.COMMENT, {"reason": "Empty line"}
    if stripped_rule.startswith("!"):
        if stripped_rule.startswith("!#") and ("if" in stripped_rule or "include" in stripped_rule) :
            return RuleType.METADATA_HEADER, {"subtype": "ubo_preprocessor_directive", "detail": stripped_rule}
        if any(stripped_rule.startswith(hdr) for hdr in ["! Title:", "! Version:", "! Expires:", "! Homepage:", "! Description:"]):
            return RuleType.METADATA_HEADER, {"subtype": "standard_header", "detail": stripped_rule}
        if stripped_rule == "[Adblock Plus 2.0]":
            return RuleType.METADATA_HEADER, {"subtype": "abp_version_header", "detail": stripped_rule, "action": "discard_from_body"}
        return RuleType.COMMENT, {"detail": stripped_rule}
    if stripped_rule.startswith("#") and not (stripped_rule.startswith("##") or stripped_rule.startswith(ABP_EXTENDED_CSS_SEPARATOR) or stripped_rule.startswith("#@#") or stripped_rule.startswith("#%#")):
        if not re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\s+", stripped_rule):
             return RuleType.COMMENT, {"detail": "Hosts file style comment"}
    if "##+js" in stripped_rule or "#@#+js" in stripped_rule: return RuleType.SCRIPTLET, {"syntax_type": "ubo_brave"}
    if "#%#//scriptlet" in stripped_rule or "#@%#//scriptlet" in stripped_rule: return RuleType.SCRIPTLET, {"syntax_type": "adguard"}
    if "#$#" in stripped_rule: return RuleType.SCRIPTLET, {"syntax_type": "abp_snippet"}
    if "##" in stripped_rule or ABP_EXTENDED_CSS_SEPARATOR in stripped_rule or ("#@#" in stripped_rule and not "#@#+js" in stripped_rule):
        return RuleType.COSMETIC, {}
    if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\s+[\w.-]+", stripped_rule):
        return RuleType.HOSTS_RULE, {}
    if stripped_rule and not stripped_rule.isspace(): return RuleType.NETWORK, {}
    return RuleType.UNKNOWN, {"reason": "Line did not match any known rule pattern"}

def parse_and_validate_rules(
    raw_lists_data: dict[str, str],
    parser_config: dict = None
) -> list[dict]:
    all_processed_rules = []
    rule_id_counter = 0
    enable_detailed_logging = parser_config.get("enable_detailed_logging", False) if parser_config else False

    for source_url, list_content_str in raw_lists_data.items():
        lines = list_content_str.splitlines()
        logger.info(f"Parser: Processing {len(lines)} lines from {source_url}...")

        for line_num, original_rule_string in enumerate(lines):
            rule_id_counter += 1
            line_stripped = original_rule_string.strip()

            parsed_rule_obj = {
                "id": rule_id_counter,
                "original_rule_string": line_stripped, # Store stripped version
                "raw_line_string": original_rule_string, # Keep original for reference if needed
                "source_url": source_url,
                "line_number": line_num + 1,
                "rule_type": RuleType.UNKNOWN.name, # Default
                "brave_validity_status": BraveValidityStatus.VALID.name, # Default
                "validation_reason": "",
                "parsed_components": {},
                "type_identification_info": {}
            }
            
            if not line_stripped:
                parsed_rule_obj.update({
                    "rule_type": RuleType.COMMENT.name,
                    "validation_reason": "Empty line",
                })
                all_processed_rules.append(parsed_rule_obj)
                continue

            rule_type, type_info = identify_rule_type(line_stripped)
            parsed_rule_obj["rule_type"] = rule_type.name
            parsed_rule_obj["type_identification_info"] = type_info

            if rule_type in [RuleType.COMMENT, RuleType.METADATA_HEADER]:
                if type_info.get("action") == "discard_from_body":
                    # This isn't really a "validity" status for rephrasing,
                    # but a flag for the unifier/generator.
                    # For now, keep it VALID but the unifier will handle the discard.
                    parsed_rule_obj["validation_reason"] = "ABP version header to be discarded from body by unifier."
                all_processed_rules.append(parsed_rule_obj)
                continue
            
            if rule_type == RuleType.UNKNOWN:
                parsed_rule_obj["brave_validity_status"] = BraveValidityStatus.INVALID_BRAVE_SYNTAX.name
                parsed_rule_obj["validation_reason"] = type_info.get("reason","Unknown rule format")
                all_processed_rules.append(parsed_rule_obj)
                if enable_detailed_logging: logger.debug(f"Rule ID {rule_id_counter} UNKNOWN: {line_stripped[:100]}")
                continue

            mock_validation_result = mock_adblock_parser.parse_rule(line_stripped)
            parsed_rule_obj["parsed_components"] = mock_validation_result.get("parsed_components", {})

            if not mock_validation_result["valid_syntax"]:
                parsed_rule_obj["brave_validity_status"] = BraveValidityStatus.INVALID_BRAVE_SYNTAX.name
                parsed_rule_obj["validation_reason"] = mock_validation_result.get("error_message", "Core syntax invalid.")
                logger.warning(f"Rule ID {rule_id_counter} INVALID_BRAVE_SYNTAX by mock: '{line_stripped[:70]}...' | Reason: {parsed_rule_obj['validation_reason']}")
                all_processed_rules.append(parsed_rule_obj)
                continue

            current_status = BraveValidityStatus.VALID
            reason = ""

            # AdGuard specific checks
            if rule_type == RuleType.SCRIPTLET.name and type_info.get("syntax_type") == "adguard":
                current_status = BraveValidityStatus.POTENTIAL_ADGUARD_SPECIFIC
                reason = "Uses AdGuard native scriptlet syntax (#%#//), needs rephrasing."
            else:
                for ag_pattern in ADGUARD_SPECIFIC_PATTERNS:
                    if ag_pattern.search(line_stripped):
                        current_status = BraveValidityStatus.POTENTIAL_ADGUARD_SPECIFIC
                        reason = f"Potential AdGuard-specific feature ({ag_pattern.pattern})."
                        if enable_detailed_logging: logger.debug(f"Rule ID {rule_id_counter} POTENTIAL_ADGUARD_SPECIFIC: {line_stripped[:100]}")
                        break
            
            if current_status == BraveValidityStatus.VALID: # Only if not already AdGuard specific
                if rule_type_str == RuleType.NETWORK.name or \
                   (rule_type_str == RuleType.SCRIPTLET.name and parsed_rule_obj["parsed_components"].get("type") == "network"):
                    options_str = parsed_rule_obj["parsed_components"].get("options_string", "")
                    if options_str:
                        options_present = [opt.strip().split("=")[0] for opt in options_str.split(',')] # Get option name before =
                        for unsupported_opt in UNSUPPORTED_NETWORK_OPTIONS:
                            if unsupported_opt in options_present:
                                current_status = BraveValidityStatus.UNSUPPORTED_BRAVE_FEATURE
                                reason = f"Uses unsupported network option: {unsupported_opt}."
                                if enable_detailed_logging: logger.debug(f"Rule ID {rule_id_counter} UNSUPPORTED (Net Opt): {line_stripped[:100]}")
                                break
                        if current_status == BraveValidityStatus.VALID:
                             for unsup_pattern in UNSUPPORTED_NETWORK_OPTION_PATTERNS:
                                if unsup_pattern.search(options_str):
                                    current_status = BraveValidityStatus.UNSUPPORTED_BRAVE_FEATURE
                                    reason = f"Uses potentially unsupported network option pattern: {unsup_pattern.pattern}."
                                    if enable_detailed_logging: logger.debug(f"Rule ID {rule_id_counter} UNSUPPORTED (Net Opt Pat): {line_stripped[:100]}")
                                    break
                elif rule_type_str == RuleType.COSMETIC.name:
                    selector_str = parsed_rule_obj["parsed_components"].get("selector", "")
                    if parsed_rule_obj["parsed_components"].get("abp_extended_syntax"):
                        current_status = BraveValidityStatus.NEEDS_REPHRASING
                        reason = "Uses ABP extended CSS syntax (#?#), requires conversion."
                        if enable_detailed_logging: logger.debug(f"Rule ID {rule_id_counter} NEEDS_REPHRASING (ABP Cosmetic): {line_stripped[:100]}")
                    else:
                        for unsup_sel_pattern in UNSUPPORTED_COSMETIC_SELECTORS_PATTERNS:
                            if unsup_sel_pattern.search(selector_str):
                                current_status = BraveValidityStatus.UNSUPPORTED_BRAVE_FEATURE
                                reason = f"Uses potentially unsupported cosmetic selector pattern: {unsup_sel_pattern.pattern}."
                                if enable_detailed_logging: logger.debug(f"Rule ID {rule_id_counter} UNSUPPORTED (Cosmetic Sel): {line_stripped[:100]}")
                                break
                        if current_status == BraveValidityStatus.VALID and ":style(" in selector_str \
                           and not re.search(r":style\(\s*display\s*:\s*none\s*!important\s*\)", selector_str, re.IGNORECASE):
                            current_status = BraveValidityStatus.UNSUPPORTED_BRAVE_FEATURE
                            reason = "Uses direct CSS style injection via :style() not for display:none."
                            if enable_detailed_logging: logger.debug(f"Rule ID {rule_id_counter} UNSUPPORTED (Cosmetic Style): {line_stripped[:100]}")
            
            parsed_rule_obj["brave_validity_status"] = current_status.name
            if reason:
                parsed_rule_obj["validation_reason"] = reason
            all_processed_rules.append(parsed_rule_obj)

    logger.info(f"Parser: Finished processing. Total lines/rules analyzed: {len(all_processed_rules)}.")
    return all_processed_rules
