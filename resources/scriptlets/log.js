// resources/scriptlets/log.js
// Name: log.js
// Aliases: ulog, brave_log.js
// Kind: template
// Purpose: Logs messages to the console.
// Arguments:
//   {{1}}: The message to log (string).
//   {{2}}: (Optional) Log level ('log', 'info', 'warn', 'error'). Defaults to 'log'.

(function(message, level) {
    'use strict';
    // The adblock engine replaces {{1}}, {{2}} with the actual string arguments.
    // If an argument is not provided, it might be an empty string or a specific placeholder.
    // We'll treat them as strings and provide defaults if they are effectively empty.
    const msg = String(message === '{{1}}' ? '(empty log message)' : (message || '(empty log message)'));
    const logLevel = String(level === '{{2}}' ? 'log' : (level || 'log')).toLowerCase();

    const prefix = '[Brave Scriptlet: log.js]';
    const logFunction = console[logLevel] || console.log;

    try {
        logFunction(`${prefix} ${msg}`);
    } catch (e) {
        console.log(`${prefix} ${msg} (level: ${level} produced error, used default log)`);
    }
})(String({{1}}), String({{2}})); // Adblock engine handles argument injection
