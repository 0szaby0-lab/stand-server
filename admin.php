<?php
require __DIR__ . '/src/include.php';

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $tier = $_POST['tier'];
    $custom_name = $_POST['custom_name'];
    
    // Generate a key
    $chars = "abcdefghijklmnopqrstuvwxyz0123456789";
    $fakeKey = "Stand-Activate-" . $tier . "-";
    for($i = 0; $i < 25; $i++) {
        $fakeKey .= $chars[rand(0, strlen($chars) - 1)];
    }

    $priv = 0;
    if ($tier === 'Basic') $priv = 1;
    if ($tier === 'Regular') $priv = 2;
    if ($tier === 'Ultimate') $priv = 3;

    if (empty($custom_name)) {
        $custom_name = "Stand (" . $tier . ")";
    }

    global $db;
    $db->query("INSERT INTO `accounts` (`activation_key`, `privilege`, `custom_root_name`) VALUES (?, ?, ?)", "sis", $fakeKey, $priv, $custom_name);
    
    $message = "Key generated: " . $fakeKey;
}

$keys = $db->query("SELECT * FROM `accounts` ORDER BY `id` DESC LIMIT 50");
?>
<!DOCTYPE html>
<html>
<head>
    <title>Admin Panel - Stand</title>
    <style>
        body { font-family: sans-serif; background: #111; color: #fff; padding: 20px; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        th, td { border: 1px solid #333; padding: 10px; text-align: left; }
        input, select, button { padding: 8px; margin: 5px; background: #222; color: #fff; border: 1px solid #444; }
        button { cursor: pointer; background: #4caf50; }
    </style>
</head>
<body>
    <h1>Admin Panel - Key Generator</h1>
    <?php if (isset($message)) echo "<p style='color:#4caf50'>$message</p>"; ?>
    <form method="POST">
        <label>Tier:</label>
        <select name="tier">
            <option value="Free">Free</option>
            <option value="Basic">Basic</option>
            <option value="Regular">Regular</option>
            <option value="Ultimate" selected>Ultimate</option>
        </select>
        <label>Menu Name (optional):</label>
        <input type="text" name="custom_name" placeholder="Leave empty for default">
        <button type="submit">Generate Key</button>
    </form>
    
    <h2>Generated Keys (Last 50)</h2>
    <table>
        <tr><th>ID</th><th>Key</th><th>Tier</th><th>Name</th><th>HWID Changes</th></tr>
        <?php foreach ($keys as $k): ?>
        <tr>
            <td><?= $k['id'] ?></td>
            <td><?= $k['activation_key'] ?></td>
            <td><?= $k['privilege'] ?></td>
            <td><?= $k['custom_root_name'] ?></td>
            <td><?= $k['hwid_changes'] ?></td>
        </tr>
        <?php endforeach; ?>
    </table>
</body>
</html>
