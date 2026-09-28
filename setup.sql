CREATE DATABASE IF NOT EXISTS `stand`;
USE `stand`;

CREATE TABLE IF NOT EXISTS `accounts` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `activation_key` varchar(255) NOT NULL,
  `privilege` int(11) NOT NULL DEFAULT '0',
  `dev` tinyint(1) NOT NULL DEFAULT '0',
  `suspended_for` varchar(255) DEFAULT NULL,
  `custom_root_name` varchar(255) DEFAULT NULL,
  `last_known_identity` varchar(255) DEFAULT NULL,
  `last_hwid` varchar(255) DEFAULT NULL,
  `hwid_changes` int(11) NOT NULL DEFAULT '0',
  `early_toxic` tinyint(1) NOT NULL DEFAULT '0',
  `pre100` tinyint(1) NOT NULL DEFAULT '0',
  `used100` tinyint(1) NOT NULL DEFAULT '0',
  `rndbool` tinyint(1) NOT NULL DEFAULT '0',
  `migrated_from` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `activation_key` (`activation_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `menus` (
  `account_id` int(11) NOT NULL,
  `hwid` varchar(255) NOT NULL,
  `identity` varchar(255) NOT NULL,
  `session` varchar(255) NOT NULL,
  `version` varchar(255) NOT NULL,
  `lang` varchar(255) NOT NULL,
  `last_heartbeat` int(11) NOT NULL,
  PRIMARY KEY (`account_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `rid_queue` (
  `rid` int(11) NOT NULL,
  PRIMARY KEY (`rid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `scaccounts` (
  `id` int(11) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Insert a test key for the admin
INSERT IGNORE INTO `accounts` (`activation_key`, `privilege`, `custom_root_name`) VALUES ('Stand-Test-Ultimate-Key', 3, 'My Custom Menu');
