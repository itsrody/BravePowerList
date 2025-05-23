// resources/scriptlets/json-prune.js
// Name: json-prune.js
// Kind: template
// Purpose: Removes specified properties from a JSON string.
// Arguments:
//   {{1}}: The JSON string.
//   {{2}}, {{3}}, ...: Dot-separated paths to properties to remove.

// This is a simplified version. Real json-prune scriptlets are more complex,
// often involving overriding JSON.parse or Response.prototype.json.
// This version assumes the JSON string is passed as {{1}} and returns the modified string.
// The adblock engine would need to handle the replacement of the original response.

(function() {
    'use strict';
    // The arguments are injected by the adblock engine.
    // {{1}} is the JSON string, {{2}}, {{3}}, ... are paths.
    // This script needs to be structured to be evaluated by the engine,
    // and the "return value" used appropriately.

    const jsonString = String({{1}} || '');
    const pathsToRemove = [];
    // Collect paths from {{2}} onwards
    for (let k = 2; ; k++) {
        // The adblock engine replaces {{k}} with the argument value.
        // If the argument doesn't exist, the replacement might be the literal '{{k}}'
        // or an empty string, or undefined. This check is a heuristic.
        let pathArg = `{{${k}}}`; // This will be the actual string argument by the adblock engine
        
        // A more robust check would be if the engine passes a specific number of args
        // or if unprovided args are `undefined`.
        // If `pathArg` remains `{{k}}` (and k is not a literal string arg), it means no more args.
        // This heuristic might fail if an argument itself is literally "{{k}}".
        const placeholderPattern = new RegExp(`^{{\\s*${k}\\s*}}$`);
        if (placeholderPattern.test(pathArg) && k > 100) { // Avoid infinite loop, assume no more than 100 paths
             break; 
        }
        if (pathArg === null || pathArg === undefined || pathArg === "" || placeholderPattern.test(pathArg) ) {
            // If it's still the placeholder or empty, assume no more arguments.
            // This check depends heavily on how the adblock engine handles missing template args.
            // For this example, if it's still the placeholder string, we stop.
             if (placeholderPattern.test(pathArg) && k > 2) break; // More reliable check for unreplaced placeholder
             if (!placeholderPattern.test(pathArg) && pathArg !== "") pathsToRemove.push(pathArg); // Add if it's a real value
             else if (k > 2 && (pathArg === "" || pathArg === null || pathArg === undefined)) break; // Stop on empty/null/undefined for subsequent args
        } else {
             pathsToRemove.push(pathArg);
        }
         if (k > 100) break; // Safety break
    }


    if (!jsonString || pathsToRemove.length === 0) {
        // console.warn('[json-prune.js] JSON string or paths to remove are missing.');
        return jsonString; // Return original if no paths or input
    }

    try {
        let obj = JSON.parse(jsonString);

        pathsToRemove.forEach(path => {
            if (typeof path !== 'string' || path === "") return; // Skip invalid paths
            const props = path.split('.');
            let current = obj;
            for (let i = 0; i < props.length - 1; i++) {
                const prop = props[i];
                // Simplified: does not handle array wildcards like path[*]
                if (!current || typeof current !== 'object' || !current.hasOwnProperty(prop)) {
                    return; // Path does not exist or not an object
                }
                current = current[prop];
            }
            const finalProp = props[props.length - 1];
            if (current && typeof current === 'object' && current.hasOwnProperty(finalProp)) {
                delete current[finalProp];
            }
        });
        // This scriptlet, when used as a redirect, should return the modified string.
        return JSON.stringify(obj);
    } catch (e) {
        // console.error('[json-prune.js] Error processing JSON:', e, 'Original string:', jsonString.substring(0,100));
        return jsonString; // Return original string on error
    }
    // The adblock engine takes the value of the last expression.
})();
