<?php
class SimpleMongoWrapper {
    private $manager;
    private $dbName;

    public function __construct($uri) {
        $this->manager = new \MongoDB\Driver\Manager($uri);
        $parsed = parse_url($uri);
        $this->dbName = trim($parsed['path'] ?? 'stand_db', '/');
    }

    public function query($sql, ...$args) {
        if (count($args) > 0 && is_string($args[0]) && preg_match('/^[sidb]+$/', $args[0])) {
            array_shift($args);
        }
        $sql = trim($sql);
        $argIdx = 0;

        if (stripos($sql, 'INSERT INTO') === 0) {
            if (preg_match('/INSERT INTO `([^`]+)` \(([^)]+)\) VALUES \((.+)\)/i', $sql, $matches)) {
                $table = $matches[1];
                $cols = array_map(function($c) { return trim($c, " `"); }, explode(',', $matches[2]));
                $vals = explode(',', $matches[3]);
                $doc = [];
                $parenDepth = 0;
                $valParts = [];
                $currentPart = '';
                // Simple parsing for VALUES to handle functions like (floor(rand() * 10) % 2)
                for ($i = 0; $i < strlen($matches[3]); $i++) {
                    $c = $matches[3][$i];
                    if ($c === '(') $parenDepth++;
                    elseif ($c === ')') $parenDepth--;
                    if ($c === ',' && $parenDepth === 0) {
                        $valParts[] = $currentPart;
                        $currentPart = '';
                    } else {
                        $currentPart .= $c;
                    }
                }
                $valParts[] = $currentPart;

                foreach ($cols as $i => $col) {
                    $v = trim($valParts[$i]);
                    if ($v === '?') {
                        $doc[$col] = $args[$argIdx++];
                    } elseif (preg_match('/^\d+$/', $v)) {
                        $doc[$col] = (int)$v;
                    } elseif (preg_match("/^'([^']*)'$/", $v, $m)) {
                        $doc[$col] = $m[1];
                    } elseif ($v === 'time()') {
                        $doc[$col] = time();
                    } elseif (stripos($v, 'rand(') !== false) {
                        $doc[$col] = rand(0,1);
                    } else {
                        $doc[$col] = 0;
                    }
                }
                $bulk = new \MongoDB\Driver\BulkWrite();
                $bulk->insert($doc);
                $this->manager->executeBulkWrite($this->dbName . '.' . $table, $bulk);
                return true;
            }
        }

        if (stripos($sql, 'UPDATE') === 0) {
            if (preg_match('/UPDATE `([^`]+)` SET (.+?) WHERE (.+)/i', $sql, $matches)) {
                $table = $matches[1];
                $setStr = $matches[2];
                $whereStr = $matches[3];
                
                $setOps = ['$set' => [], '$inc' => []];
                $sets = explode(',', $setStr);
                foreach ($sets as $s) {
                    $s = trim($s);
                    if (preg_match('/^`([^`]+)`\s*=\s*\?$/', $s, $m)) {
                        $setOps['$set'][$m[1]] = $args[$argIdx++];
                    } elseif (preg_match('/^`([^`]+)`\s*=\s*`\1`\s*\+\s*1$/', $s, $m)) {
                        $setOps['$inc'][$m[1]] = 1;
                    } elseif (preg_match("/^`([^`]+)`\s*=\s*'([^']*)'$/", $s, $m)) {
                        $setOps['$set'][$m[1]] = $m[2];
                    } elseif (preg_match('/^`([^`]+)`\s*=\s*(\d+)$/', $s, $m)) {
                        $setOps['$set'][$m[1]] = (int)$m[2];
                    }
                }
                if (empty($setOps['$inc'])) unset($setOps['$inc']);
                if (empty($setOps['$set'])) unset($setOps['$set']);
                
                $filter = $this->parseWhere($whereStr, $args, $argIdx);
                
                $bulk = new \MongoDB\Driver\BulkWrite();
                $bulk->update($filter, $setOps, ['multi' => true]);
                $this->manager->executeBulkWrite($this->dbName . '.' . $table, $bulk);
                return true;
            }
        }

        if (stripos($sql, 'DELETE FROM') === 0) {
            if (preg_match('/DELETE FROM `([^`]+)` WHERE (.+)/i', $sql, $matches)) {
                $table = $matches[1];
                $filter = $this->parseWhere($matches[2], $args, $argIdx);
                $bulk = new \MongoDB\Driver\BulkWrite();
                $bulk->delete($filter);
                $this->manager->executeBulkWrite($this->dbName . '.' . $table, $bulk);
                return true;
            }
        }

        if (stripos($sql, 'SELECT') === 0) {
            if (preg_match('/SELECT (.+?) FROM `([^`]+)`(?: WHERE (.*?))?(?: ORDER BY `([^`]+)` (ASC|DESC))?(?: LIMIT (\d+))?$/i', $sql, $matches)) {
                $selects = trim($matches[1]);
                $table = $matches[2];
                $whereStr = isset($matches[3]) ? $matches[3] : '';
                $orderCol = isset($matches[4]) ? $matches[4] : '';
                $orderDir = isset($matches[5]) ? $matches[5] : '';
                $limit = isset($matches[6]) && $matches[6] !== '' ? (int)$matches[6] : 0;
                
                $filter = $whereStr ? $this->parseWhere($whereStr, $args, $argIdx) : [];
                $options = [];
                if ($limit > 0) $options['limit'] = $limit;
                if ($orderCol) {
                    $options['sort'] = [$orderCol => (strtoupper($orderDir) === 'DESC' ? -1 : 1)];
                }
                
                $isCount = stripos($selects, 'COUNT(') !== false;
                
                $query = new \MongoDB\Driver\Query($filter, $options);
                $cursor = $this->manager->executeQuery($this->dbName . '.' . $table, $query);
                
                $results = [];
                foreach ($cursor as $doc) {
                    $arr = json_decode(json_encode($doc), true);
                    if (isset($arr['_id'])) unset($arr['_id']);
                    $results[] = $arr;
                }
                
                if ($isCount) {
                    return [["COUNT(*)" => count($results)]];
                }
                
                return $results;
            }
        }

        return [];
    }

    private function parseWhere($whereStr, $args, &$argIdx) {
        $filter = [];
        $parts = preg_split('/\s+AND\s+/i', trim($whereStr));
        foreach ($parts as $p) {
            $p = trim($p);
            if (preg_match('/^`([^`]+)`\s*=\s*\?$/', $p, $m)) {
                $filter[$m[1]] = $args[$argIdx++];
            } elseif (preg_match('/^`([^`]+)`\s*!=\s*\?$/', $p, $m)) {
                $filter[$m[1]] = ['$ne' => $args[$argIdx++]];
            } elseif (preg_match("/^`([^`]+)`\s*=\s*'([^']*)'$/", $p, $m)) {
                $filter[$m[1]] = $m[2];
            } elseif (preg_match("/^`([^`]+)`\s*!=\s*'([^']*)'$/", $p, $m)) {
                $filter[$m[1]] = ['$ne' => $m[2]];
            } elseif (preg_match('/^`([^`]+)`\s*=\s*(\d+)$/', $p, $m)) {
                $filter[$m[1]] = (int)$m[2];
            } elseif (preg_match('/^`([^`]+)`\s*!=\s*(\d+)$/', $p, $m)) {
                $filter[$m[1]] = ['$ne' => (int)$m[2]];
            }
        }
        return $filter;
    }
}

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

if (extension_loaded('mongodb')) {
    $db = new SimpleMongoWrapper("mongodb+srv://u79d5o4_db_user:fLTUABKVEHTWC9Gh@szaby.lgnxptf.mongodb.net/stand_db?retryWrites=true&w=majority");
} else {
    $db = new SimpleMySQLWrapper("localhost", "root", "", "stand");
}
