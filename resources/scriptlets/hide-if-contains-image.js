// resources/scriptlets/hide-if-contains-image.js
// Name: hide-if-contains-image.js
// Kind: template
// Purpose: Hides elements matching {{1}} if they contain an <img> whose src matches regex {{2}}.
// Arguments:
//   {{1}}: CSS selector for the container elements.
//   {{2}}: Regex pattern (string) to match against image src attributes.

(function(containerSelector, imageSrcRegexPattern) {
    'use strict';

    const selector = String({{1}} || '');
    const patternString = String({{2}} || '');

    if (!selector || !patternString) {
        // console.warn('[hide-if-contains-image.js] Missing container selector or image source regex pattern.');
        return;
    }

    try {
        const regex = new RegExp(patternString); // Regex pattern from argument
        const containers = document.querySelectorAll(selector);

        containers.forEach(container => {
            const images = container.getElementsByTagName('img');
            for (let i = 0; i < images.length; i++) {
                if (images[i].src && regex.test(images[i].src)) {
                    container.style.setProperty('display', 'none', 'important');
                    break; 
                }
            }
        });
    } catch (e) {
        // console.error(`[hide-if-contains-image.js] Error for selector "${selector}", pattern "${patternString}":`, e);
    }
})(String({{1}}), String({{2}}));
