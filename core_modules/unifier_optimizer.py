# core_modules/unifier_optimizer.py

import logging
import re
from urllib.parse import urlparse # Not strictly used in current simple domain parsing but good for future
# Assuming RuleType and BraveValidityStatus enums are defined in parser_validator
from .parser_validator import RuleType, BraveValidityStatus

logger = logging.getLogger(__name__)

def get_domain_from_network_rule(rule_string: str) -> str | None:
    rule_clean = rule_string.split("$")[0].strip()
    if rule_clean.startswith("@@"): rule_clean = rule_clean[2:]
    
    match = re.match(r"\|\|([\w.-]+)(?:[\^/].*)?", rule_clean)
    if match: return match.group(1)
    
    match = re.match(r"\|https?://([\w.-]+)(?:[/].*)?", rule_clean)
    if match: return match.group(1)
    
    if "/" not in rule_clean and "." in rule_clean and not rule_clean.startswith("*") and not rule_clean.endswith("*"):
        if re.match(r"^([\w*-]+\.)+[\w-]+$", rule_clean):
            return rule_clean[2:] if rule_clean.startswith("*.") else rule_clean
    return None

def unify_and_optimize_rules(
    processed_rule_objects: list[dict],
    unifier_config: dict = None
) -> list[str]:
    if unifier_config is None: unifier_config = {}
    initial_rule_count = len(processed_rule_objects)
    logger.info(f"Unifier: Starting with {initial_rule_count} processed rule objects.")

    valid_rules_for_unification = []
    preserved_comments = []

    for rule_obj in processed_rule_objects:
        status_str = rule_obj.get("brave_validity_status")
        rule_type_str = rule_obj.get("rule_type")
        original_rule = rule_obj.get("original_rule_string", "")
        rephrased_rule = rule_obj.get("rephrased_rule_string")
        effective_rule_str = (rephrased_rule if rephrased_rule is not None else original_rule).strip()

        if not effective_rule_str: continue

        if status_str in [BraveValidityStatus.VALID.name, BraveValidityStatus.REPHRASED_AND_VALID.name]:
            valid_rules_for_unification.append({
                "string": effective_rule_str,
                "type": RuleType[rule_type_str] if rule_type_str in RuleType.__members__ else RuleType.UNKNOWN,
                "is_exception": effective_rule_str.startswith("@@")
            })
        elif rule_type_str == RuleType.COMMENT.name:
            # PRD: preserve general informational comments, drop list-specific metadata
            # Parser should flag metadata for discard (e.g. with "action": "discard_from_body")
            # For now, simple check based on common metadata prefixes
            if not any(effective_rule_str.lower().startswith(hdr_prefix) for hdr_prefix in [
                "! title:", "! version:", "! expires:", "! homepage:", "! description:", "[adblock plus"
            ]):
                 if rule_obj.get("type_identification_info", {}).get("action") != "discard_from_body":
                    preserved_comments.append(effective_rule_str)
    
    logger.info(f"Unifier: Collected {len(valid_rules_for_unification)} active rules and {len(preserved_comments)} general comments.")

    # Deduplication of active rules
    # Store rule string to its data to keep type information for optimization
    # If multiple identical strings had different types (unlikely from parser), this keeps the first.
    unique_active_rules_map = {rule_data["string"]: rule_data for rule_data in reversed(valid_rules_for_unification)}
    unique_rules_with_type = list(unique_active_rules_map.values())
    
    count_after_deduplication = len(unique_rules_with_type)
    logger.info(f"Unifier: After deduplication: {count_after_deduplication} unique active rules.")

    optimized_rules_data = [] # Will store rule data dicts
    if unifier_config.get("perform_network_optimization", True):
        network_rules = [r for r in unique_rules_with_type if r["type"] == RuleType.NETWORK and not r["is_exception"]]
        other_rules = [r for r in unique_rules_with_type if r["type"] != RuleType.NETWORK or r["is_exception"]]
        
        domain_block_rules = {} # domain -> full_rule_string for ||domain.tld^
        for rule in network_rules:
            rule_str = rule["string"]
            # A simple check for full domain block: ||domain.tld^ (no options or only simple options)
            match = re.match(r"\|\|([\w.-]+)\^(\$[A-Za-z0-9,-_]+)?$", rule_str) # Allow simple options
            if match and "/" not in match.group(1): # Ensure it's a domain, not a path starting with ||
                domain_block_rules[match.group(1)] = rule_str
        
        if domain_block_rules: logger.debug(f"Unifier: Found {len(domain_block_rules)} full domain block rules for optimization.")

        final_network_rules_data = []
        for rule_data in network_rules:
            rule_str = rule_data["string"]
            is_redundant = False
            current_rule_domain = get_domain_from_network_rule(rule_str)

            if current_rule_domain:
                for blocked_domain, blocking_rule_str in domain_block_rules.items():
                    if rule_str == blocking_rule_str: continue # Don't mark self as redundant

                    # If current rule is for the same domain but more specific (has path)
                    if current_rule_domain == blocked_domain and "/" in rule_str.split("$")[0]:
                        is_redundant = True
                        logger.debug(f"Optimizer: Rule '{rule_str}' redundant by '{blocking_rule_str}' (path on domain).")
                        break
                    # If current rule is for a subdomain of a blocked domain
                    if current_rule_domain.endswith("." + blocked_domain):
                        is_redundant = True
                        logger.debug(f"Optimizer: Rule '{rule_str}' redundant by '{blocking_rule_str}' (subdomain).")
                        break
            if not is_redundant:
                final_network_rules_data.append(rule_data)
        
        optimized_rules_data.extend(final_network_rules_data)
        optimized_rules_data.extend(other_rules)
        logger.info(f"Unifier: After network optimization: {len(optimized_rules_data)} active rules.")
    else:
        optimized_rules_data.extend(unique_rules_with_type)
        logger.info("Unifier: Network optimization skipped by config.")

    # Final list of strings
    final_active_rule_strings = [r["string"] for r in optimized_rules_data]
    
    # Deduplicate comments and combine
    # Using dict.fromkeys preserves order and deduplicates comments
    unique_preserved_comments = list(dict.fromkeys(preserved_comments))
    
    final_list_for_generator = unique_preserved_comments + final_active_rule_strings

    if unifier_config.get("sort_output", True):
        # Separate comments from rules for sorting, then recombine
        comments_to_sort = [line for line in final_list_for_generator if line.startswith("!")]
        rules_to_sort = [line for line in final_list_for_generator if not line.startswith("!")]
        comments_to_sort.sort()
        rules_to_sort.sort()
        final_list_for_generator = comments_to_sort + rules_to_sort
        logger.info("Unifier: Final list sorted.")
    
    logger.info(f"Unifier: Finished. Final list contains {len(final_list_for_generator)} lines.")
    return final_list_for_generator
