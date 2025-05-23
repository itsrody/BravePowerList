// resources/scriptlets/set-cookie.js
// Name: set-cookie.js
// Kind: template
// Arguments: {{1}} name, {{2}} value, {{3}} maxAge, {{4}} path, {{5}} domain, {{6}} secure, {{7}} sameSite

(function(name, value, maxAge, path, domain, secure, sameSite) {
    'use strict';

    // Adblock engine replaces {{n}} with string arguments.
    // Handle cases where arguments might not be provided by checking against the placeholder itself (heuristic)
    // or if the engine provides empty strings/null/undefined.

    const cookieName = (String(name) === '{{1}}' || !name) ? '' : String(name);
    const cookieValue = (String(value) === '{{2}}' || value === undefined) ? '' : String(value);

    if (!cookieName) {
        // console.warn('[set-cookie.js] Cookie name is required.');
        return;
    }

    let cookieString = `${encodeURIComponent(cookieName)}=${encodeURIComponent(cookieValue)}`;

    const maxAgeStr = (String(maxAge) === '{{3}}' || maxAge === undefined) ? '' : String(maxAge);
    if (maxAgeStr && !isNaN(parseInt(maxAgeStr, 10))) {
        cookieString += `; Max-Age=${parseInt(maxAgeStr, 10)}`;
    }

    const pathStr = (String(path) === '{{4}}' || !path) ? '/' : String(path); // Default path to /
    cookieString += `; Path=${pathStr}`;
    
    const domainStr = (String(domain) === '{{5}}' || !domain) ? '' : String(domain);
    if (domainStr) {
        cookieString += `; Domain=${domainStr}`;
    }

    const secureStr = (String(secure) === '{{6}}' || secure === undefined) ? '' : String(secure).toLowerCase();
    if (secureStr === 'true' || secureStr === true) { // Allow boolean true if engine passes it
        cookieString += `; Secure`;
    }

    const sameSiteStr = (String(sameSite) === '{{7}}' || !sameSite) ? '' : String(sameSite);
    if (sameSiteStr) {
        const validSameSite = ['Lax', 'Strict', 'None'].find(s => s.toLowerCase() === sameSiteStr.toLowerCase());
        if (validSameSite) {
            cookieString += `; SameSite=${validSameSite}`;
        } else {
            // console.warn(`[set-cookie.js] Invalid SameSite value: ${sameSiteStr}.`);
        }
    }
    try {
        document.cookie = cookieString;
        // console.log(`[set-cookie.js] Attempted to set cookie: ${cookieString}`);
    } catch (e) {
        // console.error(`[set-cookie.js] Error setting cookie:`, e);
    }
})(String({{1}}), String({{2}}), String({{3}}), String({{4}}), String({{5}}), String({{6}}), String({{7}}));
