<?php
class SimpleMySQLWrapper {
    private $pdo;

    public function __construct($host, $user, $pass, $db) {
        $this->pdo = new PDO("mysql:host=$host;dbname=$db;charset=utf8mb4", $user, $pass);
        $this->pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
    }

    public function query($sql, ...$args) {
        if (count($args) > 0 && is_string($args[0]) && preg_match('/^[sidb]+$/', $args[0])) {
            array_shift($args);
        }
        
        $stmt = $this->pdo->prepare($sql);
        $stmt->execute($args);
        
        if (stripos(trim($sql), 'SELECT') === 0) {
            return $stmt->fetchAll(PDO::FETCH_ASSOC);
        }
        return true;
    }
}

$db = new SimpleMySQLWrapper("localhost", "root", "", "stand");
