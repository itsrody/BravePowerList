// resources/scriptlets/abort-on-property-read.js
// Name: abort-on-property-read.js
// Aliases: aopr.js
// Kind: template
// Purpose: Aborts script execution or neuters a function when a specific JS property is accessed.
// Argument:
//   {{1}}: Property path to watch (e.g., "object.subObject.propertyToWatch").

(function(propertyPath) {
    'use strict';
    const path = String({{1}} || '');
    if (!path) {
        // console.warn('[aopr.js] Property path not specified.');
        return;
    }

    const props = path.split('.');
    let obj = window;
    let i;

    for (i = 0; i < props.length - 1; i++) {
        if (typeof obj[props[i]] === 'undefined') {
            obj[props[i]] = {}; // Create path if not exists
        }
        obj = obj[props[i]];
        if (typeof obj !== 'object' && typeof obj !== 'function' || obj === null) {
            // console.warn(`[aopr.js] Invalid path component in "${path}" at "${props[i]}".`);
            return;
        }
    }

    const finalProp = props[i];
    let originalValue = undefined;
    if (obj && typeof obj === 'object' && Object.prototype.hasOwnProperty.call(obj, finalProp)) {
        try { originalValue = obj[finalProp]; } catch(e) { /* Ignore */ }
    }

    try {
        Object.defineProperty(obj, finalProp, {
            configurable: true,
            get: function() {
                // console.warn(`[aopr.js] Access to property "${path}" aborted/neutered.`);
                if (typeof originalValue === 'function') {
                    return function() { /* Neutered function */ };
                }
                return undefined; 
            },
            set: function(newValue) {
                // console.warn(`[aopr.js] Attempt to set neutered property "${path}".`);
            }
        });
    } catch (e) {
        // console.error(`[aopr.js] Failed to redefine property "${path}":`, e);
    }
})(String({{1}}));
