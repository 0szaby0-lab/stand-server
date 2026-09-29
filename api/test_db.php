<?php
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);
error_reporting(E_ALL);

require "../src/include.php";

echo "<h1>Diagnostic Test</h1>";
echo "Database wrapper class: " . get_class($db) . "<br>";
echo "MongoDB Extension Loaded: " . (extension_loaded('mongodb') ? "Yes" : "No") . "<br>";

$res = $db->query("SELECT * FROM `accounts` ORDER BY `created` DESC LIMIT 1");
echo "<h2>Latest Account in DB</h2>";
echo "<pre>";
print_r($res);
echo "</pre>";

if (!empty($res)) {
    $id = $res[0]['id'];
    echo "<h2>Testing Update on Latest Account</h2>";
    echo "Old key: " . $res[0]['activation_key'] . "<br>";
    $newKey = "TEST-" . time();
    echo "Setting new key: " . $newKey . "<br>";
    
    try {
        $db->query("UPDATE `accounts` SET `activation_key`=?, `regens`=`regens`+1, `last_regen_time`=? WHERE `id`=?", "sis", $newKey, time(), $id);
        echo "Update query executed successfully!<br>";
    } catch (Exception $e) {
        echo "Update failed with Exception: " . $e->getMessage() . "<br>";
    }
    
    $check = $db->query("SELECT `activation_key` FROM `accounts` WHERE `id`=?", "s", $id);
    echo "Key read back from DB: " . $check[0]['activation_key'] . "<br>";
    
    if ($check[0]['activation_key'] === $newKey) {
        echo "<b style='color:green'>UPDATE IS WORKING PERFECTLY!</b>";
    } else {
        echo "<b style='color:red'>UPDATE FAILED SILENTLY! (Database did not save the new value)</b>";
    }
}
