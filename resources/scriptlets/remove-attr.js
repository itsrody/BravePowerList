// resources/scriptlets/remove-attr.js
// Name: remove-attr.js
// Aliases: ra.js
// Kind: template
// Purpose: Removes a specified attribute from all elements matching a CSS selector.
// Arguments:
//   {{1}}: The name of the attribute to remove (string).
//   {{2}}: (Optional) CSS selector for the target elements (string). Defaults to "*".

(function(attributeName, selector) {
    'use strict';

    const attrName = (String(attributeName) === '{{1}}' || !attributeName) ? '' : String(attributeName);
    const cssSelector = (String(selector) === '{{2}}' || !selector) ? '*' : String(selector);


    if (!attrName) {
        // console.warn('[remove-attr.js] Attribute name not specified.');
        return;
    }

    try {
        const elements = document.querySelectorAll(cssSelector);
        elements.forEach(element => {
            if (element.hasAttribute(attrName)) {
                element.removeAttribute(attrName);
                // console.log(`[remove-attr.js] Removed attribute '${attrName}' from element:`, element);
            }
        });
    } catch (e) {
        // console.error(`[remove-attr.js] Error removing attribute '${attrName}' from '${cssSelector}':`, e);
    }
})(String({{1}}), String({{2}}));
