<?php
$path = parse_url($_SERVER["REQUEST_URI"], PHP_URL_PATH);

// Map /api/heartbeat to /api/heartbeat.php
if ($path === '/api/heartbeat') {
    require __DIR__ . '/api/heartbeat.php';
    return true;
}

// For all other files, let the built-in server handle it if the file exists
if (file_exists(__DIR__ . $path)) {
    return false; 
}

// Fallback logic
if (file_exists(__DIR__ . $path . '.php')) {
    require __DIR__ . $path . '.php';
    return true;
}

if (file_exists(__DIR__ . $path . '.html')) {
    require __DIR__ . $path . '.html';
    return true;
}

return false;
